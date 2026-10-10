# Assumptions and items needing management approval

## Safety and compliance rules that need sign-off
1. **Monitoring limits.** Monitoring is not limited to temperature: a check measures any parameter (temperature, ppm, pH, minutes) or asks a yes or no, optionally with a batch or lot reference for traceability, and is due at startup, at set times, every N minutes, on chosen weekdays or on a day of the month. Every numeric check has its own minimum and maximum, and a yes or no check passes on Yes. Templates (chiller, freezer, defrosting, cooking, reheating, cooling, hot holding, sanitiser, dishwasher, goods receiving, probe calibration) create a point with starting limits that must be reviewed. The seeded values (wash 55-65 C, final rinse 80-90 C) are placeholders. Set real limits from the manufacturer's instructions and your approved food-safety procedure before use. Only managers can change them, each change is audited, and past readings keep the limits that applied when they were taken.
2. **Machine display versus verification.** A stage is either a machine display reading or an independent probe reading. Model rinse, surface and sanitizing verification as separate stages with their own limits. The system does not decide which standard applies.
3. **Retest timing.** A corrective action schedules a retest after 15 minutes by default; an unresolved failure escalates to the manager after 60 minutes. Both are settings.
4. **Breakage approval.** Incidents of 5 or more units, or an estimated cost of 100 or more, need manager approval. Both thresholds are settings. Lost items are deducted even if stock would go negative, because the loss is real.
5. **Escalation and reminders.** Reminder 30 minutes before a deadline; escalate to the supervisor after 30 minutes overdue and to the manager after 120 minutes. All are settings.

## Behavioural assumptions
- **Late arrival.** Late is minutes after shift start once the shift's grace period is exceeded. The shift is the assigned shift whose start is closest to the check-in time.
- **Payable hours.** Elapsed time minus the shift's break. Overtime is payable time beyond the scheduled shift length, or beyond the shift's own overtime limit if set.
- **Daylight saving.** A wall-clock time that does not exist (spring forward) resolves to the next valid instant; an ambiguous one (fall back) resolves to the first occurrence.
- **Compliance percentages.** Numerator is completed, pending-verification and verified work. Denominator adds failed and overdue work. Waived and future tasks are excluded and reported separately.
- **Stock.** Balances are per item and per location and are derived from an append-only ledger. Opening stock needs a location. There is one item master shared by all locations.
- **Item master.** There is one inventory; categories tell items apart. An item is unique by name ignoring case and spacing, and its ID (`ITM-00001` style) is generated automatically. Items are retired, never deleted. Categories, units, suppliers and dropdown values are retired the same way.
- **Receiving.** A goods receipt adds stock through ledger entries that reference the document and supplier invoice number. A supplier invoice number can be posted once per supplier; a voided document frees it for correct re-entry. Voiding reverses stock with new entries and may take a balance negative if the goods were already used. Updating item costs from an invoice is optional and audited.
- **Suppliers and costs.** Only managers and supervisors can see suppliers, costs and receiving documents; stewards cannot.
- **Permissions.** Supervisors can verify others' work but not their own, and managers cannot approve a transfer or corrective action they raised themselves.
- **Evidence uploads.** JPEG, PNG, WebP and PDF up to 5 MB, checked by file signature. Any signed-in user can fetch an uploaded file if they know its random name.

## Known limits
- The scheduler is in-process (single instance).
- The login lockout is in memory.
- Reports are limited to 93 days per request.
- Email and push notifications are not implemented; notifications are in-app only. The notification model and the single `notify` function are the integration point.
- Frontend has no automated tests; the backend suite covers business rules and authorization.
- **Count limit.** A physical count cannot exceed everything received into that location for the item (opening stock, receipts, transfers in, returns and positive adjustments). Issues and breakage do not lower the limit.
- **Receiving discounts.** Line total = quantity x unit cost less the line discount (amount or percent). Sub total = sum of the undiscounted lines. Total = sub total less every line discount and the invoice discount, which applies to the amount left after line discounts. Item cost updates use the net unit price.
- **Week off and absence.** A week off is a shift of its own kind that carries no hours; it cannot overlap a working shift on the same weekday. Week off days are not scheduled and are not chased for check-in. An absence or leave (absent, sick, annual, unpaid, other) is recorded by a manager or supervisor, once per employee and day, and can be cancelled with a reason. Leave is excluded from scheduled work; a recorded absence counts as absent.
- **Role sync.** Roles and their permissions are synchronised to the database on every startup so new permissions reach existing installs.
