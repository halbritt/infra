## Testing workflow

Before choosing a test environment or writing test-launch plumbing, use the
`test-workflow` skill. Keep the agent's normal host tools, skills, authentication
and services. Make the application's test state disposable through its existing
fixtures; do not invent a container or replace the agent's home by default.

Read the repository's testing instructions. Where it has mise tasks, use
`mise tasks ls` and `mise tasks info <task>` to find the existing focused command.
Reuse the shared `host:exec` task for bounded process-spawning checks. Where
mise is not adopted, use the documented command and add a small task declaration
when useful. Fix recurring shared setup in `~/git/infra/shared/testing`, rather
than copying another runner or asking the owner to resolve the same setup again.
