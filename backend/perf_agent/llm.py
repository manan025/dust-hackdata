"""OpenAI API client (chat completions)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterator

import os
import requests

from .errors import NoCodeBlockError, OpenAIConnectionError, OpenAIModelNotFoundError
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


def _openai_chat_completion(
    *,
    model: str,
    messages: list[dict[str, str]],
    base_url: str,
    api_key: str | None,
) -> str:
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise OpenAIConnectionError(
            "OpenAI API key not set. Provide --openai-api-key or set OPENAI_API_KEY."
        )
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {key}"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=300)
    except requests.ConnectionError as e:
        raise OpenAIConnectionError(
            "Cannot connect to OpenAI API. Check network access."
        ) from e
    except requests.Timeout as e:
        raise OpenAIConnectionError(
            "OpenAI request timed out."
        ) from e

    if response.status_code == 404:
        raise OpenAIModelNotFoundError(
            f"Model '{model}' not found. Check model name."
        )
    if response.status_code >= 400:
        body = response.text[:500]
        if "model" in body.lower() and "not found" in body.lower():
            raise OpenAIModelNotFoundError(
                f"Model '{model}' not found. Check model name."
            )
        raise OpenAIConnectionError(
            f"OpenAI returned HTTP {response.status_code}:\n{body}"
        )

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise OpenAIConnectionError("OpenAI response missing choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not content:
        raise OpenAIConnectionError("OpenAI response missing content.")
    return content


def collect_optimization(
    current_source: str,
    metrics: StatMetrics,
    functions: list[HotFunction],
    binary: str,
    history: list[IterationRecord],
    iteration: int,
    max_iterations: int,
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
    api_key: str | None = None,
    on_token: Iterator[tuple[str, bool]] | None = None,
    think: bool = True,
    target_context: str | None = None,
) -> tuple[str, str, str]:
    """Optimization request via OpenAI chat completions.

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
    full_response = _openai_chat_completion(
        model=model,
        messages=messages,
        base_url=base_url,
        api_key=api_key,
    )

    thinking_text, response_text = split_thinking(full_response)
    change_summary = extract_change_summary(response_text)
    return thinking_text, response_text, change_summary


def stream_analysis(
    metrics: StatMetrics,
    functions: list[HotFunction],
    binary: str,
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
    api_key: str | None = None,
    think: bool = True,
    target_context: str | None = None,
) -> Iterator[tuple[str, bool]]:
    """Stream LLM analysis tokens from OpenAI chat completions.

    Yields (chunk, is_thinking) tuples where is_thinking=True for <think> block content.
    """
    analysis_system = SYSTEM_PROMPT
    if target_context:
        analysis_system = f"=== TARGET ARCHITECTURE ===\n{target_context}\n\n" + analysis_system

    messages = [
        {"role": "system", "content": analysis_system},
        {"role": "user", "content": build_user_message(binary, metrics, functions)},
    ]
    content = _openai_chat_completion(
        model=model,
        messages=messages,
        base_url=base_url,
        api_key=api_key,
    )
    thinking_text, response_text = split_thinking(content)
    if thinking_text:
        yield (thinking_text, True)
    if response_text:
        yield (response_text, False)
