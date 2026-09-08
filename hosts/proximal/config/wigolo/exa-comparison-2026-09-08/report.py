#!/usr/bin/env python3
import json, os, statistics as st
S = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(f"{S}/results-search.json"))
fr = json.load(open(f"{S}/results-fetch.json")) if os.path.exists(f"{S}/results-fetch.json") else []

def agg(sel, key):
    v = [r[sel][key] for r in rows if r.get(sel) and key in r[sel]]
    return (round(st.mean(v), 3) if v else None), len(v)

def med(sel, key):
    v = [r[sel][key] for r in rows if r.get(sel) and r[sel].get(key) is not None]
    return round(st.median(v)) if v else None

print("# wigolo vs Exa — search leg\n")
print(f"queries: {len(rows)}  judge failures: {sum(1 for r in rows if r.get('judge_error'))}\n")
print("| metric | wigolo | exa (auto) | exa (news cat, news set only) |")
print("|---|---|---|---|")
for label, key in (("nDCG@5 (mean)", "ndcg@5"), ("P@5 grade≥2 (mean)", "p@5")):
    a, na = agg("wigolo", key); b, nb = agg("exa", key); c, nc = agg("exa_news", key)
    print(f"| {label} | {a} | {b} | {c} (n={nc}) |")
t1 = lambda sel: round(st.mean([r[sel]["top1"] for r in rows if r.get(sel) and r[sel].get("top1") is not None]), 2)
print(f"| top-1 grade (mean, 0–3) | {t1('wigolo')} | {t1('exa')} | {t1('exa_news')} |")
print(f"| median latency ms | {med('wigolo','ms')} | {med('exa','ms')} | {med('exa_news','ms')} |")
nres = lambda sel: round(st.mean([len(r[sel]["results"]) for r in rows if r.get(sel)]), 1)
print(f"| results returned (mean of 10 asked) | {nres('wigolo')} | {nres('exa')} | {nres('exa_news')} |")
empt = lambda sel: sum(1 for r in rows if r.get(sel) and len(r[sel]["results"]) == 0)
print(f"| empty result sets | {empt('wigolo')} | {empt('exa')} | {empt('exa_news')} |")
errs = lambda sel: sum(1 for r in rows if r.get(sel) and r[sel].get("error"))
print(f"| errors | {errs('wigolo')} | {errs('exa')} | {errs('exa_news')} |")
pub = lambda sel: round(st.mean([sum(1 for x in r[sel]["results"] if x.get("published")) / max(1, len(r[sel]["results"])) for r in rows if r.get(sel) and r[sel]["results"]]), 2)
print(f"| share of results with a published date | {pub('wigolo')} | {pub('exa')} | {pub('exa_news')} |")
cost = sum((r["exa"].get("cost") or 0) + ((r.get("exa_news") or {}).get("cost") or 0) for r in rows)
print(f"| Exa spend this leg | – | ${cost:.3f} | |")
print(f"\nmean URL overlap in top-10: {round(st.mean([r['overlap@10'] for r in rows]),2)}\n")

print("## Per-category nDCG@5\n")
print("| category | n | wigolo | exa | exa news |")
print("|---|---|---|---|---|")
for cat in dict.fromkeys(r["cat"] for r in rows):
    rs = [r for r in rows if r["cat"] == cat]
    m = lambda sel: round(st.mean([r[sel]["ndcg@5"] for r in rs if r.get(sel) and "ndcg@5" in r[sel]]), 3) if any(r.get(sel) and "ndcg@5" in r[sel] for r in rs) else "–"
    print(f"| {cat} | {len(rs)} | {m('wigolo')} | {m('exa')} | {m('exa_news')} |")

print("\n## Wins by query (nDCG@5; tie within 0.05)\n")
w = e = t = 0
print("| cat | query | wigolo | exa | winner |")
print("|---|---|---|---|---|")
for r in rows:
    a = r["wigolo"].get("ndcg@5"); b = r["exa"].get("ndcg@5")
    if a is None or b is None: continue
    win = "tie" if abs(a-b) <= 0.05 else ("wigolo" if a > b else "exa")
    w += win == "wigolo"; e += win == "exa"; t += win == "tie"
    print(f"| {r['cat']} | {r['q'][:60]} | {a} | {b} | {win} |")
print(f"\nwigolo {w} · exa {e} · tie {t}\n")

print("## wigolo engine telemetry\n")
from collections import Counter
c = Counter(); n = Counter()
for r in rows:
    for t_ in r["wigolo"].get("engines") or []:
        c[(t_["name"], t_["outcome"])] += 1; n[t_["name"]] += t_["n"] or 0
print("| engine | ok | error/other | total results |")
print("|---|---|---|---|")
for eng in sorted({k[0] for k in c}):
    ok = c[(eng, "ok")]; other = sum(v for k, v in c.items() if k[0] == eng and k[1] != "ok")
    print(f"| {eng} | {ok} | {other} | {n[eng]} |")

if fr:
    print("\n# fetch leg\n")
    print("| url | wigolo ms | wigolo chars | wigolo status | exa ms | exa chars | exa status |")
    print("|---|---|---|---|---|---|---|")
    for f in fr:
        wst = f["wigolo"]["err"] or f["wigolo"]["failed"] or f["wigolo"]["method"] or "ok"
        es = f["exa"]["status"] or {}
        est = f["exa"]["err"] or (es.get("status") if isinstance(es, dict) else es) or "ok"
        if isinstance(es, dict) and es.get("error"): est = f"{es.get('status')} {es['error'].get('tag') or es['error']}"[:40]
        print(f"| {f['url'][:70]} | {f['wigolo']['ms']} | {f['wigolo']['chars']} | {str(wst)[:30]} | {f['exa']['ms']} | {f['exa']['chars']} | {str(est)[:40]} |")
    fc = sum((f["exa"].get("cost") or 0) for f in fr)
    print(f"\nExa spend this leg: ${fc:.3f}")
