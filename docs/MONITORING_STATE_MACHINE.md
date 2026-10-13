# Monitoring reading lifecycle as a state machine

A reading moves through three small machines that share one table. Each edge below is enforced on the server and has a test in
`backend/tests/test_monitoring_state_machine.py`.

## 1. The reading

```
recorded --approve--> approved                 (final; cannot be rejected afterwards)
recorded --reject---> rejected                 (final; the check is due again, the recorder is told)
```

- Only someone other than the recorder can approve or reject, and only a recorded reading (not one already approved or rejected).
- A rejected reading is ignored by due checks, compliance figures, failure counts and the approval backlog.

## 2. The failure (corrective action) of a failed reading

```
action_required --action--> retest_due --retest passes--> resolved
                                  |--retest fails-----> retest_failed (the failed retest opens its own failure)
manager decision: approve -> resolved ; reject -> action_required
any open state --its reading is rejected--> voided
```

## 3. The two-step log (defrosting, cooling)

```
(none) --time in--> open --time out recorded--> closed
open --reading rejected--> gone from the pending list
open for longer than the set hours --> one "time out missing" alert
```

## Edge cases found and what now happens

| Situation | Before | Now |
|---|---|---|
| A failed reading is rejected | Its failure stayed open, alerted, escalated and counted as a repeat failure | The failure is voided, its alerts are resolved, and it no longer counts |
| A passing retest is rejected | The original failure stayed resolved by a reading that no longer counts | The failure returns to retest due and can be retested again |
| A failed retest is rejected | The original stayed in retest failed | It returns to retest due |
| A retest of a rejected reading | Accepted | Refused; record the check again |
| A retest after a rejected retest | Refused as already retested | Allowed |
| A time in is rejected | It stayed on the pending list and a time out could still close it | It leaves the list and cannot be closed |
| A time in with a time out is rejected | Left the time out pointing at a rejected entry | Skipped; reject the time out first |
| A reading on an inactive point | Accepted | Refused |
| A time out never recorded | Nothing happened | One alert after the set hours (default 12) |

## Not changed, on purpose

- A reading approved by mistake cannot be reversed in the app; it stays in the audit trail.
- A failed reading can be approved while its failure is still open; approval confirms the entry, not the fix.
