# Index Module v1 — Unified Design Spec

**Date:** 2026-08-16  
**Status:** Draft for review (authoritative for v1 implementation)  
**Module:** `indexes` (SmartMonitor Dash app) + Index Advisor capture (`insight.*`)  
**Sequence:** This doc (**C**) → UI/tag polish (**A**) → Overview ← Advisor snapshots (**B**)

---

## 0) Purpose of this document

`INDEX_MODULE_DESIGN.md` (repo root) is an aspirational brief that mixes valid product goals with ideas **locked out of v1** (Consolidation / Super Index, emoji specialist tags, standalone Python JSON collector, eager `dm_db_index_physical_stats`).

This spec is the **single source of truth** for Index work in v1. It reconciles:

| Source | Role |
|--------|------|
| `docs/index-advisor/BUILD-PLAN.md` | Capture/schema phases + locked product decisions |
| `docs/superpowers/specs/2026-08-05-index-health-design.md` | Live DMV Index Health findings (still valid; Explorer/Overview evolved beyond “current DB only”) |
| `INDEX_MODULE_DESIGN.md` | Ideas only — **superseded** for implementation decisions |
| Current code | `modules/indexes/*`, `scripts/sql/SqlMonitor_IndexAdvisor_*.sql` |

When any older doc conflicts with this file, **this file wins** until a later version bumps the locks.

---

## 1) Locked decisions (v1) — do not reopen in A/B

| # | Decision | Implication for code/UI |
|---|----------|-------------------------|
| 1 | **Read-only** — generate T-SQL only; never execute DDL/DML on customer DBs | Copy buttons only; no “Run rebuild” actions |
| 2 | **No Consolidation / Super Index** | No KPI card, triage row, or script generator for merging overlapping indexes |
| 3 | **Snapshot + Delta** — delta computed in API/app, not stored | `IndexSnapshot` stores cumulative DMV counters; usage deltas = run₂ − run₁ |
| 4 | **Confidence 0–100 + reasons**; copyable script only if **score ≥ 70** | `INDEX_CONFIDENCE_SCRIPT_MIN = 70`; below gate → show why, hide/disable copy payload |
| 5 | **AG/Replica from day one** (`ObservedReplicaRole`) | Capture records Primary / Secondary / Standalone; UI may show role on freshness banner |
| 6 | Monitor DB **SmartMonitorDB**, schema **`insight`** — no `CREATE DATABASE` | Phase0/Capture/Jobs target existing monitor DB |
| 7 | Missing-index **Fingerprint** deterministic (Phase 2) | See `docs/index-advisor/FINGERPRINT.md`; not implemented in Phase 1 Capture |
| 8 | **No Extended Events** dependency | Soft-fail; DMV/catalog/Advisor tables only |
| 9 | **No emoji** in chrome/tags | CSS classes + short English tag labels (i18n via `core.i18n`) |
| 10 | Capture via **SQL Agent on server**, not laptop Task Scheduler | Jobs: Hourly + PreRebuild 23:30 |

---

## 2) Product surfaces (what exists vs what v1 still builds)

### 2.1 Indexes module (app) — already shipping shape

```text
Overview tab  → environment findings (preferred DB + capped multi-DB scan)
Explorer tab  → DB picker, table cache, Recommendations | Index status, confidence gate
```

**Data paths today**

| Path | Source | Notes |
|------|--------|-------|
| Live Index Health | `get_index_health_snapshot` + `modules/indexes/service.py` | DMVs; soft-fail; caps in `constants.py` |
| Index Catalog | `insight.IdxCat_*` | Optional UI cache; soft-fail if missing |
| Advisor snapshots | `insight.IndexSnapshot` (+ later Missing) | Phase 1 capture ready; **Overview not yet primarily fed from this** → work item **B** |

### 2.2 Index Advisor (SQL) — Phase status

| Phase | Status | Owns |
|-------|--------|------|
| 0 Schema | Deploy | `ServerTarget`, `CollectionBatch`, `CollectionRun`, `IndexSnapshot`, `MissingIndexSnapshot` |
| 1 Capture + Jobs | Deploy | Usage/size snapshots; `FragmentationPercent = NULL` |
| 2 Missing capture | Planned | Fingerprint + `MissingIndexSnapshot` rows |
| 3 App UI on Advisor | Planned (this module’s **B**) | Overview prefer `advisor_snapshot` when fresh |

**Scripts (source of truth):** `scripts/sql/SqlMonitor_IndexAdvisor_{Phase0,Capture,Jobs}.sql`

---

## 3) Explicitly out of scope for v1

- Consolidation / Super Index / “Duplicate Leading Edge → merge” automation  
- Standing up a separate Python collector that writes JSON feeds for React  
- Eager instance-wide `sys.dm_db_index_physical_stats` in hourly Capture (too expensive)  
- Frag KPI that **requires** physical_stats on every Overview load  
- Executing CREATE/DROP/REBUILD/REORGANIZE from the app  
- Renaming live tags to long Blitz-style marketing names with emoji  
- Metric Store time-series score as a v1 dependency  

**Deferred (post-v1 candidates — document only)**

| Idea from `INDEX_MODULE_DESIGN.md` | Earliest home |
|------------------------------------|---------------|
| Consolidation / Super Index | v2+ Advisor + UI (new lock required) |
| Specialist tag aliases (Index Hoarder, etc.) | Optional display aliases mapped to existing tags |
| Optional Frag job (`LIMITED` physical_stats, capped) | Separate Agent job + nullable column already exists |
| Key Lookup Victim / Wide Clustered Key | New finding types after v1 triage proven |

---

## 4) Tag vocabulary (canonical — keep simple)

Use these **exact** English keys in code stores; translate for FA via `core.i18n` later if needed.

### 4.1 Problem / summary tags (current product)

| Tag | Meaning (short) | Typical evidence |
|-----|-----------------|------------------|
| `Unused` | NC index, zero reads since restart (with filters) | usage DMVs / catalog |
| `Write-heavy` | Writes ≫ reads (named thresholds) | usage DMVs |
| `High frag` | Frag ≥ 30% and pages ≥ min (when frag loaded) | optional frag probe |
| `Duplicate` | Same key shape / duplicate indexes on table | catalog defs |
| `Disabled` | Index disabled | catalog |
| `Heap` | Table without clustered index | catalog |
| `Missing` | Optimizer missing-index hint | missing DMVs / Phase 2 table |

Do **not** invent parallel emoji tags in UI. Mapping from DESIGN jargon (for docs only):

| DESIGN label | v1 handling |
|--------------|-------------|
| Index Hoarder | → `Unused` / `Write-heavy` |
| High Write - Low Read | → `Write-heavy` |
| Heavy Fragmentation | → `High frag` |
| Duplicate Leading Edge | → show as `Duplicate` only; **no merge script** |
| Key Lookup Victim / Wide Clustered Key | deferred |

### 4.2 Confidence (not a tag)

- Fields: `confidence_score` (0–100), `confidence_reason` / `confidence_reasons[]`  
- Gate: copyable T-SQL iff `confidence_score >= INDEX_CONFIDENCE_SCRIPT_MIN` (70)  
- Meaning: **trust in evidence** (uptime, DMV freshness), not “guaranteed win”

---

## 5) Overview KPIs (v1 contract for A then B)

Four cards — **aligned with DESIGN intent**, **without Consolidation**:

| # | KPI id | Label (EN) | v1 data rule |
|---|--------|------------|--------------|
| 1 | `missing_impact` | Missing index impact | Sum/top of improvement-style scores from live missing hints **or** Phase 2 snapshots when available; soft-fail empty |
| 2 | `high_frag` | High frag (>30%) | Count only when frag% present; if Advisor frag is NULL and live frag not loaded → show “—” / “Load frag” not a fake zero |
| 3 | `dead_unused_writes` | Dead unused writes | Unused NC with writes > 0 (or write footprint); prefer Advisor delta when **B** wires snapshots |
| 4 | `duplicate_debt` | Duplicate indexes | Count of duplicate findings / tables — **not** consolidation opportunities |

**Rejected KPI:** Consolidation Opportunities (locked out).

Charts under the strip (when implemented): by-database breakdown, frag distribution (only if frag data exists), wasted size GB — all read-only aggregations.

---

## 6) Fragmentation policy (display + optional scripts)

Microsoft / Paul Randal bands — **recommendation text only**:

| Frag % | Band | Suggested T-SQL (copy when confidence allows) |
|--------|------|-----------------------------------------------|
| < 10 | Healthy | none |
| 10–30 | Moderate | `ALTER INDEX … REORGANIZE` |
| > 30 | Critical | `ALTER INDEX … REBUILD` (+ ONLINE where edition supports; still copy-only) |

**Capture Phase 1:** leave `FragmentationPercent` NULL (fast path).  
**App:** optional on-demand / capped frag load already exists — keep timeouts; never block Overview on full physical_stats.

Page-count floors stay in `constants.py` (`INDEX_HIGH_FRAG_MIN_PAGES`, etc.).

---

## 7) Data architecture

```text
SQL Agent (server)
  → insight.USP_IndexAdvisor_Capture
  → CollectionBatch / CollectionRun / IndexSnapshot
       (+ MissingIndexSnapshot in Phase 2)

SmartMonitor app
  provider: read insight.* + live DMVs (soft-fail)
  service: classify, confidence, scripts, deltas
  UI: Overview / Explorer / triage — never executes DDL
```

### 7.1 Delta (usage)

For an index identity `(TargetId, Database, Schema, Table, Index)` between two runs:

```text
ΔSeeks   = Seeks₂ - Seeks₁   (clamp / null if restart reset detected)
ΔUpdates = Updates₂ - Updates₁
```

Restart detection: `SqlServerStartTime` / `UptimeHours` on `CollectionRun` — if start time changed, do not treat negative deltas as “improvement”; mark confidence down and reason “usage counters reset”.

### 7.2 Advisor freshness for Overview (**B**)

Prefer Advisor when:

- Latest successful `CollectionRun` for active target is newer than **90 minutes** (`INDEX_ADVISOR_FRESHNESS_MINUTES`, locked in **B**), **and**
- Snapshot row count > 0

Else fall back to live DMV scan (current Overview behavior). Always show source badge: `advisor` | `live` | `catalog`.

---

## 8) T-SQL generation rules

1. Production-safe defaults when emitting CREATE: `ONLINE = ON` (when applicable), sensible `FILLFACTOR`, optional `DATA_COMPRESSION` / `SORT_IN_TEMPDB` as comments or guarded options — match existing service helpers.  
2. DROP / DISABLE scripts are **review copies**, secondary CTA.  
3. Never emit Consolidation “create one Super Index + drop three” packages in v1.  
4. Gate: no script string in clipboard payload when score < 70; UI explains gate.

---

## 9) Implementation sequence (after this spec is approved)

### C — this document (now)

- [x] Write unified v1 spec  
- [ ] User review / approval  
- [ ] Mark `INDEX_MODULE_DESIGN.md` superseded (header pointer)

### A — UI / tag polish (no Advisor wire yet)

- [x] Align Overview strip to the **four KPIs** in §5 (replace any Consolidation card if present)  
- [x] Keep tag set §4; no emoji; FA strings via i18n where chrome already localized  
- [x] Confidence ≥ 70 gate audited on Recommendations copy actions  

**Implementation plan:** `docs/superpowers/plans/2026-08-16-indexes-module-a-kpis.md`

### B — Overview ← Advisor

- [x] Provider method: latest batch/run + snapshot aggregates (+ deltas when ≥2 runs)  
- [x] Soft-fail if tables/proc missing  
- [x] Source badge + replica role from `ObservedReplicaRole`  
- [x] Advisor freshness gate (90 min) — stale runs fall back to catalog/live  
- Do **not** wait for Phase 2 Missing capture to ship B (missing KPI can stay live DMV until Phase 2)

### Later (not A/B)

- Phase 2 MissingIndex capture SP + fingerprint  
- Optional frag Agent job  

---

## 10) File map

| Area | Path |
|------|------|
| This spec | `docs/superpowers/specs/2026-08-16-index-module-v1-design.md` |
| Advisor build/run | `docs/index-advisor/BUILD-PLAN.md` |
| Prior Index Health MVP | `docs/superpowers/specs/2026-08-05-index-health-design.md` |
| Aspirational (superseded) | `INDEX_MODULE_DESIGN.md` |
| App module | `modules/indexes/` |
| Capture SQL | `scripts/sql/SqlMonitor_IndexAdvisor_*.sql` |

---

## 11) Spec self-review

| Check | Result |
|-------|--------|
| Placeholders / TBD | None for **B** — Advisor freshness window locked at 90 minutes (§7.2) |
| Conflicts with BUILD-PLAN | None intended; Consolidation excluded; confidence 70; read-only; insight schema |
| Conflicts with `INDEX_MODULE_DESIGN.md` | Documented as out-of-scope / mapped |
| Scope creep | A and B listed; Consolidation and Python collector excluded |
| Ambiguity for implementers | Tags canonical; KPI #4 = duplicates not consolidation; frag NULL handling explicit |

---

## 12) Approval

Please confirm this spec as the v1 reference. Suggested reply:

- **Approve** → proceed to writing the **A** implementation plan, then code A  
- **Change X** → list edits; revise this file before A  

No A/B code lands until this doc is approved.
