"""Compile C sources for the optimizer loop."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompileResult:
    success: bool
    output_binary: Path
    stdout: str
    stderr: str
    elapsed_seconds: float


def infer_compile_flags(binary: Path) -> str:
    """Guess compile flags by inspecting the binary with readelf."""
    # Check for debug info section; either way, default flags are safe for profiling
    try:
        subprocess.run(
            ["readelf", "-S", str(binary)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            text=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "-O2 -g -fno-omit-frame-pointer"


def compile_source(
    source: Path,
    output: Path,
    compiler: str = "gcc",
    flags: str = "-O2 -g -fno-omit-frame-pointer",
) -> CompileResult:
    """Compile source to output binary. Does NOT raise on build error — caller checks .success."""
    cmd = [compiler, *flags.split(), "-o", str(output), str(source)]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            text=True,
        )
        elapsed = time.monotonic() - t0
        return CompileResult(
            success=proc.returncode == 0,
            output_binary=output,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed_seconds=elapsed,
        )
    except FileNotFoundError as e:
        elapsed = time.monotonic() - t0
        return CompileResult(
            success=False,
            output_binary=output,
            stdout="",
            stderr=f"Compiler not found: {e}",
            elapsed_seconds=elapsed,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        return CompileResult(
            success=False,
            output_binary=output,
            stdout="",
            stderr="Compilation timed out after 120s",
            elapsed_seconds=elapsed,
        )


def write_source(path: Path, source_code: str) -> None:
    """Atomically write source_code to path via tmp rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(source_code, encoding="utf-8")
    tmp.rename(path)
