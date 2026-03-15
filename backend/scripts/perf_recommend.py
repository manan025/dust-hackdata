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


def parse_task_clock_ms(stat_output: str) -> float | None:
    """Extract task-clock value in milliseconds from perf stat output."""
    m = re.search(r"([\d,]+\.?\d*)\s+msec\s+task-clock", stat_output)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


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
        "and hot code paths. Be concise and technical. "
        "CRITICAL dependency rules: you must track every import/use/require/include "
        "statement in the original file — never remove any of them. If your changes "
        "introduce new types, functions, or modules, add the required import statements "
        "above the existing import block. Never remove existing functions, methods, "
        "structs, types, or non-performance-related logic."
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
        '    {"path": "relative/path.ext", "content": "COMPLETE file — all original imports and all original functions must be present; only targeted performance sections are changed"}\n'
        "  ]\n"
        "}\n"
        f"Provide up to {recommendations} changes. Only include files from the scope list.\n"
        "Dependency rules you MUST follow:\n"
        "1. Include every original import/use/require/include statement unchanged.\n"
        "2. If you use a new type or function, add its import — do not assume it is in scope.\n"
        "3. Do NOT remove or rename any existing function, method, struct, or type.\n"
        "4. Only modify lines inside the hot functions identified by profiling data.\n"
        "5. If you recommend no changes, return an empty files array.\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def extract_json(text: str) -> str:
    """Strip markdown code fences from LLM response if present."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        return m.group(1).strip()
    return text


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


def apply_changes(repo_root: Path, payload: dict) -> tuple[list[str], dict[str, str]]:
    changed: list[str] = []
    originals: dict[str, str] = {}
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
        originals[rel_path] = target.read_text(encoding="utf-8")
        target.write_text(content, encoding="utf-8")
        changed.append(rel_path)
    return changed, originals


def restore_changes(repo_root: Path, originals: dict[str, str]) -> None:
    for rel_path, content in originals.items():
        target = (repo_root / rel_path).resolve()
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            print(f"[rollback] WARNING: could not restore {rel_path}: {exc}", flush=True)


def run_build(build_cmd: str, timeout: int = 300) -> bool:
    """Rebuild the binary after source changes. Returns True on success."""
    if not build_cmd:
        return True
    result = run_cmd(["bash", "-lc", build_cmd], timeout=timeout)
    if result.returncode != 0:
        print(f"[build] FAILED:\n{result.stdout}\n{result.stderr}", flush=True)
        return False
    return True


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
        raw_path = data.get("signedURL", "")
        # Normalise: strip /storage/v1 suffix from base URL so we never double it
        base = re.sub(r"/storage/v1$", "", supabase_url.rstrip("/"))
        if raw_path and not raw_path.startswith("/storage/v1"):
            raw_path = "/storage/v1" + raw_path
        signed_url = base + raw_path
    else:
        print(f"[supabase] signed URL request failed {resp.status_code}: {resp.text[:200]}", flush=True)
    return object_name, signed_url


def _write_upload_json(out_dir: Path, payload: dict) -> None:
    (out_dir / "upload.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _log_line(log_path: Path, msg: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(msg)
        if not msg.endswith("\n"):
            f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile a command with perf and apply OpenAI recommendations iteratively.")
    parser.add_argument("--command", required=True, help="Command to profile")
    parser.add_argument("--out-dir", required=True, help="Directory to write perf.data/perf.txt/llm_output.txt")
    parser.add_argument("--timeout", type=int, default=120, help="Perf timeout seconds")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    parser.add_argument("--openai-url", default="https://api.openai.com/v1", help="OpenAI base URL")
    parser.add_argument("--openai-api-key", default=None, help="OpenAI API key (or OPENAI_API_KEY env)")
    parser.add_argument("--recommendations", type=int, default=3, help="Max code changes to request per LLM call")
    parser.add_argument("--max-iterations", type=int, default=3, help="Max perf→LLM→apply→rebuild cycles")
    parser.add_argument("--convergence-threshold", type=float, default=0.05, help="Stop when improvement < this fraction (default 5%%)")
    parser.add_argument("--build-cmd", default="", help="Shell command to rebuild the binary after source changes")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(args.repo_root).resolve()

    log_path = out_dir / "perf_recommend.log"
    _log_line(log_path, "perf_recommend: start")

    try:
        api_key = args.openai_api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")

        # ── Baseline profile ──────────────────────────────────────────────────────
        print("[baseline] Running perf stat...", flush=True)
        _log_line(log_path, f"perf_stat: {args.command}")
        baseline_stat = perf_stat(args.command, args.timeout)
        baseline_time = parse_task_clock_ms(baseline_stat)
        if baseline_time:
            print(f"[baseline] task-clock: {baseline_time:.1f} ms", flush=True)
        else:
            print("[baseline] Could not parse task-clock from perf stat output.", flush=True)
        _log_line(log_path, "perf_stat: ok")

        print("[baseline] Running perf record/report...", flush=True)
        _log_line(log_path, "perf_record_report: start")
        report_text = perf_record_report(args.command, out_dir, args.timeout)
        _log_line(log_path, "perf_record_report: ok")

        all_outputs: list[str] = []
        prev_time = baseline_time
        total_changed: list[str] = []

        # ── Iterative optimisation loop ───────────────────────────────────────────
        for iteration in range(1, args.max_iterations + 1):
            print(f"\n[iter {iteration}/{args.max_iterations}] Selecting source files...", flush=True)
            symbols = parse_hot_symbols(report_text)
            _log_line(log_path, f"hot_symbols: {symbols}")
            selected_files = select_source_files(repo_root, symbols, max_files=3)
            _log_line(log_path, f"selected_files: {[p.as_posix() for p in selected_files]}")
            source_bundle = read_source_bundle(selected_files)

            messages = build_prompt(
                args.command,
                baseline_stat if iteration == 1 else perf_stat(args.command, args.timeout),
                report_text,
                source_bundle,
                args.recommendations,
                selected_files,
            )

            print(f"[iter {iteration}/{args.max_iterations}] Calling LLM...", flush=True)
            _log_line(log_path, "openai: request")
            response = call_openai(messages, args.model, args.openai_url, api_key)
            _log_line(log_path, "openai: ok")
            all_outputs.append(f"=== Iteration {iteration} ===\n{response}")

            try:
                payload = json.loads(extract_json(response))
            except json.JSONDecodeError:
                payload = {}

            changed, originals = apply_changes(repo_root, payload)
            total_changed.extend(changed)
            _log_line(log_path, f"changed_files: {changed}")
            print(
                f"[iter {iteration}/{args.max_iterations}] Applied changes to: {changed or '(none)'}",
                flush=True,
            )

            if not changed:
                print(f"[iter {iteration}/{args.max_iterations}] No changes suggested, stopping early.", flush=True)
                break

            # Rebuild binary with updated source
            if args.build_cmd:
                print(f"[iter {iteration}/{args.max_iterations}] Rebuilding...", flush=True)
                if not run_build(args.build_cmd, args.timeout):
                    print(f"[iter {iteration}/{args.max_iterations}] Build failed — rolling back.", flush=True)
                    restore_changes(repo_root, originals)
                    break

            # Profile after changes to measure improvement
            print(f"[iter {iteration}/{args.max_iterations}] Re-profiling after changes...", flush=True)
            new_stat = perf_stat(args.command, args.timeout)
            report_text = perf_record_report(args.command, out_dir, args.timeout)
            new_time = parse_task_clock_ms(new_stat)

            if prev_time and new_time:
                improvement = (prev_time - new_time) / prev_time
                print(
                    f"[iter {iteration}/{args.max_iterations}] task-clock: {new_time:.1f} ms "
                    f"(improvement: {improvement:+.1%} vs previous {prev_time:.1f} ms)",
                    flush=True,
                )
                if improvement < args.convergence_threshold:
                    print(
                        f"[iter {iteration}/{args.max_iterations}] Improvement {improvement:.1%} < "
                        f"{args.convergence_threshold:.0%} threshold — converged.",
                        flush=True,
                    )
                    break
                prev_time = new_time
            else:
                print(f"[iter {iteration}/{args.max_iterations}] Could not measure improvement, stopping.", flush=True)
                break

        if baseline_time and prev_time:
            total_improvement = (baseline_time - prev_time) / baseline_time
            print(
                f"\n[done] Total improvement: {total_improvement:+.1%} "
                f"({baseline_time:.1f} ms → {prev_time:.1f} ms)",
                flush=True,
            )

        # ── Write LLM output ──────────────────────────────────────────────────────
        llm_path = out_dir / "llm_output.txt"
        llm_path.write_text("\n\n".join(all_outputs), encoding="utf-8")

    # ── Zip final source state ────────────────────────────────────────────────
        zip_path = out_dir / "source.zip"
        try:
            _log_line(log_path, f"zip_source: {zip_path}")
            zip_source(repo_root, zip_path)
            _log_line(log_path, "zip_source: ok")
        except Exception as exc:
            _log_line(log_path, f"zip_error: {exc}")
            result = {
                "changed_files": total_changed,
                "zip_object": "",
                "signed_url": "",
                "zip_error": str(exc),
            }
            _write_upload_json(out_dir, result)
            print(json.dumps(result))
            return 1

        # ── Upload to Supabase ────────────────────────────────────────────────────
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        supabase_bucket = os.getenv("SUPABASE_SOURCE_BUCKET", "")

        if not supabase_url or not supabase_key or not supabase_bucket:
            print(
                "[supabase] Missing env vars (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SOURCE_BUCKET) — skipping upload.",
                flush=True,
            )
            _log_line(log_path, "upload_error: missing supabase env")
            result = {
                "changed_files": total_changed,
                "zip_object": "",
                "signed_url": "",
            }
        else:
            _log_line(log_path, "supabase_upload: start")
            object_name, signed_url = supabase_upload(
                supabase_url, supabase_key, supabase_bucket, zip_path
            )
            _log_line(log_path, f"supabase_upload: ok object={object_name}")
            result = {
                "changed_files": total_changed,
                "zip_object": object_name,
                "signed_url": signed_url,
            }

        _write_upload_json(out_dir, result)
        print(json.dumps(result))
        _log_line(log_path, "perf_recommend: done")
        return 0
    except Exception as exc:
        _log_line(log_path, f"error: {exc}")
        result = {
            "changed_files": [],
            "zip_object": "",
            "signed_url": "",
            "error": str(exc),
        }
        _write_upload_json(out_dir, result)
        print(json.dumps(result))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
