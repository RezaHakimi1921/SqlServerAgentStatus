# Index Intelligence Module — Design & Implementation Brief

**Date:** 2026-08-05 (updated)  
**Purpose:** Single reference for the Indexes area.  
**Status:** Two-tab Index Intelligence — Overview (environment health) + Table Explorer (investigation).

Related files:

| Kind | Path |
|------|------|
| Product intent / earlier insight design | [`docs/superpowers/specs/2026-08-05-index-health-design.md`](../superpowers/specs/2026-08-05-index-health-design.md) |
| Permissions | [`INSTALL.md`](../../INSTALL.md) → Indexes module |

---

## 1) Product intent

**Name:** Index Intelligence (not just “Index Health”).

| Do | Do not |
|----|--------|
| Overview: finding-oriented environment scan | Dump all indexes (tens of thousands) |
| Table Explorer: architecture + relationships + recommendations | Auto DROP / CREATE / REBUILD |
| Server-side table typeahead (≥2 chars, TOP 30) | Static TOP-500 dropdown |
| Copy REVIEW ONLY scripts | Execute DDL from the app |
| Lazy fragmentation via button | Block open on `physical_stats` |

**Two DBA questions:**

1. **Overview** — Where should I look right now?
2. **Table Explorer** — Why is this table problematic and what can I improve?

---

## 2) UX

```text
Indexes
  [ Overview ]  [ Table Explorer ]

Overview:
  health chips → High write cost / Unused / Heaps / Missing-by-table
  capped multi-DB scan (finding-oriented)

Table Explorer:
  Database ▾   [ Search tables… ]
  Selected: dbo.Facture
  → Table overview → Recommendations → Inventory → Relationships → Missing
  [Load fragmentation] (optional)
```

Default landing: **Overview**. Outcome-first in Explorer: **Recommendations** before inventory.

---

## 3) Architecture

```text
UI (layout) → callbacks → SqlServerProvider
                 ↓
        service.build_table_intelligence / build_overview_payload
                 ↓
        intelligence.py (relationships, missing compare, recommendations)
```

| Layer | File | Role |
|-------|------|------|
| Constants | `modules/indexes/constants.py` | Thresholds, search/overview caps, timeouts |
| Engine | `modules/indexes/intelligence.py` | Pure analysis |
| Service | `modules/indexes/service.py` | Tags + compose payloads |
| Provider | `core/providers/sqlserver_provider.py` | `list_*`, `get_table_index_snapshot`, `get_table_index_frag`, `get_index_overview_snapshot` |
| UI / CB | `modules/indexes/layout.py`, `callbacks.py` | Two tabs, typeahead, lazy frag |

**Rules:** no Dash in engine; no DDL; `fmt_int` for quantities; soft-fail + permission hint.

### Analysis rules

- **Exact duplicate:** same ordered keys + same include set (order-insensitive) + same filter  
- **Covered-by:** same keys; narrower INCLUDE ⊆ wider  
- **Prefix overlap:** shorter keys are left-prefix of longer — investigate (never auto-drop unique/PK)  
- **Missing compare:** `extend_existing` | `create_new` | `ignore_near_duplicate`  
- **Recommendations:** `REMOVE_CANDIDATE` | `CONSOLIDATE` | `IMPROVE_EXISTING` | `INVESTIGATE`

### Performance

- Search: server-side, TOP 30, ≥2 chars, debounced  
- Table open: catalog + usage + partition_stats only  
- Frag: `btn-indexes-load-frag` only  
- Overview: capped DBs / finding rows — not full inventory  

---

## 4) Permissions

Unchanged — see `INSTALL.md`:

- `VIEW ANY DATABASE` (or equivalent DB list access)  
- Per-DB: `VIEW DEFINITION`, `VIEW DATABASE STATE`  

No Extended Events required.

---

## 5) Known limits

1. Usage stats reset at SQL Server restart — short uptime → cautious Unused.  
2. Overview is capped (not every database / every finding).  
3. Missing indexes are optimizer hints — Intelligence compares them to existing indexes; still not auto-create.  
4. Fragmentation is optional and can time out on huge tables.  
