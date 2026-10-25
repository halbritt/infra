#!/usr/bin/env python3
"""Measure the standing Qwen service; invoke through gpu-fleet-run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
import urllib.request


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def request(base, path, data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(base + path, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if os.environ.get("GPU_FLEET_NODE") != "proximal" or not os.environ.get("GPU_FLEET_LEASE_ID"):
        raise SystemExit("A proximal GPU fleet lease is required")
    base = os.environ["GPU_FLEET_ENDPOINT_URL"].removesuffix("/v1")
    props = request(base, "/props")
    if props["model_alias"] != "qwen3.8-27b":
        raise SystemExit("Unexpected model")
    pid = command("systemctl", "show", "llama-27b", "-p", "MainPID", "--value")
    corpus = Path("/home/halbritt/git/qwen-eval/corpus/wikitext-2-test.txt")
    tokens = request(base, "/tokenize", {"content": corpus.read_text()[:250000],
                                        "add_special": True})["tokens"]
    assert len(tokens) >= 16384
    identity = {
        "build": props["build_info"], "model_path": props["model_path"],
        "model_sha256": digest(props["model_path"]),
        "server_sha256": digest(f"/proc/{pid}/exe"),
        "exec_start": command("systemctl", "show", "llama-27b", "-p", "ExecStart", "--value").split(" ; ignore_errors")[0],
        "n_ctx": props["default_generation_settings"]["n_ctx"],
        "kernel": command("uname", "-r"),
        "gpu": command("nvidia-smi", "--query-gpu=name,uuid,driver_version,power.limit", "--format=csv,noheader"),
        "corpus_sha256": digest(corpus),
    }
    if args.compare:
        prior = json.loads(args.compare.read_text())
        if not prior.get("complete"):
            raise SystemExit("The baseline did not complete")
        if prior["identity"] != identity:
            changed = [k for k in identity if prior["identity"].get(k) != identity[k]]
            raise SystemExit(f"Benchmark identity changed: {changed}")
        kernel_log = command("journalctl", "-k", "-b", "--no-pager")
        if "0000:01:00.0: gpu_unlock: unlocked" not in kernel_log:
            raise SystemExit("The current boot has no successful GPU unlock record")
    result = {"identity": identity, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
              "cmdline": Path("/proc/cmdline").read_text().strip(),
              "lease": {k: v for k, v in os.environ.items() if k.startswith("GPU_FLEET_") and k != "GPU_FLEET_DB"},
              "samples": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        def sample(size, repetition):
            payload = {"prompt": tokens[:size], "n_predict": 256, "temperature": 0,
                       "seed": 42, "cache_prompt": False, "ignore_eos": True,
                       "stream": False}
            started = time.monotonic()
            response = request(base, "/completion", payload)
            timings = response["timings"]
            if timings["prompt_n"] != size or timings["predicted_n"] != 256 or timings["cache_n"] != 0:
                raise RuntimeError(f"Unexpected token counts: {timings}")
            row = {"prompt_tokens": size, "repetition": repetition,
                   "wall_seconds": time.monotonic() - started, "timings": timings,
                   "request_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                   "content_sha256": hashlib.sha256(response["content"].encode()).hexdigest(),
                   "gpu": command("nvidia-smi", "--query-gpu=temperature.gpu,power.draw,clocks.sm,clocks.mem,utilization.gpu,memory.used", "--format=csv,noheader")}
            print(json.dumps(row), flush=True)
            return row
        result["warmup"] = sample(512, -1)
        for size in (512, 4096, 16384):
            for repetition in range(5):
                result["samples"].append(sample(size, repetition))
                output.seek(0)
                json.dump(result, output, indent=2)
                output.truncate()
                output.flush()
        result["medians"] = {
            str(size): {metric: statistics.median(row["timings"][metric]
                       for row in result["samples"] if row["prompt_tokens"] == size)
                       for metric in ("prompt_per_second", "predicted_per_second")}
            for size in (512, 4096, 16384)}
        result["complete"] = True
        output.seek(0)
        json.dump(result, output, indent=2)
        output.truncate()
    print(json.dumps(result["medians"], indent=2))


if __name__ == "__main__":
    main()
