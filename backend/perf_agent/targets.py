"""Target architecture specifications for Docker-based profiling."""

from __future__ import annotations

from dataclasses import dataclass

_HW_EVENTS = (
    "task-clock,cpu-cycles,instructions,branches,branch-misses,"
    "cache-references,cache-misses"
)
_SW_EVENTS = "task-clock,context-switches,cpu-migrations,page-faults,instructions,branches"


@dataclass(frozen=True)
class TargetSpec:
    name: str
    description: str
    dockerfile: str           # filename inside dockerfiles/
    platform: str             # "linux/amd64" or "linux/arm64/v8"
    compiler: str             # "gcc-12", "clang-17", etc.
    compile_flags: str
    perf_events: str
    software_events_only: bool
    llm_context: str          # injected into LLM system prompt


CATALOG: dict[str, TargetSpec] = {
    "generic": TargetSpec(
        "generic",
        "Ubuntu 22.04, GCC 12, -O2",
        "Dockerfile.generic",
        "linux/amd64",
        "gcc-12",
        "-O2 -g -fno-omit-frame-pointer",
        _HW_EVENTS,
        False,
        "Generic x86-64, GCC 12, -O2.",
    ),
    "amd-zen3": TargetSpec(
        "amd-zen3",
        "Ubuntu 22.04, GCC 13, -march=znver3",
        "Dockerfile.amd-zen3",
        "linux/amd64",
        "gcc-13",
        "-O3 -march=znver3 -g -fno-omit-frame-pointer",
        _HW_EVENTS,
        False,
        "AMD Zen 3 (-march=znver3), GCC 13, -O3. Favour AVX2, large L3, 6-wide superscalar.",
    ),
    "intel-skylake": TargetSpec(
        "intel-skylake",
        "Ubuntu 22.04, GCC 12, -march=skylake",
        "Dockerfile.intel-skylake",
        "linux/amd64",
        "gcc-12",
        "-O3 -march=skylake -g -fno-omit-frame-pointer",
        _HW_EVENTS,
        False,
        "Intel Skylake (-march=skylake), GCC 12, -O3. AVX2, 224-entry ROB, hyperthreading.",
    ),
    "clang-lto": TargetSpec(
        "clang-lto",
        "Ubuntu 22.04, Clang 17, -O2 -flto",
        "Dockerfile.clang-lto",
        "linux/amd64",
        "clang-17",
        "-O2 -flto -g -fno-omit-frame-pointer",
        _HW_EVENTS,
        False,
        "x86-64, Clang 17, -O2 -flto. LTO active; cross-function inlining available.",
    ),
    "arm64": TargetSpec(
        "arm64",
        "Ubuntu 22.04 arm64 (QEMU), software events",
        "Dockerfile.arm64",
        "linux/arm64/v8",
        "gcc-12",
        "-O2 -g -fno-omit-frame-pointer",
        _SW_EVENTS,
        True,
        "ARM64/AArch64, GCC 12, -O2. QEMU — hardware counters unavailable. Avoid x86-specific builtins; prefer NEON.",
    ),
}


def get_target(name: str) -> TargetSpec:
    if name not in CATALOG:
        raise ValueError(
            f"Unknown target {name!r}. Available: {', '.join(sorted(CATALOG))}"
        )
    return CATALOG[name]
