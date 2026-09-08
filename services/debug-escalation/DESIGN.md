# Debug Escalation — Design & Requirements Spec

**Status:** proposed · **Date:** 2026-09-08 · **Owner:** unassigned

---

## 1. Problem

Realtime hardware debugging with a customer standing at a bench is a
single-threaded, low-latency loop: a measurement is taken, a symptom is reported,
a hypothesis is formed, and the next probe is chosen — in seconds.

The failure mode is not "the model is too weak," it is **correlated error**. A
single backend, however capable, walks the same reasoning groove; two models
from the same lineage share blind spots. The AEM13921 session is the canonical
proof: the diagnosis stalled on a *false* self-consistency story until an
adversarial cross-check — "it *did* harvest before VSTO dropped" — forced a
re-derivation (config-masking, not temperature), which was the actual answer.

We want an **escalation path**: when a case stalls, or on demand, hand the same
evidence to a panel of *unlike* models and have an arbiter collate the
disagreement into one recommendation.

---

## 2. Requirements spec

### 2.1 Functional requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| **FR-01** | **Manual escalation trigger.** The debugger can request escalation with a single keyword/shortcut at any point in a live session, with no argument or setup. | Typing the trigger during a session produces a second-opinion response without interrupting the primary answer. |
| **FR-02** | **Automatic escalation signal.** The primary model may emit a low-confidence / "raised hand" signal on its own turn; the router acts on it. | A turn with confidence below a threshold (or an explicit `RAISE_HAND` marker) is routed to the panel without operator action. |
| **FR-03** | **Evidence bundle, not chat scroll.** On escalation, the current case is serialized into a structured bundle — symptom log, measurements, hypotheses tried, open questions — and handed to each panel member intact. | No panel member re-derives context from raw transcript; each receives the identical bundle. |
| **FR-04** | **Cross-class second opinion.** At least one panel member is from a *different aliasing class* than the primary (different vendor/architecture/lineage). | The panel composition is validated against an aliasing-class table before dispatch; same-lineage-only panels are refused. |
| **FR-05** | **Arbiter collation.** A designated role (the scribe) reconciles the panel's outputs into one recommendation — agreement, divergence, and the *specific* point of disagreement — rather than returning a raw transcript. | Output is a single recommendation with an explicit "where they disagree" section. |
| **FR-06** | **Operator checkpoint on irreversible actions.** The system proposes; it never auto-applies a hardware change, rework, or firmware write. Any conclusion that implies an irreversible act pauses for operator authority. | A recommendation that implies rework/write is delivered as a *proposal* with an explicit accept step; nothing is executed automatically. |
| **FR-07** | **Provenance / traceability.** Every escalation is recorded: trigger, evidence bundle hash, panel composition (model + class), each member output, the arbiter's collation, and the operator's disposition. | The escalation record is append-only and re-readable after the fact. |

### 2.2 Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| **NFR-01** | **Latency — primary path.** The tier-0 answer is synchronous and must not be gated on the panel. | First answer ≤ the incumbent's current turn latency; escalation is *async/parallel*, never blocking it. |
| **NFR-02** | **Latency — escalation path.** A manual escalation returns a collated second opinion fast enough to be useful at a bench. | Panel round-trip ≤ ~30 s budget (configurable); progress is streamed so partial answers land sooner. |
| **NFR-03** | **Cost discipline.** Escalation is the expensive path and must be metered, never the default. | Per-session escalation spend is capped; tier-0 stays free (local). |
| **NFR-04** | **Fail-closed.** A provider outage or a refused panel composition degrades to the tier-0 answer plus an explicit "escalation unavailable" note — never a silent fallback to a weaker correlated model. | Provider failure returns a typed `escalation_unavailable`, not an unmarked substitute answer. |
| **NFR-05** | **No credential / trace leakage.** Evidence bundles and escalation records never capture secrets; any token/URL in a paste is the operator's explicit act, not a default. | Bundle schema excludes credential-bearing fields; records are secrets-scanned before persist. |
| **NFR-06** | **Determinism where it matters.** The routing decision and collation are reproducible given the same bundle + panel; model outputs remain nondeterministic. | Same bundle + same panel → same escalation record shape and routing trace. |

---

## 3. Architecture

Three tiers and four roles. Nothing here invents new ontology where an existing
concept has a home; the borrowed-concept table (§4) maps each piece.

```
                ┌──────────────────────────────────────────────┐
  debugger ───► │ Router                                        │
  (operator)    │  tier-0 fast path (synchronous, free)         │
                │  escalation decision (manual FR-01 / auto FR-02)│
                └───────┬──────────────────────────┬────────────┘
                        │ evidence bundle (FR-03)  │
                        ▼                          ▼
                ┌────────────────┐        ┌────────────────────┐
                │ Panel          │        │ Arbiter (scribe)    │
                │  member A (T0) │──────► │  collate → one      │
                │  member B (≠class)│      │  recommendation    │
                │  member C …    │        │  + disagreement map │
                └────────────────┘        └─────────┬──────────┘
                                                    │ proposal (FR-06)
                                                    ▼
                                         Operator checkpoint (human)
```

### 3.1 Tier ladder

| Tier | Backend | Class | Cost / latency | Role |
|---|---|---|---|---|
| **T0** | Local llama.cpp (`Qwen3.8-27B`) | local / Qwen lineage | free, ~57 tok/s, zero RTT | Primary — symptom parse, datasheet grind, register-map work. Always on. |
| **T1** | OpenRouter (e.g. `deepseek-v4-pro`) | hosted / DeepSeek lineage | metered, seconds RTT | First escalation rung; still single-opinion. |
| **T2** | OpenRouter panel — **≥1 member from a different aliasing class** | mixed / cross-vendor | metered, parallel | The second opinion (FR-04). The divergence *is* the value. |

### 3.2 Roles (borrowed, not invented)

- **Router** — decides *when* to escalate (FR-01/FR-02) and *what* goes in the
  evidence bundle (FR-03). Thin; no judgment it can avoid. ≈ Council's
  scheduling admission + Striatum's Driver boundary ("the Driver is not
  intelligent; if it seems to need judgment, a declaration is underspecified").
- **Panel members** — named model identities with declared model + reasoning
  effort, exactly like Council's **members**. Their only job is an independent
  read of the same bundle.
- **Arbiter (scribe)** — collates the panel into one recommendation (FR-05).
  ≈ Council's **scribe** ("drafts and revises syntheses… not a second chair").
- **Operator checkpoint** — the human gate on irreversible acts (FR-06).
  ≈ Council's **operator checkpoint**; mirrors Striatum's "consensus does not
  itself adopt anything" — *adoption* is always a separate human act.

### 3.3 The evidence bundle (FR-03)

A versioned, structured case object, not freeform chat:

```
case {
  case_id, opened_at
  symptom_log[]          // ordered, timestamped observations + measurements
  measurement_table[]    // {name, value, unit, method (DMM/register/…)}
  hypotheses[]           // {statement, status: open/refuted/live, evidence_for_against}
  registers[]            // {addr, name, value} when I²C/register state is known
  open_questions[]       // explicit unresolved items
  constraints[]          // e.g. "no debug port on-site", "no firmware reflash"
}
```

Bundle integrity: hashed at dispatch (FR-07); every member receives the *same*
bytes, so divergence is attributable to model, not to different inputs.

---

## 4. Borrowed concepts (traceability)

| This service | Council | Striatum |
|---|---|---|
| Panel members (named models) | `member` (identity persists across model/name changes) | execution backends as crash-only adapters |
| Arbiter / collation | `scribe` (synthesis role, not a chair) | — |
| Escalation signal (FR-02) | `raised hand` (request for the floor) | `escalation` record type |
| Operator checkpoint (FR-06) | `operator checkpoint`; `adoption ≠ consensus` | Principal as escalation resolution authority |
| Cross-class second opinion (FR-04) | — | `aliasing class` / independence (RFC 0019) |
| Tier-0 vs escalation placement | — | `capability-aware-placement`; model choice = scheduler policy |
| Provenance ledger (FR-07) | `deliberation ledger` | provenance ledger (records confer no authority) |

---

## 5. Worked example — AEM13921 replay

- **T0** handles symptom parse ("USB won't recover", LIC drains to cutoff) and
  datasheet lookup — the register map, charge-temperature conditions.
- **Raised hand / manual trigger** fires when the primary lands on the thermal
  divider but *self-contradicts* on "why did it harvest before."
- **Bundle** carries the measurement table (NTC 83.9 kΩ, RDIV ≈ 12.8 kΩ, VR13=VR14=0 V,
  VPV=VOC, VINT=2.2 V) + the open question ("worked before VSTO dropped — how?").
- **Panel** — a Qwen-lineage member and a cross-class member both read the bundle.
  The cross-class member flags that a *fixed* resistor fault can't be
  temperature-conditional, forcing the config-masking re-derivation.
- **Arbiter** collates: "divider mis-sized (agreed) → cold-charge trips ~41 °C;
  'why it worked earlier' is config-masking (disagreement resolved), fix is
  identical either way."
- **Operator checkpoint** — the TH_MON→VINT rework / I²C write is delivered as a
  *proposal*, applied by the engineer, not by the service.

---

## 6. Open questions

1. **Confidence signal shape (FR-02).** Local llama.cpp exposes no calibrated
   confidence. Use an explicit `RAISE_HAND` marker + cheap heuristics, or add a
   calibration probe? Lean: marker-first, calibration later.
2. **Aliasing-class table.** Who maintains the class map (vendor/architecture/
   lineage), and what qualifies as "different class"? Reuse RFC 0019's
   independence vocabulary or start with a small static table?
3. **Panel size default.** 2 members (fast) vs 3 (tie-break) for a bench loop?
4. **Realization target.** Is this a Hermes-side routing layer, a Council topic
   preset, or a thin standalone arbiter? Council already implements members /
   scribe / ledger — this may be a *configuration* of Council plus a bundle
   serializer, not a new service.
5. **Latency budget (NFR-02).** Confirm ~30 s is acceptable at a customer bench
   before pinning it.

---

## 7. Phased rollout / definition of done

- **Phase 0 (prove the mechanism):** manual keyword trigger (FR-01) → bundle
  serializer (FR-03) → two-member cross-class panel (FR-04) → scribe collation
  (FR-05). Operator checkpoint (FR-06) as a hard stop. Run it against a *replayed*
  AEM13921 case, not a live customer.
- **Phase 1:** auto escalation signal (FR-02), provenance ledger (FR-07),
  cost cap (NFR-03), fail-closed path (NFR-04).
- **Done** when Phase 0 + 1 requirements pass against three real historical
  debug cases and one live (non-customer) session.
