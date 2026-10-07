import copy
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

from outbreak_watch.core import (
    SILENT,
    Store,
    candidate,
    evidence_verified,
    execute,
    verdict,
)

TODAY = date(2026, 10, 7)
MEMBERS = ["fable", "sol", "agy", "glm"]


def fact():
    return {
        "fact": "Agency confirms an event-linked case, X-2.",
        "criterion": "C2",
        "identity": {
            "subject": "event-x/case-2",
            "predicate": "infection",
            "object": "confirmed",
        },
        "evidence": [
            {
                "url": "https://example.org/report",
                "quote": "Case X-2 is confirmed.",
                "published_at": "2026-10-06",
                "publisher": "Agency",
                "primary_origin": "case-X-2-lab",
                "provenance": "Agency laboratory report",
            }
        ],
    }


def ground(item):
    return {
        "status": "completed",
        "sources": [
            {
                "url": e["url"],
                "kind": "page_excerpt",
                "text": "Before. " + e["quote"] + " After.",
                "document_sha256": "abc",
                "retrieved_at": "2026-10-07T10:00:00Z",
            }
            for e in item["evidence"]
        ],
    }


def panel(*args):
    vote = {
        "verdict": "supported",
        "source_support": True,
        "criterion_support": True,
        "novel": True,
        "duplicate_ids": [],
        "reason": "Direct agency report supports the linked case.",
        "falsifier": "A corrected lab report withdraws the result.",
    }
    return {
        "status": "completed",
        "opinions": [
            {"member": n, "status": "completed", "advice": json.dumps(vote)}
            for n in MEMBERS
        ],
        "synthesis": {
            "status": "completed",
            "validation": "quotes_verified_not_claim_truth",
            "claims": {
                "recommendation": {"text": "APPROVE"},
                "cautions": [{"text": "NON_BLOCKING: Based on the retrieved report."}],
            },
        },
    }


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.sqlite3"
        self.legacy = {"schema": "outbreak-watch/ledger/1", "entries": []}
        Store.initialize(self.path, self.legacy)
        self.store = Store(self.path)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.store.close)
        self.records = []

    def run_watch(self, facts=None, review=panel, fetch=ground, scanner=None):
        scan = scanner or (lambda registry: {"facts": facts or []})
        return execute(
            self.store,
            scan,
            fetch,
            review,
            MEMBERS,
            TODAY,
            lambda k, v: self.records.append((k, v)),
        )

    def test_positive_alert_then_repeat_is_silent(self):
        first = self.run_watch([fact()])
        self.assertIn("TRIGGER", first)
        self.assertIn("NON_BLOCKING", first)
        self.assertEqual(self.run_watch([fact()]), SILENT)
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM alerts").fetchone()[0], 1
        )

    def test_new_publisher_date_and_wording_keep_identity(self):
        self.run_watch([fact()])
        other = fact()
        other["fact"] = "The same case X-2 was confirmed, another outlet says."
        other["evidence"][0].update(
            url="https://elsewhere.org/news", published_at="2026-10-07"
        )
        self.assertEqual(
            candidate(fact(), TODAY)["fact_id"], candidate(other, TODAY)["fact_id"]
        )
        self.assertEqual(
            self.run_watch([other], review=lambda *a: self.fail("duplicate reviewed")),
            SILENT,
        )

    def test_new_evidence_updates_pending_without_resetting_identity(self):
        item = candidate(fact(), TODAY)
        self.store.register(item)
        updated = fact()
        updated["evidence"][0]["quote"] = "A corrected, verifiable passage."
        replacement = candidate(updated, TODAY)
        self.assertFalse(self.store.register(replacement))
        self.assertEqual(self.store.pending()[0]["evidence"], replacement["evidence"])
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM publications").fetchone()[0], 2
        )
        updated["criterion"] = None
        self.store.register(candidate(updated, TODAY))
        self.assertEqual(self.store.pending()[0]["criterion"], "C2")

    def test_changed_substantive_fact_can_alert(self):
        self.run_watch([fact()])
        new = fact()
        new["identity"]["subject"] = "event-x/case-3"
        self.assertIn("TRIGGER", self.run_watch([new]))

    def test_alias_detected_by_panel_is_suppressed(self):
        self.run_watch([fact()])
        new = fact()
        new["identity"]["subject"] = "another-name-for-case-2"

        def duplicate(item, evidence, registry):
            self.assertEqual(len(registry), 1)
            p = panel()
            v = json.loads(p["opinions"][0]["advice"])
            v.update(novel=False, duplicate_ids=[registry[0]["id"]])
            p["opinions"][0]["advice"] = json.dumps(v)
            return p

        self.assertEqual(self.run_watch([new], review=duplicate), SILENT)
        duplicate_id = candidate(new, TODAY)["fact_id"]
        self.assertEqual(
            next(r["status"] for r in self.store.registry() if r["id"] == duplicate_id),
            "suppressed",
        )
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM alerts").fetchone()[0], 1
        )

    def test_pending_retry_can_fire_and_skips_scan(self):
        self.assertEqual(
            self.run_watch([fact()], review=lambda *a: {"status": "partial"}), SILENT
        )

        def reviewer(item, evidence, registry):
            self.assertEqual(registry, [])  # does not match itself
            return panel()

        out = self.run_watch(
            review=reviewer, scanner=lambda r: self.fail("scan after fired retry")
        )
        self.assertIn("TRIGGER", out)
        self.assertEqual(self.store.registry()[0]["status"], "fired")

    def test_url_without_quote_refused(self):
        v = fact()
        v["evidence"][0]["quote"] = ""
        with self.assertRaises(ValueError):
            candidate(v, TODAY)

    def test_mismatched_excerpt_never_reaches_panel(self):
        def fetch(item):
            g = ground(item)
            g["sources"][0]["text"] = "Different content"
            return g

        self.assertEqual(
            self.run_watch(
                [fact()], fetch=fetch, review=lambda *a: self.fail("review")
            ),
            SILENT,
        )
        self.assertEqual(self.store.registry()[0]["status"], "pending-review")

    def test_snippets_and_partial_fetches_do_not_clear(self):
        item = candidate(fact(), TODAY)
        for change in ["snippet", "partial", "missing-hash"]:
            with self.subTest(change=change):
                g = ground(item)
                if change == "snippet":
                    g["sources"][0]["kind"] = "search_snippet"
                elif change == "partial":
                    g["status"] = "partial"
                else:
                    del g["sources"][0]["document_sha256"]
                self.assertFalse(evidence_verified(item, g))

    def test_partial_missing_synthesis_and_unknown_roster(self):
        for change in [
            "partial",
            "missing-member",
            "missing-synthesis",
            "unvalidated",
            "wrong-member",
        ]:
            with self.subTest(change=change):
                p = panel()
                if change == "partial":
                    p["status"] = "partial"
                elif change == "missing-member":
                    p["opinions"].pop()
                elif change == "missing-synthesis":
                    p.pop("synthesis")
                elif change == "unvalidated":
                    p["synthesis"].pop("validation")
                else:
                    p["opinions"][0]["member"] = "same-model-copy"
                self.assertEqual(verdict(p, MEMBERS)[0], "pending-review")

    def test_valid_detailed_review_within_six_hundred_word_contract(self):
        p = panel()
        v = json.loads(p["opinions"][0]["advice"])
        v["reason"] = "Detailed supporting evidence. " * 150
        p["opinions"][0]["advice"] = json.dumps(v)
        self.assertEqual(verdict(p, MEMBERS)[0], "approved")

    def test_complete_but_unresolved_is_not_clearance(self):
        p = panel()
        v = json.loads(p["opinions"][0]["advice"])
        v["verdict"] = "unresolved"
        p["opinions"][0]["advice"] = json.dumps(v)
        self.assertEqual(verdict(p, MEMBERS)[0], "pending-review")

    def test_malformed_false_and_refuted_votes(self):
        for change, expected in [
            ("malformed", "pending-review"),
            ("false", "pending-review"),
            ("refuted", "suppressed"),
        ]:
            p = panel()
            v = json.loads(p["opinions"][0]["advice"])
            if change == "malformed":
                v["source_support"] = "true"
            elif change == "false":
                v["source_support"] = False
            else:
                v["verdict"] = "refuted"
            p["opinions"][0]["advice"] = json.dumps(v)
            self.assertEqual(verdict(p, MEMBERS)[0], expected)

    def test_blocking_synthesis_and_hold_are_not_clearance(self):
        p = panel()
        p["synthesis"]["claims"]["cautions"][0]["text"] = (
            "BLOCKING: Source does not establish causation."
        )
        self.assertEqual(verdict(p, MEMBERS)[0], "pending-review")
        p = panel()
        p["synthesis"]["claims"]["recommendation"]["text"] = "HOLD"
        self.assertEqual(verdict(p, MEMBERS)[0], "pending-review")

    def test_crash_after_claim_cannot_replay(self):
        item = candidate(fact(), TODAY)
        self.store.register(item)
        self.assertTrue(self.store.claim(item, "never emitted"))
        self.assertFalse(self.store.claim(item, "retry"))
        self.assertEqual(self.run_watch([fact()]), SILENT)

    def test_concurrent_claims_return_one_winner(self):
        item = candidate(fact(), TODAY)
        self.store.register(item)
        barrier = threading.Barrier(2)
        results = []

        def claim():
            with closing(Store(self.path)) as store:
                barrier.wait(timeout=5)
                results.append(store.claim(item, "one body"))

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(sorted(results), [False, True])

    def test_closure_is_silent_and_stops_all_future_work(self):
        item = fact()
        item["criterion"] = "close"
        item["closure"] = {
            "result": "non-plague",
            "last_exposure_date": "2026-09-01",
            "window_days": 14,
            "no_new_cases": True,
        }
        self.assertEqual(self.run_watch([item]), SILENT)
        self.assertTrue(self.store.closed())
        self.assertEqual(
            self.run_watch(scanner=lambda r: self.fail("scan after closure")), SILENT
        )
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM alerts").fetchone()[0], 1
        )

    def test_closure_requires_all_conditions_and_time(self):
        base = fact()
        base["criterion"] = "close"
        base["closure"] = {
            "result": "negative",
            "last_exposure_date": "2026-09-01",
            "window_days": 14,
            "no_new_cases": True,
        }
        for key, value in [
            ("result", "positive"),
            ("no_new_cases", False),
            ("last_exposure_date", "2026-10-06"),
            ("window_days", 0),
        ]:
            item = copy.deepcopy(base)
            item["closure"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                candidate(item, TODAY)

    def test_missing_state_is_not_reinitialized(self):
        with self.assertRaises(sqlite3.OperationalError):
            Store(Path(self.tmp.name) / "missing.sqlite3")
        self.assertFalse((Path(self.tmp.name) / "missing.sqlite3").exists())

    def test_import_preserves_seen_and_suppressed(self):
        p = Path(self.tmp.name) / "import.sqlite3"
        old = {
            "schema": "outbreak-watch/ledger/1",
            "entries": [
                {"key": "seed-1", "fact": "Baseline", "status": "seen"},
                {
                    "key": "seed-2",
                    "fact": "Historically rejected",
                    "status": "suppressed",
                },
            ],
        }
        Store.initialize(p, old)
        with closing(Store(p)) as s:
            self.assertEqual(
                [r["status"] for r in s.registry()], ["seen", "suppressed"]
            )
            self.assertEqual(s.pending(), [])
        with self.assertRaises(FileExistsError):
            Store.initialize(p, old)


if __name__ == "__main__":
    unittest.main()
