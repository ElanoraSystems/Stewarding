# Data structures and algorithms - implementation plan

This is the plan, separate from the findings in [DSA_SUMMARY.md](DSA_SUMMARY.md). Phases 1 to 5 are implemented, with the results
below; the one remaining item is Phase 6.

## 0. Rules for every phase

1. Measure first with `python -m scripts.benchmark` and record the numbers in the pull request.
2. Keep the old method as a test reference. A new path must match it on random data before it ships.
3. No new dependency unless the standard library cannot do the job. Say so in the pull request.
4. No schema change without an Alembic migration that has been run up, down and up again on SQLite and PostgreSQL.
5. Each change is its own commit so it can be reverted alone.
6. Done means: tests green on SQLite and PostgreSQL, benchmark not slower anywhere, and a query-count test where the
   change is about queries.

## Phase 1 - Done in this change set

| Item | Technique | Files |
|---|---|---|
| Reconciliation in one pass | Database aggregation plus hash maps | `services/inventory.py` |
| Due check and compliance matching | Sorted list plus binary search | `services/monitoring.py`, `services/metrics.py` |
| Settings read once per transaction | Memoisation on the session | `services/settings.py` |
| Corrective actions for a page of readings | Batch lookup dictionary | `api/monitoring.py` |
| Receipt lines for the record | Batch and group | `services/records.py` |
| Duplicate and near-duplicate item names | Compact key, token set, bounded edit distance | `services/similarity.py`, `api/inventory.py`, `pages/ItemForm.tsx` |
| Benchmark and equivalence tests | Synthetic large dataset, brute-force reference | `scripts/benchmark.py`, `tests/test_algorithms.py` |

## Phase 2 - Remove repeated lookups inside a request (done)

**Result.** Dashboard 212 to 81 queries and 228 ms to 65 ms; due checks 51 to 3 queries; monitoring stats 35 to 3. The time target
(under 80 ms) is met. The query target (60 or fewer) is not: 81 remain, and Phase 6 covers them. Task 2.4 (item list batching) needed
no change: the page already makes a fixed 11 queries however many rows it shows.

**Evidence.** A dashboard request still runs 132 queries on the small benchmark and 182 on the large one. The profile
by table: `temperature_reading` 25, `equipment_schedule` 16, `checklist_instance` 14, `employee_location` 13,
`shift` 12, `breakage_incident` 8, `attendance_record` 7, `equipment` 7.

| Task | Technique | Where | Expected effect | Effort |
|---|---|---|---|---|
| 2.1 Load shifts, locations and employee names once per request | Request-scoped lookup dictionaries kept on the session, dropped at transaction end (same pattern as settings) | `services/monitoring.py`, `services/metrics.py`, `services/reports.py`, `api/dashboard.py` | About 30 fewer queries per dashboard request | 1 day |
| 2.2 Work out the user's allowed locations and permissions once per request | Same session-scoped memo | `deps.py` (`scoped_locations`, `permissions_of`) | About 15 fewer queries | 0.5 day |
| 2.3 Batch the monitoring statistics across points | One query for all schedules and one for all readings of the location, grouped into dictionaries by point and schedule | `metrics.monitoring_stats`, `monitoring.due_checks` | About 40 fewer queries; due checks from 50 to about 5 | 1.5 days |
| 2.4 Batch the item list | One grouped query for balances and received quantities per page, already partly done | `api/inventory._serialize_items` | Keeps the item list flat as the page grows | 0.5 day |

**Acceptance.** Dashboard at or under 60 queries and under 80 ms on the large benchmark. A query-count test fails if a
change makes the count depend on the number of points or locations. All existing figures unchanged (the comparison tests
for compliance, attendance and checklists stay in place).

**Risk.** A request-scoped copy could hide a change made earlier in the same request. Mitigation: drop it on flush of
the affected tables, as the settings copy does, and test each lookup with a write followed by a read.

## Phase 3 - Indexes for the large tables (done, one index)

**Result.** Plans checked on PostgreSQL with `EXPLAIN (ANALYZE)`. Added `stock_transaction (location_id, occurred_at, item_id)`: the date-range
read went from 1.58 ms to 0.75 ms. The readings index showed no change and was left out. Checklist and attendance indexes were not
added for lack of a measured problem. Re-run the plans on production data before adding any more.

**Evidence to collect first.** Run the slowest endpoints on PostgreSQL with `EXPLAIN (ANALYZE, BUFFERS)` and enable
`pg_stat_statements` on the production database for a week. Add an index only where the plan shows a scan.

| Candidate | Reason |
|---|---|
| `stock_transaction (location_id, occurred_at, item_id)` | Reconciliation and movement reports filter by location and date range and group by item |
| `temperature_reading (equipment_id, recorded_at)` | Compliance stats and the monitoring log filter by point and time |
| `checklist_instance (location_id, local_date, status)` | Dashboard, charts and reports filter by location and day |
| `attendance_record (location_id, local_date)` | Attendance stats and the sheet |

**Acceptance.** Each index shows a plan change and a measured gain, and write cost on the ledger stays within 5 percent
on the benchmark insert test. One migration per index with a matching downgrade.

**Risk.** Indexes slow writes and use disk. Keep only the ones the plans justify.

## Phase 4 - Month-end balance snapshots (done)

**Result.** Built by the scheduler, verified every run, self-healing, and identical to the full sum in tests. At the benchmark size
reconciliation goes from 13 to 7 ms on PostgreSQL; the gain grows with history. The trigger below now only says when it starts to matter.

**Trigger.** Reconciliation or stock reports take more than 300 ms on production data, or the ledger passes about
2 million rows.

**Technique.** Prefix sums. At each month end, store the closing quantity per item and location in a
`stock_snapshot` table, written by the existing scheduler. Reconciliation then starts from the previous snapshot and sums
only the current month instead of the whole history.

**Rules.** The ledger stays the single source of truth. A snapshot is a cache that can be rebuilt; a nightly check
compares each snapshot with a full sum and raises an alert on any difference. A back-dated correction rebuilds the
affected months.

**Effort.** 3 days including the migration, the rebuild command and the check.

## Phase 5 - Item search at larger scale (done)

**Result.** Stored `compact_key` and `token_key` with indexes make the duplicate check an index lookup. The similar-name warning scans every name
up to 5,000 items and narrows candidates in the database above that. The trigram alternative was not needed.

**Trigger.** The item master passes about 20,000 names or the lookup takes more than 100 ms.

**Technique.** Keep the compact key and token set as stored, indexed columns so most comparisons happen in the
database, and run the edit distance only on the few candidates that share a token or the same first characters.
PostgreSQL trigram search (`pg_trgm`) is the alternative if installing an extension is acceptable.

**Acceptance.** The same classification results as the current in-memory method on a fixed set of 500 name pairs.

## Phase 6 - Batch the remaining dashboard statistics (proposed)

**Evidence.** 81 queries remain per dashboard request, one per statistic per location window: `checklist_instance` 14, `employee_location` 8,
`breakage_incident` 8, `attendance_record` 7, `shift_assignment` 6, `absence_record` 6.

| Task | Technique | Effort |
|---|---|---|
| 6.1 Checklist statistics for all locations at once | One query filtered by the location list, grouped into dictionaries by location and day | 1 day |
| 6.2 Attendance statistics for all locations at once | The same, for assignments, records and absences | 1 day |
| 6.3 Breakage and employee-location lookups | One grouped query each | 0.5 day |

**Acceptance.** Dashboard at 40 queries or fewer, and every figure unchanged (the existing comparison tests stay in place).

## Order and effort

| Order | Phase | Effort | Value | Decide by |
|---|---|---|---|---|
| Done | Phases 1 to 5 | - | See the results under each phase | - |
| Next | Phase 6 | about 2.5 days | Dashboard under 40 queries | Next release |

## Verification and rollout

- **Before merging:** unit and comparison tests, query-count tests, the benchmark on the large dataset, and the full suite on
  SQLite and PostgreSQL.
- **Staging:** run the benchmark against a copy of production data, and compare reconciliation, compliance and attendance
  totals with the previous release for the same period; they must match exactly.
- **After release:** watch response times and the slow query log for a week. The settings, lookup and snapshot copies are
  plain caches, so a rollback is a revert of one commit with no data to repair.

## Open questions for the owner

1. What is the largest item master and ledger expected in the first two years? This decides whether Phases 4 and 5 are ever needed.
2. Is `pg_stat_statements` allowed on the production database?
3. Is one worker still the deployment model? If several workers are planned, the session-scoped copies stay correct, but any
   shared cache would need an agreed invalidation rule first.
