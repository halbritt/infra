# Codex interruption hook repair — 2026-11-08

The owner reported repeated `hook returned invalid interrupt hook JSON output`
warnings and authorized fixing the installed hook. The coordinator updated
Cairn presence after an interruption, then returned a `hookSpecificOutput`
context envelope. Codex's Interrupt contract accepts an empty response or an
object with an optional `systemMessage`; the context envelope is rejected.

Cairn source commit `86a78e6f17ff1d97ef5a448c26ff18a5d90a44bc` returns `{}`
after the existing presence update and before inbox/context handling. The
existing interruption test now asserts the returned object as well as presence
and preservation of pending inbox work.

## Installed selection

The canonical host launcher is `coordination-entrypoint.py`, installed at
`~/.local/share/cairn/coordination/coordination.py` as a regular executable file.
It executes this complete bundle through `runpy`:

`~/.local/share/cairn/deployments/codex-interrupt-agent1333-20261108/lifecycle/`

The bundle is the checked previous installation plus the exact source patch,
applied and compared independently. Other bundle members retain their installed
bytes. This avoids deploying unrelated source changes. Coordinator SHA-256:

- Before: `92716c54be54a9f2e0fbe4dbd5edc77aecb02d6f7da3422708828376e63b0116`
- After: `6c656741464019e8fcedd8bb72a4945b75da24c1a09fd52afab491fc4102eeb6`

Codex profiles `.codex`, `.codex-harm`, and `.codex-3` retain their configured
hook commands, so subsequent hook invocations use the fixed bundle. The shared
entrypoint also serves other harness events, whose behavior is unchanged.
Account configurations, credentials, session state, and pinned inbox memory and
bridge files were not replaced. The presence watcher uses its separate
`cairn-424-a6dfabb3` deployment; no service or native session was restarted.

An initial symlink selection failed the loader's `O_NOFOLLOW` entrypoint check.
The original regular file was restored immediately. The final regular launcher
passed the isolated probe before installation and again at the live command path.

## Verification

- The new response assertion failed on the original implementation and passed
  after the repair. The same regression passed against the staged installed code.
- All 80 tests in `test_idle_wakeup`, `test_agent_coordination`, and
  `test_installed_lifecycle_bundle` passed, including the trunk integration check.
  An initial run from `scripts/` exposed a fixture import-path requirement;
  rerunning from the repository root with `PYTHONPATH=scripts` passed.
- A subprocess probe exercised actual hook stdin/stdout with synthetic state
  and an isolated fake API. It returned exit 0 and `{}`, changed presence to idle,
  and preserved the pending inbox intent. The staged launcher passed in
  Bubblewrap with networking and the source checkout unavailable; the installed
  command path passed the same probe.
- All five Codex/Claude inbox configuration bindings validated before activation.
  Real owner sessions were not interrupted for testing. The fixture establishes
  the installed output contract, not observation of a later owner interruption.

The deployment directory retains `deployment.json`, the exact `source.patch`,
`probe.py`, the launcher, and a complete `before/` bundle. No operational database
or provider was used for tests.

## Rollback

Atomically restore `before/coordination.py` from the retained deployment directory
to the stable coordination entrypoint, preserving mode `0700`. Its original
adjacent helpers and manifest were not modified. This restores the prior behavior,
including the reported interruption warning. Keep the fixed immutable bundle
while any process may still be executing it.
