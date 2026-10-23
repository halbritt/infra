#!/usr/bin/env python3
"""hostmon supervisor: one cheap host-monitor agent per fleet host (owner instruction relayed by agent-521, 2026-10-22).

  hostmon.py run HOSTNAME KIND ACCOUNT [--via-ssh SSHHOST]

Deterministic sampling every 60 s (probe.py, no model). The model (Sonnet via claude, or gpt-6-luna via codex) gets a
turn only for new alert transitions, or at most every 5 min when the deterministic digest changed; a quiet host costs
nothing. The model only reads evidence and writes JSON; it gets no write or shell tools. Material alerts go to
outbox.jsonl, which proximal's forwarder (hostmon.py forward) publishes to Cairn. Monitors never kill, restart,
change limits or bypass admission. --via-ssh samples a host remotely with ~1 s probes (agent-ee-gate-c4, so the
monitor never keeps the paid host from its idle shutdown; an unreachable host is UNKNOWN, never woken).
"""
import datetime
import json, os, re, subprocess, sys, time, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE / "probe.py"
MODELS = {"sonnet": "sonnet", "luna": "gpt-6-luna"}
HOMES = {"claude": "~/.claude", "claude-harm": "~/.claude-harm", "codex": "~/.codex", "codex-harm": "~/.codex-harm",
         "codex-3": "~/.codex-3"}
SAMPLE_S, TURN_MIN_S, ROTATE_TURNS = 60, 300, 40
FULL_SUITE_MIN = 200  # modules; the full strict suite is ~277
QUOTA = re.compile(r"quota|usage limit|rate limit|unauthori[sz]ed|401|403|credit|exhausted|log ?in", re.I)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


def sample(via):
    cmd = (["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", via, "python3", "-"] if via
           else [sys.executable, str(PROBE)])
    try:
        r = subprocess.run(cmd, stdin=open(PROBE) if via else subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=45)
        return json.loads(r.stdout) if r.returncode == 0 else {"ts": now(), "error": (r.stderr or "")[-300:]}
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return {"ts": now(), "error": str(e)[:300]}


def _agent_ee(x):
    """Agent-ee test containers only (475: image agent-ee:* or the ae-ci-exec name/label); owner services are out of scope."""
    return x["name"].startswith("ae-ci-exec") or str(x.get("image") or "").startswith("agent-ee:")


def init_ok(x):
    """475: a container is init-protected when HostConfig.Init is true OR PID 1 is tini/docker-init."""
    return bool(x.get("init")) or "init" in str(x.get("pid1")) or "tini" in str(x.get("pid1"))

def conditions(s, host):
    """Deterministic alert conditions {key: text}. A missing probe is UNKNOWN, never healthy."""
    c = {}
    if "error" in s:
        return {"unreachable": f"probe failed: {s['error'][:200]}"}
    psi, io_cap = s.get("psi") or {}, (50 if host == "agent-ee-gate-c4" else 30)  # 475: sustained c4 io > 50 = discard regression
    for k, cap in (("cpu", 50), ("io", io_cap), ("memory", 20)):
        v = psi.get(k)
        if v == "UNKNOWN" or not isinstance(v, dict):
            c[f"psi-{k}-unknown"] = f"PSI {k} UNKNOWN"
        elif v.get("avg60", 0) >= cap:
            c[f"psi-{k}"] = f"PSI {k} avg60 {v['avg60']} >= {cap}"
    m = s.get("mem")
    if isinstance(m, dict):
        if m["avail_mb"] < 0.08 * m["total_mb"]:
            c["mem-low"] = f"MemAvailable {m['avail_mb']} MB of {m['total_mb']}"
        mpsi = (psi.get("memory") or {}).get("avg60", 0) if isinstance(psi.get("memory"), dict) else 0
        # 475 2026-10-22: full swap with memory PSI ~0 is stale pages, normal on proximal; warn only with pressure.
        if m["swap_total_mb"] and m["swap_used_mb"] > 0.9 * m["swap_total_mb"] and mpsi > 10:
            c["swap-full"] = f"swap {m['swap_used_mb']}/{m['swap_total_mb']} MB used"
    else:
        c["mem-unknown"] = "meminfo UNKNOWN"
    for p, d in (s.get("disk") or {}).items():
        if d == "UNKNOWN":
            c[f"disk-unknown:{p}"] = f"disk {p} UNKNOWN"
        elif d["used_pct"] >= 90:
            c[f"disk:{p}"] = f"disk {p} {d['used_pct']}% used, {d['free_gb']} GB free"
    if s.get("zombies", 0) >= 200:
        top = (s.get("zombie_parents") or [{}])[0]
        c[f"zombies:{top.get('ppid')}"] = f"{s['zombies']} zombies; top parent {top}"
    a = s.get("admission")
    if a == "UNKNOWN" or not isinstance(a, dict):
        c["admission-unknown"] = "native-admit status UNKNOWN"
    else:
        if isinstance(a["used"], int) and isinstance(a["budget"], int) and a["used"] > a["budget"]:
            c["admission-over"] = f"admission over budget: {a['status_line']}"
        if isinstance(a["suites"], int) and isinstance(a["suite_cap"], int) and a["suites"] > a["suite_cap"]:
            c["suites-over"] = f"suites over cap: {a['status_line']}"
    ns = s.get("native_sample")
    if ns == "UNKNOWN" or not isinstance(ns, dict) or ns.get("capacity_known") is False:
        c["capacity-unknown"] = "native-admit sample: capacity unknown or unavailable"
    else:
        for l in ns.get("dead_leases") or []:
            c[f"dead-lease:{l.get('id')}"] = f"admission lease {l} listed but its pid is gone"
    if isinstance(ns, dict) and isinstance(ns.get("root_free_gb"), (int, float)) and ns["root_free_gb"] < 10:
        c["root-free-low"] = f"root free {ns['root_free_gb']} GB < 10"
    # Suite counts come from admission leases (475): lanes may call native-admit run directly, so no name grep.
    if len(s.get("suites") or []) > 1:
        c["multi-suite"] = f"{len(s['suites'])} strict_suite processes: " + ", ".join(
            str(x.get("summary")) for x in s["suites"])
    for x in s.get("suites") or []:
        if x.get("summary") and re.search(r"remain|summary2|full2|strict[2-9]|shard|rerun", x["summary"], re.I):
            c[f"suite-relaunch:{x['summary']}"] = f"suite continuation/relaunch: {x}"
    cs = s.get("containers")
    if cs == "UNKNOWN":
        c["containers-unknown"] = "docker ps UNKNOWN"
    for x in cs if isinstance(cs, list) else []:
        if (x.get("started") or "") < "2026-10-22T21:56":
            continue
        # 475: conforming = PID1 comm in {tini, docker-init} AND lease label AND cpus>0 AND pids_limit>0.
        if _agent_ee(x) and not x.get("lease"):
            c[f"no-lease:{x['name']}"] = f"container {x['name']} has no native-admission.lease label"
        if _agent_ee(x) and not init_ok(x):
            c[f"no-init:{x['name']}"] = f"container {x['name']} PID1 {x.get('pid1')} without init ({x.get('image')})"
        if _agent_ee(x) and (not x.get("cpus") or not x.get("pids_limit")):
            c[f"no-limits:{x['name']}"] = f"container {x['name']} cpus={x.get('cpus')} pids_limit={x.get('pids_limit')}"
    return c


def digest(s):
    a = s.get("admission") if isinstance(s.get("admission"), dict) else {}
    return json.dumps({"err": "error" in s, "suites": sorted(str(x.get("summary")) for x in s.get("suites") or []),
                       "containers": sorted(x["name"] for x in s.get("containers") or [] if isinstance(x, dict)),
                       "queued": a.get("queued"), "reserved": a.get("reserved"),
                       "agents": len(s.get("agent_processes") or [])}, sort_keys=True)


def brief(host, via):
    return (HERE / "brief.txt").read_text().replace("{HOST}", host).replace(
        "{WHERE}", f"sampled remotely over ssh from proximal ({via})" if via else "running on the host itself")


def model_turn(st, kind, account, host, via, evidence):
    """One model turn; returns parsed JSON or raises RuntimeError('route: ...') on quota/auth failure."""
    sess = st.get("session")
    first = sess is None or st.get("turns", 0) >= ROTATE_TURNS
    text = (brief(host, via) + "\n\n" if first else "") + "EVIDENCE\n" + json.dumps(evidence)[:60000] + (
        "\n\nReply with ONLY the JSON object described in your brief.")
    env = {k: v for k, v in os.environ.items() if not (k.endswith("_API_KEY") or k in (
        "OPENAI_BASE_URL", "OPENAI_API_BASE", "ANTHROPIC_BASE_URL", "CLAUDECODE", "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CONFIG_DIR", "CODEX_HOME"))}
    env["HERDR_ENV"] = "0"
    work = Path(st["dir"]) / "model"
    work.mkdir(exist_ok=True)
    if kind == "sonnet":
        env["CLAUDE_CONFIG_DIR"] = os.path.expanduser(HOMES[account])
        if first:
            sess = str(uuid.uuid4())
        cmd = ["claude", "--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--model", "sonnet", "--effort", "low", "--print", "--output-format", "json",
               "--disallowedTools", "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Agent,Task",
               *(["--session-id", sess] if first else ["--resume", sess])]
    else:
        env["CODEX_HOME"] = os.path.expanduser(HOMES[account])
        # `codex exec resume` has no --sandbox flag (2026-10-23 failure); the config key works on both paths.
        base = ["--ignore-user-config", "-m", MODELS[kind], "-c", 'model_provider="openai"',
                "-c", 'model_reasoning_effort="low"', "-c", 'sandbox_mode="read-only"', "--skip-git-repo-check",
                "--json"]
        cmd = ["codex", "exec", *base, "-"] if first else ["codex", "exec", "resume", *base, sess, "-"]
    r = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=600, env=env, cwd=work)
    raw = r.stdout
    if kind == "sonnet":
        try:
            o = json.loads(raw)
            out, err = o.get("result", ""), (o.get("result", "") if o.get("is_error") else "")
        except ValueError:
            out, err = "", raw[-400:] + r.stderr[-400:]
    else:
        out, err = "", ""
        for line in raw.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "thread.started" and first:
                sess = e["thread_id"]
            if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message":
                out = e["item"]["text"]
            if e.get("type") in ("turn.failed", "error"):
                err = json.dumps(e)[:400]
        err = err or (r.stderr[-400:] if r.returncode else "")
    if r.returncode or err:
        msg = err or r.stderr[-400:]
        if QUOTA.search(msg):
            raise RuntimeError(f"route {kind}/{account}: {msg[:300]}")
        return {"summary": f"model turn failed (exit {r.returncode}): {msg[:200]}", "send": [],
                "model_failed": f"exit {r.returncode}: {msg[:300]}"}
    st["session"], st["turns"] = sess, (1 if first else st.get("turns", 0) + 1)
    m = re.search(r"\{.*\}", out, re.S)
    try:
        return json.loads(m.group(0)) if m else {"summary": out[:500], "send": []}
    except ValueError:
        return {"summary": out[:500], "send": []}


def run(host, kind, account, via):
    d = Path.home() / ".local" / "state" / "hostmon" / host
    d.mkdir(parents=True, exist_ok=True)
    stf = d / "state.json"
    st = json.loads(stf.read_text()) if stf.exists() else {}
    st.update({"dir": str(d), "host": host, "kind": kind, "account": account, "via": via, "pid": os.getpid(),
               "started": now(), "model": MODELS[kind]})
    active, last_turn, last_digest, events, prev_suites = {}, 0.0, None, [], None
    while True:
        s = sample(via)
        append(d / "samples.jsonl", s)
        cur = conditions(s, host)
        new = {k: v for k, v in cur.items() if k not in active}
        cleared = [k for k in active if k not in cur]
        # Persisting UNKNOWN/unreachable needs two consecutive samples before it counts (one ssh blip is noise).
        for k in list(new):
            if k == "unreachable" or k.endswith("-unknown") or k.startswith("disk-unknown"):
                if st.get("pending_unknown") != k:
                    st["pending_unknown"] = k
                    new.pop(k)
        for k, v in new.items():
            active[k] = {"since": s["ts"], "text": v}
            events.append({"ts": s["ts"], "alert": k, "text": v})
            append(d / "alerts.jsonl", {"ts": s["ts"], "state": "new", "key": k, "text": v})
        for k in cleared:
            events.append({"ts": s["ts"], "cleared": k, "since": active[k]["since"]})
            append(d / "alerts.jsonl", {"ts": s["ts"], "state": "cleared", "key": k})
            active.pop(k)
        suites = {str(x.get("pid")): x.get("summary") for x in s.get("suites") or []}
        if prev_suites is not None:
            for p, summ in prev_suites.items():
                if p not in suites:
                    events.append({"ts": s["ts"], "suite_ended": p, "summary": summ})
            for p, summ in suites.items():
                if p not in prev_suites:
                    events.append({"ts": s["ts"], "suite_started": p, "summary": summ})
        if "error" not in s:
            prev_suites = suites
        dg = digest(s)
        due = bool(new) or (dg != last_digest and time.time() - last_turn >= TURN_MIN_S and last_digest is not None)
        if last_digest is None:
            due = True  # first snapshot
        last_digest = dg if due or last_digest is None else last_digest
        if due:
            try:
                res = model_turn(st, kind, account, host, via, {"host": host, "sample": s, "suite_module_counts": [x.get("modules") for x in s.get("suites") or [] if isinstance(x, dict)],
                    "full_suite_threshold_modules": FULL_SUITE_MIN, "init_ok_containers": sorted(
                    x.get("name") for x in s.get("containers") or [] if isinstance(x, dict) and init_ok(x)), "active_alerts": active,
                                                                "new_alerts": new, "events_since_last_turn": events})
            except RuntimeError as e:
                append(d / "outbox.jsonl", {"ts": now(), "host": host, "severity": "warning", "to": ["449"],
                                            "key": "route-unavailable", "text": f"hostmon-{host} STOPPED: {e}"})
                st["stopped"] = str(e)
                stf.write_text(json.dumps(st, indent=1))
                return 3
            last_turn, last_digest, events = time.time(), dg, []
            append(d / "summaries.jsonl", {"ts": s["ts"], "summary": res.get("summary", "")[:2000]})
            # Monitor health is deterministic and independent of the model: a failed model turn raises one
            # deduplicated warning to 449; the first successful turn afterwards sends the clearance.
            if res.get("model_failed"):
                if not st.get("model_failing"):
                    st["model_failing"] = {"since": s["ts"], "error": res["model_failed"]}
                    append(d / "outbox.jsonl", {"ts": now(), "host": host, "severity": "warning", "to": ["449"],
                                                "key": "monitor-model-failed",
                                                "text": f"hostmon-{host} model turn FAILED ({kind}/{account}): "
                                                        f"{res['model_failed']}. Deterministic sampling continues; "
                                                        "model summaries are unavailable until a turn succeeds."})
            elif st.get("model_failing"):
                append(d / "outbox.jsonl", {"ts": now(), "host": host, "severity": "info", "to": ["449"],
                                            "key": "monitor-model-recovered",
                                            "text": f"hostmon-{host} model turns recovered ({kind}/{account}); "
                                                    f"failing since {st['model_failing']['since']}."})
                st.pop("model_failing")
            cs_ = [x for x in s.get("containers") or [] if isinstance(x, dict) and _agent_ee(x)]
            all_init_ok = isinstance(s.get("containers"), list) and all(init_ok(x) for x in cs_)
            # A full strict suite is ~277 modules (or no module list); a focused lane run of tens of modules is normal.
            full = [x for x in s.get("suites") or [] if isinstance(x, dict)
                    and not (isinstance(x.get("modules"), int) and x["modules"] < FULL_SUITE_MIN)]
            for m in res.get("send") or []:
                # The deterministic full-suite check is authoritative (peecee ee387 14-module false positive).
                if "full-suite" in str(m.get("key")).lower() and not full:
                    continue
                # The deterministic init check is authoritative (talos 6e798876, peecee 4467ee6e false positives):
                # a model init claim is dropped while every agent-ee container is init-protected.
                if "init" in str(m.get("key")).lower() and all_init_ok:
                    continue
                if m.get("key") and m.get("text"):
                    append(d / "outbox.jsonl", {"ts": now(), "host": host, **{k: m.get(k) for k in
                                                ("severity", "to", "key", "text")}})
        st["last_sample"], st["active_alerts"] = s["ts"], active
        stf.write_text(json.dumps(st, indent=1))
        time.sleep(SAMPLE_S)


def capacity(hosts, sd, state):
    """Deterministic, model-free: the latest sample of every monitor -> capacity.json, plus one deduplicated
    idle-host/queued-work alert (and its clearance) in proximal's outbox, and a stale-monitor alert when a host's
    newest sample is older than 5 minutes. Eligibility (KiCad lane hosts, staged evidence) is NOT known here; the
    alert names candidate hosts for the dispatcher to check."""
    snap, now_s = {}, time.time()
    for host, ssh in hosts.items():
        path = f"~/.local/state/hostmon/{host}/samples.jsonl"
        cmd = ["bash", "-c", f"tail -n1 {path} 2>/dev/null"] if ssh is None else [
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", ssh, f"tail -n1 {path} 2>/dev/null"]
        try:
            line = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
            smp = json.loads(line) if line else {}
        except (OSError, subprocess.SubprocessError, ValueError):
            smp = {}
        # Probes report admission="UNKNOWN" (a string) when unreadable: keep it unknown (free=null), never idle.
        adm = smp.get("admission") if isinstance(smp.get("admission"), dict) else {}
        try:
            age = now_s - datetime.datetime.fromisoformat(smp["ts"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError, TypeError):
            age = None
        free = (adm.get("budget") - adm.get("used")) if isinstance(adm.get("budget"), int) and isinstance(
            adm.get("used"), int) else None
        snap[host] = {"ts": smp.get("ts"), "age_s": None if age is None else int(age), "free_units": free,
                      "suites": adm.get("suites"), "suite_cap": adm.get("suite_cap"), "queued": adm.get("queued"),
                      "load1": (smp.get("load") or [None])[0] if isinstance(smp.get("load"), list) else smp.get("load")}
    tmp = sd / "capacity.json.tmp"
    tmp.write_text(json.dumps({"ts": now(), "hosts": snap}, indent=1))
    os.replace(tmp, sd / "capacity.json")
    out = sd / "proximal" / "outbox.jsonl"
    alerts = {}
    for h, v in snap.items():
        if v["age_s"] is None or v["age_s"] > 300:
            alerts[f"monitor-stale-{h}"] = f"hostmon-{h}: newest sample {v['ts']} is stale or missing; the host's " \
                                          "capacity is UNKNOWN to dispatch."
    waiting = {h: v for h, v in snap.items() if (v["queued"] or 0) > 0}
    idle = [h for h, v in snap.items() if (v["free_units"] or 0) > 0 and (v["queued"] or 0) == 0
            and v["age_s"] is not None and v["age_s"] <= 300]
    # Persistence: a lane's affected-test run briefly queued behind its own host's suite slot is normal (the worker
    # is bound to that host's worktree); raise only after the condition holds for 3 consecutive loops (~3 min).
    state["idle_streak"] = state.get("idle_streak", 0) + 1 if (waiting and idle) else 0
    if waiting and idle and state["idle_streak"] >= 3:
        alerts["idle-host-queued-work"] = (
            "Queued native work while qualified-capacity candidates are idle: queued "
            + ", ".join(f"{h}={v['queued']}" for h, v in waiting.items()) + "; free "
            + ", ".join(f"{h}={snap[h]['free_units']}u" for h in idle)
            + ". Dispatcher: check each queued job's eligibility (KiCad lane hosts, staged evidence) and move or "
              "launch on a free host; record any concrete incompatibility.")
    seen = state.setdefault("capacity_alerts", {})
    for k, text in alerts.items():
        if k not in seen:
            seen[k] = now()
            append(out, {"ts": now(), "host": "proximal", "severity": "warning", "to": ["449"], "key": k, "text": text})
    for k in [k for k in seen if k not in alerts and not (k == "idle-host-queued-work" and waiting and idle)]:
        append(out, {"ts": now(), "host": "proximal", "severity": "info", "to": ["449"], "key": k + "-cleared",
                     "text": f"cleared: {k} (raised {seen.pop(k)})"})


def forward(hosts):
    """proximal: publish new outbox lines from every monitor to Cairn (449; 475 when addressed; 521 when critical).
    Durable and idempotent (agent-521 follow-up 2026-10-22): each outbox line gets persisted request IDs for its
    record and for every recipient; a step counts only on a confirmed ok JSON reply; a failure retries the SAME IDs
    and arguments next round; the host offset advances only after every recipient is confirmed."""
    ids = {"449": "7e1258f7-63a0-4184-a1d9-4ae9c6bbf7aa", "475": "36dbce71-5f29-4cc3-ae5a-a80798f08a98",
           "521": "eb30524a-ca5a-484e-ab30-0ba31380a133"}
    tok, sock = os.path.expanduser("~/.local/share/cairn/hosted-agent.token"), os.path.expanduser(
        "~/.local/share/cairn/api.sock")
    sd = Path.home() / ".local" / "state" / "hostmon"
    offs_f, pend_f = sd / "forward-offsets.json", sd / "forward-pending.json"
    offs = json.loads(offs_f.read_text()) if offs_f.exists() else {}
    pend = json.loads(pend_f.read_text()) if pend_f.exists() else {}

    def save():
        for f, v in ((pend_f, pend), (offs_f, offs)):
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(v, indent=1))
            os.replace(tmp, f)

    def ok(r):
        try:
            return r.returncode == 0 and json.loads(r.stdout).get("ok") is True
        except ValueError:
            return False

    while True:
        for host, ssh in hosts.items():
            path = f"~/.local/state/hostmon/{host}/outbox.jsonl"
            cmd = ["bash", "-c", f"cat {path} 2>/dev/null"] if ssh is None else [
                "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", ssh, f"cat {path} 2>/dev/null"]
            try:
                lines = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.splitlines()
            except (OSError, subprocess.SubprocessError):
                continue
            while offs.get(host, 0) < len(lines):
                i = offs.get(host, 0)
                key = f"{host}#{i}"
                try:
                    m = json.loads(lines[i])
                except ValueError:
                    offs[host] = i + 1  # an unparseable line can never publish; skip it, recorded in pending
                    pend[key] = {"skipped": "unparseable"}
                    save()
                    continue
                to = {str(t).replace("agent-", "") for t in (m.get("to") or ["449"])} | {"449"}
                if m.get("severity") == "critical":
                    to |= {"475", "521"}
                p = pend.setdefault(key, {"rec_req": str(uuid.uuid4()),
                                          "pubs": {t: {"req": str(uuid.uuid4()), "ok": False} for t in sorted(to) if t in ids}})
                save()
                if not p.get("rid"):
                    body = (f"hostmon-{host} {m.get('severity', 'warning').upper()} [{m.get('key')}] {m.get('ts')}\n"
                            f"{m.get('text')}\n(read-only host monitor; evidence ~/.local/state/hostmon/{host}/ on "
                            f"{'proximal' if ssh is None else ssh}; no action taken by the monitor)")
                    r = subprocess.run(["cairn", "agent", "--socket", sock, "--token-file", tok, "remember", "--repo",
                                        str(Path.home() / "git" / "cairn"), "--task", f"coordination/hostmon-{host}",
                                        "--request-id", p["rec_req"], "--shareable", "--stdin"], input=body,
                                       capture_output=True, text=True)
                    if not ok(r):
                        break  # retry the same request ID next round
                    p["rid"] = json.loads(r.stdout)["data"]["record_id"]
                    save()
                for t, pub in p["pubs"].items():
                    if pub["ok"]:
                        continue
                    r = subprocess.run(["cairn", "agent", "--token-file", tok, "--socket", sock, "--agent-id", ids["449"],
                                        "--execution-id", os.environ.get("HOSTMON_EXECUTION_ID", ""), "publish",
                                        "--request-id", pub["req"], "--to", f"agent/{ids[t]}", "--kind", "notice",
                                        "--version", "1", p["rid"]], capture_output=True, text=True)
                    pub["ok"] = ok(r)
                    if not pub["ok"]:
                        pub["last_error"] = (r.stdout + r.stderr)[-300:]
                    save()
                if not all(pub["ok"] for pub in p["pubs"].values()):
                    break  # keep the offset; retry identical IDs next round
                p["done"] = now()
                offs[host] = i + 1
                save()
        try:
            cst_f = sd / "capacity-state.json"
            cst = json.loads(cst_f.read_text()) if cst_f.exists() else {}
            capacity(hosts, sd, cst)
            cst_f.write_text(json.dumps(cst, indent=1))
        except Exception as e:  # the forwarder must keep forwarding even if aggregation breaks
            append(sd / "proximal" / "forwarder-errors.jsonl", {"ts": now(), "capacity_error": repr(e)[:300]})
        time.sleep(60)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["run"]:
        via = a[a.index("--via-ssh") + 1] if "--via-ssh" in a else None
        sys.exit(run(a[1], a[2], a[3], via))
    if a[:1] == ["forward"]:
        forward(json.loads(a[1]))
    sys.exit(__doc__)
