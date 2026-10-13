# Scale: two years of data

Measured with `python -m scripts.benchmark_scale` on a throwaway SQLite database holding two years of a busy three-location kitchen:
60 employees, about 44,000 attendance records, 52,000 checklist instances, 29,000 monitoring readings, 150,000 stock movements,
150,000 audit rows and 60,000 notifications.

## Everyday screens

Every list page is paginated server-side (at most 200 rows) and answers in under 10 ms on that data: monitoring log (page 1 and page 600),
attendance, checklists for a day, employees, notifications, audit log, stock movements (page 1 and page 3000), and the due checks.
The dashboard for its default range takes about 130 ms and the daily and weekly reports 20 to 35 ms.

## What was changed for scale

| Area | Problem on two years of data | Change |
|---|---|---|
| Pending activities | Listed every overdue task ever recorded and loaded each as an object: 222 ms and a list that grows for ever | Only tasks due in the last 30 days, read as plain columns, list capped at 200 (the totals still count everything): 20 ms |
| PDF records | A year of attendance took 14.5 s and a large memory use | A PDF is refused above 4,000 rows with a message to narrow the period or use Excel or CSV; Excel and CSV have no cap |
| Record preview | The whole record was sent to the browser for a 25-row preview | The server sends the first 200 rows and the row count |
| Date limits | Reports were limited to 93 days | Reports take up to 366 days and records up to 731 days; the dashboard stays at 93 days |
| PDF layout | Fixed column weights wrapped short values and wasted width | Column widths follow the content, small tables stay on one page, empty tables are a single line |

## Still to watch

- Excel for a year of attendance takes about 1.3 s; a very large export is built in memory.
- The dashboard makes 81 queries per request; batching them across locations is Phase 6 in `DSA_IMPLEMENTATION_PLAN.md`.
- The audit log and notifications grow without limit; add a retention rule when they pass a few million rows.
