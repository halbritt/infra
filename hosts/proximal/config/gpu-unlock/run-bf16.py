#!/usr/bin/env python3
"""Capture BF16 benchmark results and GPU telemetry under a fleet lease."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    if os.environ.get("GPU_FLEET_NODE") != "proximal" or not os.environ.get("GPU_FLEET_LEASE_ID"):
        raise SystemExit("A proximal GPU fleet lease is required")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kernel": command("uname", "-r"),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "cmdline": Path("/proc/cmdline").read_text().strip(),
        "gpu": command("nvidia-smi", "--query-gpu=name,uuid,pci.bus_id,driver_version,power.limit", "--format=csv"),
        "compute_processes": command("nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv"),
        "binary_sha256": digest(args.binary),
        "source_sha256": digest(Path(__file__).with_name("benchmark-bf16.cu")),
        "lease": {key: os.environ[key] for key in (
            "GPU_FLEET_NODE", "GPU_FLEET_SLOT_ID", "GPU_FLEET_LEASE_ID",
            "GPU_FLEET_ENDPOINT_URL", "GPU_FLEET_SERVED_MODEL")},
    }
    kernel_log = command("journalctl", "-k", "-b", "--no-pager")
    metadata["unlock_log"] = [line for line in kernel_log.splitlines() if "gpu_unlock: unlocked" in line]
    (args.output_dir / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    with (args.output_dir / "telemetry.csv").open("x") as telemetry, \
         (args.output_dir / "telemetry.stderr").open("x") as telemetry_errors, \
         (args.output_dir / "benchmark.json").open("x") as result:
        monitor = subprocess.Popen([
            "nvidia-smi", "--query-gpu=timestamp,power.draw,power.limit,clocks.sm,clocks.mem,temperature.gpu,utilization.gpu,memory.used",
            "--format=csv,nounits", "--loop-ms=200"], stdout=telemetry, stderr=telemetry_errors)
        try:
            subprocess.run([str(args.binary.resolve())], stdout=result, check=True, timeout=180)
        finally:
            monitor.terminate()
            monitor.wait(timeout=5)
    if (args.output_dir / "telemetry.stderr").stat().st_size:
        raise RuntimeError("nvidia-smi telemetry reported errors; inspect telemetry.stderr")
    benchmark = json.loads((args.output_dir / "benchmark.json").read_text())
    if not benchmark.get("complete"):
        raise RuntimeError("Benchmark did not complete")
    print(json.dumps(benchmark, indent=2))


if __name__ == "__main__":
    main()
