#!/usr/bin/env python3
"""hostmon probe: one read-only host snapshot as JSON on stdout (agent-449, owner monitoring 2026-10-22).
Run locally or as `ssh HOST python3 - < probe.py`. Never reads secrets or environments; a probe that cannot
run reports "UNKNOWN" for its field, never a healthy default."""
import json, os, re, shutil, socket, subprocess, time

U = "UNKNOWN"


def sh(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=isinstance(cmd, str))
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def psi(kind):
    try:
        some = open(f"/proc/pressure/{kind}").read().splitlines()[0]
        return {k: float(v) for k, v in re.findall(r"(avg10|avg60)=([\d.]+)", some)}
    except OSError:
        return U


def meminfo():
    try:
        m = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
        return {"total_mb": m["MemTotal"] // 1024, "avail_mb": m["MemAvailable"] // 1024,
                "swap_total_mb": m["SwapTotal"] // 1024, "swap_used_mb": (m["SwapTotal"] - m["SwapFree"]) // 1024}
    except (OSError, KeyError, ValueError):
        return U


def disks():
    out = {}
    for p in ("/", "/var/lib/docker", os.path.expanduser("~"), "/tmp"):
        try:
            if os.path.exists(p):
                u = shutil.disk_usage(p)
                out[p] = {"used_pct": round(100 * u.used / u.total, 1), "free_gb": round(u.free / 2**30, 1)}
        except OSError:
            out[p] = U
    return out


def procs():
    zomb, parents, suites, workers, wrappers = 0, {}, [], [], 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            stat = open(f"/proc/{pid}/stat").read()
            comm = stat[stat.index("(") + 1:stat.rindex(")")]
            fields = stat[stat.rindex(")") + 2:].split()
            state, ppid = fields[0], fields[1]
            if state == "Z":
                zomb += 1
                parents[ppid] = parents.get(ppid, 0) + 1
                continue
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace").strip()
        except (OSError, ValueError):
            continue
        if cmd.startswith("python3 scripts/strict_suite.py"):
            m = re.search(r"--summary (\S+)", cmd)
            mods = len([t for t in cmd.split() if t.startswith("test_")])
            suites.append({"pid": int(pid), "summary": m.group(1) if m else None, "modules": mods,
                           "jobs": (re.search(r"--jobs (\d+)", cmd) or [None, None])[1]})
        elif cmd.startswith("bash ") and "/ae-ci-exec" in cmd:
            wrappers += 1
        elif re.match(r"(\S*/)?(claude|codex)\b", cmd) and ("--print" in cmd or " exec" in cmd):
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                cwd = U
            model = (re.search(r"(?:--model|-m) (\S+)", cmd) or [None, None])[1]
            workers.append({"pid": int(pid), "model": model, "cwd": os.path.basename(cwd)})
    top = sorted(parents.items(), key=lambda kv: -kv[1])[:5]
    named = []
    for ppid, n in top:
        try:
            pc = open(f"/proc/{ppid}/comm").read().strip()
        except OSError:
            pc = U
        named.append({"ppid": int(ppid), "comm": pc, "zombies": n})
    return {"zombies": zomb, "zombie_parents": named, "suites": suites, "ae_ci_exec_wrappers": wrappers,
            "agent_processes": workers}


def admission():
    na = os.path.expanduser("~/.local/bin/native-admit")
    if not os.path.exists(na):
        return U
    out = sh([na, "status"])
    if out is None:
        return U
    first = out.splitlines()[0] if out else ""
    m = re.search(r"used (\d+)/(\d+), suites (\d+)/(\d+)", first)
    res = re.search(r"reserved for '([^']*)' until (.*)", out)
    return {"used": int(m[1]) if m else U, "budget": int(m[2]) if m else U, "suites": int(m[3]) if m else U,
            "suite_cap": int(m[4]) if m else U, "queued": len(re.findall(r"^\s+queued ", out, re.M)),
            "unleased": len(re.findall(r"^\s+unleased ", out, re.M)),
            "reserved": {"by": res[1], "until": res[2].strip()} if res else None, "status_line": first[:200]}


def containers():
    out = sh(["docker", "ps", "--format", "{{.ID}} {{.Names}}"])
    if out is None:
        return U
    rows = [l.split(None, 1) for l in out.splitlines() if l.strip()]
    res = []
    if rows:
        ins = sh(["docker", "inspect", *[r[0] for r in rows]], timeout=20)
        try:
            data = json.loads(ins) if ins else []
        except ValueError:
            data = []
        for c in data:
            hc = c.get("HostConfig", {})
            pid = c.get("State", {}).get("Pid")
            try:
                pid1 = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")[0].decode(errors="replace")
            except (OSError, TypeError):
                pid1 = U
            res.append({"name": c.get("Name", "").lstrip("/"), "image": c.get("Config", {}).get("Image"),
                        "started": c.get("State", {}).get("StartedAt", "")[:19], "init": hc.get("Init"),
                        "cpus": (hc.get("NanoCpus") or 0) / 1e9, "lease": (c.get("Config", {}).get("Labels") or {}).get("native-admission.lease"), "pids_limit": hc.get("PidsLimit"), "pid1": pid1})
    return res


def native_sample():
    na = os.path.expanduser("~/.local/bin/native-admit")
    out = sh([na, "sample", "--print"]) if os.path.exists(na) else None
    try:
        d = json.loads(out.strip().splitlines()[-1]) if out else None
    except (ValueError, IndexError):
        return U
    if d is None:
        return U
    # 475: a lease is stuck only if its pid is gone while still listed; check liveness, never grep names.
    dead = []
    for l in d.get("leases") or []:
        try:
            os.kill(int(l.get("pid")), 0)
        except PermissionError:
            pass
        except (ProcessLookupError, TypeError, ValueError):
            dead.append({k: l.get(k) for k in ("id", "label", "pid", "started")})
    d["dead_leases"] = dead
    return d


def main():
    try:
        load = [float(x) for x in open("/proc/loadavg").read().split()[:3]]
    except OSError:
        load = U
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "host": socket.gethostname(),
                      "load": load, "nproc": os.cpu_count(), "psi": {k: psi(k) for k in ("cpu", "io", "memory")},
                      "mem": meminfo(), "disk": disks(), "admission": admission(), "native_sample": native_sample(), "containers": containers(),
                      **procs()}))


if __name__ == "__main__":
    main()
