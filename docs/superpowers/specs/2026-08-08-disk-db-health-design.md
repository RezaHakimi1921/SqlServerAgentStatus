# Disk & DB Health — Deferred Module Spec (Approach 2)

**Date:** 2026-08-08  
**Status:** Planned — implement after Tables & Growth V1 is stable  
**Product rule:** Separate Home module (`disk`); own `insight` snapshots; do **not** fold into `IdxCat_*` or `ObjSize_History`.

---

## Intent

Answer:

1. Which data/log files are largest / nearly full?
2. How stale are backups (scoped to monitored DBs only)?
3. Autogrowth thrashing — only when a history (or approved trace) source exists (not Live V1 alone)

Link to Tables & Growth only by **database name** (“this DB is large because these tables…”), not a polymorphic object model.

---

## Proposed data (when built)

### Live (V1)

- `sys.master_files` / `sys.database_files` — size, max_size, growth settings (current state only)
- Volume free space via `sys.dm_os_volume_stats` — **requires `VIEW SERVER STATE`** (same grant class as Activity; blast radius is instance/filesystem-aware — document carefully in INSTALL; prefer existing server-level grant pattern, do not invent broader rights)
- Last full/diff/log backup from `msdb.dbo.backupset` — aggregate **per DB**, but **filter to databases in monitor scope** (same user-DB list / preferred set as Tables & Indexes). Never dump every DB that appears in `backupset` on a shared instance.

### Autogrowth thrashing (not Live V1)

`sys.master_files` alone cannot detect thrashing (settings ≠ event history).

Ship thrashing only when one of these exists:

1. **`insight.FileSpace_History`** (preferred, aligns with Approach 2 sibling history), or  
2. Default Trace via `fn_trace_gettable` on Auto Grow events 92/93 — only with explicit approval (sensitive / ops-heavy; not XE, but still not free)

Until then: show growth **settings** (enabled, increment, max size) as informational — label clearly, do not claim thrashing.

### Optional history (later)

- `insight.FileSpace_History` — daily grain `(captured_date, database_name, file_id)` with size_mb / used_mb  
- Separate capture proc + Agent job — sibling pattern like ObjSize_History  
- Enables “file grew N MB in 7d” and thrashing heuristics without Default Trace  

---

## Permissions / blast radius (locked notes)

| Source | Grant | Caution |
|--------|-------|---------|
| `sys.dm_os_volume_stats` | `VIEW SERVER STATE` | Exposes volume/path free space — review before enabling; soft-fail if missing |
| `msdb.dbo.backupset` | read on msdb (typical Agent login) | Scope results to monitored DBs only |
| Default Trace autogrow | file read on trace path | Optional later; not V1 |

---

## App shape

- `modules/disk/` parallel to `modules/tables/`  
- Registry flip `disk` → `ready` when V1 ships  
- Soft-fail + INSTALL grants section  

---

## Explicit non-goals

- Unified Object Catalog schema  
- Rewriting Index Catalog  
- Extended Events / file I/O XE  
- Auto-grow DDL from the app  
- Claiming autogrowth thrashing from live `master_files` alone  
