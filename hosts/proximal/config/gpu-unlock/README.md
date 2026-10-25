# GPU unlock on proximal

Owner-requested installation of <https://github.com/Zagitta/gpu-unlock> to
`~/git/gpu-unlock`, pinned at `af28cbbfd3d922a659227ecfb7369adfd924cf03`
(version 1.0.0), on 2026-10-25. Both Debian packages are installed. The
2026-10-25 11:17 PDT boot confirmed `0000:01:00.0: gpu_unlock: unlocked`.

`benchmark.py` runs against the existing local llama.cpp service under a
gpu-fleet lease. It keeps the serving configuration, uses uncached prompts,
greedy decoding, a warmup and five measured repetitions at each prompt size.
Results include request hashes, output hashes, server timings and environment
identity. Generation results describe this workload, including MTP effects.

## Installation

`make install` built the Debian packages from the pinned upstream HEAD, fetched
checksum-verified firmware inputs, passed all five upstream tests and installed
`gpu-unlock-dkms` and `gpu-unlock-firmware` version 1.0.0. DKMS built for both
installed kernels, `6.8.0-146-generic` and `6.8.0-147-generic`. Secure Boot is
disabled. Build log: `~/.cache/gpu-unlock-install-20261025.log`; packages remain
under `~/git/gpu-unlock/build/deb/`.

The current kernel's rebuilt initramfs contains `gpu_unlock.ko.zst` and all five
firmware files. Its `conf/modules` loads `gpu_unlock`. The NVIDIA display/compute
driver is absent from this image, so udev cannot bind it there before the unlock.
The upstream module's load completes before NVIDIA binds from the root filesystem.

| Canonical file | Installed path |
|---|---|
| `99-gpu-unlock.cfg` | `/etc/default/grub.d/99-gpu-unlock.cfg` |
| `benchmark-after-boot.sh` | `/usr/local/libexec/gpu-unlock-benchmark-after-boot` (0755) |
| `gpu-unlock-benchmark.service` | `/etc/systemd/system/gpu-unlock-benchmark.service` |
| `benchmark.py`, `results/before.json` | Read directly from this checkout |

The GRUB drop-in adds `gpu_unlock.targets=0000:01:00.0` to normal boot entries.
`update-grub` completed. A one-time `grub-reboot` selection was configured for
`6.8.0-146-generic`; the normal default was the newer 147 kernel.
No reboot had been issued at the installation checkpoint. The subsequent boot
used kernel 147; the one-time GRUB selection was empty when inspected afterward.

## Baseline

Raw measurements: [results/before.json](results/before.json). Model:
Qwen3.8-27B UD-Q4_K_XL, context 131072, q8_0 KV, all layers on GPU, flash
attention, MTP depth 2. RTX 3090 at 350 W; NVIDIA driver 615.71.09.

The running llama.cpp build was older than the on-disk executable. Before any
measurements, `llama-27b` was restarted under a fleet lease and became healthy
on build `b11870-74bca3950`. This is the required build for the after-run. The
benchmark checks the executable and model SHA-256, serving arguments, kernel,
GPU identity, driver, power limit, context and input corpus before comparing.

| Prompt tokens | Prompt tokens/s, median | Generation tokens/s, median |
|---:|---:|---:|
| 512 | 1192.69 | 80.52 |
| 4096 | 1413.10 | 69.84 |
| 16384 | 1370.76 | 70.56 |

Each row represents five requests generating 256 tokens after one excluded
warmup. Inputs are prefixes of the existing qwen-eval WikiText-2 corpus.
Sampling is greedy with seed 42; `ignore_eos=true` fixes output length;
`cache_prompt=false` forces full prefill. All 15 samples reported zero cached
tokens, the expected counts, and one stable output hash per prompt size.
Prompt-speed ranges were 1136.76–1208.76, 1398.58–1423.69 and
1347.60–1371.63 tokens/s respectively. These measurements cover corpus
continuation on the standing service, not all chat or concurrent workloads.
Other GPU users that do not honor the fleet lease remain a possible confounder;
per-sample GPU clocks, power, temperature and memory usage are retained.

## After the reboot

`gpu-unlock-benchmark.service` was enabled for the first qualifying boot. It first
saves the kernel log, requires a successful unlock, waits up to five minutes for
a fleet lease, then runs the same benchmark. A partial run is never retried.
Results go outside Git to `~/.local/state/gpu-unlock/after.json` and
`kernel-after.log`. The existence of `after.json` prevents another automatic run.

Inspect:

```sh
systemctl status gpu-unlock-benchmark.service
journalctl -u gpu-unlock-benchmark.service -b --no-pager
journalctl -k -b --no-pager | grep gpu_unlock
```

The automatic run aborted with `Benchmark identity changed: ['kernel']` because
the baseline used 146 and this boot used 147. The owner explicitly requested
running on the current kernel and reporting the comparison. The manual run used
the same script without `--compare`; both recorded identities remain intact.
The strict automatic comparison behavior is unchanged.

Manual invocation, after resolving any failure and preserving its evidence:

```sh
sudo systemctl start gpu-unlock-benchmark.service
```

## Measured after-results (2026-10-25)

Raw measurements: [results/after.json](results/after.json). All 15 samples
completed under a proximal fleet lease; the runner exited 0. Each prompt size
used five repetitions, 256 generated tokens, and zero cached prompt tokens.
Request and output hashes match the baseline at every size.

| Prompt tokens | Before prompt tok/s | After prompt tok/s | Change | Before generation tok/s | After generation tok/s | Change |
|---:|---:|---:|---:|---:|---:|---:|
| 512 | 1192.69 | 1226.91 | +2.87% | 80.52 | 81.92 | +1.74% |
| 4096 | 1413.10 | 1439.96 | +1.90% | 69.84 | 70.60 | +1.09% |
| 16384 | 1370.76 | 1402.18 | +2.29% | 70.56 | 70.99 | +0.62% |

Values are medians. Prompt processing increased 1.90–2.87%; generation increased
0.62–1.74%. This workload shows a small improvement. The only recorded identity
difference is kernel 6.8.0-146 versus 6.8.0-147; model, server build, serving
arguments, driver, GPU power limit, context and corpus match. These measurements
include the reboot/kernel change and do not isolate its contribution.

The manual command was `gpu-fleet-run --model qwen3.8-27b --max-context 17000
--job gpu-unlock-after-agent563-20261025 --timeout 1200 -- python3
/home/halbritt/git/infra/hosts/proximal/config/gpu-unlock/benchmark.py
/home/halbritt/.local/state/gpu-unlock/after.json` (one shell command).
Fleet checkout: `2de20079385e9792910c4c8a26da8913db11107b`.
The one-time benchmark service was disabled after completion.

## BF16 tensor throughput (2026-10-25)

The owner requested a direct check against published BF16 results after fixing
the keyboard-free GRUB boot behavior (see [boot](../boot/README.md)).
`benchmark-bf16.cu` measures dense 8192-by-8192-by-8192 cuBLAS GEMM with BF16
inputs and FP32 accumulation/output. Reduced-precision reductions are disabled.
There are 200 warmup multiplications, then five samples of 500 multiplications
timed with CUDA events. Each GEMM counts as `2*N*N*N` floating-point operations.
Input initialization, transfers and correctness checks are outside the timings.
Sixty-four output elements are compared with a CPU FP64 reference before and
after timing; the observed maximum absolute error was zero.

The median was **126.86 TFLOPS** (126.61–127.32 across samples), or 8.67 ms per
GEMM. The power limit stayed at 350 W; sampled draw averaged about 345 W and
sample mean SM clocks ranged from 1583 to 1606 MHz. Maximum sampled temperature
was 63 C. Median throughput per MHz was **0.07984 TFLOPS/MHz**.

For comparison, the [published RTX 3090 report](https://github.com/Zagitta/gpu-unlock/issues/33)
at 350 W measured 114.8 TFLOPS at 1425 MHz unlocked (0.08056 TFLOPS/MHz), versus
72.0 at 1710 MHz locked (0.04211 TFLOPS/MHz). Our per-clock rate is within 1%
of that unlocked result, consistent with full-rate BF16 operation. This is a
cross-machine comparison; no locked BF16 baseline was measured on proximal.
The published report used PyTorch/cuBLAS on CUDA 13, while this test uses direct
cuBLAS 12.8.5 with CUDA runtime 12.8 and the installed 615.71.09 driver.

[Raw benchmark](results/bf16-unlocked-20261025/benchmark.json),
[environment](results/bf16-unlocked-20261025/environment.json),
[200 ms telemetry](results/bf16-unlocked-20261025/telemetry.csv), and
[summary](results/bf16-unlocked-20261025/summary.json) are retained. Telemetry
averages use only each sample's timed interval. The run held a proximal GPU
fleet lease and exited 0. The existing llama-27b process stayed resident and
healthy; no NVIDIA Xid appeared during the run.

Build and run from the repository root (use a fresh output directory each run):

```sh
mkdir -p ~/.cache/gpu-unlock-benchmark
/usr/local/cuda/bin/nvcc -O3 -std=c++17 -arch=sm_86 -Xcompiler=-Wall,-Wextra \
  hosts/proximal/config/gpu-unlock/benchmark-bf16.cu -lcublas \
  -o ~/.cache/gpu-unlock-benchmark/benchmark-bf16
/home/halbritt/git/gpu-fleet/bin/gpu-fleet-run \
  --model qwen3.8-27b --max-context 17000 --job gpu-unlock-bf16 --timeout 240 -- \
  python3 hosts/proximal/config/gpu-unlock/run-bf16.py \
  ~/.cache/gpu-unlock-benchmark/benchmark-bf16 \
  ~/.local/state/gpu-unlock/bf16-new-run
```

## Rollback

For one boot, delete `gpu_unlock.targets=0000:01:00.0` from GRUB's edited Linux
command line. Persistently disable with:

```sh
sudo rm /etc/default/grub.d/99-gpu-unlock.cfg
sudo update-grub
sudo systemctl disable gpu-unlock-benchmark.service
```

The selector change lasts until the card loses power. Removing the boot option
does not undo an already-running unlock. Remove packages, if desired, with
`sudo apt-get remove gpu-unlock-dkms gpu-unlock-firmware`; package removal
rebuilds the initramfs. If the module reports hung firmware, upstream requires
a power-off before another attempt.

## Verification boundary

Installation checks passed: upstream tests (5), infrastructure tests (43),
repository validation, shell syntax and systemd unit validation. The systemd
validator also reported an existing unrelated `systemd-resolved` drop-in with
an unknown `Resolve` section. The model endpoint remained healthy after installation.
The current boot's kernel log verifies activation. Non-target GPU workloads and
broad model-quality equivalence have not been evaluated by this benchmark.
