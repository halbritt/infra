# proximal fleet state

Durable, inspectable provenance and desired state for the machines operated by
Halbritt. This repository began as the record for the host `proximal`; it now
uses a fleet layout so additional machine repositories can be imported without
flattening their identities or assigning a permanent Git branch to each host.

The repository records configuration, installation mappings, measurements,
incidents, rejected approaches, and host exceptions. It does not store live
credentials.

## Layout

```text
.
├── hosts/                 # one stable directory per physical or virtual machine
│   └── <machine>/
│       ├── machine.yaml   # identity, platform, hardware summary, and roles
│       ├── AGENTS.md      # host-specific operating boundaries
│       ├── CHANGELOG.md   # host-specific operational history
│       ├── notes.md       # machine-wide notes and exceptions
│       └── config/        # self-contained host subsystem directories
├── roles/                 # reusable responsibility and machine-type bundles
├── shared/                # configuration proven reusable across hosts
├── secrets/               # policy only, or SOPS-encrypted files in the future
├── docs/                  # fleet procedures, including history-preserving imports
└── scripts/               # lightweight repository validation
```

The original machine is [`hosts/proximal/`](hosts/proximal/). The standalone
`peecee` repository and its 15-commit history were imported into
[`hosts/peecee/`](hosts/peecee/) after an initial partial record was reconciled.
The `proximal` subsystem index remains at
[`hosts/proximal/config/README.md`](hosts/proximal/config/README.md).

## Layering and ownership

The three configuration layers answer different questions:

1. `shared/` owns a configuration fragment only after at least two hosts can use
   the same bytes and meaning.
2. `roles/` declares a reusable responsibility, its invariants, and the shared
   files it consumes. A role does not contain a disguised copy of one host.
3. `hosts/<name>/` owns machine identity, hardware facts, installed service
   topology, operational evidence, and overrides. Host configuration wins when
   a role or shared default cannot represent a real machine constraint.

Keep a subsystem self-contained under `hosts/<name>/config/<subsystem>/` unless
there is evidence that a file is genuinely shared. Do not deduplicate similar
files merely because their names match.

## Naming conventions

- Host directories use the stable lowercase hostname: `proximal`, `peecee`, or
  another DNS-safe name matching `[a-z0-9][a-z0-9-]*`.
- Subsystem directories use lowercase kebab-case and describe one operational
  responsibility.
- Role names use lowercase kebab-case and describe a capability or machine type,
  such as `developer`, `linux`, or `server`.
- Shared paths name the tool or concern, not the first machine that used them.
- A machine rename is a deliberate migration. Do not rename a host directory
  because hardware, an IP address, or an operator changes.

## Add a machine

For a machine with no repository to import:

1. Choose its stable hostname and create `hosts/<name>/config/`.
2. Copy the manifest shape from
   [`hosts/proximal/machine.yaml`](hosts/proximal/machine.yaml). The manifests
   use JSON-compatible YAML so the standard-library validator needs no YAML
   dependency.
3. Add `hosts/<name>/AGENTS.md`, `notes.md`, and `CHANGELOG.md`.
4. Add only roles that apply to the machine. Add a new role when it defines a
   reusable responsibility, not just to label one service.
5. Put each machine-specific subsystem under `config/<subsystem>/` with a
   `README.md` or `AGENTS.md` that maps canonical files to installed paths.
6. Put secret values in the machine's external secret store or in an approved
   SOPS/age workflow. See [`secrets/README.md`](secrets/README.md).
7. Run `scripts/validate-fleet.py`, inspect the diff, commit, and push.

When a machine already has a Git repository, use the history-preserving process
in [`docs/importing-hosts.md`](docs/importing-hosts.md). Import one repository at
a time. Do not create a permanent branch per machine.

## History and changelogs

Git remains the provenance ledger. To see changes that touched one host after it
joined this layout:

```sh
git log -- hosts/proximal
git log -- hosts/<machine-name>
```

The current repository spent its first 165 commits in a single-host layout. The
fleet migration preserves those commits, but a directory path filter cannot
infer a pre-migration directory name. Follow an individual moved file across the
migration when older history is needed:

```sh
git log --follow -- hosts/proximal/CHANGELOG.md
git log --follow -- hosts/proximal/config/postgres/desired.md
```

For a subsystem-wide investigation that spans the migration, name both paths:

```sh
git log --all --full-history -- postgres hosts/proximal/config/postgres
```

Imported repositories retain their original commits and original historical
paths. For peecee, use its recorded source tip for pre-import archaeology:

```sh
git log 8bc7435470026341bf547de3da5bd0f654db464b -- health/check-whea.sh
git log --follow -- hosts/peecee/config/health/check-whea.sh
```

Use [`hosts/<name>/CHANGELOG.md`](hosts/proximal/CHANGELOG.md) for meaningful
machine-level operational changes. Use subsystem history and reports for dense
implementation evidence.

## Validation

Run the lightweight validator from the repository root:

```sh
scripts/validate-fleet.py
```

It checks manifest structure, host and role names, role references, shared-file
references, required host paths, self-contained subsystem documentation, broken
repository-local Markdown links, broken symlinks, and stale references to the
old single-host checkout paths.

## Secrets

Commit values and configuration, never plaintext credentials. The repository
may name a secret, record its owner and install path, and contain a template with
an empty or unmistakably fake value. It must not contain passwords, API tokens,
private keys, webhook URLs, secret-bearing DSNs, recovery codes, or decrypted
SOPS output.

Read [`secrets/README.md`](secrets/README.md) before importing another machine.
Import history can contain a secret even when the source tree is currently
clean; scan both the current tree and reachable history before merging it.

## Operating convention

Canonical files live in this repository; installed copies run on each machine.
After changing operational configuration, install it on the target host, verify
the live result, and record the rationale. Long-running services belong under
the host's service manager. Never end a turn with uncommitted or unpushed work.

Agents must read [`AGENTS.md`](AGENTS.md), then the target host and subsystem
instructions before acting.
