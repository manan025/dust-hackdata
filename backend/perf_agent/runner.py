"""perf subprocess execution: stat, record, report."""

import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .errors import (
    BinaryNotELFError,
    BinaryNotFoundError,
    PerfNotFoundError,
    PerfPermissionError,
    PerfTimeoutError,
)

_ELF_MAGIC = b"\x7fELF"


def check_elf(binary: Path) -> None:
    """Verify the binary exists and starts with ELF magic bytes."""
    if not binary.exists():
        raise BinaryNotFoundError(f"Binary not found: {binary}")
    try:
        with binary.open("rb") as f:
            magic = f.read(4)
    except PermissionError as e:
        raise BinaryNotFoundError(f"Cannot read binary: {e}") from e
    if magic != _ELF_MAGIC:
        raise BinaryNotELFError(
            f"{binary} does not appear to be an ELF binary (magic: {magic!r})"
        )


@dataclass
class PerfResult:
    stdout: str
    stderr: str
    returncode: int
    elapsed_seconds: float


@dataclass
class PerfResults:
    stat_raw: str
    report_raw: str
    elapsed_stat: float
    elapsed_record: float
    perf_data: Path = field(default_factory=lambda: Path("/tmp/perf.data"))


def _check_perf() -> str:
    path = shutil.which("perf")
    if path is None:
        raise PerfNotFoundError(
            "perf not found on PATH. Install it:\n"
            "  Arch:   sudo pacman -S perf\n"
            "  Debian: sudo apt install linux-perf"
        )
    return path


def _run(cmd: list[str], timeout: int) -> PerfResult:
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
        )
    except FileNotFoundError as e:
        raise PerfNotFoundError(f"Could not execute {cmd[0]}: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise PerfTimeoutError(
            f"perf timed out after {timeout}s. Try --timeout <seconds>."
        ) from e
    elapsed = time.monotonic() - t0
    return PerfResult(
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
        elapsed_seconds=elapsed,
    )


def _check_permission_error(result: PerfResult) -> None:
    combined = result.stdout + result.stderr
    if result.returncode != 0:
        if "Permission denied" in combined or "EPERM" in combined:
            raise PerfPermissionError(
                "perf was denied access (perf_event_paranoid too restrictive).\n"
                "Fix options:\n"
                "  echo -1 | sudo tee /proc/sys/kernel/perf_event_paranoid\n"
                "  Or run: sudo perf-agent ..."
            )
        if "perf_event_paranoid" in combined:
            raise PerfPermissionError(
                "perf_event_paranoid blocks profiling.\n"
                "  echo 1 | sudo tee /proc/sys/kernel/perf_event_paranoid"
            )


_STAT_EVENTS = (
    "task-clock,cpu-cycles,instructions,branches,branch-misses,"
    "cache-references,cache-misses"
)


def run_perf_stat(
    binary: Path, args: list[str], timeout: int
) -> PerfResult:
    perf = _check_perf()
    cmd = [perf, "stat", "-e", _STAT_EVENTS, str(binary.resolve())] + args
    result = _run(cmd, timeout)
    _check_permission_error(result)
    return result


def run_perf_record(
    binary: Path, args: list[str], timeout: int, perf_data: Path
) -> PerfResult:
    perf = _check_perf()
    cmd = [perf, "record", "-g", "-F", "99", "-o", str(perf_data), str(binary.resolve())] + args
    result = _run(cmd, timeout)
    _check_permission_error(result)
    return result


def run_perf_stat_cmd(cmd_args: list[str], timeout: int) -> PerfResult:
    perf = _check_perf()
    cmd = [perf, "stat", "-e", _STAT_EVENTS, "--", *cmd_args]
    result = _run(cmd, timeout)
    _check_permission_error(result)
    return result


def run_perf_record_cmd(
    cmd_args: list[str], timeout: int, perf_data: Path
) -> PerfResult:
    perf = _check_perf()
    cmd = [
        perf, "record", "-g", "-F", "99", "-o", str(perf_data), "--", *cmd_args
    ]
    result = _run(cmd, timeout)
    _check_permission_error(result)
    return result


def run_perf_report(perf_data: Path) -> PerfResult:
    perf = _check_perf()
    cmd = [perf, "report", "--stdio", "--no-children", "-n", "-i", str(perf_data)]
    result = _run(cmd, timeout=60)
    return result


def collect_all(
    binary: Path, args: list[str], timeout: int = 120
) -> tuple[PerfResults, Path]:
    """Run stat + record + report, returning PerfResults and the tmpdir to clean up."""
    tmpdir = Path(tempfile.mkdtemp(prefix="perf_agent_"))
    perf_data = tmpdir / "perf.data"

    stat_result = run_perf_stat(binary, args, timeout)
    _run_record_result = run_perf_record(binary, args, timeout, perf_data)
    report_result = run_perf_report(perf_data)

    return (
        PerfResults(
            stat_raw=stat_result.stderr,
            report_raw=report_result.stdout,
            elapsed_stat=stat_result.elapsed_seconds,
            elapsed_record=_run_record_result.elapsed_seconds,
            perf_data=perf_data,
        ),
        tmpdir,
    )
