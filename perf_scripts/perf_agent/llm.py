"""Ollama API client with streaming support."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Iterator

import requests

from .errors import NoCodeBlockError, OllamaConnectionError, OllamaModelNotFoundError
from .parser import HotFunction, StatMetrics

if TYPE_CHECKING:
    from .optimizer import IterationRecord

SYSTEM_PROMPT = """\
You are a performance engineering expert specializing in Linux perf analysis.
Analyze the provided profiling data and give actionable, specific recommendations.
Focus on: CPU bottlenecks, memory access patterns, branch prediction failures,
and hot code paths. Be concise and technical.

Structure your response as:
1) Key Observations — workload characterization (CPU-bound vs memory-bound vs branch-bound)
2) Top Bottlenecks — specific functions and counter values that point to issues
3) Recommendations — 3-5 concrete, actionable steps with expected impact
"""

OPTIMIZE_SYSTEM_PROMPT = """\
You are an expert C performance engineer optimizing a program iteratively.
Rules:
1. Propose exactly ONE optimization per response.
2. Output the complete modified source in a single ```c ... ``` block.
3. Start your explanation with "CHANGE: " (one sentence).
4. End with "EXPECTED: " (one sentence on expected speedup).
5. Do NOT change observable stdout output.
6. If no safe optimizations remain, output exactly: NO_FURTHER_OPTIMIZATIONS
Prefer (in order): cache-friendly access, algorithmic improvements,
compiler hints (__builtin_expect, restrict), loop restructuring.
"""

_MAX_REPORT_CHARS = 8000

_C_BLOCK_RE = re.compile(r"```c\s*\n(.*?)```", re.DOTALL)
_CHANGE_LINE_RE = re.compile(r"^CHANGE:\s*(.+)$", re.MULTILINE)
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def build_user_message(
    binary: str,
    metrics: StatMetrics,
    functions: list[HotFunction],
) -> str:
    def _fmt_int(v: int | None) -> str:
        return f"{v:,}" if v is not None else "N/A"

    def _fmt_float(v: float | None, precision: int = 2) -> str:
        return f"{v:.{precision}f}" if v is not None else "N/A"

    hotfuncs_lines: list[str] = []
    for f in functions[:20]:
        hotfuncs_lines.append(
            f"  {f.overhead_pct:6.2f}%  {f.samples:6d}  {f.symbol}  [{f.dso}]"
        )
    hotfuncs_block = "\n".join(hotfuncs_lines) if hotfuncs_lines else "  (no data)"

    return f"""\
Binary: {binary}
Runtime: {_fmt_float(metrics.elapsed_seconds)}s | IPC: {_fmt_float(metrics.ipc)} | Cycles: {_fmt_int(metrics.cycles)}

=== Hardware Counters ===
Instructions:     {_fmt_int(metrics.instructions)}
Task clock:       {_fmt_float(metrics.task_clock_ms, 1)} ms
CPUs utilized:    {_fmt_float(metrics.cpu_utilized)}
Branches:         {_fmt_int(metrics.branches)} ({_fmt_float(metrics.branch_miss_pct, 1)}% mispredicted)
Cache references: {_fmt_int(metrics.cache_references)} ({_fmt_float(metrics.cache_miss_pct, 1)}% misses)

=== Top Hot Functions (perf report) ===
{hotfuncs_block}

Identify the main performance bottlenecks and provide 3-5 specific,
actionable recommendations to improve performance.
"""


def build_optimize_user_message(
    binary: str,
    current_source: str,
    metrics: StatMetrics,
    functions: list[HotFunction],
    history: list[IterationRecord],
    iteration: int,
    max_iterations: int,
) -> str:
    def _fmt_int(v: int | None) -> str:
        return f"{v:,}" if v is not None else "N/A"

    def _fmt_float(v: float | None, precision: int = 2) -> str:
        return f"{v:.{precision}f}" if v is not None else "N/A"

    hotfuncs_lines: list[str] = []
    for f in functions[:20]:
        hotfuncs_lines.append(
            f"  {f.overhead_pct:6.2f}%  {f.samples:6d}  {f.symbol}  [{f.dso}]"
        )
    hotfuncs_block = "\n".join(hotfuncs_lines) if hotfuncs_lines else "  (no data)"

    if history:
        rows = ["  Iter  Result          Delta    Description"]
        for rec in history:
            if rec.compile_failed:
                result_str = "COMPILE FAIL  "
                delta_str = "    N/A"
            elif rec.user_rejected:
                result_str = "USER REJECTED  "
                delta_str = "    N/A"
                desc = rec.description
                if rec.user_feedback:
                    desc += f"  [Feedback: {rec.user_feedback}]"
                rows.append(f"  {rec.iteration:4d}  {result_str}  {delta_str}  {desc}")
                continue
            elif rec.kept:
                result_str = "KEPT          "
                delta_str = f"{rec.delta_pct:+7.1f}%"
            else:
                result_str = "REJECTED      "
                delta_str = f"{rec.delta_pct:+7.1f}%"
            rows.append(
                f"  {rec.iteration:4d}  {result_str}  {delta_str}  {rec.description}"
            )
        history_block = "\n".join(rows)
    else:
        history_block = "  (no previous attempts)"

    source_block = current_source[:_MAX_REPORT_CHARS]
    if len(current_source) > _MAX_REPORT_CHARS:
        source_block += "\n... (truncated)"

    return f"""\
=== OPTIMIZATION REQUEST — Iteration {iteration}/{max_iterations} ===
Binary: {binary} | elapsed: {_fmt_float(metrics.elapsed_seconds)}s | IPC: {_fmt_float(metrics.ipc)} | Cache miss: {_fmt_float(metrics.cache_miss_pct, 1)}%

=== Current Hardware Counters ===
Instructions:     {_fmt_int(metrics.instructions)}
Task clock:       {_fmt_float(metrics.task_clock_ms, 1)} ms
CPUs utilized:    {_fmt_float(metrics.cpu_utilized)}
Branches:         {_fmt_int(metrics.branches)} ({_fmt_float(metrics.branch_miss_pct, 1)}% mispredicted)
Cache references: {_fmt_int(metrics.cache_references)} ({_fmt_float(metrics.cache_miss_pct, 1)}% misses)

=== Top Hot Functions ===
{hotfuncs_block}

=== Optimization History ===
{history_block}

=== Current Source Code ===
```c
{source_block}
```

Propose exactly one optimization. Output full modified source in a ```c block.
"""


def split_thinking(text: str) -> tuple[str, str]:
    """Return (thinking_content, clean_text) by extracting <think>...</think> blocks."""
    thinking_parts = _THINK_RE.findall(text)
    thinking_text = "\n\n".join(p.strip() for p in thinking_parts)
    clean_text = _THINK_RE.sub("", text).strip()
    return thinking_text, clean_text


def extract_code_block(response: str) -> str:
    """Return the first ```c ... ``` block content. Raises NoCodeBlockError if absent."""
    m = _C_BLOCK_RE.search(response)
    if m is None:
        raise NoCodeBlockError("LLM response contained no ```c code block")
    return m.group(1)


def extract_change_summary(response: str) -> str:
    """Return CHANGE: line content, or fall back to first non-empty line."""
    m = _CHANGE_LINE_RE.search(response)
    if m:
        return m.group(1).strip()
    for line in response.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return "(no description)"


def collect_optimization(
    current_source: str,
    metrics: StatMetrics,
    functions: list[HotFunction],
    binary: str,
    history: list[IterationRecord],
    iteration: int,
    max_iterations: int,
    model: str = "qwen3.5:latest",
    base_url: str = "http://localhost:11434",
    on_token: Iterator[tuple[str, bool]] | None = None,
    think: bool = True,
    target_context: str | None = None,
) -> tuple[str, str, str]:
    """Streaming optimization request (accumulates full response before returning).

    Uses stream=True so the per-chunk timeout applies instead of a total-response
    timeout — avoids ReadTimeout on long generations with large source files.

    Returns (thinking_text, response_text, change_summary).
    thinking_text: content of all <think>...</think> blocks (may be empty).
    response_text: full response with <think> blocks removed.
    """
    system_content = OPTIMIZE_SYSTEM_PROMPT
    if target_context:
        system_content = f"=== TARGET ARCHITECTURE ===\n{target_context}\n\n" + system_content

    messages = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": build_optimize_user_message(
                binary, current_source, metrics, functions,
                history, iteration, max_iterations,
            ),
        },
    ]
    payload = {"model": model, "messages": messages, "stream": True}
    if not think:
        payload["think"] = False
    url = f"{base_url.rstrip('/')}/api/chat"

    try:
        response = requests.post(url, json=payload, stream=True, timeout=300)
    except requests.ConnectionError as e:
        raise OllamaConnectionError(
            "Cannot connect to Ollama. Start it with:\n  ollama serve"
        ) from e
    except requests.Timeout as e:
        raise OllamaConnectionError(
            "Ollama connection timed out. Is it running?"
        ) from e

    if response.status_code == 404:
        raise OllamaModelNotFoundError(
            f"Model '{model}' not found. Pull it with:\n  ollama pull {model}"
        )
    if response.status_code != 200:
        body = response.text[:500]
        if "model" in body.lower() and "not found" in body.lower():
            raise OllamaModelNotFoundError(
                f"Model '{model}' not found. Pull it with:\n  ollama pull {model}"
            )
        raise OllamaConnectionError(
            f"Ollama returned HTTP {response.status_code}:\n{body}"
        )

    # Accumulate streamed chunks into a full response string.
    # We track <think> state across chunks so we can call on_token if provided.
    full_response = ""
    in_think = False
    for line in response.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = chunk.get("message", {}).get("content", "")
        if not content:
            if chunk.get("done"):
                break
            continue
        full_response += content
        if chunk.get("done"):
            break

    thinking_text, response_text = split_thinking(full_response)
    change_summary = extract_change_summary(response_text)
    return thinking_text, response_text, change_summary


def stream_analysis(
    metrics: StatMetrics,
    functions: list[HotFunction],
    binary: str,
    model: str = "qwen3.5:latest",
    base_url: str = "http://localhost:11434",
    think: bool = True,
    target_context: str | None = None,
) -> Iterator[tuple[str, bool]]:
    """Stream LLM analysis tokens from Ollama /api/chat.

    Yields (chunk, is_thinking) tuples where is_thinking=True for <think> block content.
    """
    analysis_system = SYSTEM_PROMPT
    if target_context:
        analysis_system = f"=== TARGET ARCHITECTURE ===\n{target_context}\n\n" + analysis_system

    messages = [
        {"role": "system", "content": analysis_system},
        {"role": "user", "content": build_user_message(binary, metrics, functions)},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if not think:
        payload["think"] = False
    url = f"{base_url.rstrip('/')}/api/chat"

    try:
        response = requests.post(url, json=payload, stream=True, timeout=300)
    except requests.ConnectionError as e:
        raise OllamaConnectionError(
            "Cannot connect to Ollama. Start it with:\n  ollama serve"
        ) from e
    except requests.Timeout as e:
        raise OllamaConnectionError(
            "Ollama connection timed out. Is it running?"
        ) from e

    if response.status_code == 404:
        raise OllamaModelNotFoundError(
            f"Model '{model}' not found. Pull it with:\n  ollama pull {model}"
        )
    if response.status_code != 200:
        body = response.text[:500]
        if "model" in body.lower() and "not found" in body.lower():
            raise OllamaModelNotFoundError(
                f"Model '{model}' not found. Pull it with:\n  ollama pull {model}"
            )
        raise OllamaConnectionError(
            f"Ollama returned HTTP {response.status_code}:\n{body}"
        )

    in_think = False
    for line in response.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue

        content = chunk.get("message", {}).get("content", "")
        if not content:
            continue

        # Walk through content splitting on <think> / </think> tags,
        # yielding chunks tagged with whether they're thinking content.
        i = 0
        while i < len(content):
            if not in_think:
                think_start = content.find("<think>", i)
                if think_start == -1:
                    if content[i:]:
                        yield (content[i:], False)
                    break
                else:
                    if content[i:think_start]:
                        yield (content[i:think_start], False)
                    in_think = True
                    i = think_start + len("<think>")
            else:
                think_end = content.find("</think>", i)
                if think_end == -1:
                    if content[i:]:
                        yield (content[i:], True)
                    break
                else:
                    if content[i:think_end]:
                        yield (content[i:think_end], True)
                    in_think = False
                    i = think_end + len("</think>")
