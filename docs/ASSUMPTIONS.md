# Assumptions and items needing management approval

## Safety and compliance rules that need sign-off
1. **Temperature limits.** Every monitored stage has its own minimum and maximum. The seeded values (wash 55-65 C, final rinse 80-90 C) are placeholders. Set real limits from the manufacturer's instructions and your approved food-safety procedure before use. Only managers can change them, each change is audited, and past readings keep the limits that applied when they were taken.
2. **Machine display versus verification.** A stage is either a machine display reading or an independent probe reading. Model rinse, surface and sanitizing verification as separate stages with their own limits. The system does not decide which standard applies.
3. **Retest timing.** A corrective action schedules a retest after 15 minutes by default; an unresolved failure escalates to the manager after 60 minutes. Both are settings.
4. **Breakage approval.** Incidents of 5 or more units, or an estimated cost of 100 or more, need manager approval. Both thresholds are settings. Lost items are deducted even if stock would go negative, because the loss is real.
5. **Escalation and reminders.** Reminder 30 minutes before a deadline; escalate to the supervisor after 30 minutes overdue and to the manager after 120 minutes. All are settings.

## Behavioural assumptions
- **Late arrival.** Late is minutes after shift start once the shift's grace period is exceeded. The shift is the assigned shift whose start is closest to the check-in time.
- **Payable hours.** Elapsed time minus the shift's break. Overtime is payable time beyond the scheduled shift length, or beyond the shift's own overtime limit if set.
- **Daylight saving.** A wall-clock time that does not exist (spring forward) resolves to the next valid instant; an ambiguous one (fall back) resolves to the first occurrence.
- **Compliance percentages.** Numerator is completed, pending-verification and verified work. Denominator adds failed and overdue work. Waived and future tasks are excluded and reported separately.
- **Stock.** Balances are per item and per location and are derived from an append-only ledger. Opening stock needs a location. There is no per-location item master.
- **Permissions.** Supervisors can verify others' work but not their own, and managers cannot approve a transfer or corrective action they raised themselves.
- **Evidence uploads.** JPEG, PNG, WebP and PDF up to 5 MB, checked by file signature. Any signed-in user can fetch an uploaded file if they know its random name.

## Known limits
- The scheduler is in-process (single instance).
- The login lockout is in memory.
- Reports are limited to 93 days per request.
- Email and push notifications are not implemented; notifications are in-app only. The notification model and the single `notify` function are the integration point.
- Frontend has no automated tests; the backend suite covers business rules and authorization.
