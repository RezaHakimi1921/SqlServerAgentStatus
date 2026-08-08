# Index Catalog & Index Intelligence — Documentation

**Product:** SqlServer Agent Status / Smart Monitor  
**Module:** Index Intelligence  
**Date:** 2026-08-05  
**Scope:** Optional `insight` index catalog, selective refresh UI, SQL Agent jobs, performance path for Overview / Table Explorer, UX fixes, and operational rules.

---

## 1. Why this was built

### Problem
- Live multi-database DMV scans for Index Intelligence were **slow** (especially Overview and Table Explorer search).
- Every UI refresh could stress production by querying many user databases.
- Fragmentation (`dm_db_index_physical_stats`) stays **lazy / on-demand** (not cached) because it is expensive.

### Goals
| Goal | Outcome |
|------|---------|
| **Speed** | Overview + table typeahead read from local catalog tables when present |
| **Load control** | Heavy work runs on schedule or on demand — not on every page tick |
| **Selective refresh** | Operator chooses Tables / Index defs / Index states |
| **Soft-fail** | If catalog is missing, app falls back to live DMVs |
| **No Extended Events** | Catalog is DMV + catalog tables only (no XE requirement) |
| **Local time** | Timestamps use `GETDATE()` (server local), not UTC |

---

## 2. Architecture overview

```
┌─────────────────────────────────────────────────────────────┐
│  Dash UI — Index Intelligence                               │
│  • Overview (env health ring + stats)                       │
│  • Triage (ranked findings rail + detail + copy T-SQL)      │
│  • Table Explorer (table list + recommendations / status)   │
│  • Update catalog modal (parts + scope + confirm)           │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Python provider (core/providers/sqlserver_provider.py)     │
│  • Prefer MONITOR_DATABASE (SmartMonitorDB) for catalog     │
│  • Fallback to app default DB if catalog only exists there  │
│  • EXEC insight.USP_Insight_IndexCatalog_Refresh            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  SmartMonitorDB — schema insight                            │
│  • IdxCat_Table / IdxCat_Index / IdxCat_RefreshLog          │
│  • USP_Insight_IndexCatalog_Refresh                         │
│  • Optional SQL Agent: daily full + hourly stats            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  User databases (via 3-part names / dynamic SQL)            │
│  • sys.tables / sys.indexes / usage + partition stats       │
│  • COLLATE DATABASE_DEFAULT for Persian collation mixes     │
└─────────────────────────────────────────────────────────────┘
```

**UI shell (2026-08 redesign):** sticky Index Intelligence header (Overview · Triage · Table Explorer), severity tokens (`critical` / `warning` / `watch` / `ok`), Triage left rail + detail panel. Findings are shaped by `modules/indexes/triage.py` from the same Overview catalog/DMV snapshot — no new SQL objects.

**Related (Approach 2):** Tables & Growth uses sibling `insight.ObjSize_History` (see `scripts/sql/SqlMonitor_ObjSizeHistory.sql` and `docs/superpowers/specs/2026-08-08-tables-growth-design.md`). It may copy from `IdxCat_Table` but does **not** redesign this catalog into a unified Object Catalog.

---

## 3. Data model (`insight` schema)

All objects live in **`insight`** (never `dbo` for monitor objects).  
Install database: **`MONITOR_DATABASE`** (usually `SmartMonitorDB`).

### 3.1 `insight.IdxCat_Table`
Cached user tables per database.

| Column | Meaning |
|--------|---------|
| `database_name`, `schema_name`, `table_name` | Identity (PK) |
| `object_id` | Source object id (for joins during stats refresh) |
| `is_heap` | Heap flag |
| `row_count`, `size_mb` | Approximate size metrics |
| `refreshed_at` | Last touch (`GETDATE()`) |

### 3.2 `insight.IdxCat_Index`
Cached non-hypothetical indexes (`index_id > 0`).

| Column | Meaning |
|--------|---------|
| keys / identity | `database_name`, `schema_name`, `table_name`, `index_id` |
| Structure | `index_name`, `type_desc`, unique/PK/UQ flags, filter, `key_cols`, `include_cols` |
| State | `reads`, `writes`, `size_mb`, `page_count` |
| `refreshed_at` | Last touch (`GETDATE()`) |

**Not stored:** physical fragmentation (still loaded on demand in UI).

### 3.3 `insight.IdxCat_RefreshLog`
Audit of refresh runs.

| Column | Meaning |
|--------|---------|
| `started_at` / `finished_at` | Local server time |
| `database_name` | Scope (`NULL` = all accessible) |
| `status` | `running` / `ok` / `error` |
| `message` | Status or error text |
| `tables_upserted` / `indexes_upserted` | Row counters |
| `refresh_parts` | e.g. `tables=1;defs=1;stats=1` |

### 3.4 Procedure `insight.USP_Insight_IndexCatalog_Refresh`

```sql
EXEC insight.USP_Insight_IndexCatalog_Refresh
    @DatabaseName      = NULL,              -- NULL = all accessible user DBs
    @RefreshTables     = 1,                 -- table list + heap/row/size
    @RefreshIndexDefs  = 1,                 -- full replace of index definitions
    @RefreshIndexStats = 1;                 -- usage + size (and light table state if tables=0)
```

| Part | Behavior |
|------|----------|
| **Tables = 1** | `DELETE` + `INSERT` for that DB’s tables |
| **Index defs = 1** | `DELETE` + `INSERT` indexes (keys/includes/filters + current stats) |
| **Index stats = 1** (defs off) | `UPDATE` reads/writes/size on existing catalog rows; also light-updates table row/size if tables part is off |
| **Collation** | All cross-DB name comparisons/inserts use `COLLATE DATABASE_DEFAULT` |
| **Time** | All timestamps use `GETDATE()` |

**Preferred EXEC form** (omit `@DatabaseName` for “all DBs” — avoid `@DatabaseName = NULL` in some clients):

```sql
USE [SmartMonitorDB];
EXEC insight.USP_Insight_IndexCatalog_Refresh
    @RefreshTables = 1, @RefreshIndexDefs = 1, @RefreshIndexStats = 1;
```

---

## 4. SQL scripts (install & jobs)

| File | Purpose |
|------|---------|
| `scripts/sql/SqlMonitor_IndexCatalog.sql` | Create/alter catalog objects + SP (idempotent) |
| `scripts/sql/SqlMonitor_IndexCatalog_FullInstall.sql` | **One-shot:** `USE SmartMonitorDB` + objects + grants + first full refresh + verify |
| `scripts/sql/SqlMonitor_IndexCatalog_Jobs.sql` | SQL Agent jobs: daily full (~06:00) + hourly stats |

### Recommended install order
1. Run **`SqlMonitor_IndexCatalog_FullInstall.sql`** as sysadmin (F5).
2. Optionally run **`SqlMonitor_IndexCatalog_Jobs.sql`** (edit `@monitor_db` / `@preferred` if needed).
3. Confirm app login has `SELECT` + `EXECUTE` on catalog objects in **SmartMonitorDB**.

### Grants (example login `AgentGraph`)

```sql
USE [SmartMonitorDB];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'AgentGraph')
    CREATE USER [AgentGraph] FOR LOGIN [AgentGraph];
GRANT SELECT ON insight.IdxCat_Table TO [AgentGraph];
GRANT SELECT ON insight.IdxCat_Index TO [AgentGraph];
GRANT SELECT ON insight.IdxCat_RefreshLog TO [AgentGraph];
GRANT EXECUTE ON insight.USP_Insight_IndexCatalog_Refresh TO [AgentGraph];
```

---

## 5. Application behavior

### 5.1 Overview
- Prefers catalog findings (unused / write-heavy / heaps) when `IdxCat_*` has data.
- Badge: **Catalog** vs **Live DMV**.
- Missing-index suggestions are still peeked live (not in catalog).
- **Scan more databases** widens DB scope (deep mode).

### 5.2 Table Explorer
- On database select: prefetch all tables for that DB from catalog into client cache.
- Typeahead filters **locally** (fast); live search is fallback if cache empty.
- Table detail / recommendations still use live per-table snapshot (plus optional frag button).

### 5.3 Update catalog (UI)
- Toolbar button **Update catalog**.
- Modal (app root, `dir="ltr"`) with:
  - **What to update:** Tables / Index definitions / Index states (checkboxes)
  - **Scope:** All accessible DBs / Selected Table Explorer DB (radios)
  - Confirm styled like Pause (red filled); Cancel secondary
- Status line under toolbar: last refresh, row counts, `refresh_parts`.
- Loading: **single** overlay (no duplicate body spinner).
- Errors: humanized toast for EXECUTE denied / collation conflict.

### 5.4 Connection resolution
Provider `_open_catalog_connection()`:
1. Try `MONITOR_DATABASE` / `SmartMonitorDB`
2. Else fall back to app default database if catalog exists there (legacy)
3. Refresh / status / catalog list / catalog overview all use this path

---

## 6. Design & UX notes

### Principles applied
- Dark dashboard theme; teal accent (`--accent-running` / `#3dd9b6`).
- Modal forced LTR so English labels/controls do not reverse under RTL shell.
- Toasts at **app root** (not inside animated `.module-panel`).
- One loading overlay; auto-dismiss when data arrives.
- Native clickable checkbox/radio styled as cards (`pointer-events: auto`) — no invisible inputs.
- Confirm button uses Pause-style treatment; **no neon conic `::before`** (that caused skewed green overlay on hover).
- No emoji icons on catalog toolbar control.

### Key CSS / layout IDs
| Area | IDs / classes |
|------|----------------|
| Modal | `indexes-catalog-modal`, `indexes-catalog-parts`, `indexes-catalog-scope`, `indexes-catalog-confirm` |
| Cards | `.idx-opt-card`, `.indexes-catalog-check-input`, `.indexes-catalog-radio-input` |
| Status | `indexes-catalog-status` |
| Loading | `indexes-loading` / `indexes-loading-text` |
| Toast | `indexes-toast-refresh` |

### Files touched (UI)
- `app.py` — modal markup
- `modules/indexes/layout.py` — toolbar, status renderer, overview source badge
- `modules/indexes/callbacks.py` — modal, refresh, table cache, overview reload
- `assets/custom.css` — catalog modal, option cards, button styles

---

## 7. Python / provider surface

| API | Role |
|-----|------|
| `get_index_catalog_status()` | Last log + counts + `catalog_database` |
| `refresh_index_catalog(db, tables=, index_defs=, index_stats=)` | Selective EXEC |
| `list_tables(..., all_for_db=True)` | Prefetch for typeahead |
| `get_index_overview_snapshot(deep=)` | Catalog-first overview |
| `_open_catalog_connection()` | Monitor DB preferred |

Constants: `modules/indexes/constants.py`  
(`INDEX_CATALOG_*`, `INDEX_TABLE_CACHE_CAP`, `INDEX_CATALOG_REFRESH_TIMEOUT_SEC`).

Monitor helpers: `core/insight/store.py` → `monitor_database_name()`, `get_monitor_connection(timeout=...)`.

---

## 8. Project rules added / reinforced

| Rule file | Content |
|-----------|---------|
| `.cursor/rules/sql-getdate.mdc` | Use **`GETDATE()`** only — never `SYSUTCDATETIME()` / UTC for catalog timestamps |
| `.cursor/rules/database-insight-schema.mdc` | Objects in `insight`, `USP_Insight_*` naming |
| `.cursor/rules/no-extended-events.mdc` | Do not require XE for this feature |
| `.cursor/rules/ui-toasts.mdc` | Top-right toasts; loading for slow views |
| `.cursor/rules/number-formatting.mdc` | `fmt_int` / duration formatters in UI |

Also documented in **`INSTALL.md` §3b** (English + Persian summary).

---

## 9. Known issues fixed during this work

| Symptom | Cause | Fix |
|---------|--------|-----|
| Slow Overview / table search | Live multi-DB scans | Catalog + client table cache |
| EXECUTE denied on `msdb` | Wrong DB / missing GRANT | Prefer SmartMonitorDB + clear GRANT toast |
| Double loading text | Overlay + body clientside spinner | Single overlay |
| Checkbox not selectable | Hidden input `pointer-events: none` | Visible styled native inputs |
| Skewed green on confirm button | Neon `::before` on `.activity-ctrl-btn` | Disable `::before` in modal actions; Pause style |
| Collation 468 Persian_* | Cross-DB string compare | `COLLATE DATABASE_DEFAULT` in SP |
| Confusing refresh times | `SYSUTCDATETIME()` | `GETDATE()` + rule |

---

## 10. Operator playbook

### First-time setup
1. SSMS → run `scripts/sql/SqlMonitor_IndexCatalog_FullInstall.sql`
2. Optional: `SqlMonitor_IndexCatalog_Jobs.sql`
3. Restart / refresh app → Index Intelligence should show **Catalog** + status line

### Daily / hourly (if jobs installed)
- **06:00:** full (`tables+defs+stats`)
- **Hourly:** stats only

### Manual from app
Index Intelligence → **Update catalog** → pick parts → confirm.

### Manual from SSMS (stats only)

```sql
USE [SmartMonitorDB];
EXEC insight.USP_Insight_IndexCatalog_Refresh
    @RefreshTables = 0, @RefreshIndexDefs = 0, @RefreshIndexStats = 1;
```

### Verify

```sql
USE [SmartMonitorDB];
SELECT TOP 5 * FROM insight.IdxCat_RefreshLog ORDER BY refresh_id DESC;
SELECT COUNT(*) FROM insight.IdxCat_Table;
SELECT COUNT(*) FROM insight.IdxCat_Index;
```

---

## 11. Tests

Relevant automated coverage (mocked):
- `tests/test_index_layout.py` — shell IDs including catalog controls
- `tests/test_index_health_provider.py` — catalog prefer / refresh parts / EXECUTE message

---

## 12. File map (this feature)

```
scripts/sql/
  SqlMonitor_IndexCatalog.sql
  SqlMonitor_IndexCatalog_FullInstall.sql
  SqlMonitor_IndexCatalog_Jobs.sql

core/providers/sqlserver_provider.py   # catalog read/refresh/overview
core/insight/store.py                  # monitor DB connection + timeout
modules/indexes/
  constants.py / layout.py / callbacks.py / service.py
app.py                                 # catalog confirm modal
assets/custom.css                      # modal + option cards
INSTALL.md                             # §3b setup
.cursor/rules/sql-getdate.mdc
docs/indexes-catalog-development.md    # this document
```

---

## 13. Out of scope (intentional)

- Caching fragmentation in catalog
- Capturing missing-index DMVs into catalog
- Creating Extended Events sessions
- DDL from the UI (copy scripts only elsewhere in Index Intelligence)

---

*End of document.*
