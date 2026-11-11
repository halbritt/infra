#!/usr/bin/env python3
"""wigolo vs Exa comparison harness. Sequential; never exceeds 1 QPS to Exa."""
import json, os, sys, time, random, urllib.request, urllib.error
S = os.path.dirname(os.path.abspath(__file__))
EXA_KEY = os.environ["EXA_API_KEY"]
WIG = "http://127.0.0.1:3333"
N = 10

def post(url, body, headers=None, timeout=120):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
        headers={"Content-Type": "application/json", **(headers or {})})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode())
        return out, round((time.time()-t0)*1000), None
    except urllib.error.HTTPError as e:
        return None, round((time.time()-t0)*1000), f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
    except Exception as e:
        return None, round((time.time()-t0)*1000), f"{type(e).__name__}: {e}"

def exa_search(q, category=None):
    body = {"query": q, "type": "auto", "numResults": N, "contents": {"highlights": True}}
    if category: body["category"] = category
    out, ms, err = post("https://api.exa.ai/search", body, {"x-api-key": EXA_KEY})
    if err: return {"error": err, "ms": ms, "results": []}
    res = []
    for r in out.get("results", []):
        hl = r.get("highlights") or []
        res.append({"title": r.get("title"), "url": r.get("url"), "published": r.get("publishedDate"),
                    "snippet": (hl[0] if hl else "")[:600]})
    return {"ms": ms, "cost": (out.get("costDollars") or {}).get("total"), "results": res,
            "resolved_type": out.get("resolvedSearchType")}

def wig_search(q):
    body = {"query": q, "max_results": N, "force_refresh": True, "include_content": True}
    out, ms, err = post(f"{WIG}/v1/search", body, timeout=180)
    if err: return {"error": err, "ms": ms, "results": []}
    ev = {}
    for e in out.get("evidence") or []:
        u = e.get("url") or e.get("source_url")
        if u and u not in ev: ev[u] = e.get("excerpt") or e.get("text") or e.get("snippet") or ""
    res = []
    for r in out.get("results", []):
        snip = r.get("excerpt") or r.get("snippet") or r.get("summary") or ev.get(r.get("url"), "") or ""
        res.append({"title": r.get("title"), "url": r.get("url"), "published": r.get("published_date"),
                    "snippet": snip[:600], "score": (r.get("evidence_score") or {}).get("final"),
                    "junk": r.get("is_junk") or r.get("junk")})
    tel = [{"name": t.get("name"), "outcome": t.get("outcome"), "n": t.get("result_count")} for t in out.get("engine_telemetry") or []]
    return {"ms": ms, "server_ms": out.get("total_time_ms"), "results": res, "engines": tel,
            "warnings": out.get("engine_warnings")}

def judge(q, items):
    """items: list of {title,url,snippet}. Returns list of 0-3 grades (same order)."""
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"[{i}] title: {it.get('title') or ''}\n    url: {it.get('url')}\n    snippet: {(it.get('snippet') or '')[:400]}")
    prompt = ("You grade web search results for relevance to a query. Grades: 3 = directly answers/covers the query, "
              "authoritative; 2 = relevant and useful; 1 = marginally related; 0 = irrelevant, spam, or wrong topic. "
              "Judge from title, url and snippet only. Today is 2026-09-08; for queries about current or recent things, "
              "prefer up-to-date pages.\n\n"
              f"Query: {q}\n\nResults:\n" + "\n".join(lines) +
              f"\n\nReturn ONLY a JSON object mapping each result number (1..{len(items)}) to its grade, e.g. {{\"1\":2,\"2\":0}}.")
    body = {"model": "qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "max_tokens": 400,
            "temperature": 0.0, "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_object"}}
    out, ms, err = post("http://localhost:8081/v1/chat/completions", body, timeout=300)
    if err: return None, err
    txt = out["choices"][0]["message"]["content"].strip()
    try:
        g = json.loads(txt)
        return [int(g.get(str(i), 0)) for i in range(1, len(items)+1)], None
    except Exception as e:
        return None, f"bad judge json: {txt[:200]}"

def dcg(grades):
    import math
    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades))

def norm(u):
    u = (u or "").lower().rstrip("/")
    for p in ("https://", "http://", "www."):
        if u.startswith(p): u = u[len(p):]
    return u

def main():
    qs = json.load(open(f"{S}/queries.json"))
    rows = []
    for cat, qlist in qs.items():
        for q in qlist:
            print(f"== [{cat}] {q}", file=sys.stderr, flush=True)
            w = wig_search(q)
            e = exa_search(q)
            en = exa_search(q, "news") if cat == "news" else None
            time.sleep(0.3)
            row = {"cat": cat, "q": q, "wigolo": w, "exa": e, "exa_news": en}
            # pooled blind judging
            pool, seen = [], {}
            for tool, r in (("wigolo", w), ("exa", e), ("exa_news", en)):
                if not r: continue
                for it in r["results"][:5]:
                    k = norm(it["url"])
                    if k not in seen:
                        seen[k] = len(pool); pool.append(dict(it))
            random.seed(hash(q) & 0xffff); order = list(range(len(pool))); random.shuffle(order)
            shuffled = [pool[i] for i in order]
            grades, jerr = judge(q, shuffled) if shuffled else ([], None)
            if grades:
                gmap = {norm(shuffled[i]["url"]): grades[i] for i in range(len(shuffled))}
                for tool, r in (("wigolo", w), ("exa", e), ("exa_news", en)):
                    if not r: continue
                    top = [gmap.get(norm(it["url"]), 0) for it in r["results"][:5]]
                    ideal = sorted(top, reverse=True)
                    r["grades@5"] = top
                    r["ndcg@5"] = round(dcg(top) / dcg(ideal), 3) if dcg(ideal) else 0.0
                    r["p@5"] = round(sum(1 for g in top if g >= 2) / 5, 2)
                    r["top1"] = top[0] if top else None
            row["judge_error"] = jerr
            wu = {norm(x["url"]) for x in w["results"]}; eu = {norm(x["url"]) for x in e["results"]}
            row["overlap@10"] = len(wu & eu)
            rows.append(row)
            json.dump(rows, open(f"{S}/results-search.json", "w"), indent=1)
    # fetch leg
    frows = []
    for u in open(f"{S}/fetch-urls.txt").read().split():
        print(f"== fetch {u}", file=sys.stderr, flush=True)
        wo, wms, werr = post(f"{WIG}/v1/fetch", {"url": u, "force_refresh": True, "max_content_chars": 200000}, timeout=180)
        eo, ems, eerr = post("https://api.exa.ai/contents", {"urls": [u], "text": {"maxCharacters": 200000}}, {"x-api-key": EXA_KEY})
        er = (eo or {}).get("results") or []
        est = (eo or {}).get("statuses") or []
        frows.append({"url": u,
            "wigolo": {"ms": wms, "err": werr, "chars": len((wo or {}).get("markdown") or ""), "title": (wo or {}).get("title"),
                       "method": (wo or {}).get("fetch_method"), "http": (wo or {}).get("http_status"),
                       "failed": (wo or {}).get("fetch_failed"), "completeness": (wo or {}).get("content_completeness")},
            "exa": {"ms": ems, "err": eerr, "chars": len((er[0].get("text") or "")) if er else 0,
                    "title": er[0].get("title") if er else None, "status": est[0] if est else None,
                    "cost": ((eo or {}).get("costDollars") or {}).get("total")}})
        json.dump(frows, open(f"{S}/results-fetch.json", "w"), indent=1)
        time.sleep(0.3)
    print("done", file=sys.stderr)

if __name__ == "__main__":
    main()
