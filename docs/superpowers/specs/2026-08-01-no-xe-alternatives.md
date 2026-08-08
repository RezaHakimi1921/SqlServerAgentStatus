# Features that wanted Extended Events — alternatives

**Status (2026-08-01):** User cannot grant XE create/alter on this instance (sensitive data). Do not depend on XE until they opt in.

## Priority (agreed)

| Priority | Work | Needs XE? |
|----------|------|-----------|
| 1 | Progress bar from `dm_exec_query_profiles` (never false 100% while still running) | No |
| 2 | Optional light `SqlMonitor.LogProgress` + short-lived progress table for 3–4 heavy SPs | No |
| 3 | `sql_text` / statement offsets from existing DMVs | No (already done) |
| 4 | Full XE PRINT capture | Only if later opt-in |

## PRINT / progress table (option 2) — known limits

- **Not automatic** for ad-hoc SSMS scripts — author must call the helper.
- Best ROI: a few long-running Import/Migration procedures, not a full codebase retrofit.
- Suggested shape:

```sql
EXEC SqlMonitor.LogProgress
  @job_name = N'ImportOrders',
  @rows_done = 10000,
  @message = N'Updated 10000 rows';
```

- Progress table must be **short-lived** (hours + cleanup job), not permanent history.

## `dm_exec_query_profiles`

- Gives operator `rows_done` / `rows_est` (raw counts).
- Does **not** give custom PRINT text — complements LogProgress, does not replace it.

## What already works without XE

- Session Lookup profile, waits, CPU/reads/writes  
- Query-profile row progress + progress bar logic  
- Live Resource Charts (server + session)  
- Blocking tree / Running Now  

## If XE is approved later

- Minimal: `error_reported` severity ≤ 10, prefer **no** `sql_text` action if sensitive  
- Ring buffer only, short retention  
- Script: `scripts/sql/SqlMonitor_PrintMessages.sql` (strip sensitive actions first)
