# Debug Escalation

**Status:** proposed (2026-09-08) — not yet realized.

**One line:** a multi-model escalation path for realtime hardware debugging, so an
on-site debugger (a customer-facing engineer) can tap stronger models from a
*different* model class when a case stalls, instead of being pinned to a single
backend.

**Driving use case:** Joshua's on-site AEM13921 session (2026-09-08). The
breakthrough was an adversarial cross-check ("it *did* harvest before VSTO
dropped"), not more parameters — the kind of pressure a panel of unlike models
automates.

**Ownership:** proposed service; no host realizes it yet. The full design and
requirements spec live in [`DESIGN.md`](./DESIGN.md).

**Prior art drawn on (on-box):**

- [`~/git/council`](../../git/council) — members (named models), chair (arbiter),
  scribe (synthesis), deliberation ledger (challenge/ready/ballot/consensus),
  raised hand (escalation signal), operator checkpoint (human authority gate).
- [`~/git/striatum-next`](../../git/striatum-next) — model choice is *scheduler
  policy*; execution backends are crash-only adapters behind a submit/admit seam;
  escalation is a first-class record type; backend qualification (RFC 0019)
  names **independence / aliasing class** (uncorrelated models) and
  capability-aware placement.

See [`DESIGN.md`](./DESIGN.md) for how each concept is reused.
