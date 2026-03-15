"""Docker-based compilation and perf profiling backend."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from . import parser
from .compiler import CompileResult
from .errors import (
    DockerContainerError,
    DockerImageBuildError,
    DockerNotFoundError,
    PerfPermissionError,
)
from .parser import HotFunction, StatMetrics
from .runner import PerfResult
from .targets import TargetSpec


class DockerBackend:
    """One container per optimization session, kept alive via sleep infinity.

    All compilation and perf commands run via docker exec.  The work_dir is
    bind-mounted as /work so no explicit file transfer is required.
    """

    def __init__(
        self,
        target: TargetSpec,
        work_dir: Path,
        dockerfiles_dir: Path,
        privileged: bool = True,
        no_build: bool = False,
    ) -> None:
        self.target = target
        self._work_dir = work_dir
        self._dockerfiles_dir = dockerfiles_dir
        self._privileged = privileged
        self._no_build = no_build
        self._container_id: str | None = None
        self._image_tag = f"perf-agent-{target.name}:latest"

    def __enter__(self) -> "DockerBackend":
        _require_docker()
        if not self._no_build:
            build_image(self.target, self._dockerfiles_dir)
        self._container_id = self._start_container()
        return self

    def __exit__(self, *_) -> None:
        if self._container_id:
            try:
                subprocess.run(
                    ["docker", "stop", self._container_id],
                    capture_output=True,
                    timeout=15,
                )
            except Exception:
                pass
            try:
                subprocess.run(
                    ["docker", "rm", "-f", self._container_id],
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass
            self._container_id = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compile_source(
        self,
        source: Path,
        output: Path,
        compiler: str | None = None,
        flags: str | None = None,
    ) -> CompileResult:
        cc = compiler or self.target.compiler
        fl = flags or self.target.compile_flags
        src_cpath = self._container_path(source)
        out_cpath = self._container_path(output)
        cmd = [cc, *shlex.split(fl), "-o", out_cpath, src_cpath]
        result = self._docker_exec(cmd, timeout=120)
        return CompileResult(
            success=result.returncode == 0,
            output_binary=output,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_seconds=result.elapsed_seconds,
        )

    def run_perf_stat(
        self,
        binary: Path,
        args: list[str],
        timeout: int,
    ) -> PerfResult:
        bin_cpath = self._container_path(binary)
        cmd = ["perf", "stat", "-e", self.target.perf_events, "--", bin_cpath, *args]
        result = self._docker_exec(cmd, timeout=timeout + 30)
        _check_permission_error(result)
        return result

    def run_perf_record(
        self,
        binary: Path,
        args: list[str],
        timeout: int,
        perf_data: Path,
    ) -> PerfResult:
        bin_cpath = self._container_path(binary)
        data_cpath = self._container_path(perf_data)
        cmd = [
            "perf", "record",
            "-g", "-F", "99",
            "-o", data_cpath,
            "--", bin_cpath, *args,
        ]
        result = self._docker_exec(cmd, timeout=timeout + 30)
        _check_permission_error(result)
        return result

    def run_perf_report(self, perf_data: Path) -> PerfResult:
        data_cpath = self._container_path(perf_data)
        cmd = [
            "perf", "report",
            "--stdio", "--no-children", "-n",
            "-i", data_cpath,
        ]
        return self._docker_exec(cmd, timeout=60)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_container(self) -> str:
        cmd = ["docker", "run", "--rm", "-d"]
        if self._privileged:
            cmd.append("--privileged")
        cmd += ["--platform", self.target.platform]
        # Run as current user so compiled files are owned by us on the host bind-mount
        cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
        cmd += ["-v", f"{self._work_dir}:/work"]
        cmd.append(self._image_tag)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise DockerContainerError(
                f"Failed to start container for target '{self.target.name}':\n"
                + result.stderr.strip()
            )
        return result.stdout.strip()

    def _docker_exec(
        self,
        cmd: list[str],
        timeout: int = 300,
        workdir: str = "/work",
    ) -> PerfResult:
        if self._container_id is None:
            raise DockerContainerError("No active container — use DockerBackend as a context manager")
        full_cmd = ["docker", "exec", "-w", workdir, self._container_id, *cmd]
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise DockerContainerError(
                f"docker exec timed out after {timeout}s"
            ) from exc
        elapsed = time.monotonic() - t0
        return PerfResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
            elapsed_seconds=elapsed,
        )

    def _container_path(self, host_path: Path) -> str:
        """Map a host path under work_dir to the corresponding /work path."""
        rel = host_path.relative_to(self._work_dir)
        return f"/work/{rel}"


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _require_docker() -> None:
    if shutil.which("docker") is None:
        raise DockerNotFoundError(
            "docker not found on PATH.\n"
            "Install Docker: https://docs.docker.com/engine/install/"
        )


def build_image(target: TargetSpec, dockerfiles_dir: Path) -> None:
    """Build the Docker image for *target* from dockerfiles_dir."""
    dockerfile = dockerfiles_dir / target.dockerfile
    if not dockerfile.exists():
        raise DockerImageBuildError(
            f"Dockerfile not found: {dockerfile}",
            build_log="",
        )
    image_tag = f"perf-agent-{target.name}:latest"
    cmd = [
        "docker", "build",
        "-f", str(dockerfile),
        "-t", image_tag,
        "--platform", target.platform,
        str(dockerfiles_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DockerImageBuildError(
            f"Failed to build Docker image for target '{target.name}'",
            build_log=result.stderr + result.stdout,
        )


def _check_permission_error(result: PerfResult) -> None:
    combined = result.stderr + result.stdout
    if result.returncode != 0 and (
        "perf_event_paranoid" in combined
        or "Permission denied" in combined
        or "permission denied" in combined
    ):
        raise PerfPermissionError(
            "perf permission denied inside container.\n"
            "  Ensure the container runs with --privileged and\n"
            "  /proc/sys/kernel/perf_event_paranoid <= 1 on the host:\n"
            "    echo 1 | sudo tee /proc/sys/kernel/perf_event_paranoid"
        )


def profile_binary_in_docker(
    backend: DockerBackend,
    binary: Path,
    args: list[str],
    timeout: int,
    perf_data: Path,
) -> tuple[StatMetrics, list[HotFunction]]:
    """Profile *binary* inside *backend*'s container. Drop-in for optimizer._profile_binary."""
    stat = backend.run_perf_stat(binary, args, timeout)
    metrics = parser.parse_stat(stat.stderr)
    if not backend.target.software_events_only:
        backend.run_perf_record(binary, args, timeout, perf_data)
        report = backend.run_perf_report(perf_data)
        functions = parser.parse_report(report.stdout)
    else:
        functions = []
    return metrics, functions
