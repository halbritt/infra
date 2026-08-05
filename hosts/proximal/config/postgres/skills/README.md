# skills/ — vendored reference skills

Vendored, version-pinned agent skills that the tuning instrument
(`~/git/prompts/POSTGRES_TUNING.md`) and any fleet agent working this repo can
read as a Postgres best-practices reference library. These are **reference
material, not desired-state** — nothing here is asserted against the live
cluster. Instance-specific application of these rules lives in `reports/` (see
the mined-insights report) and in `baseline.md` / `desired.md` / `known-bad.md`.

## supabase-postgres-best-practices

- **Source:** https://github.com/supabase/agent-skills `skills/supabase-postgres-best-practices`
- **Pinned commit:** `1356046015476711a769601079262b5635929427` (2026-06-05)
- **Vendored:** 2026-06-17 · **License:** MIT (Supabase) — see the rule files' headers
- **Version:** 1.1.1

Vendor-neutral Postgres performance/correctness rules across 8 categories
(`query-`, `conn-`, `security-`, `schema-`, `lock-`, `data-`, `monitor-`,
`advanced-`). Start at `SKILL.md`, then read individual `references/<prefix>-*.md`
rule files. The authoring scaffolds (`_template.md`, `_contributing.md`) were
dropped; everything content-bearing was kept verbatim.

### Not vendored (intentionally)

The companion `supabase` skill from the same repo was **not** vendored — it is
Supabase-cloud platform guidance (supabase-js/SSR, Edge Functions, the Data API,
hosted Auth, the Supabase CLI/MCP) with little bearing on a self-hosted
single-node cluster. Its handful of generic-Postgres security facts (views
bypass RLS, `SECURITY DEFINER` bypasses RLS, UPDATE needs a SELECT policy, etc.)
were extracted into the mined-insights report under `reports/` instead.

## Refreshing

These are pinned, not a submodule — they do not auto-update. To refresh, re-pull
the upstream repo, re-copy under the new commit, and bump the commit/date above.
