# striatum-train — the 04:30 semantic-environment train

Materialized 2026-08-31. Semantic-environment writes to striatum-next's main
(rendered policy / catalog / registry / decision records) land only at a
scheduled train epoch — one shared-pin movement per epoch — per the
maintenance-has-a-computed-successor ruling the Principal signed 2026-08-31
(sitting record RQ-340088 on the striatum-next ledger).

Authority chain for the current payload (payload-2026-08-31/):
- RQ-339830 — the signed Principal instruction (standing policy + governance sitting).
- RQ-339831 — the standing drain-deadlock policy record (code-class merges; context only here).
- RQ-340088 — the sitting acceptances (governance branch, mhcs Phase-2, B1(ii) hold, bootstrap pin renewal), selections verbatim.
- RQ-340254 — timing ("first train after withholding-a integrates", fallback 2026-09-07), D0010/D0016 decision-generation output pre-acceptance (this bracket only, D0013 form), and unattended-execution authority (merge --no-verify scoped to the accepted transaction; fail-closed abort), all verbatim.
- RQ-340279 — governance branch re-stage 377c0a0 -> 47e1b98 (decision-gen projection fix).

Mechanics: daily 04:30 timer -> striatum-train.sh. Condition: the three
withholding-guards checks read delivery_status != red on origin/main, OR the
date >= 2026-09-07. Then, fail-closed and fully logged
(~/.local/state/striatum-train/): preflight (clean tree, main == origin/main,
signed SHAs intact) -> script-computed consequence projection -> merge record
written on the ledger BEFORE the write -> merge both accepted branches
(--no-verify, scoped) -> policy artifact -> decision-gen D0010/D0016 ->
make deploy (full check inline) -> race guard -> push -> observed closes ->
Alertmanager notice. Any failure: rescue branch train-failed-<ts>, checkout
restored to origin/main, nothing deployed, severity=page alert.

Condition-read fix 2026-08-31 21:30 PDT (before the first fire): the registry
keys entries on `check_id` (not `id`) and a delivered check carries NO
`delivery_status` field, so the original read counted 0/3 even with every guard
delivered — only the 2026-09-07 fallback could ever have fired the train. Now
delivered == present and status != red (tested: live 0/3; synthetic 2/3).

Timing amendment 2026-08-31 22:15 PDT (Principal, verbatim "do it now", ledger
record RQ-345848 on striatum-next): the guard condition and the 09-07 fallback are
superseded for this payload; the transaction was executed immediately with
`STRIATUM_TRAIN_FORCE_RULING=RQ-345848 STRIATUM_TRAIN_WORKTREE=1` — the forced
mode logs the ruling and proceeds; the worktree mode runs the whole transaction
from a clean detached worktree at origin/main (the shared checkout carried another
session's uncommitted backends/*.yaml, which the train must never touch), pushes
`HEAD:main`, then fast-forwards the shared checkout non-fatally. Run log:
`~/.local/state/striatum-train/train-20260831T220944.log`.



The payload is one-shot (done-marker). Future payloads: new payload dir +
new pinned SHAs + a new Principal ruling on the ledger; the mhcs delivery is
expected to absorb this machinery into the compiler proper.

LANDED 2026-08-31 23:21 PDT — attempt 2 (run 20260831T230749, after attempt 1
failed closed on three latent defects in the signed branches, each fixed as a
striatum-next code-class landing): main e1d8124, deploy/20260901T062120Z-e1d8124de351,
merge record RQ-346414 before the write, observed closes RQ-346561–346566. The
done-marker is set and `striatum-train.timer` is disabled (`systemctl --user
disable --now`); the unit files stay installed for the next payload.
