# Secret storage policy

This directory documents secret handling for the infrastructure repository. It contains no secret
values today.

## What belongs outside plaintext Git

Do not commit passwords, API tokens, private keys, webhook URLs, secret-bearing
DSNs, recovery codes, generated credential bundles, or decrypted SOPS output.
Configuration may record a secret's name, owner, mode, consumer, and installed
path without recording its value.

The `proximal` host currently references these secret classes outside Git:

- Plane API and application environment files under `~/.config/plane/` and the
  service deployment directories;
- Cloudflare tunnel credential JSON and API credentials;
- Garage RPC, admin, metrics, and application key material;
- PostgreSQL role passwords, CAPLAB temporary credentials, and exporter DSNs;
- Grafana administrator data, Home Assistant InfluxDB credentials, and the
  Alertmanager Slack webhook;
- Praxis, Hermes, and Slack application tokens;
- OpenRouter and other model-provider API keys;
- the SMS gateway's HTTP authentication values.

Those files remain at their documented external paths until a separate,
service-by-service migration is tested. This repository-layout change does not read,
copy, rotate, or relocate their values.

The repository also contains sensitive metadata that is not an authentication
secret: private addresses, public hostnames, service topology, hardware serial
or modem identifiers, a cellular number, and Slack app or member identifiers.
Keep repository access appropriately restricted even when credential scans are
clean.

## SOPS and age target layout

When encrypted-in-Git storage is approved, use paths such as:

```text
secrets/
└── hosts/
    └── proximal/
        ├── plane.sops.yaml
        ├── observability.sops.yaml
        └── praxis.sops.yaml
```

Use one encrypted document per independently rotated or deployed secret set.
Do not create a single infrastructure-wide blob. Name only real hosts and services; do not
invent entries for machines that have not been imported.

An age public recipient may be committed in a future `.sops.yaml`. The matching
age private identity must remain outside Git, preferably in an operator hardware
token, password manager, or root-only host file. Do not add placeholder recipient
keys that could be mistaken for a deployable policy.

Only SOPS-encrypted files with a `.sops.yaml`, `.sops.json`, or `.sops.env`
suffix may be committed below `secrets/`. Plaintext files are ignored and the
infrastructure validator rejects unexpected files in this directory.

## Migrate one secret set

1. Inventory the current source path, owner, mode, consumers, reload behavior,
   rotation procedure, and rollback path without printing the value.
2. Confirm the age recipients with the owner. Add and review the SOPS creation
   rule before encrypting anything.
3. Create plaintext only outside the repository in a `0700` temporary directory
   with `umask 077`, or pipe it directly into SOPS.
4. Encrypt to `secrets/hosts/<host>/<service>.sops.yaml`. Verify that `sops -d`
   succeeds for every intended operator or deployment identity, but do not send
   decrypted output to logs or the terminal transcript.
5. Materialize the secret at the service's existing external install path with
   its existing owner and restrictive mode. Prefer `sops exec-file` or a
   root-only atomic install step so plaintext is short-lived.
6. Reload or restart only the affected service and run its documented health
   check.
7. Remove the old plaintext source only after the encrypted deployment and
   rollback path are proven. Record the migration in the host changelog.
8. Rotate the credential if its value was ever exposed in a commit, log, issue,
   paste, shell history, or agent transcript. Encryption does not revoke an
   already exposed credential.

Never decrypt all infrastructure secrets as a validation step. Validate file structure
without decryption, then test the smallest affected secret set with the least
privileged identity.

## Import rule

A source repository can contain a deleted secret in reachable history. Scan the
working tree and all reachable commits before importing it. If a real credential
is found, rotate it first and create a sanitized history outside this repository.
Do not merge the leak and then delete the file: the value remains in Git objects.
