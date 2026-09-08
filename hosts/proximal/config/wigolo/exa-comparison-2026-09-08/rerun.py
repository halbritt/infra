#!/usr/bin/env python3
"""Re-run wigolo (only) for queries where DuckDuckGo returned 0, after DDG's challenge clears; re-judge against stored Exa results."""
import json, os, sys, time, random, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run
S = run.S
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

def ddg_clear():
    req = urllib.request.Request("https://html.duckduckgo.com/html/?q=sqlite+vec0", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode(errors="replace")
            return r.status == 200 and "result__a" in body and "anomaly" not in body
    except Exception as e:
        print(f"probe error {e}", file=sys.stderr); return False

t0 = time.time()
while not ddg_clear():
    if time.time() - t0 > 1800: print("DDG still challenged after 30 min; running anyway", file=sys.stderr); break
    print(f"DDG still challenged, waiting ({int(time.time()-t0)}s)", file=sys.stderr, flush=True); time.sleep(60)
print("DDG clear; starting rerun", file=sys.stderr, flush=True)

rows = json.load(open(f"{S}/results-search.json"))
targets = [r for r in rows if any(t["name"] == "duckduckgo" and not t["n"] for t in r["wigolo"].get("engines") or [])]
print(f"rerunning {len(targets)} queries", file=sys.stderr, flush=True)
out = []
for r in targets:
    q = r["q"]; print(f"== {q}", file=sys.stderr, flush=True)
    w = run.wig_search(q)
    pool, seen = [], {}
    for tool, rr in (("wigolo", w), ("exa", r["exa"]), ("exa_news", r.get("exa_news"))):
        if not rr: continue
        for it in rr["results"][:5]:
            k = run.norm(it["url"])
            if k not in seen: seen[k] = len(pool); pool.append(dict(it))
    random.seed(hash(q) & 0xffff); order = list(range(len(pool))); random.shuffle(order)
    shuffled = [pool[i] for i in order]
    grades, jerr = run.judge(q, shuffled) if shuffled else ([], None)
    if grades:
        gmap = {run.norm(shuffled[i]["url"]): grades[i] for i in range(len(shuffled))}
        for tool, rr in (("wigolo", w), ("exa", r["exa"]), ("exa_news", r.get("exa_news"))):
            if not rr: continue
            top = [gmap.get(run.norm(it["url"]), 0) for it in rr["results"][:5]]
            ideal = sorted(top, reverse=True)
            rr["grades@5"] = top; rr["ndcg@5"] = round(run.dcg(top) / run.dcg(ideal), 3) if run.dcg(ideal) else 0.0
            rr["p@5"] = round(sum(1 for g in top if g >= 2) / 5, 2); rr["top1"] = top[0] if top else None
    ddg = [t["n"] for t in w.get("engines") or [] if t["name"] == "duckduckgo"]
    out.append({"cat": r["cat"], "q": q, "wigolo_before": r["wigolo"].get("ndcg@5"), "wigolo_after": w.get("ndcg@5"),
                "exa": r["exa"].get("ndcg@5"), "ddg_n_after": ddg[0] if ddg else None, "wigolo": w, "judge_error": jerr})
    json.dump(out, open(f"{S}/results-rerun.json", "w"), indent=1)
    time.sleep(20)
print("done", file=sys.stderr)
