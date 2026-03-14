"""argparse + top-level orchestration for perf-agent."""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from . import __version__
from . import compiler, display, llm, optimizer, parser, runner
from .errors import (
    BinaryNotELFError,
    BinaryNotFoundError,
    DockerContainerError,
    DockerImageBuildError,
    DockerNotFoundError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    PerfNotFoundError,
    PerfPermissionError,
    PerfTimeoutError,
)


class _ListTargetsAction(argparse.Action):
    def __call__(self, parser_obj, namespace, values, option_string=None):
        from rich.table import Table
        from .targets import CATALOG

        table = Table(title="Available Targets", show_lines=True)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Platform", style="dim")
        table.add_column("Compiler")
        table.add_column("Flags")
        table.add_column("Description")

        for name, spec in sorted(CATALOG.items()):
            table.add_row(
                name,
                spec.platform,
                spec.compiler,
                spec.compile_flags,
                spec.description,
            )

        display.CONSOLE.print(table)
        parser_obj.exit(0)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="perf-agent",
        description="AI-powered Linux perf profiler — profile any ELF binary and get LLM analysis.",
    )
    p.add_argument(
        "binary",
        nargs="?",
        default=None,
        help="Path to the ELF binary to profile",
    )
    p.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the binary",
    )
    p.add_argument(
        "--model",
        default="qwen3.5:latest",
        help="Ollama model to use (default: qwen3.5:latest)",
    )
    p.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="perf execution timeout in seconds (default: 120)",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"perf-agent {__version__}",
    )

    # Optimization loop arguments
    opt_group = p.add_argument_group("self-optimization")
    opt_group.add_argument(
        "--loops",
        type=int,
        default=0,
        metavar="N",
        help="Number of optimization iterations (0 = analysis only, default: 0)",
    )
    opt_group.add_argument(
        "--source",
        type=Path,
        default=None,
        metavar="PATH",
        help="C source file to optimize (required when --loops > 0 or --target is set)",
    )
    opt_group.add_argument(
        "--compiler",
        default="gcc",
        metavar="CMD",
        help="Compiler to use for local builds (default: gcc)",
    )
    opt_group.add_argument(
        "--compile-flags",
        default=None,
        metavar="FLAGS",
        help="Compile flags (default: inferred from binary)",
    )
    opt_group.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="Directory to write optimized source (default: optimized/ next to source)",
    )

    # Docker target arguments
    docker_group = p.add_argument_group("docker targets")
    docker_group.add_argument(
        "--target",
        default=None,
        metavar="NAME",
        help="Build and profile inside a Docker container for this architecture target",
    )
    docker_group.add_argument(
        "--list-targets",
        nargs=0,
        action=_ListTargetsAction,
        help="List available Docker targets and exit",
    )
    docker_group.add_argument(
        "--no-build",
        action="store_true",
        default=False,
        help="Skip docker build — fail if the image is not already present",
    )

    p.add_argument(
        "--no-think",
        action="store_true",
        default=False,
        help="Disable LLM chain-of-thought (faster, less thorough)",
    )
    p.add_argument(
        "--user-approved",
        action="store_true",
        default=False,
        help="Pause after each LLM proposal and ask for approval before compiling. "
             "Rejection feedback is fed back to the LLM.",
    )

    return p


def main() -> None:
    p = _build_parser()
    ns = p.parse_args()

    binary_args: list[str] = [a for a in (ns.args or []) if a != "--"]

    tmpdir = None
    work_dir = None
    try:
        if ns.target is not None:
            _run_docker_path(p, ns, binary_args)
        else:
            _run_local_path(p, ns, binary_args)

    except PerfPermissionError as e:
        display.show_error(str(e))
        sys.exit(2)
    except PerfNotFoundError as e:
        display.show_error(str(e))
        sys.exit(3)
    except PerfTimeoutError as e:
        display.show_error(str(e))
        sys.exit(4)
    except OllamaConnectionError as e:
        display.show_error(str(e))
        sys.exit(5)
    except OllamaModelNotFoundError as e:
        display.show_error(str(e))
        sys.exit(6)
    except DockerNotFoundError as e:
        display.show_error(str(e))
        sys.exit(7)
    except DockerImageBuildError as e:
        msg = str(e)
        if e.build_log:
            msg += f"\n\nBuild log:\n{e.build_log[-2000:]}"
        display.show_error(msg)
        sys.exit(8)
    except DockerContainerError as e:
        display.show_error(str(e))
        sys.exit(9)
    except KeyboardInterrupt:
        display.CONSOLE.print("\n[yellow]Interrupted.[/]")
        sys.exit(130)


def _run_local_path(p: argparse.ArgumentParser, ns: argparse.Namespace, binary_args: list[str]) -> None:
    """Original local perf path — unchanged behaviour."""
    if ns.binary is None:
        p.error("binary argument is required")

    binary = Path(ns.binary)
    tmpdir = None
    try:
        # 1. Validate binary
        try:
            runner.check_elf(binary)
        except BinaryNotFoundError as e:
            display.show_error(str(e))
            sys.exit(1)
        except BinaryNotELFError as e:
            display.show_error(str(e))
            sys.exit(1)

        # 2. Check perf is installed
        if shutil.which("perf") is None:
            display.show_error(
                "perf not found on PATH.\n"
                "  Arch:   sudo pacman -S perf\n"
                "  Debian: sudo apt install linux-perf"
            )
            sys.exit(1)

        display.show_banner(str(binary))

        # 3. perf stat
        with display.spinner("Running perf stat..."):
            stat_result = runner.run_perf_stat(binary, binary_args, ns.timeout)

        # 4. perf record + report
        tmpdir_path = Path(tempfile.mkdtemp(prefix="perf_agent_"))
        tmpdir = tmpdir_path
        perf_data = tmpdir_path / "perf.data"

        with display.spinner("Recording call graph..."):
            runner.run_perf_record(binary, binary_args, ns.timeout, perf_data)

        with display.spinner("Generating perf report..."):
            report_result = runner.run_perf_report(perf_data)

        # 5. Parse
        metrics = parser.parse_stat(stat_result.stderr)
        functions = parser.parse_report(report_result.stdout)
        has_sym = parser.has_symbols(functions)

        # 6. Display metrics table
        display.show_metrics_table(metrics, functions)

        if not has_sym:
            display.show_warning_no_symbols()

        if ns.loops > 0:
            # --- Self-optimization path ---
            if ns.source is None:
                p.error("--loops > 0 requires --source")
            if not ns.source.exists():
                display.show_error(f"Source file not found: {ns.source}")
                sys.exit(1)
            if shutil.which(ns.compiler) is None:
                display.show_error(
                    f"Compiler not found on PATH: {ns.compiler}\n"
                    "Install it or specify a different compiler with --compiler."
                )
                sys.exit(1)

            compile_flags = ns.compile_flags or compiler.infer_compile_flags(binary)
            output_dir = ns.output_dir or (ns.source.parent / "optimized")

            display.CONSOLE.print(
                display.Rule(
                    f"[bold cyan]Starting optimization loop — up to {ns.loops} iteration(s)[/]",
                    style="cyan",
                )
            )

            config = optimizer.OptimizeConfig(
                source=ns.source,
                binary=binary,
                binary_args=binary_args,
                compiler=ns.compiler,
                compile_flags=compile_flags,
                max_iterations=ns.loops,
                timeout=ns.timeout,
                model=ns.model,
                ollama_url=ns.ollama_url,
                think=not ns.no_think,
                output_dir=output_dir,
                initial_metrics=metrics,
                initial_functions=functions,
                on_iteration_start=display.show_iteration_header,
                on_llm_start=lambda n, m: display.spinner(
                    f"Asking LLM for optimization {n}/{m}..."
                ),
                on_compile_result=display.show_compile_result,
                on_profile_start=display.spinner,
                on_profile_done=display.show_metrics_table,
                on_llm_response=lambda thinking, response, n: (
                    display.show_llm_thinking(thinking, n),
                    display.show_llm_optimization_response(response, n),
                ),
                on_iteration_done=display.show_iteration_result,
                on_source_written=display.show_source_diff,
                on_user_approval=(
                    (lambda cur, new: display.prompt_user_approval(cur, new, ns.source.name))
                    if ns.user_approved else None
                ),
                on_near_best=display.show_near_theoretical_best,
            )

            history, output_path = optimizer.run_optimize_loop(config)
            display.show_optimization_summary(history, output_path)

        else:
            # --- Analysis-only path ---
            chunks = llm.stream_analysis(
                metrics=metrics,
                functions=functions,
                binary=str(binary),
                model=ns.model,
                base_url=ns.ollama_url,
                think=not ns.no_think,
            )
            display.stream_llm_panel(chunks)

    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _run_docker_path(p: argparse.ArgumentParser, ns: argparse.Namespace, binary_args: list[str]) -> None:
    """Docker-based profiling and optimization path."""
    from . import docker_runner
    from .targets import get_target

    # Validate prerequisites
    if shutil.which("docker") is None:
        raise DockerNotFoundError(
            "docker not found on PATH.\n"
            "Install Docker: https://docs.docker.com/engine/install/"
        )

    try:
        target_spec = get_target(ns.target)
    except ValueError as e:
        display.show_error(str(e))
        sys.exit(1)

    if ns.source is None:
        p.error("--target requires --source")
    if not ns.source.exists():
        display.show_error(f"Source file not found: {ns.source}")
        sys.exit(1)

    # Derive display name for binary
    binary_display = ns.binary or ns.source.stem

    # Locate our dockerfiles/ directory relative to this package
    dockerfiles_dir = Path(__file__).parent.parent / "dockerfiles"
    if not dockerfiles_dir.exists():
        display.show_error(f"dockerfiles/ directory not found: {dockerfiles_dir}")
        sys.exit(1)

    output_dir = ns.output_dir or (ns.source.parent / "optimized")

    work_dir = Path(tempfile.mkdtemp(prefix="perf_agent_docker_"))
    try:
        # Copy source into work_dir (bind-mounted as /work)
        src_in_work = work_dir / ns.source.name
        src_in_work.write_text(ns.source.read_text(encoding="utf-8"), encoding="utf-8")

        binary_in_work = work_dir / ns.source.stem

        display.show_banner(f"{binary_display} [{target_spec.name}]")

        with docker_runner.DockerBackend(
            target=target_spec,
            work_dir=work_dir,
            dockerfiles_dir=dockerfiles_dir,
            no_build=ns.no_build,
        ) as backend:
            # Compile initial binary
            with display.spinner(f"Compiling with {target_spec.compiler} ({target_spec.compile_flags})..."):
                compile_result = backend.compile_source(src_in_work, binary_in_work)
            display.show_compile_result(compile_result)
            if not compile_result.success:
                display.show_error("Initial compilation failed — cannot continue.")
                sys.exit(1)

            binary_in_work.chmod(0o755)

            # Baseline profile
            initial_perf_data = work_dir / "initial.data"
            with display.spinner("Profiling initial binary..."):
                metrics, functions = docker_runner.profile_binary_in_docker(
                    backend, binary_in_work, binary_args, ns.timeout, initial_perf_data
                )
            display.show_metrics_table(metrics, functions)

            if not parser.has_symbols(functions):
                display.show_warning_no_symbols()

            if ns.loops > 0:
                # --- Docker optimization path ---
                display.CONSOLE.print(
                    display.Rule(
                        f"[bold cyan]Starting optimization loop — up to {ns.loops} iteration(s) [{target_spec.name}][/]",
                        style="cyan",
                    )
                )

                def _docker_compile(src: Path, out: Path):
                    return backend.compile_source(src, out)

                def _docker_profile(binary, args, timeout, perf_data):
                    return docker_runner.profile_binary_in_docker(
                        backend, binary, args, timeout, perf_data
                    )

                config = optimizer.OptimizeConfig(
                    source=src_in_work,
                    binary=binary_in_work,
                    binary_args=binary_args,
                    compiler=target_spec.compiler,
                    compile_flags=target_spec.compile_flags,
                    max_iterations=ns.loops,
                    timeout=ns.timeout,
                    model=ns.model,
                    ollama_url=ns.ollama_url,
                    think=not ns.no_think,
                    output_dir=output_dir,
                    initial_metrics=metrics,
                    initial_functions=functions,
                    compile_fn=_docker_compile,
                    profile_fn=_docker_profile,
                    target_context=target_spec.llm_context,
                    work_dir=work_dir,
                    on_iteration_start=display.show_iteration_header,
                    on_llm_start=lambda n, m: display.spinner(
                        f"Asking LLM for optimization {n}/{m}..."
                    ),
                    on_compile_result=display.show_compile_result,
                    on_profile_start=display.spinner,
                    on_profile_done=display.show_metrics_table,
                    on_llm_response=lambda thinking, response, n: (
                        display.show_llm_thinking(thinking, n),
                        display.show_llm_optimization_response(response, n),
                    ),
                    on_iteration_done=display.show_iteration_result,
                    on_source_written=display.show_source_diff,
                    on_user_approval=(
                        (lambda cur, new: display.prompt_user_approval(cur, new, ns.source.name))
                        if ns.user_approved else None
                    ),
                    on_near_best=display.show_near_theoretical_best,
                )

                history, output_path = optimizer.run_optimize_loop(config)
                display.show_optimization_summary(history, output_path)

            else:
                # --- Docker analysis-only path ---
                chunks = llm.stream_analysis(
                    metrics=metrics,
                    functions=functions,
                    binary=binary_display,
                    model=ns.model,
                    base_url=ns.ollama_url,
                    think=not ns.no_think,
                    target_context=target_spec.llm_context,
                )
                display.stream_llm_panel(chunks)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
