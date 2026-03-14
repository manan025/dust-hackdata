#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path

import requests

_SKIP_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
}

_SOURCE_EXTS = {
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp",
    ".rs", ".go", ".java", ".kt", ".cs", ".swift", ".m", ".mm", ".scala",
}

_REPORT_FULL = re.compile(
    r"^\s*(\d+\.\d+)%\s+(\d+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+(\S+)"
)


def run_cmd(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def perf_stat(command: str, timeout: int) -> str:
    cmd = [
        "perf", "stat",
        "-e", "task-clock,cpu-cycles,instructions,branches,branch-misses,cache-references,cache-misses",
        "--", "bash", "-lc", command,
    ]
    result = run_cmd(cmd, timeout=timeout)
    return result.stderr


def perf_record_report(command: str, out_dir: Path, timeout: int) -> str:
    perf_data = out_dir / "perf.data"
    record_cmd = [
        "perf", "record", "-g", "-F", "99",
        "-o", str(perf_data),
        "--", "bash", "-lc", command,
    ]
    run_cmd(record_cmd, timeout=timeout)
    report_cmd = ["perf", "report", "--stdio", "--no-children", "-n", "-i", str(perf_data)]
    report = run_cmd(report_cmd, timeout=60)
    (out_dir / "perf.txt").write_text(report.stdout, encoding="utf-8")
    return report.stdout


def parse_hot_symbols(report_text: str, limit: int = 10) -> list[str]:
    symbols: list[str] = []
    for line in report_text.splitlines():
        m = _REPORT_FULL.match(line)
        if m:
            symbols.append(m.group(6))
        if len(symbols) >= limit:
            break
    return symbols


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in _SKIP_DIRS or part.startswith(".") for part in path.parts):
            continue
        if path.suffix.lower() in _SOURCE_EXTS:
            files.append(path)
    return files


def select_source_files(root: Path, symbols: list[str], max_files: int = 3) -> list[Path]:
    candidates = iter_source_files(root)
    if not candidates:
        return []
    selected: list[Path] = []
    if symbols:
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(sym in text for sym in symbols):
                selected.append(path)
            if len(selected) >= max_files:
                break
    if not selected:
        candidates.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
        selected = candidates[:max_files]
    return selected


def read_source_bundle(paths: list[Path], max_chars: int = 30000) -> str:
    parts: list[str] = []
    total = 0
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        header = f"\n=== FILE: {path.as_posix()} ===\n"
        chunk = header + text
        if total + len(chunk) > max_chars:
            remaining = max_chars - total
            if remaining <= 0:
                break
            chunk = chunk[:remaining]
        parts.append(chunk)
        total += len(chunk)
        if total >= max_chars:
            break
    return "".join(parts)


def build_prompt(
    command: str,
    stat_text: str,
    report_text: str,
    source_bundle: str,
    recommendations: int,
    files: list[Path],
) -> list[dict[str, str]]:
    system = (
        "You are a performance engineering expert specializing in Linux perf analysis. "
        "Analyze the provided profiling data and propose concrete code changes. "
        "Focus on CPU bottlenecks, memory access patterns, branch prediction failures, "
        "and hot code paths. Be concise and technical."
    )
    file_list = "\n".join(f"- {p.as_posix()}" for p in files) or "(none)"
    user = (
        f"Command: {command}\n\n"
        "=== perf stat ===\n"
        f"{stat_text}\n\n"
        "=== perf report (top) ===\n"
        f"{report_text[:8000]}\n\n"
        "=== Files in scope ===\n"
        f"{file_list}\n\n"
    )
    if source_bundle:
        user += "=== Source (excerpt) ===\n" + source_bundle + "\n\n"
    user += (
        "Return JSON ONLY, with the following schema:\n"
        "{\n"
        '  "summary": "short summary",\n'
        '  "files": [\n'
        '    {"path": "relative/path.ext", "content": "FULL file contents with changes applied"}\n'
        "  ]\n"
        "}\n"
        f"Provide up to {recommendations} changes. Only include files from the scope list.\n"
        "If you recommend no changes, return an empty files array.\n"
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


def apply_changes(repo_root: Path, payload: dict) -> list[str]:
    changed: list[str] = []
    for item in payload.get("files", []) or []:
        rel_path = item.get("path", "")
        content = item.get("content", "")
        if not rel_path or not isinstance(content, str):
            continue
        target = (repo_root / rel_path).resolve()
        if repo_root not in target.parents and target != repo_root:
            continue
        if not target.exists():
            continue
        if target.suffix.lower() not in _SOURCE_EXTS:
            continue
        target.write_text(content, encoding="utf-8")
        changed.append(rel_path)
    return changed


def zip_source(repo_root: Path, out_path: Path) -> None:
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in iter_source_files(repo_root):
            rel = path.relative_to(repo_root)
            zf.write(path, rel.as_posix())


def supabase_upload(
    supabase_url: str,
    service_key: str,
    bucket: str,
    file_path: Path,
) -> tuple[str, str]:
    object_name = f"source-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex}.zip"
    upload_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_name}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "application/zip",
    }
    with file_path.open("rb") as f:
        resp = requests.post(upload_url, headers=headers, data=f)
    if resp.status_code >= 400:
        raise RuntimeError(f"Supabase upload failed {resp.status_code}: {resp.text[:500]}")
    signed_url = ""
    sign_url = f"{supabase_url.rstrip('/')}/storage/v1/object/sign/{bucket}/{object_name}"
    resp = requests.post(
        sign_url,
        headers={"Authorization": f"Bearer {service_key}", "apikey": service_key},
        json={"expiresIn": 60 * 60 * 24 * 7},
        timeout=30,
    )
    if resp.status_code < 400:
        data = resp.json()
        signed_url = f"{supabase_url.rstrip('/')}{data.get('signedURL', '')}"
    return object_name, signed_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile a command with perf and apply OpenAI recommendations.")
    parser.add_argument("--command", required=True, help="Command to profile")
    parser.add_argument("--out-dir", required=True, help="Directory to write perf.data/perf.txt/llm_output.txt")
    parser.add_argument("--timeout", type=int, default=120, help="Perf timeout seconds")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    parser.add_argument("--openai-url", default="https://api.openai.com/v1", help="OpenAI base URL")
    parser.add_argument("--openai-api-key", default=None, help="OpenAI API key (or OPENAI_API_KEY env)")
    parser.add_argument("--recommendations", type=int, default=3, help="Number of recommendations to request")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(args.repo_root).resolve()

    stat_text = perf_stat(args.command, args.timeout)
    report_text = perf_record_report(args.command, out_dir, args.timeout)
    symbols = parse_hot_symbols(report_text)
    selected_files = select_source_files(repo_root, symbols, max_files=3)
    source_bundle = read_source_bundle(selected_files)

    api_key = args.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")

    messages = build_prompt(
        args.command,
        stat_text,
        report_text,
        source_bundle,
        args.recommendations,
        selected_files,
    )
    response = call_openai(messages, args.model, args.openai_url, api_key)

    llm_path = out_dir / "llm_output.txt"
    llm_path.write_text(response, encoding="utf-8")

    payload = {}
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        payload = {}

    changed = apply_changes(repo_root, payload)

    zip_path = out_dir / "source.zip"
    zip_source(repo_root, zip_path)

    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_bucket = os.getenv("SUPABASE_SOURCE_BUCKET", "")
    if not supabase_url or not supabase_key or not supabase_bucket:
        raise RuntimeError("Missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/SUPABASE_SOURCE_BUCKET")

    object_name, signed_url = supabase_upload(
        supabase_url, supabase_key, supabase_bucket, zip_path
    )

    result = {
        "changed_files": changed,
        "zip_object": object_name,
        "signed_url": signed_url,
    }
    (out_dir / "upload.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
