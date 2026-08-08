# Index Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a read-only Indexes module that shows Unused, Write-heavy, Duplicate, Heaps, and Missing findings with confidence, summary strip (including Reviewable index space), and copy-only DISABLE/DROP/CREATE scripts.

**Architecture:** `SqlServerProvider.get_index_health_snapshot()` returns raw DMV/catalog batches (soft-fail per section). Pure `modules/indexes/service.py` classifies, applies constants, assigns confidence, builds scripts, and attaches table context. Dash UI only renders. No DDL execution, no Metric Store, no XE, no fragmentation.

**Tech Stack:** Python 3, Dash, existing `SqlServerProvider` / `QueryResult`, `pytest`, `assets/custom.css`, `core.formatters.fmt_int`

**Spec:** `docs/superpowers/specs/2026-08-05-index-health-design.md` (frozen)

## Global Constraints

- Never execute DROP / DISABLE / CREATE from the app (copy scripts only)
- No Metric Store / insight collector writes
- No Extended Events
- No `sys.dm_db_index_physical_stats` (size via `sys.dm_db_partition_stats` only)
- Current connection database only
- Write-heavy gate uses named constants; compare with `writes >= reads * RATIO` (no divide-for-gate)
- Missing: **cap first** → distinct `object_id` → inventory **only those tables**
- Confidence = trust in evidence, not “problem is real”
- Structural findings (duplicate, heap): confidence always `high`; no misleading freshness chip
- UI: centered loading; toasts top-right app root on manual refresh/errors only
- Numbers via `fmt_int`; identifiers unformatted
- Service / constants: **no Dash imports**

---

## File map

| File | Responsibility |
|------|----------------|
| `modules/indexes/constants.py` | Named thresholds and caps |
| `modules/indexes/service.py` | `build_index_health(raw) -> dict`; classify; confidence; scripts; mutual exclusion |
| `modules/indexes/layout.py` | Shell + render strip/sections/findings |
| `modules/indexes/callbacks.py` | Refresh / open module → fetch → store → render |
| `modules/indexes/__init__.py` | Package export |
| `core/providers/sqlserver_provider.py` | `get_index_health_snapshot()` + private SQL batches |
| `core/registry.py` | `indexes` → `ready`; subtitle update |
| `app.py` | Module panel + switch_module + show_module + register callbacks |
| `assets/custom.css` | Index health strip / finding / confidence styles |
| `tests/test_index_health_service.py` | Classification, constants, confidence, scripts, caps |
| `tests/test_index_health_scripts.py` | Identifier quoting / script text (optional split) |

---

### Task 1: Constants + Write-heavy / Unused classification (TDD)

**Files:**
- Create: `modules/indexes/constants.py`
- Create: `modules/indexes/service.py` (classification helpers first)
- Create: `tests/test_index_health_service.py`

**Interfaces:**
- Produces:
  - Constants as in spec (`INDEX_USAGE_MIN_UPTIME_DAYS`, `INDEX_WRITE_HEAVY_MIN_WRITES`, `INDEX_WRITE_HEAVY_MIN_DIFF`, `INDEX_WRITE_HEAVY_MIN_RATIO`, caps)
  - `is_write_heavy(reads: int, writes: int) -> bool`
  - `classify_usage_row(row: dict) -> Literal["unused","write_heavy",None]`  
    (`None` = neither; e.g. healthy usage). Assumes row already eligible NC non-unique etc. or checks flags on row.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_index_health_service.py
from modules.indexes.constants import (
    INDEX_WRITE_HEAVY_MIN_WRITES,
    INDEX_WRITE_HEAVY_MIN_DIFF,
    INDEX_WRITE_HEAVY_MIN_RATIO,
)
from modules.indexes.service import is_write_heavy, classify_usage_row


def test_write_heavy_rejects_near_equal():
    assert is_write_heavy(reads=1000, writes=1100) is False


def test_write_heavy_accepts_large_diff():
    assert is_write_heavy(reads=1000, writes=1000 + INDEX_WRITE_HEAVY_MIN_DIFF) is True


def test_write_heavy_accepts_ratio():
    reads = 100
    writes = reads * INDEX_WRITE_HEAVY_MIN_RATIO
    assert writes >= INDEX_WRITE_HEAVY_MIN_WRITES
    assert is_write_heavy(reads=reads, writes=writes) is True


def test_write_heavy_requires_min_writes():
    assert is_write_heavy(reads=1, writes=50) is False


def test_unused_reads_zero_not_write_heavy():
    assert classify_usage_row({"reads": 0, "writes": 5_000_000, "eligible": True}) == "unused"


def test_mutual_exclusion():
    assert classify_usage_row({"reads": 0, "writes": 10_000, "eligible": True}) != "write_heavy"
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_index_health_service.py -v
```

Expected: import / not defined failures

- [ ] **Step 3: Implement constants + helpers**

```python
# modules/indexes/constants.py
INDEX_USAGE_MIN_UPTIME_DAYS = 7
INDEX_WRITE_HEAVY_MIN_WRITES = 1000
INDEX_WRITE_HEAVY_MIN_DIFF = 10000
INDEX_WRITE_HEAVY_MIN_RATIO = 10
INDEX_CAP_UNUSED = 50
INDEX_CAP_WRITE_HEAVY = 50
INDEX_CAP_MISSING = 25

# modules/indexes/service.py
def is_write_heavy(reads: int, writes: int) -> bool:
    reads = int(reads or 0)
    writes = int(writes or 0)
    if reads <= 0:
        return False
    if writes <= reads:
        return False
    if writes < INDEX_WRITE_HEAVY_MIN_WRITES:
        return False
    if (writes - reads) >= INDEX_WRITE_HEAVY_MIN_DIFF:
        return True
    return writes >= reads * INDEX_WRITE_HEAVY_MIN_RATIO  # multiply, not divide


def classify_usage_row(row: dict) -> str | None:
    if not row.get("eligible", True):
        return None
    reads = int(row.get("reads") or 0)
    writes = int(row.get("writes") or 0)
    if reads == 0:
        return "unused"
    if is_write_heavy(reads, writes):
        return "write_heavy"
    return None
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_index_health_service.py -v
```

- [ ] **Step 5: Commit** (only if user asked to commit; otherwise skip)

```bash
git add modules/indexes/constants.py modules/indexes/service.py tests/test_index_health_service.py
git commit -m "feat(indexes): add write-heavy/unused classification helpers"
```

---

### Task 2: Confidence + duplicate grouping + script builders (TDD)

**Files:**
- Modify: `modules/indexes/service.py`
- Modify: `tests/test_index_health_service.py`

**Interfaces:**
- Produces:
  - `assign_confidence(category, *, uptime_days, writes=0) -> tuple[str, str]` → `(confidence, confidence_reason)`
  - `group_exact_duplicates(inventory_rows: list[dict]) -> list[dict]`  
    Each group: `{group_id, schema, table, members: [...], excess: [...]}`  
    Key = `(object_id, key_cols_ordered, includes_sorted, filter or "")`
  - `quotename(ident: str) -> str`
  - `build_disable_drop_script(schema, table, index_name) -> str`
  - `build_create_missing_script(...)` → suggested CREATE text

- [ ] **Step 1: Write failing tests**

```python
from modules.indexes.service import (
    assign_confidence,
    group_exact_duplicates,
    build_disable_drop_script,
    quotename,
)


def test_duplicate_heap_always_high():
    c, _ = assign_confidence("duplicate", uptime_days=1)
    assert c == "high"
    c, _ = assign_confidence("heap", uptime_days=1)
    assert c == "high"


def test_unused_low_when_short_uptime():
    c, reason = assign_confidence("unused", uptime_days=2, writes=1_000_000)
    assert c == "low"
    assert "restart" in reason.lower() or "2" in reason


def test_missing_at_most_medium():
    c, _ = assign_confidence("missing", uptime_days=30)
    assert c in ("medium", "low")
    assert c != "high"


def test_exact_duplicate_group():
    rows = [
        {"object_id": 1, "schema_name": "dbo", "table_name": "T", "index_name": "IX_A",
         "key_cols": "A,B", "include_cols": "C", "filter_def": ""},
        {"object_id": 1, "schema_name": "dbo", "table_name": "T", "index_name": "IX_B",
         "key_cols": "A,B", "include_cols": "C", "filter_def": ""},
        {"object_id": 1, "schema_name": "dbo", "table_name": "T", "index_name": "IX_C",
         "key_cols": "A", "include_cols": "", "filter_def": ""},
    ]
    groups = group_exact_duplicates(rows)
    assert len(groups) == 1
    assert len(groups[0]["members"]) == 2
    assert len(groups[0]["excess"]) == 1


def test_script_quotes_and_review_header():
    s = build_disable_drop_script("dbo", "My Table", "IX_x")
    assert s.startswith("-- REVIEW ONLY")
    assert "[My Table]" in s or quotename("My Table") in s
    assert "DISABLE" in s and "DROP INDEX" in s
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_index_health_service.py -v
```

- [ ] **Step 3: Implement** `assign_confidence`, `group_exact_duplicates`, `quotename`, script builders per frozen spec wording:
  - Script label concept: both DISABLE and DROP in one script; recommendation elsewhere notes disable is reversible but still needs workload validation
  - Includes compared as sorted sets of names; keys as ordered list string

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit** (if requested)

---

### Task 3: `build_index_health` assembly (TDD on fake raw)

**Files:**
- Modify: `modules/indexes/service.py`
- Modify: `tests/test_index_health_service.py`

**Interfaces:**
- Produces:
  - `build_index_health(raw: dict) -> dict` with shape:

```python
{
  "database_name": str,
  "uptime": {
    "sqlserver_start_time": str | None,
    "uptime_days": float,
    "insufficient": bool,  # uptime_days < INDEX_USAGE_MIN_UPTIME_DAYS
  },
  "summary": {
    "unused": int,
    "write_heavy": int,
    "duplicate_excess": int,
    "heaps": int,
    "missing": int,
    "missing_total": int,  # before/after awareness for "top N of M"
    "reviewable_index_space_mb": float | None,
  },
  "findings": [IndexFinding dicts...],  # each with category, confidence, metrics nested, scripts, table_indexes
  "errors": {"unused": str | None, ...},  # soft-fail messages per section
}
```

**Raw input contract** (from provider later):

```python
raw = {
  "database_name": "MyDb",
  "sqlserver_start_time": datetime | None,
  "usage_rows": [...],      # eligible NC + reads/writes/size_mb + names
  "heap_rows": [...],
  "inventory_rows": [...],  # ALL indexes needed for duplicate detect on tables that appear; see provider task for scope
  "missing_rows": [...],    # may be longer than cap; service caps
  "errors": {},             # optional per-key errors from provider
}
```

**Assembly rules:**
1. Classify usage → unused / write_heavy lists; sort; apply caps
2. Duplicates from inventory (exact groups only)
3. Heaps from heap_rows
4. Missing: sort by impact_score → **cap to INDEX_CAP_MISSING** → then attach `table_indexes` filtered from inventory by those object_ids only (if inventory is broader, filter; if provider already scoped, still filter defensively)
5. Assign confidence per finding
6. Build scripts (not for heaps)
7. Summary + reviewable space = sum size_mb of unused + duplicate excess members

- [ ] **Step 1: Write failing integration-style unit test with fake raw** covering mutual exclusion, missing cap-before-context (inventory for uncapped object must not be required), reviewable space, confidence on unused short uptime

```python
def test_build_caps_missing_before_needing_extra_tables():
    raw = {
        "database_name": "D",
        "sqlserver_start_time": None,  # service treats as insufficient or 0 days
        "usage_rows": [],
        "heap_rows": [],
        "inventory_rows": [
            {"object_id": 1, "schema_name": "dbo", "table_name": "T1", "index_name": "IX1",
             "key_cols": "a", "include_cols": "", "filter_def": "", "is_unique": False, "type": "NONCLUSTERED"},
        ],
        "missing_rows": [
            {"object_id": 1, "schema_name": "dbo", "table_name": "T1", "impact_score": 100,
             "equality_columns": "a", "inequality_columns": None, "included_columns": None,
             "user_seeks": 10, "avg_user_impact": 50, "avg_total_user_cost": 2.0},
        ] + [
            {"object_id": 999, "schema_name": "dbo", "table_name": "Other", "impact_score": 1,
             "equality_columns": "z", "inequality_columns": None, "included_columns": None,
             "user_seeks": 1, "avg_user_impact": 1, "avg_total_user_cost": 1.0},
        ] * 30,  # enough noise; only top scores matter
        "errors": {},
    }
    # Force many missing with object 999 lower score — after cap, finding for 999 may be absent
    out = build_index_health(raw)
    assert out["summary"]["missing"] <= 25
    # Any missing finding for T1 must include table_indexes from inventory
    for f in out["findings"]:
        if f["category"] == "missing" and f["table_name"] == "T1":
            assert f["table_indexes"]
```

Adjust fixture so impact scores clearly prefer object_id 1 in top 25.

- [ ] **Step 2: Run FAIL → implement `build_index_health` → PASS**

- [ ] **Step 3: Commit** (if requested)

---

### Task 4: Provider snapshot — query shapes (soft-fail)

**Files:**
- Modify: `core/providers/sqlserver_provider.py`
- Optional: `core/providers/base.py` Protocol method (nice-to-have; not blocking)

**Interfaces:**
- Produces: `SqlServerProvider.get_index_health_snapshot() -> dict` matching Task 3 `raw` contract

**Query order inside the method (mandatory):**

1. **E — start time**  
   `SELECT sqlserver_start_time FROM sys.dm_os_sys_info`

2. **A — usage + size** (NC eligible)  
   Catalog indexes LEFT JOIN `dm_db_index_usage_stats` (current `database_id`)  
   Size: `SUM(used_page_count)*8.0/1024` from `sys.dm_db_partition_stats` (NOT physical_stats)  
   Filter: user tables, `type_desc = N'NONCLUSTERED'`, not PK/unique/unique_constraint/disabled/hypothetical  
   Emit: schema, table, index_name, object_id, index_id, reads, writes, size_mb, eligible=True

3. **B — heaps**  
   User tables with heap and no clustered index

4. **D — missing**  
   Join missing-index DMVs; compute `impact_score`; order desc; fetch a safe upper bound (e.g. top 200) so service can report “top N of M” with `M = min(200, full)` or run count query — keep simple: fetch top 200, `missing_total = len(rows)` before service cap, service caps to 25

5. **C — inventory (scoped, measured)**  
   - Collect distinct `object_id` from: usage rows, heap object_ids, and **capped** missing object_ids (cap Missing to 25 **before** attaching missing context).  
   - **Duplicate detection inventory strategy (v1):**  
     1. **Default attempt:** one inventory query for all nonclustered indexes in the current DB (keys/includes/filter via `STRING_AGG` or FOR XML PATH).  
     2. **Must measure/log duration and row count** (structured log: `index_health.inventory_ms`, `index_health.inventory_rows`).  
     3. **If too expensive** (guideline: e.g. &gt; ~3s or &gt; ~5k NC indexes — tune constants in provider): **fallback** to inventory **only for touched tables** — object_ids from usage + heaps + capped missing. Duplicate detection then runs only within that subset (may miss duplicates on cold tables; acceptable MVP trade-off vs turning the Indexes page into a workload).  
   - When attaching missing `table_indexes` in service, filter inventory to capped missing object_ids only.

6. Soft-fail: wrap each query in try/except → `errors["usage"]=str(e)`, empty list; continue

**Display ratio only (optional column):** `CASE WHEN reads=0 THEN NULL ELSE writes*1.0/reads END` — classification still uses multiply gate in Python.

**Annotation (review):** Full-DB NC inventory is valuable for duplicates but must not dominate page cost. Prefer correct duplicates when cheap; prefer scoped inventory when measured cost is high.

- [ ] **Step 1: Implement `get_index_health_snapshot`** with the five batches and error dict

- [ ] **Step 2: Manual smoke** (against a non-prod instance if available): call provider, print summary keys / error keys / row counts — no UI yet

- [ ] **Step 3: Commit** (if requested)

---

### Task 5: Module shell UI (layout + CSS)

**Files:**
- Create: `modules/indexes/layout.py`
- Create: `modules/indexes/__init__.py`
- Modify: `assets/custom.css`

**Interfaces:**
- Produces:
  - `build_indexes_layout() -> html.Div` with ids:
    - `btn-indexes-refresh`
    - `indexes-health-strip`
    - `indexes-uptime-banner`
    - `indexes-loading`
    - `indexes-meta`
    - `indexes-body`
    - `store-indexes`
  - `render_indexes_view(payload: dict) -> (strip_children, banner, body, meta)`

**UI content rules:**
- Strip cards: Unused, Write-heavy, Duplicate, Heaps, Missing, Reviewable index space (+ tooltip text from spec)
- Sections by category; finding row: **primary** = recommendation / review text; **secondary** = “Copy script” (do not visually promote scripts as the main action)
- Confidence badge+reason (skip freshness chip on duplicate/heap)
- Loading card centered (reuse `activity-loading` patterns)
- Unused/write_heavy recommendation notes disable is reversible but still needs workload validation (not “safe action”)
- Scripts always include `-- REVIEW ONLY`; generate in service, expose only via secondary copy control

- [ ] **Step 1: Build layout shell + render functions using fake payload in a tiny manual check or unit test that render returns non-empty for sample dict**

- [ ] **Step 2: Add CSS classes under `.indexes-*` matching dark UI of Insights/Activity (severity borders, confidence pills)

- [ ] **Step 3: Commit** (if requested)

---

### Task 6: Callbacks + app / registry wiring

**Files:**
- Create: `modules/indexes/callbacks.py`
- Modify: `core/registry.py` — indexes `status: "ready"`, subtitle `"Health glance & recommendations"`
- Modify: `app.py` — import layout/callbacks; add `module-indexes` panel; allow tile switch to `indexes`; `show_module` outputs/classes/label; `register_indexes_callbacks(app)`

**Callback behavior (fetch discipline — critical):**

```text
Home → click Indexes → fetch ONCE → store payload → render from store
Refresh button → explicit fetch → replace store → render
```

- **Do not** re-query SQL on every Dash re-render, layout paint, or unrelated store change.
- Trigger fetch only when:
  1. `store-module` **transitions to** `"indexes"` (enter module), or
  2. `btn-indexes-refresh` is clicked while module is indexes.
- Pattern: compare previous module vs current (State of store-module + ctx.triggered_id), or use a one-shot clientside loading + server callback that returns `no_update` for store when trigger is not enter/refresh.
- **No auto-interval** for Indexes in v1.
- Render functions read **only** from `store-indexes` (or callback outputs derived from the single fetch). Never call provider inside a pure render path.
- Manual refresh: top-right toast “Refreshing indexes…” then clear when done (app-root toast pattern).
- Soft-fail errors already in payload; hard failure → toast + empty body message.

**Annotation (review):** Dash callback chains easily multi-fire; gate on enter-once + explicit Refresh only.

- [ ] **Step 1: Wire registry + app panel + switch_module allow-list**

- [ ] **Step 2: Implement `register_indexes_callbacks`**

- [ ] **Step 3: Manual UI test:** Home → Indexes → loading → strip/sections; copy script; confirm no DDL

- [ ] **Step 4: Commit** (if requested)

---

### Task 7: Acceptance pass + regression tests

**Files:**
- Modify tests as needed
- Manual checklist from spec §13

- [ ] **Step 1: Run full relevant suite**

```bash
pytest tests/test_index_health_service.py tests/test_blocking_tree.py -v
```

- [ ] **Step 2: Walk acceptance checklist in spec** (confidence chips, reviewable space wording, missing context, mutual exclusion, no physical_stats in provider SQL — grep the provider file)

```bash
rg "dm_db_index_physical_stats" core/providers/sqlserver_provider.py
```

Expected: no matches for index health path

- [ ] **Step 3: Commit** (if requested)

---

## Spec coverage (self-check)

| Spec area | Task |
|-----------|------|
| Write-heavy constants + multiply gate | 1 |
| Mutual exclusion | 1, 3 |
| Confidence + reason + structural high | 2, 3 |
| Exact duplicates + excess count | 2, 3 |
| Scripts + REVIEW ONLY + DISABLE wording | 2, 5 |
| Missing cap-then-context attach | 3, 4 |
| Reviewable index space + tooltip | 3, 5 |
| partition_stats size / no physical_stats | 4 |
| Soft-fail per section | 4, 6 |
| UI strip / loading / toasts / registry | 5, 6 |
| No Metric Store / no DDL / no XE / current DB | Global + 4–6 |
| Acceptance | 7 |

## Out of plan (do not implement)

Fragmentation, overlap graph, multi-DB, Metric Store score, executing DDL, auto-interval noise.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-05-index-health.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

Which approach?
