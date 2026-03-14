# How to Run perf-agent

## Prerequisites

- Linux (perf requires the Linux perf subsystem)
- Python 3.11+
- `perf` installed (`sudo pacman -S perf` / `sudo apt install linux-perf`)
- [Ollama](https://ollama.com) running locally with a model pulled (default: `qwen3.5:latest`)
- GCC (for the optimization loop)
- Docker (only for `--target` cross-architecture runs)

## Install

```bash
pip install -e /home/monarq/Work/hackdata-26
```

## Quick start — profile a binary

```bash
# Compile the included test program
gcc -O0 -g -fno-omit-frame-pointer -o /tmp/test_prog test_prog.c

# Profile and get AI analysis
perf-agent /tmp/test_prog
```

## Optimization loop

Iteratively rewrite source code and re-profile until improvement stalls or a ceiling
is reached.

```bash
perf-agent --loops 10 \
           --source test_prog.c \
           --output-dir /tmp/optimized \
           /tmp/test_prog
```

Optimized source is written to `--output-dir` (default: `optimized/` next to the source).
The loop stops early when any of the following is true:

- 3 consecutive iterations produce no improvement
- The LLM emits `NO_FURTHER_OPTIMIZATIONS`
- The current score is within 5% of the theoretical hardware ceiling
- Max iterations (`--loops`) reached
- Ctrl-C

## Options

| Flag | Default | Description |
|---|---|---|
| `--loops N` | 0 | Optimization iterations (0 = analysis only) |
| `--source PATH` | — | C source file (required with `--loops > 0`) |
| `--output-dir DIR` | `optimized/` | Where to write the best source |
| `--compiler CMD` | `gcc` | Compiler for local builds |
| `--compile-flags FLAGS` | auto-inferred | Compiler flags |
| `--model NAME` | `qwen3.5:latest` | Ollama model |
| `--ollama-url URL` | `http://localhost:11434` | Ollama endpoint |
| `--timeout N` | 120 | perf execution timeout (seconds) |
| `--no-think` | off | Disable chain-of-thought (faster) |
| `--user-approved` | off | Pause and ask before each compile |
| `--target NAME` | — | Run inside Docker for a specific architecture |
| `--list-targets` | — | Print available Docker targets and exit |
| `--no-build` | off | Skip Docker image build |

## Docker targets (cross-architecture)

Build and profile inside a container — useful for testing architecture-specific
compiler flags without native hardware.

```bash
# List available targets
perf-agent --list-targets

# Optimize for AMD Zen 3
perf-agent --target amd-zen3 \
           --loops 5 \
           --source test_prog.c

# Optimize with Clang LTO
perf-agent --target clang-lto \
           --loops 5 \
           --source test_prog.c
```

Available targets:

| Name | Compiler | Flags | Notes |
|---|---|---|---|
| `generic` | GCC 12 | `-O2` | Ubuntu 22.04 x86-64 |
| `amd-zen3` | GCC 13 | `-O3 -march=znver3` | AMD Zen 3 |
| `intel-skylake` | GCC 12 | `-O3 -march=skylake` | Intel Skylake |
| `clang-lto` | Clang 17 | `-O2 -flto` | LTO-enabled |
| `arm64` | GCC 12 | `-O2` | AArch64 via QEMU (software counters only) |

## User-approval mode

Review and optionally reject each LLM proposal before it is compiled:

```bash
perf-agent --loops 10 --source test_prog.c --user-approved /tmp/test_prog
```

At each proposal you will see a unified diff and a prompt:
- `y` / Enter — accept
- `n` — reject silently
- Any other text — reject and feed the text back to the LLM as guidance

## perf permissions

If perf reports a permissions error, lower the paranoia level:

```bash
sudo sysctl kernel.perf_event_paranoid=1
```

Or make it permanent in `/etc/sysctl.d/99-perf.conf`:

```
kernel.perf_event_paranoid = 1
```
