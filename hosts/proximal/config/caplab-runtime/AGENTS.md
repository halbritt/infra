# Proximal CAPLAB runtime host integration

Read [`README.md`](README.md) before changing or enacting this subsystem.

CAPLAB product and research authority lives in the standalone repository at
`/home/halbritt/git/caplab`. This directory owns only the `proximal` host
integration: local identities, installed non-secret config, expiry enforcement,
and the bounded bootstrap/rollback tool. Do not add CAPLAB runtime or research
logic here.

Never commit or print a Garage key, credential file, PostgreSQL password, or
secret-bearing command output. `SOURCE_COMMIT` must be a full standalone CAPLAB
commit containing the runtime entry point and hash-locked requirements. A valid
Git hash alone is not runtime fitness.

The synthetic-effect marker is irreversible. Before it is armed, empty
bootstrap rollback requires independent zero-state checks. After it is armed,
only access disablement, cleanup-plan generation, and quarantine are permitted.
Do not add purge, object deletion, application-row deletion, fault injection, a
daemon, or a public endpoint to this subsystem.

Repository checks do not authorize installation or live execution. Preserve the
current campaign ID and expiry unless a later CAPLAB decision and authorization
replace them explicitly.
