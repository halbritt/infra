# Import another machine repository

This procedure brings an existing single-machine repository into the infrastructure repository while
preserving useful provenance and avoiding a permanent branch per machine.

## Before the import

- [ ] Confirm the source repository, default branch, owner, and stable machine
  hostname.
- [ ] Fetch the source and verify that its working tree and default branch are in
  the expected state.
- [ ] Read its root and nested agent instructions, READMEs, changelogs, install
  mappings, and service-manager units.
- [ ] Inventory current files, symlinks, submodules, ignored operational files,
  large artifacts, generated output, and absolute checkout paths.
- [ ] Scan the current tree and all reachable history for credentials. Record
  only file names, commit IDs, and secret classes during triage; do not print
  values.
- [ ] Rotate any exposed credential and sanitize the source history before it is
  connected to this repository.
- [ ] Decide which source files are host-specific. Treat everything as
  host-specific by default; promote to `shared/` only after comparison with an
  existing real consumer.
- [ ] Record the source URL, source branch, source tip, scan tool and version,
  scan result, and import method in the new host's `notes.md`.

Work from a clean, up-to-date infrastructure checkout. A short-lived import task branch is
reasonable for review, but it must be merged and removed. Do not create a branch
that remains the machine's home.

## Recommended import: `git subtree`

`git subtree` is available with Git on this host and does not require the source
tree to collide with the fleet root. Omit `--squash`; squashing would discard the
individual source commits that this migration is intended to preserve.

```sh
machine=<stable-hostname>
source_repo=/absolute/path/to/source-repository
source_branch=<source-default-branch>

git subtree add \
  --prefix="hosts/${machine}/config" \
  "${source_repo}" "${source_branch}"
```

Run this before creating `hosts/<name>/config`. The subtree commit connects the
source history to the fleet history and places its current tree below the host.
Imported historical commits retain their original repository-root paths; the
new host notes must therefore record the subtree commit and source tip for
pre-import archaeology.

### When a partial host record already exists

Do not delete or overwrite an existing `hosts/<name>/` partition to make the
normal prefix available. Import into a temporary child that does not exist:

```sh
git subtree add \
  --prefix="hosts/${machine}/source-import" \
  "${source_repo}" "${source_branch}"
```

In the separate normalization commit, move the imported subsystems into
`hosts/<name>/config/`, reconcile imported root documentation with the existing
manifest and notes, and remove the empty `source-import/` directory. Preserve
both versions where they carry distinct evidence. The temporary prefix must not
remain in the accepted layout.

Immediately follow the subtree commit with a separate normalization commit:

1. Add `machine.yaml`, `AGENTS.md`, `notes.md`, and `CHANGELOG.md` at the host
   root. If the imported repository already has a changelog or agent file, move
   it rather than copying it.
2. Group the imported root files into self-contained subsystem directories only
   where the source evidence supports that split.
3. Update absolute checkout paths, install commands, unit `Documentation=`
   fields, run-from-checkout entry points, and repository-local links.
4. Extract a shared file only if its exact behavior is already reusable. Keep
   the host override next to the host.
5. Declare existing roles in `machine.yaml`. Do not invent a role to mirror
   every source directory.
6. Reinstall any live unit that executes from the checkout, reload the service
   manager, and verify that service before continuing.
7. Run the source repository's original checks from the new paths, then run
   `scripts/validate-infra.py`.

To inspect the original source history after a subtree import, start from the
recorded source tip and use its original paths:

```sh
git log <recorded-source-tip> -- path/as/it/existed/in/source
```

## Alternative: prefix-rewrite before merge

Use this route when path-filtered history under `hosts/<name>/` is more important
than retaining the source commit IDs. It requires `git filter-repo` and rewrites
the imported commit IDs while preserving authors, dates, messages, file content,
and commit order.

```sh
machine=<stable-hostname>
source_repo=/absolute/path/to/source-repository
staging_repo=$(mktemp -d)/source

git clone --no-local "${source_repo}" "${staging_repo}"
git -C "${staging_repo}" filter-repo \
  --to-subdirectory-filter "hosts/${machine}/config" \
  --force

git remote add "import-${machine}" "${staging_repo}"
git fetch "import-${machine}"
git merge --no-ff --allow-unrelated-histories \
  "import-${machine}/<rewritten-default-branch>"
git remote remove "import-${machine}"
```

Run secret scanning before `filter-repo`, not after. The staging clone must be
outside the infrastructure repository. Record the old source tip and the rewritten import
tip so future maintainers can correlate the two histories.

## Post-import acceptance checklist

- [ ] `hosts/<name>/machine.yaml` parses and its `name` matches the directory.
- [ ] Every declared role exists; every referenced shared file exists.
- [ ] Every immediate subsystem directory has a README or agent instruction.
- [ ] Host hardware, network facts, operational notes, exceptions, and rejected
  approaches survived the move.
- [ ] The host changelog survived as a moved file, not a fresh summary.
- [ ] No source content was silently discarded. Deliberate exclusions are listed
  in `notes.md` with their source location and reason.
- [ ] No plaintext secret or decrypted SOPS output is present in the index.
- [ ] Absolute checkout paths and live run-from-checkout units use the new host
  path.
- [ ] Repository-local Markdown links resolve.
- [ ] Original tests and checks pass from the new path, or pre-existing failures
  are recorded separately from migration regressions.
- [ ] `scripts/validate-infra.py` passes.
- [ ] `git log -- hosts/<name>` shows the import and subsequent host changes.
- [ ] The import task branch, temporary remote, and temporary checkout are
  removed after merge; the target branch is pushed.

## Exact next-machine sequence

For the next machine, perform these actions in order:

1. Obtain its repository path or clone URL and default branch.
2. Choose the stable hostname used for `hosts/<name>/`.
3. Run the current-tree and full-history secret scans; rotate and sanitize first
   if either scan finds a real credential.
4. From a clean fleet checkout, run the unsquashed `git subtree add` command
   above into `hosts/<name>/config`, or use the temporary child procedure when
   a partial host partition already exists.
5. Add the host manifest and notes, then normalize paths in a second commit.
6. Reinstall and verify checkout-bound services on that machine.
7. Run the imported repository's checks plus `scripts/validate-infra.py`.
8. Review the host-scoped diff and history, merge the short-lived task branch if
   one was used, remove temporary import state, and push.
