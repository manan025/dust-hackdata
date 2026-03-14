#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
from pathlib import Path

import requests


def run_cmd(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def perf_stat(command: str, timeout: int) -> str:
    cmd = ["perf", "stat", "-e", "task-clock,cpu-cycles,instructions,branches,branch-misses,cache-references,cache-misses", "--", "bash", "-lc", command]
    result = run_cmd(cmd, timeout=timeout)
    return result.stderr


def perf_record_report(command: str, out_dir: Path, timeout: int) -> str:
    perf_data = out_dir / "perf.data"
    record_cmd = ["perf", "record", "-g", "-F", "99", "-o", str(perf_data), "--", "bash", "-lc", command]
    run_cmd(record_cmd, timeout=timeout)
    report_cmd = ["perf", "report", "--stdio", "--no-children", "-n", "-i", str(perf_data)]
    report = run_cmd(report_cmd, timeout=60)
    (out_dir / "perf.txt").write_text(report.stdout, encoding="utf-8")
    return report.stdout


def build_prompt(command: str, stat_text: str, report_text: str, source_snippet: str, recommendations: int) -> list[dict[str, str]]:
    system = (
        "You are a performance engineering expert specializing in Linux perf analysis. "
        "Analyze the provided profiling data and give actionable, specific recommendations. "
        "Focus on: CPU bottlenecks, memory access patterns, branch prediction failures, "
        "and hot code paths. Be concise and technical."
    )
    user = (
        f"Command: {command}\n\n"
        "=== perf stat ===\n"
        f"{stat_text}\n\n"
        "=== perf report (top) ===\n"
        f"{report_text[:8000]}\n\n"
    )
    if source_snippet:
        user += "=== Source (excerpt) ===\n" + source_snippet[:8000] + "\n\n"
    user += (
        f"Provide {recommendations} concrete code change recommendations. "
        "If you suggest code changes, include small code snippets. "
        "Do not change observable behavior."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_openai(messages: list[dict[str, str]], model: str, base_url: str, api_key: str) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": 0.2}
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(url, json=payload, headers=headers, timeout=300)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI response missing choices")
    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("OpenAI response missing content")
    return content


def read_source_snippet(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile a command with perf and get OpenAI recommendations.")
    parser.add_argument("--command", required=True, help="Command to profile")
    parser.add_argument("--out-dir", required=True, help="Directory to write perf.data/perf.txt/llm_output.txt")
    parser.add_argument("--timeout", type=int, default=120, help="Perf timeout seconds")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    parser.add_argument("--openai-url", default="https://api.openai.com/v1", help="OpenAI base URL")
    parser.add_argument("--openai-api-key", default=None, help="OpenAI API key (or OPENAI_API_KEY env)")
    parser.add_argument("--source", default=None, help="Optional source file to include in prompt")
    parser.add_argument("--recommendations", type=int, default=3, help="Number of recommendations to request")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stat_text = perf_stat(args.command, args.timeout)
    report_text = perf_record_report(args.command, out_dir, args.timeout)
    source_snippet = read_source_snippet(args.source)

    api_key = args.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")

    messages = build_prompt(args.command, stat_text, report_text, source_snippet, args.recommendations)
    response = call_openai(messages, args.model, args.openai_url, api_key)

    llm_path = out_dir / "llm_output.txt"
    llm_path.write_text(response, encoding="utf-8")
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
