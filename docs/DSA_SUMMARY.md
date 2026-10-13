# Data structures and algorithms in Plato - summary and impacts

This document says where Plato uses data structures and algorithms, what was changed in this round, what it measured,
what it affects, and what was deliberately left alone. The plan for the remaining work is in
[DSA_IMPLEMENTATION_PLAN.md](DSA_IMPLEMENTATION_PLAN.md).

## 1. The approach

The goal was faster, more correct behaviour, not more clever code. Each change had to meet three tests:

1. A measured problem on a realistic dataset, not a guess.
2. A standard technique that fits the problem (hash grouping, binary search, edit distance, memoisation, batching).
3. A test showing the new code gives the same answer as the obvious slow version.

The measurements come from `backend/scripts/benchmark.py`. It builds a throwaway database with 400 items, 3 locations,
91,200 stock movements, 34,967 monitoring readings, 14 monitoring points and 45 days of history, then times the
heaviest read paths and counts database queries. Run it with `python -m scripts.benchmark` from `backend/`
(add `--small` for a quick run).

## 2. Results

| Path | Before | After | Change |
|---|---|---|---|
| Month-end reconciliation, one location | 2,417 ms | 22 ms, or 5 ms with snapshots | about 110 to 480 times faster |
| `GET /api/stock/reconciliation` | 2,455 ms | 12 ms | about 200 times faster |
| Monitoring compliance stats, 45 days | 696 ms, 35 queries | 65 ms, 3 queries | about 11 times faster |
| `GET /api/dashboard` | 228 ms, 212 queries | 65 ms, 81 queries | 3.5 times faster, 2.6 times fewer queries |
| Due checks for today | 7.2 ms, 51 queries | 1.8 ms, 3 queries | 4 times faster, 17 times fewer queries |
| Monitoring log page of 25 readings | 31 queries | 7 queries | 4.4 times fewer queries |

On PostgreSQL the same run gives reconciliation 13 ms (6.6 ms with snapshots), dashboard 95 ms and 81 queries.
Times are the best of three runs on one laptop; use them to compare, not as production promises.
The suite passes on SQLite and PostgreSQL (457 tests).

## 3. What was implemented

### 3.1 Reconciliation: group and total in the database (hash grouping)
- **Where:** `services/inventory.reconcile`.
- **Problem:** for every item it re-scanned every stock movement of the location, so the work grew with
  items times movements (O(I x T)). With 400 items and 30,000 movements for the location that was 12 million comparisons.
- **Change:** the database now sums movements grouped by item, movement type and "before the month or inside it", and the
  code builds two dictionaries from that small result. The work grows with movements once (O(T)) and only a few thousand
  summary rows cross from the database.
- **Guarantee:** a test compares it with the original scan on 600 random movements across five months.

### 3.2 Matching due checks to readings: sorted list and binary search
- **Where:** `services/monitoring.has_reading`, used by `slot_status` (due checks) and `metrics.monitoring_stats`
  (dashboard and reports).
- **Problem:** each due slot was compared with every reading, so a month of hourly checks cost slots times readings.
- **Change:** reading times are sorted once per check and a slot asks "is there a reading in this window?" with
  `bisect`, O(log n) per slot. Readings are also loaded as four plain columns instead of full objects.
- **Guarantee:** a test checks it against `any(...)` over 2,000 random windows, including the window edges
  (start included, end excluded).

### 3.3 Settings: read once per transaction (memoisation)
- **Where:** `services/settings.get_setting`.
- **Problem:** most settings are not stored and fall back to defaults, and the database cannot cache a missing row,
  so every call asked the database again. One dashboard request made dozens of such calls.
- **Change:** all stored settings are read once and kept on the database session for the length of the transaction.
  The copy is dropped when the transaction ends or a setting is changed, so it can never go stale across requests.
- **Guarantee:** tests show one query for 50 reads, that a flushed change is seen at once, and that a rolled back
  change is forgotten.

### 3.4 Monitoring log: one query for the whole page (batch lookup table)
- **Where:** `api/monitoring._serialize_readings`.
- **Problem:** the newest corrective action of each reading was fetched with its own query (the "N+1" pattern).
- **Change:** one query fetches the actions for the page and a dictionary keyed by reading id serves them.
- **Guarantee:** a test shows the query count is the same for 1 failed reading and 15.

### 3.5 Receipts record: lines fetched together
- **Where:** `services/records._receipt_groups`. One query for every line of every document, grouped by document, instead of one
  query per document.

### 3.6 Duplicate item names: normalised keys, token sets and edit distance
- **Where:** new `services/similarity.py`, used by `api/inventory` (`_check_duplicate` and `/items/lookup`) and the item form.
- **Problem:** only names that matched after lower-casing and trimming spaces were caught. "Plate, Dinner 27cm",
  "Dinner-Plate 27 cm" and "Dinner Plates 27cm" slipped through as new items.
- **Change:** names are compared three ways:
  - compact key: letters and digits only (`dinnerplate27cm`)
  - token set: words as a set, lower case and singular, so order and plurals do not matter
  - bounded edit distance (two-row dynamic programming that stops early) for typos such as "Dinner Plat 27cm"
- **Behaviour:** a name that is the same item written differently is refused with the existing item named. A close
  name (typo, extra word, overlapping words) shows a warning and may be saved. The lookup returns `match: same`
  or `match: similar` and ranks the same item first.
- **Guarantee:** table-driven tests for ten cases, the edit-distance limit, ranking, and the refuse-versus-warn behaviour.

### 3.7 Phase 2 - lookups and batches inside one request
- **Where:** new `cache.py` (a per-transaction memo) and `services/reference.py` (shifts, locations, employee names);
  `deps.scoped_locations`; `monitoring.due_checks`; `metrics.monitoring_stats`, `failure_counts`, `movements`.
- **Problem:** the same small tables (shifts, locations, names, a user's locations) were read again by every function,
  and monitoring code ran two queries per point and per check.
- **Change:** those tables are loaded once per request and dropped when the transaction ends or a row they came from
  changes. Schedules and readings of all points come from two queries. Stock movements are read as plain tuples and each
  one finds its local day by binary search over that location's day starts, which stays exact across a clock change.
- **Guarantee:** the day finder is tested against converting every time, across the London clock change; the movement
  days are compared with the per-row method; a copy is shown to be dropped on a flush and a rollback.

### 3.8 Phase 3 - one index, chosen from query plans
- **Where:** `stock_transaction (location_id, occurred_at, item_id)`, migration `e6b4c8d2f9a3`.
- **Evidence:** on PostgreSQL the date-range read of a location's movements went from 1.58 ms to 0.75 ms and stopped
  visiting 9,486 rows it threw away. A matching index on readings changed nothing at this size, so it was not added.
  Checklist and attendance indexes were not added because there was no measured scan to fix.

### 3.9 Phase 4 - month-end balance snapshots
- **Where:** new `services/snapshots.py`, table `stock_snapshot` (migration `f7c5d9e3a0b4`), the scheduler, and `reconcile`.
- **Technique:** prefix sums. The closing quantity per item and location is stored at each month end; reconciliation starts
  from the latest snapshot and sums only the movements since. A build starts from the previous snapshot, in one batched insert.
- **Safety:** the ledger stays the source of truth. Every scheduler run checks the two newest snapshots against a full ledger
  sum; a snapshot that differs is dropped with all later ones, managers are notified, and reconciliation falls back to the full
  sum until the next run rebuilds it. Changing a location's time zone drops its snapshots.
- **Guarantee:** identical reconciliation with and without snapshots on random ledgers, proof that a deliberately damaged
  snapshot is used and then healed, idempotent runs, and no snapshot for the month still in progress.

### 3.10 Phase 5 - item search keys
- **Where:** `compact_key` and `token_key` columns on items (migration `a1e7f3c9d5b2`, backfilled), set by a model event on every
  insert and rename, and used by `api/inventory`.
- **Change:** a duplicate is now an indexed equality lookup on three keys (spaced name, letters only, sorted words) instead of a scan.
  The word rules also treat "glasses" and "glass", "boxes" and "box" as the same word. The similar-name warning compares every name up
  to 5,000 items; beyond that the database first narrows candidates to names that contain the typed letters, share a word or start
  the same way, so a typo in the first three letters is the one case a very large list could miss.
- **Guarantee:** the indexed check agrees with the full comparison on about 90 generated name variants, and the narrowed lookup returns
  the same best match as the full one on seven queries.

## 4. Structures and algorithms Plato already used

Plato already relies on sound ones, and none were changed: hash maps for lookups by id (item, location, employee name
maps), sets for membership (locations in scope, weekdays), `Counter` and sorting for rankings, interval arithmetic for
shift and slot times (including overnight shifts and daylight saving through `local_to_utc`), an immutable append-only
ledger with a derived balance (an event-sourcing style prefix sum), partial unique indexes as constraints
(one open attendance record, one posted invoice per supplier), and dictionary joins in the report builders.

## 5. Considered and not adopted

These are the usual textbook choices. None earns its place here today, and adding them would only add code to maintain.

| Idea | Why not now | Revisit when |
|---|---|---|
| Trie or inverted index for item search | The item list is a few hundred to a few thousand names; the full scan with early exits takes milliseconds | More than about 20,000 items |
| Heap or priority queue for pending items and alerts | The lists are tens of rows; sorting is simpler and as fast | Pending lists reach tens of thousands |
| Segment tree or Fenwick tree for stock totals | Totals are computed by the database over indexed columns; a second structure would need keeping in sync | Reports over many years of ledger |
| Bloom filter for duplicates | The database unique constraint is exact and cheap | Never needed at this size |
| Process-wide LRU cache for reads | Several workers or a restart would serve stale data; the per-transaction copy (section 3.7) gives the win without the risk | A shared cache such as Redis, with a clear invalidation rule |
| Graph algorithms, union-find | There is no graph in the data | A real dependency graph appears |
| Interval tree for shift conflicts | The conflict query is indexed and returns a handful of rows | Thousands of assignments per employee |

## 6. Impacts

**Users**
- Month-end reconciliation opens in a fraction of a second instead of several seconds, and gets faster relative to
  the data as history grows.
- The dashboard and the monitoring screens are quicker and make far fewer database calls under load.
- Item entry is safer: reordered, re-spaced or pluralised duplicates are blocked, and typos are flagged.

**Behaviour changes to know about**
- Creating or renaming an item can now be refused for a name that looks different but is the same item
  (word order, punctuation, plural). The refusal names the existing item. A genuinely different item with a similar name
  is still allowed, with a warning.
- `/api/inventory/items/lookup` returns an extra `match` field and may return items that merely overlap in words, not
  only ones that contain the typed text.
- Reconciliation, compliance and dashboard figures are unchanged; the tests prove it.

**Operations**
- Less database load and fewer round trips per request. Memory use rises slightly (one small dictionary per request).
- No schema change, no migration, no new dependency (standard library only: `bisect`, `re`, `collections`).
- The benchmark script can be run before any release to catch a slowdown.

**Risks and how they are covered**
- A faster path giving a different answer: covered by comparison tests against the original method.
- A stale settings copy: it lives only for one transaction and is dropped on any change, commit or rollback.
- A false "same item" refusal: the rule is conservative (identical after removing punctuation and spacing, or the same
  set of singular words); everything fuzzier only warns. A manager can still add a deliberately different item by
  giving it a clearly different name.
- The similarity scan reads every item name on each lookup. That is fast now; the plan lists the point at which to
  move to an indexed approach.

## 7. Where the time still goes

The dashboard makes 81 queries, down from 212. Most of what is left is one query per statistic per location window (checklists,
attendance, breakage, absences). Batching those across locations is the next gain and is listed at the end of
[DSA_IMPLEMENTATION_PLAN.md](DSA_IMPLEMENTATION_PLAN.md). Snapshots and the large-list search narrowing pay off as the data grows; at the
benchmark size they cost nothing and gain a little.
