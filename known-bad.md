# Known-bad settings ledger

Values tried on `proximal:5432` and reverted, with the evidence. The tuning
instrument reads this at preflight and must not re-propose a reverted value
without new evidence that overcomes the prior failure. Append a row whenever a
change is reverted (in the lab or in production).

| date | parameter | tried value | reverted to | why reverted | evidence |
|---|---|---|---|---|---|
| _(none yet)_ | | | | | |
