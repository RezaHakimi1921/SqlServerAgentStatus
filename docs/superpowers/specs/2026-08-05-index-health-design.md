# Index Health (Indexes module) — Design Spec

**Date:** 2026-08-05  
**Status:** Frozen (ready for plan) — final review notes incorporated  
**Module id:** `indexes` (Home tile already registered as `soon`)  
**Scope:** Read-only Index Health glance for DBAs — categorized findings + recommendations + optional copy scripts  
**Out of scope:** Executing DROP/DISABLE/CREATE/REBUILD from the app; fragmentation maintenance; Metric Store persistence; Extended Events

---

## 1) Problem & product intent

### Problem

DBAs need a **fast storage/index sanity glance**: which indexes waste space and write cost, which tables lack a clustered index, which duplicates exist, and which “missing index” hints the optimizer keeps emitting — without opening SSMS and running five scripts.

### Intent (explicit)

| Do | Do not |
|----|--------|
| Inform + recommend | Auto-apply schema changes |
| Speed up DBA review | Replace DBA judgment |
| Show context (same-table indexes) | Hide caveats (uptime / DMV reset) |
| Copy helper scripts for review | Primary CTA = “Drop now” |

**Primary loop:** Open → Understand → Investigate (not Open → Click Drop).

**Press-release one-liner:**  
“Open Indexes → see in one screen what’s unused, expensive to maintain, duplicated, heap-shaped, or suggested as missing — with enough context to decide what to investigate next.”

### Success metrics (qualitative for v1)

- DBA can answer “where should I look first?” in under a minute (summary strip).
- Each finding states *what / why it matters / what to consider* without leaving the page.
- Zero false sense of safety after a recent restart (uptime warning + per-finding confidence where meaningful).
- No path in the UI that runs DDL.

### Value signal (operator ICP)

Primary buyer/user: production SQL Server DBA / senior developer who already uses DMVs.  
Pain: index debt grows quietly (write amplification, backup size, maintenance windows).  
Signal that this module wins: “I found three candidates worth reviewing before lunch without writing a script.”

---

## 2) Approach

**Chosen:** **Insight-format Index Health** (BlitzIndex-inspired categories, Insights/Blocking UX patterns) — current database only, DMV-only, read-only.

**Rejected:**

| Approach | Why not |
|----------|---------|
| Action-first Unused-only MVP | Too narrow for stated “comprehensive glance” goal |
| Wrap / call `sp_BlitzIndex` in-app | Dependency on First Responder Kit install; license/ops friction; harder soft-fail |
| Auto DROP/DISABLE from UI | Safety + permission + audit risk; conflicts with product intent |
| Daily Index Health Score in Metric Store (v1) | Retention, schema version, comparison, migration, cleanup — out of proportion to Open → Understand → Investigate |

### Expert mapping (ideas, not code copies)

| Expert / source | Borrowed idea |
|-----------------|---------------|
| Brent Ozar `sp_BlitzIndex` | Multi-disorder sanity: unused, duplicate, heaps, missing; table-context when reviewing missing |
| Glenn Berry diagnostics | Write ≫ read “bad NC” indexes; full business-cycle / uptime caveat |
| Pinal Dave unused script | Zero reads + DROP statement for review |
| Repo `queries/` | Seed SQL shapes for usage, inventory, space (not shipped as-is) |

---

## 3) Architecture

### Placement (modular monolith — match Activity / Insights)

```text
modules/indexes/
  __init__.py
  layout.py          # shell: toolbar, strip, uptime banner, category sections, loading
  callbacks.py       # refresh → store → render
  service.py         # pure: classify, confidence, scripts, table context
  constants.py       # named thresholds (write-heavy, uptime, caps)
  render.py          # optional: HTML builders (keep layout thin if large)

core/providers/sqlserver_provider.py
  + get_index_health_snapshot()   # batched read path → raw rows only

core/formatters.py               # reuse fmt_int, size helpers if present
core/registry.py                 # indexes: status ready; subtitle updated
app.py                           # wire module panel like insights/activity
```

**Dependency direction (do not invert):**

```text
provider  →  raw snapshot
service   →  classification + confidence + scripts
UI        →  render only
```

No Dash imports in `service` / `constants` / provider helpers. No Metric Store writes in this module.  
Classification stays out of UI so a future CLI export / API / scheduled report can reuse the same service.

### ADR-001: Insight categories, not one flat grid

**Context:** Five disorder types confuse if dumped as one 200-row table.  
**Decision:** Summary strip + five labeled sections; each row is a finding with recommendation text.  
**Consequence:** More UI work; clearer glance; matches Blocking health-strip + Insights glance pattern.

### ADR-002: Read-only recommendations; scripts secondary

**Context:** DROP scripts speed DBA work but invite accidental trust.  
**Decision:** Primary text = finding + recommendation. “Copy script for review” is secondary (clipboard). App never executes DDL.  
**Consequence:** Safe for shared/prod viewers; DBA still gets speed.

### ADR-003: Current database only (MVP)

**Context:** All-database scans are slow and permission-heavy.  
**Decision:** Scope = database of the configured app connection. Multi-DB later.  
**Consequence:** Simple permissions; header shows `Database: X`.

### ADR-004: No Extended Events

**Context:** Workspace rule — no XE dependency.  
**Decision:** DMVs + catalog only. Soft-fail per category on permission errors.  
**Consequence:** Incomplete after restart is expected and labeled via uptime + confidence.

### ADR-005: Confidence = trust in evidence, not “is this a real problem?”

**Context:** Usage DMVs reset on restart; catalog facts do not.  
**Decision:** Every finding carries `confidence` + `confidence_reason`. Meaning: *how much we trust the data behind this finding*, not whether the DBA should act.  
**Consequence:** Structural findings stay high; usage/missing findings can be low after short uptime without sounding like “the tool is broken.”

---

## 4) Named constants (service / `constants.py`)

```python
INDEX_USAGE_MIN_UPTIME_DAYS = 7

INDEX_WRITE_HEAVY_MIN_WRITES = 1000
INDEX_WRITE_HEAVY_MIN_DIFF = 10000          # writes - reads
INDEX_WRITE_HEAVY_MIN_RATIO = 10            # writes / reads

INDEX_CAP_UNUSED = 50
INDEX_CAP_WRITE_HEAVY = 50
INDEX_CAP_MISSING = 25
```

All write-heavy gates and uptime rules must reference these names (so small-workload prod can tune/understand empty lists).

---

## 5) Finding categories (MVP)

Mutual exclusion and definitions must stay stable so strip totals are not double-counted.

### 5.1 Unused

**Definition:** Nonclustered; not PK / unique constraint / unique / disabled / hypothetical; **user reads = 0** (`seeks + scans + lookups`). Catalog `sys.indexes` **LEFT JOIN** `dm_db_index_usage_stats` (current DB); missing usage row ⇒ reads = 0, writes = 0 (same meaning as zero counters since last restart).

**Exclude:** Clustered, heaps (`index_id = 0`), XML/spatial/columnstore (defer), PK, unique indexes/constraints.

**Sort:** Writes desc, then size desc. Zero-write unused still listed (schema clutter) after write-tax rows.

**Recommendation tone:** “No reads since last SQL Server start; still paying write/maintenance cost — review before drop; confirm a full business cycle.”

### 5.2 Write-heavy (not unused)

**Eligibility:** Same base filters as Unused, **and** `reads > 0`, **and** all of:

```text
writes > reads
AND writes >= INDEX_WRITE_HEAVY_MIN_WRITES
AND (
  (writes - reads) >= INDEX_WRITE_HEAVY_MIN_DIFF
  OR writes >= reads * INDEX_WRITE_HEAVY_MIN_RATIO
)
```

This gate is **mandatory** (not optional). Tiny `writes ≈ reads` noise must not appear.

**Implementation note:** Prefer multiply form `writes >= reads * RATIO` over division in SQL/Python classification. If a ratio is displayed, use `writes / NULLIF(reads, 0)` (or equivalent) only for display metrics — never for the gate alone without the absolute floors above.

**Mutual exclusion:** If `reads = 0` → **Unused only**, never Write-heavy.

**Sort:** `(writes - reads)` desc, then writes desc.

**Recommendation tone:** “Used for reads but write cost dominates — check whether keys/filter still match workload.”

### 5.3 Duplicate

**Definition:** Two or more nonclustered indexes on the same table with **identical ordered key columns**, **identical include sets** (order-insensitive), and **identical filter definition** (exact duplicate only).

**Not in MVP:** Leading-column / overlapping indexes (Phase 2).

**Recommendation tone:** “Same keys/includes/filter — keep one; drop excess only after confirming uniqueness/FK needs.”

**Counts:** Section header = number of **groups**; strip “Duplicate” = **excess** indexes `sum(group_size - 1)`.

### 5.4 Heaps

**Definition:** User tables that are heaps (`index_id = 0`) with **no clustered index**.

**Recommendation tone:** “Heap — evaluate a clustered index (often PK) for lookups and maintenance behavior.”

**Not a drop candidate.** No DROP script.

### 5.5 Missing (optimizer suggestions)

**Definition:** Missing-index DMVs for current DB, ordered by impact  
`avg_user_impact * avg_total_user_cost * user_seeks` (or equivalent). Cap: `INDEX_CAP_MISSING` with “top N of M” when truncated.

**Always attach table context:** existing indexes on that table (keys, includes, filter).

**Fetch order (mandatory for plan/impl):** Cap Missing to `INDEX_CAP_MISSING` **first** → collect distinct `object_id` from that capped set → inventory existing indexes **only for those tables**. Do not load all missing rows then all indexes for every mentioned table.

**Severity:** `info` only.  
**Recommendation tone (required wording):** “Optimizer suggestion, not a recommendation — compare with existing indexes before creating anything.”

**No CREATE button.** Secondary copy-only suggested `CREATE` script allowed.

---

## 6) Confidence model

### Meaning

`confidence` answers: **How much do we trust the evidence used for this finding?**  
It does **not** answer: “Is this definitely a production problem?” or “Should you drop it?”

### Field

```text
confidence: high | medium | low
confidence_reason: one short sentence (EN or FA; stable, user-visible)
```

### Rules by category

| Category | Confidence | Notes |
|----------|------------|--------|
| Duplicate | **high** always | Catalog fact; no freshness warning on the card |
| Heap | **high** always | Catalog fact; no freshness warning on the card |
| Unused | uptime + signal | See below |
| Write-heavy | uptime + intensity | See below |
| Missing | **at most medium**; **low** if uptime &lt; `INDEX_USAGE_MIN_UPTIME_DAYS` | Missing DMVs are inherently over-confident |

**Unused / Write-heavy:**

- Uptime &lt; 7 days → **low** (reason cites restart / short collection window).
- Uptime ≥ 7 days:
  - Unused with very high writes → **high**
  - Unused with zero/low writes → **medium**
  - Write-heavy that passed gates → **high** if uptime ≥ 7 days; else **low**

**UI:** Show confidence badge + reason on usage/missing findings. Structural findings may omit a “freshness” chip entirely (or show a quiet “Schema” label) — **never** attach a misleading “data only N days old” warning to Duplicate/Heap.

Page-level uptime banner still exists for the module as a whole; it must not imply structural findings are unreliable.

---

## 7) Summary strip & uptime

### Summary strip

| Card | Value |
|------|--------|
| Unused | Count |
| Write-heavy | Count |
| Duplicate | Excess index count (§5.3) |
| Heaps | Count |
| Missing | Count (show top N of M if truncated) |
| **Reviewable index space** | Sum of sizes for Unused indexes + duplicate **excess** members when known; `—` if unknown |

**Wording:** Do **not** use “Recoverable size.”  
Tooltip / helper (required): dropping indexes reduces used space inside data files and write/backup cost; it does **not** guarantee immediate free disk without a file shrink (shrink is not recommended by this product).

Numbers: `fmt_int`; sizes: human MB/GB.

### Size source

Use **`sys.dm_db_partition_stats`** (or equivalent lightweight allocation views) for size.  
Do **not** use `sys.dm_db_index_physical_stats` for MVP size (expensive; reserved for future fragmentation work).

### Uptime / freshness banner

- Source: `sqlserver_start_time` (`sys.dm_os_sys_info`) + app clock.  
- Uptime &lt; `INDEX_USAGE_MIN_UPTIME_DAYS`: warning — usage-based categories may be incomplete.  
- Uptime ≥ 7 days: quiet info “Usage stats since {start} ({N} days)” + note that monthly jobs may need longer.

---

## 8) Finding row shape (UI contract)

```text
IndexFinding {
  category: unused | write_heavy | duplicate | heap | missing
  severity: info | warn | critical
    # unused / write-heavy / dup (large) → warn|critical by size/write tax
    # missing → info always
    # heap → warn
  confidence: high | medium | low
  confidence_reason: str
  database_name, schema_name, table_name
  index_name | null
  metrics: {
    usage?: { reads, writes, write_read_ratio? }
    storage?: { size_mb }
    missing?: { user_seeks, avg_user_impact, avg_total_user_cost, impact_score }
    score?: number   # optional rollup for sort display
  }
  title: short label
  recommendation: one short paragraph (FA preferred for glance text, matching Insights)
  scripts: [{ label, tsql }]
  table_indexes: [{ name, keys, includes, filter, is_unique, type }]
  duplicate_group_id?: str
}
```

Category-specific metrics live under the nested bags above (not a flat grab-bag of unrelated keys).

**UI rules (workspace):**

- Loading: centered spinner in module body on open / manual refresh.  
- Toast: top-right app root; manual Refresh / errors only — never inside animated `.module-panel`.  
- Uptime banner is **module content**, not a toast.  
- Identifiers unformatted; counts via `fmt_int`.

### Registry / chrome

- Tile `indexes` → `status: "ready"` when shipped.  
- Subtitle: **"Health glance & recommendations"** (replace “Fragmentation & unused”).  
- Title: **Indexes**.

---

## 9) Data flow

```text
User opens Indexes / clicks Refresh
  → show loading in module body
  → provider.get_index_health_snapshot()
       batched queries:
         A. NC index usage + size (partition_stats)
         B. heap tables
         C. index key/include/filter inventory (duplicates + table context)
         D. missing index groups
         E. sqlserver_start_time
  → service.build_index_health(raw)
       → classify (mutual exclusion + write-heavy constants)
       → confidence + confidence_reason
       → scripts + table context
       → { summary, uptime, findings[] }
  → store + render
  → hide loading; dismiss refresh toast if any
```

**Performance:**

- Few SQL batches; no per-table N+1.  
- Caps first, then context: especially Missing (§5.5 fetch order). Same idea for other categories — distinct object_ids from **capped** findings only.  
- Caps: `INDEX_CAP_*`.  
- No `dm_db_index_physical_stats` in MVP.

**Soft-fail:** One failed query ⇒ that category empty + inline error chip; other categories still render.

---

## 10) Copy scripts (secondary)

| Category | Script |
|----------|--------|
| Unused / Write-heavy | Copy-only bundle: both `ALTER INDEX … DISABLE` and `DROP INDEX …` under one secondary action labeled **“Copy DISABLE/DROP script for DBA review”** — not a primary recommendation to disable |
| Duplicate | DROP for **excess** members only |
| Heap | none |
| Missing | Suggested `CREATE NONCLUSTERED INDEX …` for review only |

Header comment on every script: `-- REVIEW ONLY — not executed by SqlMonitor`.  
Identifier quoting via careful Python `QUOTENAME`-equivalent.

**DISABLE wording:** Do not present DISABLE as “the safe action.” Recommendation text must note that disable is reversible but **still requires workload validation**. UI treats both scripts as review artifacts only.

---

## 11) Explicit non-goals (this version)

- Fragmentation / rebuild / reorganize UI  
- Overlapping (non-exact) duplicate / consolidation graph  
- Multi-database scan  
- Metric Store persistence / daily index health score / email  
- Executing DROP / DISABLE / CREATE from the app  
- Columnstore / XML / spatial specialist analysis  
- Query Store forced-plan / hint detection before drop  

---

## 12) Testing

| Layer | What |
|-------|------|
| Unit `service` | Unused vs Write-heavy mutual exclusion; write-heavy constants gate; duplicate groups + excess count; confidence rules by category; script quoting; uptime thresholds |
| Unit | LEFT JOIN missing usage → zero reads; caps |
| Unit | Structural findings never get low confidence solely from short uptime |
| Manual | Open → loading → strip (incl. Reviewable index space) → sections; copy script; no DDL |

---

## 13) Acceptance checklist

- [ ] Home tile Indexes opens a real module (not `soon`)
- [ ] Summary strip: Unused, Write-heavy, Duplicate, Heaps, Missing, **Reviewable index space**
- [ ] Reviewable index space tooltip does not claim immediate free disk
- [ ] Uptime &lt; 7 days shows module warning; usage categories still listed
- [ ] Unused and Write-heavy never list the same index
- [ ] Write-heavy uses named constants (`INDEX_WRITE_HEAVY_*`), not bare `writes > reads`
- [ ] Duplicate = exact key + include + filter only
- [ ] Missing rows include existing indexes on the same table
- [ ] Missing copy uses “optimizer suggestion, not a recommendation”; severity `info`
- [ ] Each finding has `confidence` + `confidence_reason`; meaning = evidence trust
- [ ] Confidence is only emphasized where meaningful; structural findings do **not** show misleading freshness warnings
- [ ] Recommendations textual; scripts copy-only secondary
- [ ] App never executes DROP/DISABLE/CREATE
- [ ] Size from partition stats (not physical_stats)
- [ ] `fmt_int`; centered loading; toasts only for manual refresh/errors at app root
- [ ] No Extended Events; soft-fail per category; current DB only
- [ ] No Metric Store writes

---

## 14) Follow-ups (not this version)

1. Fragmentation / maintenance glance (`tuning.sql`)  
2. Overlapping index / consolidation opportunity (not auto-drop)  
3. Multi-DB mode with explicit cost acknowledgment  
4. Metric Store: optional daily “index debt” cards (separate design)  
5. DISABLE → monitor workflow hints tied to Activity  

---

## 15) Next step

Write implementation plan: `docs/superpowers/plans/2026-08-05-index-health.md`  
(provider → service/constants → layout/callbacks → registry/app → tests).  
Do not implement until that plan is written and executed deliberately.

---

## Addendum — v1.1 Tag glance + DB/Table picker (2026-08-05)

**Supersedes** the insight-first main screen for day-to-day use.

### Flow

```text
Select Database → Search/Select Table → Index rows with compact tags
```

Default DB preference: `RasBankAccountingCloud` when present in the list.

### Primary UI

- One row per index on the selected table
- Tags: Unused, Write-heavy, High frag (≥30% and ≥1000 pages, LIMITED), Duplicate, OK, Filtered, Unique, Disabled
- Tag summary chips at top
- Scripts secondary under Details
- Missing-index suggestions demoted to a collapsed panel

### Permissions (see INSTALL.md)

Per target DB: `VIEW DEFINITION` + `VIEW DATABASE STATE`  
Server (DB list): `VIEW ANY DATABASE` (or CONNECT per DB)

### Data

- `list_user_databases`, `list_tables`, `get_table_index_snapshot`
- Fragmentation only via `dm_db_index_physical_stats(..., 'LIMITED')` for the **selected object**
- Classification: `build_table_index_tags` / `tag_index_row`
