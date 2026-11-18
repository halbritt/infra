# Shared development evidence

`development-evidence` writes one receipt for an assessment, checks that the
receipt and its artifacts are intact, and compares the recorded source and input
identity with a repository's current state. It formats and compares
observations. It does not run checks, schedule work or decide acceptance, and no
workflow is gated on it.

Reason for sharing: the first native skill trials
(`skillpack/evaluations/shared_development/RESULTS-2026-11-17.md`) showed each
harness assembling the same hashes and observations by hand. The consumers are
the `verify-behavior` skill, Cairn checkpoint and status notes, and an advisory
comparison in `git-land`. Owner authorized 2026-11-17.

## Use

```sh
development-evidence record --output ~/evidence/run-1/receipt.json \
  --project example-cli --outcome clear-within-scope --base origin/master \
  --material build/reference.txt --rules REVIEW.md \
  --observations ~/evidence/run-1/observations.json \
  --unknown "second consumer not exercised"
development-evidence inspect ~/evidence/run-1/receipt.json
development-evidence compare ~/evidence/run-1/receipt.json --base origin/master --json
```

`record` options: `--repo DIR` (default `.`), `--intent TEXT`, repeatable
`--material FILE`, `--nonmaterial PATH`, `--unaccounted-input TEXT`,
`--rules PATH`, `--observations FILE` (`-` is stdin), `--unknown TEXT` and
`--annotation KEY=VALUE`, and `--json`. It refuses to overwrite a receipt, and
it writes nothing when an input is invalid.

Every untracked, non-ignored file must be classified, or the receipt can never
be current. `--material FILE` fingerprints it. `--nonmaterial PATH` (an exact
path, or `directory/` for everything below it) states that it cannot affect the
assessment; it is not read. `--unaccounted-input TEXT` names a material input
that could not be fingerprinted, such as a tool version or a file outside the
repository; it makes the receipt permanently `unknown`. `--unknown TEXT` is
different: it limits what the assessment covered and does not change freshness.
`record` warns on stderr, and `--json` reports `can_be_current: false`, when
something was recorded without a digest.

An observation is recorded once, by the caller that ran the check:

```json
{"claim": "checker rejects reference drift", "kind": "runtime",
 "command": ["make", "test"], "cwd": ".", "status": "passed", "exit_code": 0,
 "started_at": "2026-11-17T10:00:00Z", "ended_at": "2026-11-17T10:00:04Z",
 "reason": null, "artifacts": ["run.log"]}
```

`kind` is `runtime`, `source-reasoning` or `model-judgment`. `status` is
`passed`, `failed`, `skipped`, `not-run` or `unknown`; the last three need a
`reason`. `command` is an argument list kept as text. Nothing in a receipt or an
observation is ever executed.

| Operation | Exit 0 | 1 | 2 | 3 | 64 |
| --- | --- | --- | --- | --- | --- |
| `record` | written | | | | invalid input or repository |
| `inspect` | valid, artifacts verified | artifact missing, changed or never fingerprinted | malformed | no receipt | usage |
| `compare` | current | stale | unknown | no receipt | usage |

`inspect` and `compare` only read. They take no index lock and write no Git
object. `--json` gives `development-evidence-inspection/1` and
`development-evidence-comparison/1`; the comparison has `freshness`, `outcome`,
`reasons` (`class`, `code`, `path`, `detail`), `limits`, `receipt_sha256` and
`current_subject` (`head`, `candidate`, `dirty`, `snapshot` as observed now;
`candidate` is null for a dirty tree, and the whole object is null when the
repository cannot be read). It is the same for the same inputs.

As a library, load `development_evidence.py` and call `record()`, `inspect()`,
`compare()`, `validate()` or `load()`.

## Receipt schema `development-evidence/1`

All fields below are required. Unknown fields and other schema versions are
rejected, so a reader never guesses. Free-form strings go in `annotations`.

| Field | Content |
| --- | --- |
| `schema`, `hash` | `development-evidence/1`, `sha256` |
| `recorded_at` | UTC, `YYYY-MM-DDTHH:MM:SSZ`; observation times use the same form |
| `project`, `intent_source` | caller's project name; source of intent or null |
| `repository` | `root` (informational path) and `roots_sha256` (digest of the root commit IDs) |
| `subject` | `base`, `head`, `head_tree`, `dirty`, `candidate`, `tree`, `snapshot`, `changes`, `staged`, `untracked_count` |
| `rules` | null, or `revision` (the base) and `files` with `path`, `state`, `sha256` |
| `material` | declared files: `path`, `state`, `kind`, `sha256`, `size` |
| `nonmaterial`, `unaccounted_inputs` | paths classified as not material; inputs that could not be fingerprinted |
| `observations` | as above; each artifact has `path`, `state`, `kind`, `sha256`, `size` |
| `outcome` | `clear-within-scope`, `findings-open`, `failed-check` or `incomplete` |
| `unknowns` | coverage limits stated by the caller |

Identity:

- Commits and trees are full Git object IDs. Every content digest is SHA-256
  over the file's bytes; a symlink is hashed as its target text and is not
  followed.
- A clean tree has `candidate` = `head` and `tree` = `head_tree`.
- A tree with working or staged changes has `candidate` and `tree` null. Its
  identity is `snapshot`, a digest over `head`, each tracked path whose working
  content differs from `HEAD` (status and content digest) and each index entry
  that differs from `HEAD` (status and object ID). A staged change counts even
  when the working file was restored to match `HEAD`. It never inherits the commit under it. A reader
  recomputes this digest and rejects a receipt whose fields disagree.
- `untracked_count` counts untracked files that were neither material nor
  nonmaterial when recorded. They are listed with `git ls-files`, so
  `status.showUntrackedFiles` does not hide them.
- A tracked change without a content digest, such as a submodule whose commit
  or working content differs, is recorded as `unsupported` and is never current.
  Submodule changes are always reported, whatever `diff.ignoreSubmodules` says.
- Review rules are read from the base revision, not from the working tree. A
  rule file absent from the base is recorded as `missing`.
- A declared file that is absent, unreadable or not a regular file is recorded
  with that `state` and no digest.

Paths: material paths are inside the repository and stored relative to its top
level, so a receipt compares in another worktree. Rule paths are relative to
the top level. Artifact paths are relative to the receipt's directory, so an
evidence directory can move as a unit. A receipt cannot hold an absolute path
or `..`.

## Freshness and outcome

Freshness is computed by `compare`. Outcome is the value the caller recorded
and is reported unchanged, so a current receipt can have open findings and a
stale one can say clear.

| Freshness | Cause |
| --- | --- |
| `stale` | different repository, base, candidate or snapshot; working or staged files now differ from `HEAD`; a rule changed at the current base; a recorded material file changed or disappeared |
| `unknown` | malformed or self-contradictory receipt; unreadable repository; a base was recorded and `--base` was not passed; a material file or artifact was never fingerprinted; an artifact is missing or changed; an unclassified untracked file exists now or existed when recorded; a tracked change has no content digest; an unaccounted input was declared |
| `missing` | the receipt does not exist |
| `current` | none of the above |

`stale` outranks `unknown`; every reason is listed. A material file that was
missing when recorded stays `unknown` even if it appears later.

For `git-land`, run `compare RECEIPT --repo WORKTREE --base origin/TRUNK --json`
on the final candidate after the rebase and checks, and report the result. A
rebase changes the base and the candidate, so earlier evidence reads as stale.

## Limits

- The caller declares which files are material. Ignored files are not seen at
  all unless declared, and a path declared nonmaterial is trusted, not checked.
- A digest identifies content. It does not show that the evidence covers the
  claim or that the content is correct.
- Files outside the repository and tool versions cannot be fingerprinted in
  this version; state them with `--unaccounted-input`.
- A clean submodule is identified only by the commit the parent tree pins.
- Observation text is stored as given. Do not put credentials or session
  transcripts in it.
- `compare` reads the working tree it is given. Serialization against
  concurrent changes belongs to the caller.

## Source and install

Source of truth is this directory. The installed copy is
`~/.local/bin/development-evidence`, a byte copy of `development_evidence.py`.

```sh
python3 shared/development/install.py
python3 shared/development/install.py --check
```

Tests: `tests/test_development_evidence.py`, run by `mise run test`. To roll
back, reinstall from the previous infra revision or remove the installed file.
