"""Behaviour of shared/development/development_evidence.py on disposable Git repositories."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "shared/development/development_evidence.py"
spec = importlib.util.spec_from_file_location("development_evidence", TOOL)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)
spec = importlib.util.spec_from_file_location("development_evidence_install", ROOT / "shared/development/install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class RepoCase(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name).resolve()
        self.repo = self.scratch / "repo"
        self.store = self.scratch / "evidence"   # outside the repository
        self.store.mkdir()
        self.git("init", "-q", "-b", "main", str(self.repo), cwd=self.scratch)
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        self.write("checker.py", "def check():\n    return 'reference'\n")
        self.write("REVIEW.md", "Reject reference drift.\n")
        self.write(".gitignore", "generated/\n")
        self.base = self.commit("base")
        self.write("checker.py", "def check():\n    return 'reference'  # candidate\n")
        self.candidate = self.commit("candidate")
        self.write("generated/reference.txt", "built from checker\n")   # ignored, material
        (self.store / "run.log").write_text("9 passed\n")
        self.receipt = self.store / "receipt.json"

    def git(self, *args, cwd=None):
        done = subprocess.run(["git", *args], cwd=cwd or self.repo, capture_output=True, text=True, check=True)
        return done.stdout.strip()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def observation(self, **changes):
        item = {"claim": "checker rejects reference drift", "kind": "runtime", "command": ["make", "test"],
                "cwd": ".", "status": "passed", "exit_code": 0, "started_at": "2026-11-17T10:00:00Z",
                "ended_at": "2026-11-17T10:00:04Z", "reason": None, "artifacts": ["run.log"]}
        item.update(changes)
        return item

    def record(self, **changes):
        options = {"base": self.base, "material": [str(self.repo / "generated/reference.txt")],
                   "rules": ["REVIEW.md"], "observations": [self.observation()], "intent": "task TEST-1",
                   "unknowns": ["transfer to a second consumer was not exercised"]}
        options.update(changes)
        return evidence.record(self.repo, self.receipt, "example-cli", "clear-within-scope", **options)

    def compare(self, base="default", repo=None):
        return evidence.compare(self.receipt, repo or self.repo, base=self.base if base == "default" else base)

    def codes(self, report):
        return {(r["class"], r["code"]) for r in report["reasons"]}

    def rewrite(self, change):
        record = json.loads(self.receipt.read_text())
        change(record)
        self.receipt.write_text(json.dumps(record))

    def cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(TOOL), *args], cwd=self.repo, input=stdin,
                              capture_output=True, text=True, check=False)


class RecordTests(RepoCase):
    def test_clean_candidate_records_commit_tree_base_rules_and_material(self):
        record, digest = self.record()
        subject = record["subject"]
        self.assertEqual((subject["base"], subject["candidate"], subject["dirty"]), (self.base, self.candidate, False))
        self.assertEqual(subject["tree"], self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(record["schema"], "development-evidence/1")
        self.assertRegex(record["recorded_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(record["material"][0]["path"], "generated/reference.txt")
        self.assertEqual(record["material"][0]["sha256"], evidence.sha256_bytes(b"built from checker\n"))
        self.assertEqual(record["rules"], {"revision": self.base, "files": [
            {"path": "REVIEW.md", "state": "present", "sha256": evidence.sha256_bytes(b"Reject reference drift.\n")}]})
        self.assertEqual(record["observations"][0]["artifacts"][0]["sha256"], evidence.sha256_bytes(b"9 passed\n"))
        self.assertEqual(digest, evidence.sha256_bytes(self.receipt.read_bytes()))
        self.assertEqual(evidence.validate(json.loads(self.receipt.read_text())), [])

    def test_dirty_snapshot_never_inherits_head_identity(self):
        self.write("checker.py", "def check():\n    return 'only SKILL.md'\n")
        subject = self.record()[0]["subject"]
        self.assertTrue(subject["dirty"])
        self.assertIsNone(subject["candidate"])
        self.assertIsNone(subject["tree"])
        self.assertEqual(subject["head"], self.candidate)
        self.assertEqual([c["path"] for c in subject["changes"]], ["checker.py"])
        first = subject["snapshot"]
        self.receipt.unlink()
        self.write("checker.py", "def check():\n    return 'another edit'\n")
        self.assertNotEqual(self.record()[0]["subject"]["snapshot"], first)

    def test_rules_come_from_the_base_not_the_working_rewrite(self):
        self.write("REVIEW.md", "Approve everything.\n")
        rules = self.record(rules=["REVIEW.md", "docs/REVIEW-extra.md"])[0]["rules"]["files"]
        self.assertEqual(rules[0]["sha256"], evidence.sha256_bytes(b"Reject reference drift.\n"))
        self.assertEqual(rules[1], {"path": "docs/REVIEW-extra.md", "state": "missing", "sha256": None})

    def test_receipt_is_written_once_and_bad_input_writes_nothing(self):
        self.record()
        with self.assertRaisesRegex(evidence.EvidenceError, "already exists"):
            self.record()
        self.receipt.unlink()
        for bad in ({"observations": [self.observation(status="green")]},
                    {"observations": [self.observation(artifacts=["../../etc/passwd"])]},
                    {"observations": [self.observation(run="rm -rf /")]},
                    {"material": ["/etc/hostname"]},
                    {"rules": ["../outside.md"]},
                    {"rules": ["REVIEW.md"], "base": None},
                    {"base": "no-such-revision"}):
            with self.subTest(bad=bad), self.assertRaises(evidence.EvidenceError):
                self.record(**bad)
            self.assertFalse(self.receipt.exists())

    def test_only_declared_files_are_read(self):
        self.write("generated/secret.env", "TOKEN=do-not-read\n")
        self.write("notes.txt", "untracked, undeclared\n")
        record = self.record()[0]
        text = self.receipt.read_text()
        self.assertNotIn(evidence.sha256_bytes(b"TOKEN=do-not-read\n"), text)
        self.assertNotIn(evidence.sha256_bytes(b"untracked, undeclared\n"), text)
        self.assertNotIn("notes.txt", text)
        self.assertEqual(record["subject"]["untracked_count"], 1)
        self.assertNotIn(os.environ["HOME"], json.dumps(record["annotations"]))


class CompareTests(RepoCase):
    def test_unchanged_identity_is_current_and_outcome_is_separate(self):
        self.record()
        report, code = self.compare()
        self.assertEqual((report["freshness"], report["outcome"], code), ("current", "clear-within-scope", 0))
        self.assertEqual(report["reasons"], [])
        self.assertIn("coverage unknown: transfer to a second consumer was not exercised", report["limits"])
        self.assertEqual(self.compare(), (report, code))   # deterministic
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_current_evidence_can_carry_open_findings(self):
        evidence.record(self.repo, self.receipt, "example-cli", "findings-open", base=self.base,
                        observations=[self.observation(status="failed", exit_code=1)])
        report, code = self.compare()
        self.assertEqual((report["freshness"], report["outcome"], code), ("current", "findings-open", 0))

    def test_source_dirty_without_head_change_is_stale(self):
        self.record()
        self.write("checker.py", "def check():\n    return 'only SKILL.md'\n")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.candidate)
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("stale", 1))
        self.assertIn(("stale", "working-tree-dirty"), self.codes(report))
        self.assertEqual(report["outcome"], "clear-within-scope")   # a stale clear result is still reported as stale

    def test_dirty_snapshot_is_current_only_for_the_same_content(self):
        self.write("checker.py", "def check():\n    return 'experiment'\n")
        self.record()
        self.assertEqual(self.compare()[0]["freshness"], "current")
        self.write("checker.py", "def check():\n    return 'experiment 2'\n")
        self.assertIn(("stale", "snapshot-changed"), self.codes(self.compare()[0]))
        self.git("checkout", "-q", "checker.py")
        self.assertIn(("stale", "snapshot-changed"), self.codes(self.compare()[0]))

    def test_staged_change_hidden_by_restored_working_file_is_not_clean(self):
        self.record()
        original = (self.repo / "checker.py").read_text()
        self.write("checker.py", "def check():\n    return 'staged'\n")
        self.git("add", "checker.py")
        self.write("checker.py", original)           # working bytes equal HEAD; the index does not
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("stale", 1))
        self.assertIn(("stale", "working-tree-dirty"), self.codes(report))
        self.assertEqual((report["current_subject"]["dirty"], report["current_subject"]["candidate"]), (True, None))
        self.receipt.unlink()
        subject = self.record()[0]["subject"]
        self.assertEqual((subject["dirty"], subject["candidate"], subject["changes"]), (True, None, []))
        self.assertEqual([item["path"] for item in subject["staged"]], ["checker.py"])
        self.assertEqual(self.compare()[0]["freshness"], "current")
        self.git("reset", "-q")
        self.assertIn(("stale", "snapshot-changed"), self.codes(self.compare()[0]))

    def test_ignored_generated_input_change_is_stale_with_clean_status(self):
        self.record()
        self.write("generated/reference.txt", "rebuilt differently\n")
        self.assertEqual(self.git("status", "--porcelain"), "")
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("stale", 1))
        self.assertEqual([(r["code"], r["path"]) for r in report["reasons"]],
                         [("material-changed", "generated/reference.txt")])

    def test_material_missing_at_record_time_is_never_current(self):
        (self.repo / "generated/reference.txt").unlink()
        record = self.record()[0]
        self.assertEqual(record["material"][0],
                         {"path": "generated/reference.txt", "state": "missing", "kind": None, "sha256": None,
                          "size": None})
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("unknown", 2))
        self.assertIn(("unknown", "material-unavailable"), self.codes(report))
        self.write("generated/reference.txt", "appeared later\n")
        self.assertEqual(self.compare()[0]["freshness"], "unknown")

    def test_material_removed_after_record_is_stale(self):
        self.record()
        (self.repo / "generated/reference.txt").unlink()
        self.assertIn(("stale", "material-missing"), self.codes(self.compare()[0]))

    def test_corrupted_or_absent_artifact_is_unknown_and_inspect_reports_it(self):
        self.record()
        (self.store / "run.log").write_text("0 passed\n")
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("unknown", 2))
        self.assertIn(("unknown", "artifact-changed"), self.codes(report))
        inspected, code = evidence.inspect(self.receipt)
        self.assertEqual((inspected["valid"], code, inspected["artifacts"][0]["result"]), (True, 1, "changed"))
        (self.store / "run.log").unlink()
        self.assertIn(("unknown", "artifact-missing"), self.codes(self.compare()[0]))
        self.assertEqual(evidence.inspect(self.receipt)[0]["artifacts"][0]["result"], "missing")

    def test_artifact_absent_at_record_time_stays_unavailable(self):
        (self.store / "run.log").unlink()
        record = self.record()[0]
        self.assertEqual(record["observations"][0]["artifacts"][0]["state"], "missing")
        (self.store / "run.log").write_text("9 passed\n")
        self.assertIn(("unknown", "artifact-unavailable"), self.codes(self.compare()[0]))
        self.assertEqual(evidence.inspect(self.receipt)[1], 1)

    def test_base_and_rules_change_are_stale(self):
        self.record()
        self.git("checkout", "-q", "-b", "trunk", self.base)
        self.write("REVIEW.md", "Approve everything.\n")
        new_base = self.commit("weaken rules on trunk")
        self.git("checkout", "-q", "main")
        report, code = self.compare(base=new_base)
        self.assertEqual((report["freshness"], code), ("stale", 1))
        self.assertEqual({r["code"] for r in report["reasons"]}, {"base-changed", "rules-changed"})

    def test_rebased_candidate_is_stale(self):
        self.record()
        self.git("commit", "-q", "--amend", "-m", "candidate, reworded")
        self.assertIn(("stale", "candidate-changed"), self.codes(self.compare()[0]))

    def test_recorded_base_without_current_base_is_unknown(self):
        self.record()
        report, code = self.compare(base=None)
        self.assertEqual((report["freshness"], code), ("unknown", 2))
        self.assertIn(("unknown", "base-not-supplied"), self.codes(report))

    def test_undeclared_untracked_file_is_unknown_whether_new_or_unchanged(self):
        self.record()
        self.write("helper.py", "VALUE = 1\n")
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("unknown", 2))
        self.assertIn(("unknown", "untracked-unaccounted"), self.codes(report))
        self.receipt.unlink()
        self.write("input.cfg", "v1\n")
        self.git("config", "status.showUntrackedFiles", "no")
        self.assertEqual(self.record()[0]["subject"]["untracked_count"], 2)
        self.write("input.cfg", "v2\n")      # same names, different content
        report, _ = self.compare()
        self.assertEqual(report["freshness"], "unknown")
        self.assertLessEqual({("unknown", "untracked-unaccounted"), ("unknown", "untracked-unaccounted-at-record")},
                             self.codes(report))
        (self.repo / "helper.py").unlink()
        (self.repo / "input.cfg").unlink()
        self.assertEqual(self.compare()[0]["freshness"], "unknown")   # incomplete when recorded

    def test_explicit_nonmaterial_and_material_classification_accounts_for_untracked_files(self):
        self.write("scratch/notes.txt", "thinking\n")
        self.write("input.cfg", "v1\n")
        record = self.record(material=[str(self.repo / "generated/reference.txt"), str(self.repo / "input.cfg")],
                             nonmaterial_paths=["scratch/"])[0]
        self.assertEqual((record["subject"]["untracked_count"], record["nonmaterial"]), (0, ["scratch/"]))
        self.write("scratch/notes.txt", "more thinking\n")
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("current", 0))
        self.assertIn("declared nonmaterial, not fingerprinted: scratch/", report["limits"])
        self.assertNotIn(evidence.sha256_bytes(b"thinking\n"), self.receipt.read_text())
        self.write("input.cfg", "v2\n")
        self.assertIn(("stale", "material-changed"), self.codes(self.compare()[0]))

    def test_unaccounted_input_is_never_current_and_coverage_unknown_is_only_a_limit(self):
        self.record(unaccounted_inputs=["tool version of the external linter"])
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("unknown", 2))
        self.assertEqual(self.codes(report), {("unknown", "input-unaccounted")})
        self.assertFalse(any("external linter" in item for item in report["limits"]))

    def test_comparison_reports_the_observed_subject(self):
        self.record()
        self.assertEqual(self.compare()[0]["current_subject"],
                         {"head": self.candidate, "candidate": self.candidate, "dirty": False, "snapshot": None})
        self.write("checker.py", "changed\n")
        now = self.compare()[0]["current_subject"]
        self.assertEqual((now["head"], now["candidate"], now["dirty"]), (self.candidate, None, True))
        self.assertRegex(now["snapshot"], "^[0-9a-f]{64}$")
        self.receipt.unlink()
        self.assertEqual(self.compare()[0]["current_subject"], now)      # still observed with no receipt
        self.assertIsNone(self.compare(repo=self.store)[0]["current_subject"])

    def test_dirty_submodule_content_is_never_current(self):
        sub = self.scratch / "subrepo"
        self.git("init", "-q", "-b", "main", str(sub), cwd=self.scratch)
        (sub / "tracked").write_text("v0\n")
        self.git("add", "-A", cwd=sub)
        self.git("-c", "user.email=t@example.invalid", "-c", "user.name=T", "commit", "-q", "-m", "sub", cwd=sub)
        self.git("-c", "protocol.file.allow=always", "submodule", "--quiet", "add", str(sub), "sub")
        self.commit("add submodule")
        self.git("config", "diff.ignoreSubmodules", "all")   # must not hide the change
        self.record()
        self.assertEqual(self.compare()[0]["freshness"], "current")
        self.receipt.unlink()
        (self.repo / "sub/tracked").write_text("v1\n")
        record = self.record()[0]
        self.assertEqual([(c["path"], c["state"]) for c in record["subject"]["changes"]], [("sub", "unsupported")])
        (self.repo / "sub/tracked").write_text("v2\n")
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("unknown", 2))
        self.assertIn(("unknown", "change-unfingerprinted"), self.codes(report))

    def test_receipt_and_artifacts_inside_the_repository_do_not_disturb_identity(self):
        self.receipt = self.repo / "evidence/receipt.json"
        self.receipt.parent.mkdir()
        (self.receipt.parent / "run.log").write_text("9 passed\n")
        self.record()
        self.assertEqual(self.compare()[0]["freshness"], "current")

    def test_other_repository_and_non_repository_are_not_current(self):
        self.record()
        other = self.scratch / "other"
        self.git("init", "-q", "-b", "main", str(other), cwd=self.scratch)
        self.git("-c", "user.email=t@example.invalid", "-c", "user.name=T", "commit", "-q", "--allow-empty",
                 "-m", "unrelated", cwd=other)
        self.assertIn(("stale", "repository-changed"), self.codes(self.compare(base=None, repo=other)[0]))
        report, code = self.compare(repo=self.store)
        self.assertEqual((report["freshness"], code), ("unknown", 2))
        self.assertIn(("unknown", "repository-unreadable"), self.codes(report))


class MalformedTests(RepoCase):
    def test_missing_receipt_is_missing_not_empty(self):
        report, code = self.compare()
        self.assertEqual((report["freshness"], report["outcome"], code), ("missing", None, 3))
        inspected, code = evidence.inspect(self.receipt)
        self.assertEqual((inspected["valid"], inspected["record"], code), (False, None, 3))
        self.assertFalse(self.receipt.exists())

    def test_malformed_records_are_diagnosed(self):
        self.record()
        good = self.receipt.read_text()
        cases = {
            "not JSON": lambda text: "{" + text,
            "other version": lambda text: text.replace("development-evidence/1", "development-evidence/2"),
            "missing field": lambda text: self.drop(text, "outcome"),
            "unknown field": lambda text: self.add(text, "approved", True),
            "bad timestamp": lambda text: self.add(text, "recorded_at", "yesterday"),
            "bad outcome": lambda text: self.add(text, "outcome", "passed"),
            "short commit": lambda text: text.replace(self.candidate, self.candidate[:12]),
            "list": lambda text: "[]",
        }
        for name, change in cases.items():
            with self.subTest(name=name):
                self.receipt.write_text(change(good))
                report, code = self.compare()
                self.assertEqual((report["freshness"], report["outcome"], code), ("unknown", None, 2))
                self.assertEqual([r["code"] for r in report["reasons"]], ["receipt-malformed"])
                inspected, code = evidence.inspect(self.receipt)
                self.assertEqual((inspected["valid"], code), (False, 2))
                self.assertTrue(inspected["diagnostics"])

    @staticmethod
    def drop(text, key):
        record = json.loads(text)
        del record[key]
        return json.dumps(record)

    @staticmethod
    def add(text, key, value):
        record = json.loads(text)
        record[key] = value
        return json.dumps(record)

    def test_contradictory_identity_fields_cannot_be_current(self):
        self.record()
        zero = "0" * 40
        self.rewrite(lambda r: r["subject"].update(tree=zero, head_tree=zero))
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("unknown", 2))
        self.assertIn(("unknown", "receipt-inconsistent"), self.codes(report))
        self.receipt.unlink()
        self.write("checker.py", "def check():\n    return 'dirty'\n")
        self.record()
        self.assertEqual(self.compare()[0]["freshness"], "current")
        self.rewrite(lambda r: r["subject"]["changes"][0].update(sha256="0" * 64))
        report, code = self.compare()
        self.assertEqual((report["freshness"], code), ("unknown", 2))
        self.assertEqual([r["code"] for r in report["reasons"]], ["receipt-malformed"])
        self.assertIn("subject.snapshot", report["reasons"][0]["detail"])

    def test_dirty_record_claiming_a_commit_is_rejected(self):
        self.write("checker.py", "def check():\n    return 'dirty'\n")
        self.record()
        self.rewrite(lambda r: r["subject"].update(candidate=r["subject"]["head"]))
        self.assertEqual(self.compare()[0]["reasons"][0]["code"], "receipt-malformed")

    def test_malicious_fields_never_execute_or_escape(self):
        marker = self.scratch / "executed"
        payload = f"touch {marker}"
        self.record(observations=[self.observation(command=["sh", "-c", payload], claim=f"$({payload})")],
                    annotations={"note": f"`{payload}`"}, intent=f"; {payload}")
        self.assertEqual(self.compare()[0]["freshness"], "current")
        self.assertEqual(evidence.inspect(self.receipt)[1], 0)
        self.assertEqual(self.cli("inspect", str(self.receipt)).returncode, 0)
        outside = self.scratch / "outside.txt"
        outside.write_text("private\n")
        attacks = {
            "material traversal": lambda r: r["material"][0].update(path="../outside.txt"),
            "material absolute": lambda r: r["material"][0].update(path=str(outside)),
            "artifact traversal": lambda r: r["observations"][0]["artifacts"][0].update(path="../outside.txt"),
            "rule option": lambda r: r["rules"]["files"][0].update(path="../../x"),
            "revision option": lambda r: r["subject"].update(base="--upload-pack=" + payload),
            "command string": lambda r: r["observations"][0].update(command=payload),
        }
        good = self.receipt.read_text()
        for name, change in attacks.items():
            with self.subTest(name=name):
                self.receipt.write_text(good)
                self.rewrite(change)
                report, code = self.compare()
                self.assertEqual((report["freshness"], code), ("unknown", 2))
                self.assertEqual([r["code"] for r in report["reasons"]], ["receipt-malformed"])
                self.assertNotIn(evidence.sha256_bytes(b"private\n"), json.dumps(report))
        self.assertFalse(marker.exists())

    def test_repository_fsmonitor_hook_is_not_run(self):
        marker = self.scratch / "hook-ran"
        hook = self.scratch / "hook.sh"
        hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
        hook.chmod(0o755)
        self.git("config", "core.fsmonitor", str(hook))
        self.record()
        self.compare()
        self.assertFalse(marker.exists())


class CommandLineTests(RepoCase):
    def test_record_inspect_compare_round_trip_and_exit_codes(self):
        observations = self.store / "observations.json"
        observations.write_text(json.dumps([self.observation(), self.observation(
            claim="transfer to consumer-b", status="not-run", exit_code=None, command=None, started_at=None,
            ended_at=None, reason="no second consumer in this fixture", artifacts=[])]))
        done = self.cli("record", "--output", str(self.receipt), "--project", "example-cli", "--outcome",
                        "incomplete", "--base", self.base, "--material", "generated/reference.txt", "--rules",
                        "REVIEW.md", "--observations", str(observations), "--unknown", "consumer-b not exercised",
                        "--annotation", "reviewer=fresh-context", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        summary = json.loads(done.stdout)
        self.assertEqual(summary["receipt_sha256"], evidence.sha256_bytes(self.receipt.read_bytes()))
        inspected = self.cli("inspect", str(self.receipt), "--json")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["record"]["observations"][1]["status"], "not-run")
        compared = self.cli("compare", str(self.receipt), "--base", self.base, "--json")
        self.assertEqual(compared.returncode, 0, compared.stdout)
        self.assertEqual(json.loads(compared.stdout)["schema"], "development-evidence-comparison/1")
        self.assertEqual(json.loads(compared.stdout)["outcome"], "incomplete")
        self.write("checker.py", "changed\n")
        self.assertEqual(self.cli("compare", str(self.receipt), "--base", self.base).returncode, 1)
        self.assertEqual(self.cli("compare", str(self.store / "absent.json")).returncode, 3)
        again = self.cli("record", "--output", str(self.receipt), "--project", "p", "--outcome", "incomplete")
        self.assertEqual(again.returncode, 64)
        self.assertIn("already exists", again.stderr)
        untracked = self.cli("record", "--output", str(self.store / "second.json"), "--project", "p", "--outcome",
                             "incomplete", "--nonmaterial", "scratch/", "--unaccounted-input", "linter version",
                             "--json")
        self.assertEqual(untracked.returncode, 0, untracked.stderr)
        self.assertFalse(json.loads(untracked.stdout)["can_be_current"])
        self.assertIn("recorded without a digest: unaccounted input: linter version", untracked.stderr)
        self.assertEqual(self.cli("compare").returncode, 64)
        self.assertEqual(self.cli("record", "--output", "x", "--project", "p", "--outcome", "passed").returncode, 64)

    def test_observations_from_stdin_and_skip_needs_a_reason(self):
        done = self.cli("record", "--output", str(self.receipt), "--project", "p", "--outcome", "incomplete",
                        "--observations", "-", stdin=json.dumps(self.observation(status="skipped", artifacts=[])))
        self.assertEqual(done.returncode, 64)
        self.assertIn("reason: required when status is skipped", done.stderr)
        self.assertFalse(self.receipt.exists())


class InstallTests(unittest.TestCase):
    def test_install_then_check_then_detect_drift(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "bin/development-evidence"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(install.main(["--target", str(target), "--check"]), 1)
                self.assertEqual(install.main(["--target", str(target)]), 0)
                self.assertEqual(install.main(["--target", str(target), "--check"]), 0)
            self.assertEqual(target.read_bytes(), TOOL.read_bytes())
            self.assertTrue(os.access(target, os.X_OK))
            done = subprocess.run([str(target), "--version"], capture_output=True, text=True, check=False)
            self.assertEqual((done.returncode, done.stdout.strip()), (0, "development-evidence/1"))
            target.write_text("#!/bin/sh\n")
            with contextlib.redirect_stdout(out):
                self.assertEqual(install.main(["--target", str(target), "--check"]), 1)
            self.assertIn("differs", out.getvalue())


if __name__ == "__main__":
    unittest.main()
