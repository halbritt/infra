"""Persistent fact identity and conservative review transitions; no messaging API."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone

SILENT = "[SILENT]"
CRITERIA = {
    "C1": "High-consequence pathogen confirmed",
    "C2": "Event-linked spread confirmed",
    "C3": "Risk escalation confirmed",
    "C4": "Event-linked uncontrolled disease",
    "C5": "Event-specific offensive-program evidence",
    "C6": "Containment failure supported by evidence",
    "close": "Watch closed without notification",
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def text(value, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("missing or oversized text")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError("control character in text")
    return value.strip()


def json_object(raw):
    # One complete object; commentary or multiple JSON objects cannot clear a gate.
    raw = raw.strip()
    if raw.startswith("```json\n") and raw.endswith("\n```"):
        raw = raw[8:-4]
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("expected an object")
    return value


def candidate(value, today):
    if not isinstance(value, dict):
        raise ValueError("invalid candidate")
    criterion = value.get("criterion")
    if criterion not in CRITERIA and criterion is not None:
        raise ValueError("unknown criterion")
    ident = value.get("identity")
    if not isinstance(ident, dict) or set(ident) != {"subject", "predicate", "object"}:
        raise ValueError("identity needs subject, predicate, object")
    # Publication metadata never enters this identity. Event/case IDs belong in
    # subject; substantive changes belong in predicate/object. Review checks aliases.
    ident = {k: " ".join(text(v, 200).casefold().split()) for k, v in ident.items()}
    fact_id = "fact-" + hashlib.sha256(canonical(ident).encode()).hexdigest()[:24]
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 3:
        raise ValueError("one to three source records required")
    sources = []
    for e in evidence:
        if not isinstance(e, dict):
            raise ValueError("invalid source record")
        published = date.fromisoformat(text(e.get("published_at"), 10))
        if published > today:
            raise ValueError("future publication")
        sources.append(
            {
                k: text(e.get(k), limit)
                for k, limit in [
                    ("url", 2000),
                    ("quote", 3000),
                    ("publisher", 200),
                    ("primary_origin", 400),
                    ("provenance", 1000),
                ]
            }
            | {"published_at": published.isoformat()}
        )
    result = {
        "fact_id": fact_id,
        "identity": ident,
        "fact": text(value.get("fact")),
        "criterion": criterion,
        "evidence": sources,
    }
    if criterion == "close":
        c = value.get("closure")
        if not isinstance(c, dict) or c.get("result") not in {"negative", "non-plague"}:
            raise ValueError("closure requires negative/non-plague result")
        days = c.get("window_days")
        if type(days) is not int or not 1 <= days <= 365:
            raise ValueError("invalid evidence-backed observation window")
        anchor = date.fromisoformat(text(c.get("last_exposure_date"), 10))
        if c.get("no_new_cases") is not True or today < anchor + timedelta(days=days):
            raise ValueError("closure window not satisfied")
        result["closure"] = {
            "result": c["result"],
            "window_days": days,
            "last_exposure_date": anchor.isoformat(),
            "no_new_cases": True,
        }
    return result


class Store:
    """One SQLite owner; caller holds the run lock across scan, review and claim."""

    def __init__(self, path):
        self.path = path
        # Missing state is an error, never permission to recreate an empty ledger.
        self.db = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")

    def close(self):
        self.db.close()

    @classmethod
    def initialize(cls, path, legacy):
        if path.exists():
            raise FileExistsError(path)
        if legacy.get("schema") != "outbreak-watch/ledger/1":
            raise ValueError("unknown legacy ledger")
        # Validate the complete import before creating authoritative state.
        entries = legacy["entries"]
        if not isinstance(entries, list) or len({e["key"] for e in entries}) != len(
            entries
        ):
            raise ValueError("invalid legacy ledger")
        for e in entries:
            text(e["fact"])
            if e["status"] not in {"seen", "suppressed", "fired", "closed"}:
                raise ValueError(
                    "legacy pending entries require an evidence-preserving migration"
                )
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("""
                PRAGMA synchronous=FULL;
                CREATE TABLE watch (id INTEGER PRIMARY KEY CHECK(id=1), state TEXT NOT NULL);
                CREATE TABLE facts (id TEXT PRIMARY KEY, identity TEXT UNIQUE,
                    status TEXT NOT NULL, payload TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '');
                CREATE TABLE publications (fact_id TEXT NOT NULL, record TEXT NOT NULL,
                    UNIQUE(fact_id, record));
                CREATE TABLE alerts (fact_id TEXT PRIMARY KEY REFERENCES facts(id),
                    claimed_at TEXT NOT NULL, body TEXT NOT NULL);
                INSERT INTO watch VALUES (1, 'active');
            """)
            for e in entries:
                db.execute(
                    "INSERT INTO facts VALUES (?,NULL,?,?,?)",
                    (
                        "legacy-" + e["key"],
                        e["status"],
                        canonical(e),
                        "legacy import; do not reopen",
                    ),
                )
            if any(e["status"] == "closed" for e in entries):
                db.execute("UPDATE watch SET state='closed'")

    def closed(self):
        row = self.db.execute("SELECT state FROM watch WHERE id=1").fetchone()
        if row is None or row[0] not in {"active", "closed"}:
            raise ValueError("invalid watch state")
        return row[0] == "closed"

    def registry(self):
        return [
            {
                "id": r["id"],
                "status": r["status"],
                "fact": json.loads(r["payload"])["fact"],
                "identity": json.loads(r["identity"]) if r["identity"] else None,
            }
            for r in self.db.execute("SELECT * FROM facts ORDER BY id")
        ]

    def pending(self):
        return [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT payload FROM facts WHERE status='pending-review' ORDER BY rowid LIMIT 4"
            )
        ]

    def register(self, item):
        status = "seen" if item["criterion"] is None else "pending-review"
        with self.db:
            changed = self.db.execute(
                "INSERT OR IGNORE INTO facts(id,identity,status,payload) VALUES (?,?,?,?)",
                (item["fact_id"], canonical(item["identity"]), status, canonical(item)),
            ).rowcount
            if not changed and item["criterion"] is not None:
                self.db.execute(
                    "UPDATE facts SET payload=? WHERE id=? AND status='pending-review'",
                    (canonical(item), item["fact_id"]),
                )
            for source in item["evidence"]:
                self.db.execute(
                    "INSERT OR IGNORE INTO publications VALUES (?,?)",
                    (item["fact_id"], canonical(source)),
                )
        return bool(changed)

    def transition(self, item, status, reason):
        with self.db:
            self.db.execute(
                "UPDATE facts SET status=?, reason=? WHERE id=? AND status='pending-review'",
                (status, reason, item["fact_id"]),
            )

    def claim(self, item, body):
        # Commit before stdout/delivery. A crash after commit loses an alert; it
        # never authorizes replay. This is the requester's chosen tradeoff.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.closed():
                return False
            r = self.db.execute(
                "SELECT status FROM facts WHERE id=?", (item["fact_id"],)
            ).fetchone()
            if r is None or r[0] != "pending-review":
                return False
            self.db.execute(
                "INSERT INTO alerts VALUES (?,?,?)",
                (item["fact_id"], datetime.now(timezone.utc).isoformat(), body),
            )
            self.db.execute(
                "UPDATE facts SET status=? WHERE id=?",
                (
                    "closed" if item["criterion"] == "close" else "fired",
                    item["fact_id"],
                ),
            )
            if item["criterion"] == "close":
                self.db.execute("UPDATE watch SET state='closed' WHERE id=1")
        return True


def evidence_verified(item, grounding):
    if grounding.get("status") != "completed":
        return False
    pages = {
        s["url"]: s
        for s in grounding.get("sources", [])
        if s.get("kind") == "page_excerpt"
        and s.get("document_sha256")
        and s.get("retrieved_at")
    }
    return all(
        e["url"] in pages and e["quote"] in pages[e["url"]]["text"]
        for e in item["evidence"]
    )


def verdict(result, expected_members):
    if result.get("status") != "completed":
        return "pending-review", "partial/unavailable panel", []
    opinions = result.get("opinions", [])
    synthesis = result.get("synthesis", {})
    if (
        len(opinions) != len(expected_members)
        or {r.get("member") for r in opinions} != set(expected_members)
        or any(r.get("status") != "completed" for r in opinions)
        or synthesis.get("status") != "completed"
        or synthesis.get("validation") != "quotes_verified_not_claim_truth"
    ):
        return "pending-review", "missing member or verified synthesis", []
    try:
        votes = [json_object(r["advice"]) for r in opinions]
        for v in votes:
            if v.get("verdict") not in {"supported", "refuted", "unresolved"}:
                raise ValueError("invalid verdict")
            if any(
                type(v.get(k)) is not bool
                for k in ("source_support", "criterion_support", "novel")
            ):
                raise ValueError("invalid support fields")
            if not isinstance(v.get("duplicate_ids"), list) or any(
                not isinstance(x, str) for x in v["duplicate_ids"]
            ):
                raise ValueError("invalid duplicates")
            text(v.get("reason"), 6000)
            text(v.get("falsifier"))
    except (ValueError, KeyError, TypeError):
        return "pending-review", "unparseable panel verdict", []
    if any(
        v["verdict"] == "refuted" or not v["novel"] or v["duplicate_ids"] for v in votes
    ):
        return "suppressed", "refutation or previously observed fact", votes
    if any(
        v["verdict"] != "supported"
        or not v["source_support"]
        or not v["criterion_support"]
        for v in votes
    ):
        return "pending-review", "evidence or criterion unresolved", votes
    claims = synthesis.get("claims", {})
    if (
        claims.get("recommendation", {}).get("text") != "APPROVE"
        or not isinstance(claims.get("cautions"), list)
        or not 1 <= len(claims["cautions"]) <= 4
        or any(
            not c.get("text", "").startswith("NON_BLOCKING: ")
            for c in claims["cautions"]
        )
    ):
        return (
            "pending-review",
            "synthesis did not affirm unconditional clearance",
            votes,
        )
    return (
        "approved",
        "all members and synthesis support evidence, criterion and novelty",
        votes,
    )


def alert(item, members, votes, cautions):
    def plain(s):
        return s.replace("<", "").replace(">", "").replace("@", "(at)")

    return "\n".join(
        [
            "TRIGGER — " + CRITERIA[item["criterion"]],
            "What is new — " + plain(item["fact"]),
            *[e["published_at"] + " " + e["url"] for e in item["evidence"]],
            "Review — "
            + ", ".join(n + ": supported" for n in members)
            + "; synthesis: APPROVE",
            *[plain(c["text"]) for c in cautions],
            "Falsifier — "
            + plain(" / ".join(dict.fromkeys(v["falsifier"] for v in votes))),
            "This fact set will not be re-alerted. (" + item["fact_id"] + ")",
        ]
    )


def execute(store, scan, ground, review, members, today, record):
    if store.closed():
        return SILENT
    attempted = set()

    def consider(item):
        attempted.add(item["fact_id"])
        grounding = ground(item)
        record("grounding", grounding)
        if not evidence_verified(item, grounding):
            store.transition(
                item,
                "pending-review",
                "supporting quotes not verified in fetched pages",
            )
            return SILENT
        # The current item is excluded from novelty comparisons; other pending
        # facts remain visible. This is the explicit retry bypass of novelty.
        registry = [r for r in store.registry() if r["id"] != item["fact_id"]]
        result = review(item, grounding, registry)
        record("panel", result)
        status, reason, votes = verdict(result, members)
        if status != "approved":
            store.transition(item, status, reason)
            return SILENT
        body = (
            SILENT
            if item["criterion"] == "close"
            else alert(item, members, votes, result["synthesis"]["claims"]["cautions"])
        )
        return body if store.claim(item, body) else SILENT

    for item in store.pending():
        output = consider(item)
        if output != SILENT or store.closed():
            return output
    proposals = scan(store.registry())
    record("scan", proposals)
    if (
        not isinstance(proposals, dict)
        or not isinstance(proposals.get("facts"), list)
        or len(proposals["facts"]) > 8
    ):
        raise ValueError("invalid scan envelope")
    for raw in proposals["facts"]:
        item = candidate(raw, today)
        new = store.register(item)
        if new and item["criterion"] is not None and item["fact_id"] not in attempted:
            output = consider(item)
            if output != SILENT or store.closed():
                return output
    return SILENT
