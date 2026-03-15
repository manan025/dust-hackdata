"""Iterative self-optimization loop for perf-agent."""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager, AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

from . import llm, parser, runner
from .compiler import CompileResult, compile_source, write_source
from .errors import NoCodeBlockError, PerfPermissionError, PerfTimeoutError
from .parser import HotFunction, StatMetrics

IMPROVEMENT_THRESHOLD = 0.01  # 1% minimum improvement to KEEP
NEAR_BEST_THRESHOLD = 0.05   # stop when within 5% of theoretical best


_IPC_TABLE = [
    (("znver3", "znver4"), 6.0),
    (("znver1", "znver2"), 4.0),
    (("alder lake", "raptor lake", "meteor lake"), 6.0),
    (("skylake", "kaby lake", "coffee lake", "broadwell"), 4.0),
]
_DEFAULT_PEAK_IPC = 4.0


def _read_cpu_peak_freq_hz() -> float | None:
    try:
        p = Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
        return float(p.read_text()) * 1000.0  # kHz → Hz
    except (OSError, ValueError):
        pass
    try:
        mhz_values = []
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("cpu MHz"):
                try:
                    mhz_values.append(float(line.split(":")[1]))
                except (IndexError, ValueError):
                    pass
        if mhz_values:
            return max(mhz_values) * 1e6
    except OSError:
        pass
    return None


def _read_cpu_peak_ipc() -> float:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].lower()
                for patterns, ipc in _IPC_TABLE:
                    if any(p in model for p in patterns):
                        return ipc
                break
    except OSError:
        pass
    return _DEFAULT_PEAK_IPC


def _compute_theoretical_best_score(baseline: "StatMetrics") -> float | None:
    peak_ipc = _read_cpu_peak_ipc()
    peak_freq = _read_cpu_peak_freq_hz()

    score = 0.0
    total_weight = 0.0

    if (baseline.elapsed_seconds and baseline.instructions is not None
            and peak_freq is not None and peak_ipc > 0):
        theoretical_min = baseline.instructions / (peak_ipc * peak_freq)
        score += 0.7 * (theoretical_min / baseline.elapsed_seconds)
        total_weight += 0.7

    if baseline.ipc and baseline.ipc > 0 and peak_ipc > 0:
        score += 0.2 * (baseline.ipc / peak_ipc)
        total_weight += 0.2

    if baseline.cache_miss_pct and baseline.cache_miss_pct > 0:
        # theoretical min = 0 cache misses → contributes 0 but weight still counts
        total_weight += 0.1

    if total_weight == 0:
        return None
    return score / total_weight


def _near_theoretical_best(
    current: "StatMetrics",
    baseline: "StatMetrics",
    theoretical_score: float | None,
) -> bool:
    if theoretical_score is None:
        return False
    current_score = _score_metrics(current, baseline)
    total_gap = 1.0 - theoretical_score  # baseline score is always 1.0
    if total_gap <= 0:
        return False
    return (current_score - theoretical_score) / total_gap <= NEAR_BEST_THRESHOLD


@dataclass
class IterationRecord:
    iteration: int
    description: str
    kept: bool
    elapsed_before: float | None
    elapsed_after: float | None
    delta_pct: float
    ipc_before: float | None
    ipc_after: float | None
    compile_failed: bool = False
    no_code_block: bool = False
    revert_reason: str = ""
    user_rejected: bool = False
    user_feedback: str = ""


@dataclass
class OptimizeConfig:
    source: Path
    binary: Path
    binary_args: list[str]
    compiler: str
    compile_flags: str
    max_iterations: int
    timeout: int
    model: str
    openai_url: str
    openai_api_key: str | None
    # Callbacks — display logic stays in cli.py
    on_iteration_start: Callable[[int, int], None]
    on_llm_start: Callable[[int, int], AbstractContextManager]    # spinner context manager
    on_compile_result: Callable[[CompileResult], None]
    on_profile_start: Callable[[str], AbstractContextManager]     # spinner context manager
    on_profile_done: Callable[[StatMetrics, list[HotFunction]], None]
    on_llm_response: Callable[[str, str, int], None]  # (thinking, response, iteration)
    on_iteration_done: Callable[[IterationRecord], None]
    on_source_written: Callable[[str, str, Path], None] = field(
        default_factory=lambda: lambda old, new, path: None
    )  # (old_source, new_source, path)
    think: bool = True
    output_dir: Optional[Path] = None  # If set, write optimized source here instead of in-place
    # If provided, skip the baseline re-profile and use these directly
    initial_metrics: Optional[StatMetrics] = None
    initial_functions: Optional[list[HotFunction]] = field(default=None)
    # Docker / pluggable backends — None means use local compiler / perf
    compile_fn: Optional[Callable[[Path, Path], CompileResult]] = None
    profile_fn: Optional[Callable[..., tuple[StatMetrics, list[HotFunction]]]] = None
    target_context: Optional[str] = None   # injected into LLM system prompt
    work_dir: Optional[Path] = None        # optimizer places its tmpdir here (needed for Docker bind mount)
    on_user_approval: Optional[Callable[[str, str], tuple[bool, str]]] = None
    # (current_source, proposed_source) -> (approved: bool, feedback: str)
    # None = auto-approve (current behaviour)
    on_near_best: Callable[[float], None] = field(
        default_factory=lambda: lambda score: None
    )  # receives theoretical_best_score so display can show it


def _score_metrics(m: StatMetrics, baseline: StatMetrics) -> float:
    """Compute a normalized score relative to baseline. Lower = better."""
    score = 0.0
    total_weight = 0.0

    if m.elapsed_seconds is not None and baseline.elapsed_seconds:
        score += 0.7 * (m.elapsed_seconds / baseline.elapsed_seconds)
        total_weight += 0.7

    if m.ipc is not None and baseline.ipc and m.ipc > 0:
        # Higher IPC is better: normalize as baseline.ipc / m.ipc so lower = better
        score += 0.2 * (baseline.ipc / m.ipc)
        total_weight += 0.2

    if m.cache_miss_pct is not None and baseline.cache_miss_pct and baseline.cache_miss_pct > 0:
        score += 0.1 * (m.cache_miss_pct / baseline.cache_miss_pct)
        total_weight += 0.1

    if total_weight == 0:
        return 1.0  # can't measure, assume no change

    return score / total_weight


def _is_improvement(
    before: StatMetrics, after: StatMetrics, baseline: StatMetrics
) -> bool:
    score_before = _score_metrics(before, baseline)
    score_after = _score_metrics(after, baseline)
    delta = score_before - score_after  # positive = improvement
    return delta > IMPROVEMENT_THRESHOLD


def _profile_binary(
    binary: Path,
    args: list[str],
    timeout: int,
    perf_data: Path,
) -> tuple[StatMetrics, list[HotFunction]]:
    stat_result = runner.run_perf_stat(binary, args, timeout)
    runner.run_perf_record(binary, args, timeout, perf_data)
    report_result = runner.run_perf_report(perf_data)
    metrics = parser.parse_stat(stat_result.stderr)
    functions = parser.parse_report(report_result.stdout)
    return metrics, functions


def run_optimize_loop(config: OptimizeConfig) -> tuple[list[IterationRecord], Path]:
    """Run the iterative optimization loop.

    Returns (history, output_path) where output_path is where the best source was written.
    """
    history: list[IterationRecord] = []

    _compile = config.compile_fn or (
        lambda src, out: compile_source(src, out, compiler=config.compiler, flags=config.compile_flags)
    )
    _profile = config.profile_fn or (
        lambda binary, args, timeout, perf_data: _profile_binary(binary, args, timeout, perf_data)
    )

    if config.work_dir is not None:
        tmpdir = config.work_dir / "_opt_tmp"
        tmpdir.mkdir(exist_ok=True)
        _tmpdir_owned = False
    else:
        tmpdir = Path(tempfile.mkdtemp(prefix="perf_opt_"))
        _tmpdir_owned = True

    # Determine where to write optimized source
    if config.output_dir is not None:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = config.output_dir / config.source.name
    else:
        output_path = config.source

    try:
        # Read initial source
        current_source = config.source.read_text(encoding="utf-8")

        # Use caller-supplied metrics if available, otherwise re-profile
        if config.initial_metrics is not None and config.initial_functions is not None:
            baseline_metrics = config.initial_metrics
            baseline_functions = config.initial_functions
        else:
            baseline_perf_data = tmpdir / "baseline.data"
            baseline_metrics, baseline_functions = _profile_binary(
                config.binary, config.binary_args, config.timeout, baseline_perf_data
            )
            config.on_profile_done(baseline_metrics, baseline_functions)

        baseline = baseline_metrics
        current_metrics = baseline_metrics
        current_functions = baseline_functions
        # Path to the current "best" binary; starts as the original
        current_binary = config.binary

        theoretical_score = _compute_theoretical_best_score(baseline)
        consecutive_rejections = 0

        for iteration in range(1, config.max_iterations + 1):
            config.on_iteration_start(iteration, config.max_iterations)

            # --- Ask LLM for one optimization ---
            with config.on_llm_start(iteration, config.max_iterations):
                thinking_text, response_text, change_summary = llm.collect_optimization(
                    current_source=current_source,
                    metrics=current_metrics,
                    functions=current_functions,
                    binary=str(config.binary),
                    history=history,
                    iteration=iteration,
                    max_iterations=config.max_iterations,
                    model=config.model,
                    base_url=config.openai_url,
                    api_key=config.openai_api_key,
                    think=config.think,
                    target_context=config.target_context,
                )
            config.on_llm_response(thinking_text, response_text, iteration)

            # --- Check terminal signal ---
            if "NO_FURTHER_OPTIMIZATIONS" in response_text:
                break

            # --- Extract code block ---
            try:
                new_source = llm.extract_code_block(response_text)
            except NoCodeBlockError:
                record = IterationRecord(
                    iteration=iteration,
                    description=change_summary,
                    kept=False,
                    elapsed_before=current_metrics.elapsed_seconds,
                    elapsed_after=None,
                    delta_pct=0.0,
                    ipc_before=current_metrics.ipc,
                    ipc_after=None,
                    no_code_block=True,
                    revert_reason="No ```c block in response",
                )
                history.append(record)
                config.on_iteration_done(record)
                consecutive_rejections += 1
                if consecutive_rejections >= 3:
                    break
                continue

            # --- User approval gate ---
            _user_approved_this = False
            if config.on_user_approval is not None:
                approved, feedback = config.on_user_approval(current_source, new_source)
                if not approved:
                    record = IterationRecord(
                        iteration=iteration,
                        description=change_summary,
                        kept=False,
                        elapsed_before=current_metrics.elapsed_seconds,
                        elapsed_after=None,
                        delta_pct=0.0,
                        ipc_before=current_metrics.ipc,
                        ipc_after=None,
                        user_rejected=True,
                        user_feedback=feedback,
                        revert_reason="User rejected" + (f": {feedback}" if feedback else ""),
                    )
                    history.append(record)
                    config.on_iteration_done(record)
                    consecutive_rejections += 1
                    if consecutive_rejections >= 3:
                        break
                    continue
                _user_approved_this = True

            # --- Write candidate and compile ---
            candidate_src = tmpdir / f"candidate_{iteration}.c"
            candidate_src.write_text(new_source, encoding="utf-8")
            candidate_bin = tmpdir / f"candidate_{iteration}"

            compile_result = _compile(candidate_src, candidate_bin)
            config.on_compile_result(compile_result)

            if not compile_result.success:
                record = IterationRecord(
                    iteration=iteration,
                    description=change_summary,
                    kept=False,
                    elapsed_before=current_metrics.elapsed_seconds,
                    elapsed_after=None,
                    delta_pct=0.0,
                    ipc_before=current_metrics.ipc,
                    ipc_after=None,
                    compile_failed=True,
                    revert_reason="Compilation failed",
                )
                history.append(record)
                config.on_iteration_done(record)
                consecutive_rejections += 1
                if consecutive_rejections >= 3:
                    break
                continue

            # --- Profile candidate binary ---
            candidate_bin.chmod(0o755)
            candidate_perf_data = tmpdir / f"perf_{iteration}.data"
            try:
                with config.on_profile_start(f"Profiling candidate {iteration}/{config.max_iterations}..."):
                    candidate_metrics, candidate_functions = _profile(
                        candidate_bin, config.binary_args, config.timeout, candidate_perf_data
                    )
            except (PerfPermissionError, PerfTimeoutError) as e:
                record = IterationRecord(
                    iteration=iteration,
                    description=change_summary,
                    kept=False,
                    elapsed_before=current_metrics.elapsed_seconds,
                    elapsed_after=None,
                    delta_pct=0.0,
                    ipc_before=current_metrics.ipc,
                    ipc_after=None,
                    revert_reason=f"Profiling failed: {e}",
                )
                history.append(record)
                config.on_iteration_done(record)
                consecutive_rejections += 1
                if consecutive_rejections >= 3:
                    break
                continue

            config.on_profile_done(candidate_metrics, candidate_functions)

            # --- Decide keep or reject ---
            elapsed_before = current_metrics.elapsed_seconds
            elapsed_after = candidate_metrics.elapsed_seconds
            if elapsed_before and elapsed_after:
                delta_pct = (elapsed_after - elapsed_before) / elapsed_before * 100.0
            else:
                delta_pct = 0.0

            kept = _user_approved_this or _is_improvement(current_metrics, candidate_metrics, baseline)

            if kept:
                # Write best source and update state
                old_source = current_source
                write_source(output_path, new_source)
                config.on_source_written(old_source, new_source, output_path)
                current_source = new_source
                current_metrics = candidate_metrics
                current_functions = candidate_functions
                current_binary = candidate_bin
                consecutive_rejections = 0
                revert_reason = ""
            else:
                consecutive_rejections += 1
                if delta_pct >= 0:
                    revert_reason = f"No improvement ({delta_pct:+.1f}%)"
                else:
                    revert_reason = f"Below threshold ({delta_pct:+.1f}% < 1%)"

            record = IterationRecord(
                iteration=iteration,
                description=change_summary,
                kept=kept,
                elapsed_before=elapsed_before,
                elapsed_after=elapsed_after,
                delta_pct=delta_pct,
                ipc_before=current_metrics.ipc if not kept else baseline_metrics.ipc,
                ipc_after=candidate_metrics.ipc,
                revert_reason="" if kept else revert_reason,
            )
            history.append(record)
            config.on_iteration_done(record)

            if consecutive_rejections >= 3:
                break

            if _near_theoretical_best(current_metrics, baseline, theoretical_score):
                config.on_near_best(theoretical_score)
                break

    finally:
        if _tmpdir_owned:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return history, output_path
