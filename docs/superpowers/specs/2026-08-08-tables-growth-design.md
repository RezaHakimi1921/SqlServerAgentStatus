# Tables & Growth — Data Spec (Approach 2)

**Date:** 2026-08-08  
**Status:** Locked for implementation  
**Product rule:** Separate module from Indexes; shared `insight` schema; no unified Object Catalog.

---

## Intent

Answer without redesigning Index Catalog:

1. Which databases / tables dominate space **now**?
2. Which tables grew (rows / MB) over 1d / 7d / 30d once history exists?

Indexes keeps owning `IdxCat_*`. Tables & Growth owns append-only size history.

---

## Objects

### `insight.ObjSize_History` (append-only daily grain)

| Column | Type | Notes |
|--------|------|--------|
| `captured_date` | `DATE` | Calendar day (server local via `GETDATE()`) |
| `database_name` | `SYSNAME` | |
| `schema_name` | `SYSNAME` | |
| `table_name` | `SYSNAME` | |
| `row_count` | `BIGINT` | Heap/clustered rows |
| `size_mb` | `FLOAT` | Used pages across indexes on the table |
| `is_heap` | `BIT` | |
| `source` | `VARCHAR(20)` | `catalog` \| `live` |
| `captured_at` | `DATETIME2(0)` | Exact capture time |

**PK:** `(captured_date, database_name, schema_name, table_name)`

**Retention:** 90 days (proc step).

### `insight.USP_Insight_ObjSize_Capture`

1. Prefer copy from `insight.IdxCat_Table` when present and non-empty → `source = 'catalog'`.
2. Else live scan of accessible user DBs (same grain as IdxCat tables refresh) → `source = 'live'`.
3. Upsert today’s grain (delete-today + insert, or MERGE).
4. Delete rows older than `@RetentionDays` (default 90).

Soft-fail in the app: if history/catalog missing, live DMV path still serves **current** sizes.

---

## App contract

Provider returns a snapshot dict:

- `databases` — rollup per DB  
- `top_tables` — largest by `size_mb`  
- `growers` — largest positive Δ MB over available windows  
- `history_available` — bool  
- `source` — `catalog` \| `live`  
- `errors` / permission hints  

Deltas computed in Python (or SQL) by comparing today’s (or latest) row to the nearest prior day ≤ N days ago.

---

## Out of scope (this ship)

Partition map, LOB split, stats freshness, filegroup, Metric Store growth rules, DDL, XE, unified Object Catalog schema.
