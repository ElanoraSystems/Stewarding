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
| Month-end reconciliation, one location | 2,417 ms | 14 ms | about 178 times faster |
| `GET /api/stock/reconciliation` | 2,455 ms | 20 ms | about 122 times faster |
| Monitoring compliance stats, 45 days | 696 ms | 62 ms | about 11 times faster |
| `GET /api/dashboard` | 228 ms, 212 queries | 128 ms, 182 queries | 1.8 times faster |
| Monitoring log page of 25 readings | 31 queries | 7 queries | 4.4 times fewer queries |
| Due checks for today | 7 ms | 7 ms | unchanged (already small) |

Times are the best of three runs on one laptop with SQLite; use them to compare, not as production promises.
The suite passes on SQLite and PostgreSQL (435 tests).

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
| Process-wide LRU cache for reads | Several workers or a restart would serve stale data; the per-transaction copy gives the win without the risk | A shared cache such as Redis, with a clear invalidation rule |
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

The dashboard still makes 182 queries, mostly one or two per monitoring point and per location window. The next gains
are in batching those, in a composite index on the stock ledger, and in month-end balance snapshots. They are set out,
with order, effort and acceptance tests, in [DSA_IMPLEMENTATION_PLAN.md](DSA_IMPLEMENTATION_PLAN.md).
