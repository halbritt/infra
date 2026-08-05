# Import a device, service, or provider repository

Use this procedure for a standalone repository that maps to `devices/`,
`services/`, or `providers/`. Machine repositories use
[`importing-hosts.md`](importing-hosts.md), which also defines the shared secret,
history, path, verification, and cleanup rules.

## Select the resource boundary

Read [`CONTEXT.md`](../CONTEXT.md) before choosing a prefix:

- `devices/<name>/` for an appliance such as a printer, router, switch, or Home
  Assistant Yellow;
- `services/<name>/` for desired state managed independently of one host;
- `providers/<name>/` for an external provider control plane such as Runpod,
  Google Cloud, or OpenRouter.

Do not split one source repository across categories during import. Import its
history intact under the closest existing boundary, then move genuinely
independent configuration in later commits with explicit rationale.

## Preserve history

Start from a clean, synchronized infrastructure checkout. Read the source
instructions and inventory its current files, ignored files, symlinks,
submodules, absolute paths, and service consumers. Scan the current tree and all
reachable history for credentials without printing values. Rotate and sanitize
the source history before import if a real credential is found.

For a resource with no existing target directory, import without squashing:

```sh
category=devices  # replace with services or providers when appropriate
name=<stable-resource-name>
source_repo=/absolute/path/to/source-repository
source_branch=<source-default-branch>

git subtree add \
  --prefix="${category}/${name}" \
  "${source_repo}" "${source_branch}"
```

If a partial target already exists, import into
`${category}/${name}/source-import`, then reconcile it in a separate commit.
Remove the temporary child after every source file is accounted for. Record the
source URL, branch, tip, subtree commit, scan method, and deliberate exclusions
in the resource notes.

Normalize absolute checkout paths and install mappings only after the subtree
commit. Reinstall and verify any runtime consumer that executes from the
checkout. Run the source checks and `scripts/validate-infra.py`, inspect the
resource-scoped history, commit, and push. Remove or trash the standalone
checkout only after its source tip is reachable from `infra`, the new path is
live, and the repository registry has been updated.

## Exact Home Assistant import sequence

The current Home Assistant source is `/home/halbritt/git/homeassistant` on
`master`. It describes a Home Assistant Yellow appliance, so its initial target
is `devices/homeassistant/`.

1. Confirm the source is clean and synchronized and record its exact tip.
2. Scan the current tree and reachable history for Home Assistant access tokens,
   private MCP URLs, `secrets.yaml`, add-on credentials, backup keys, SSH keys,
   and environment files. Record only paths, commit IDs, and secret classes.
3. Rotate and sanitize before import if the scan finds a real credential.
4. Run the unsquashed subtree command above with `category=devices`,
   `name=homeassistant`, `source_repo=/home/halbritt/git/homeassistant`, and
   `source_branch=master`.
5. In a second commit, add resource notes and normalize references to
   `hosts/proximal/` and other infrastructure paths. Keep appliance-specific
   state under the device; extract service-level Home Assistant configuration
   only after a real independent ownership boundary appears.
6. Run the source checks, `scripts/validate-infra.py`, and a read-only live
   Home Assistant access probe. Do not expose token-bearing URLs in logs.
7. Verify the recorded source tip is an ancestor of `infra`, update
   `project-fleet`, then move the standalone checkout to trash. Do not delete the
   GitHub source repository as part of the checkout cleanup.
