# Blocking Tree (Live) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Activity → Blocking pair-cards with nested head-blocker trees, blast radius / chain age strip, SQL snippets, and batched per-database wait-object resolve (`schema.table` or `None`).

**Architecture:** Keep `get_blocking` DMV edges. Add pure helpers: graph/tree builder + `resolve_wait_object` (batch by `db_id`). UI `render_blocking_table` becomes tree cards with collapse. No Metric Store / collector writes.

**Tech Stack:** Python 3, Dash/HTML, existing `SqlServerProvider` + `pyodbc`/`connect`, `pytest`, `assets/custom.css`

**Spec:** `docs/superpowers/specs/2026-08-01-blocking-tree-design.md`

## Global Constraints

- `resolve_wait_object(...) -> str | None` returns only `schema.table` or `None` (never raw `wait_resource`)
- Exceptions in resolve → log + `None`; never fail Live Blocking
- Batch resolve: group unique keys **by `db_id`**, one batched SQL per db (not global cross-db, not per-node)
- Filter `blocker_id == blocked_id`; break cycles → independent root (no infinite loop)
- Strip blast radius = **union** of blocked SPIDs across roots (dedupe globally)
- No insight Metric Store / collector `dim` changes in this plan
- No new required stored procedures (inline SQL / Python helpers only)

---

## File map

| File | Responsibility |
|------|----------------|
| `core/wait_resource.py` | Parse resource strings; `resolve_wait_object`; `resolve_wait_objects_batch` |
| `core/blocking_tree.py` | Build trees from edge rows; blast/chain_age aggregates |
| `tests/test_wait_resource.py` | Parser + batch grouping + None-on-error |
| `tests/test_blocking_tree.py` | Graph, self-edge, cycle, blast dedupe, chain age |
| `modules/activity/layout.py` | `render_blocking_table` tree UI; health strip labels |
| `assets/custom.css` | Tree / blast / collapse styles |
| `core/providers/sqlserver_provider.py` | Optional: attach nothing required if resolve runs after fetch in service/layout |
| `modules/activity/service.py` | After `fetch_blocking`, run batch resolve + tree enrich OR leave enrich in layout |

**Recommendation:** enrich in `modules/activity/service.py` (or a thin `modules/activity/blocking_view.py`) so layout stays presentational: `fetch_blocking` → rows → `build_blocking_trees(rows)` → `attach_wait_objects(trees)` → render.

---

### Task 1: Wait-resource parse + resolve API (unit-tested, no UI)

**Files:**
- Create: `core/wait_resource.py`
- Create: `tests/test_wait_resource.py`

**Interfaces:**
- Produces:
  - `parse_wait_resource(wait_resource: str) -> dict | None` with keys like `kind` (`object`|`key`|`page`|`rid`), `db_id: int`, plus `object_id` / `hobt_id` / file/page as relevant
  - `resolve_wait_object(wait_resource: str, wait_type: str | None = None, *, executor=None) -> str | None`
  - `resolve_wait_objects_batch(items: list[tuple[str, str | None]], *, executor) -> dict[str, str | None]`  
    Key = `wait_resource` string (or `(resource, type)` if needed); values `schema.table` or `None`  
    Internally: unique → group by `db_id` → one lookup SQL per db

- [ ] **Step 1: Write failing tests**

```python
# tests/test_wait_resource.py
from core.wait_resource import parse_wait_resource, resolve_wait_object, resolve_wait_objects_batch

def test_parse_object():
    p = parse_wait_resource("OBJECT: 5:688773561:0")
    assert p["kind"] == "object"
    assert p["db_id"] == 5
    assert p["object_id"] == 688773561

def test_parse_key_hobt():
    p = parse_wait_resource("KEY: 7:72057594039926784 (abcd1234)")
    assert p["kind"] == "key"
    assert p["db_id"] == 7
    assert p["hobt_id"] == 72057594039926784

def test_resolve_returns_none_on_unknown():
    assert resolve_wait_object("UNKNOWN: foo", "LCK_M_S") is None

def test_resolve_swallows_executor_errors():
    def boom(*a, **k):
        raise RuntimeError("db down")
    assert resolve_wait_object("OBJECT: 5:1:0", "LCK_M_X", executor=boom) is None

def test_batch_groups_by_db_id():
    calls = []
    def fake_executor(db_id, specs):
        calls.append((db_id, tuple(sorted(specs, key=str))))
        # specs: list of parsed dicts for this db
        out = {}
        for s in specs:
            out[s["resource"]] = f"dbo.T{s.get('object_id') or s.get('hobt_id')}"
        return out

    items = [
        ("OBJECT: 5:10:0", "LCK_M_X"),
        ("OBJECT: 5:11:0", "LCK_M_X"),
        ("OBJECT: 8:20:0", "LCK_M_S"),
        ("OBJECT: 5:10:0", "LCK_M_X"),  # dup
    ]
    m = resolve_wait_objects_batch(items, executor=fake_executor)
    assert len(calls) == 2  # db 5 and db 8 only
    assert m["OBJECT: 5:10:0"] == "dbo.T10"
    assert m["OBJECT: 8:20:0"] == "dbo.T20"
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

Run: `pytest tests/test_wait_resource.py -v`  
Expected: import / not found failures

- [ ] **Step 3: Implement `core/wait_resource.py`**

- Regex parsers for OBJECT / KEY / PAGE / RID (best-effort; unknown → None)
- `resolve_wait_object`: try/except around executor; success string must match `schema.table` pattern; else None
- Default executor (when `executor is None`): use `core.connection.connect` and run db-scoped SQL:
  - OBJECT: `SELECT OBJECT_SCHEMA_NAME(@oid, @dbid) + '.' + OBJECT_NAME(@oid, @dbid)`
  - KEY: query `sys.partitions` in that database via three-part name or `USE`/`DB_NAME` — prefer:
    ```sql
    SELECT OBJECT_SCHEMA_NAME(p.object_id, @dbid) + N'.' + OBJECT_NAME(p.object_id, @dbid)
    FROM sys.partitions p WHERE p.hobt_id = @hobt
    ```
    Note: `sys.partitions` is database-scoped; for cross-db use dynamic SQL / `Database.sys.partitions` with quotename(db name from `DB_NAME(@dbid)`).
  - Batch executor: for each db_id, one round-trip resolving all object_ids / hobt_ids in that group (TVP or UNION ALL of VALUES)
- Never return raw `wait_resource`

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_wait_resource.py -v`

- [ ] **Step 5: Commit**

```bash
git add core/wait_resource.py tests/test_wait_resource.py
git commit -m "feat: add batched wait_resource resolve helper"
```

---

### Task 2: Blocking tree builder

**Files:**
- Create: `core/blocking_tree.py`
- Create: `tests/test_blocking_tree.py`

**Interfaces:**
- Consumes: list of edge dicts (same field names as `get_blocking` rows)
- Produces:
  - `build_blocking_trees(rows: list[dict]) -> list[dict]` each root:
    ```python
    {
      "head_session_id": int,
      "head": {...node fields for head...},
      "children": [node, ...],  # nested
      "blast_radius": int,      # distinct descendants (blocked under this root)
      "chain_age_sec": int,
      "blocked_spids": set[int] | list[int],
    }
    ```
  - `summarize_blocking_trees(trees) -> dict` with `head_blockers`, `blast_radius` (global unique blocked SPIDs), `chain_age_sec` (max)

- [ ] **Step 1: Failing tests**

```python
from core.blocking_tree import build_blocking_trees, summarize_blocking_trees

def _edge(blocker, blocked, *, head=1, elapsed=10, wait_ms=1000, **kw):
    return {
        "blocker_session_id": blocker,
        "blocked_session_id": blocked,
        "is_head_blocker": head,
        "request_elapsed_sec": elapsed,
        "wait_time": wait_ms,
        "wait_seconds": wait_ms / 1000,
        "wait_resource": kw.get("wait_resource", "OBJECT: 1:1:0"),
        "wait_type": "LCK_M_S",
        "blocker_login": "head_login",
        "blocked_login": "victim",
        "blocker_sql": "UPDATE t SET x=1",
        "blocked_sql": "SELECT 1 FROM t",
        "blocker_command": "UPDATE",
        "blocked_command": "SELECT",
        "chain_display": f"{blocker} -> {blocked}",
        **kw,
    }

def test_filters_self_block():
    trees = build_blocking_trees([_edge(5, 5)])
    assert trees == []

def test_simple_tree():
    rows = [_edge(874, 1156, elapsed=160), _edge(874, 1101, elapsed=40)]
    trees = build_blocking_trees(rows)
    assert len(trees) == 1
    assert trees[0]["head_session_id"] == 874
    assert trees[0]["blast_radius"] == 2
    assert trees[0]["chain_age_sec"] == 160

def test_nested_indirect():
    # 1 blocks 2, 2 blocks 3  → one root 1 with child 2 → child 3
    rows = [
        _edge(1, 2, head=1, elapsed=50),
        _edge(2, 3, head=0, elapsed=30),
    ]
    trees = build_blocking_trees(rows)
    assert len(trees) == 1
    assert trees[0]["head_session_id"] == 1
    kids = trees[0]["children"]
    assert kids[0]["session_id"] == 2
    assert kids[0]["children"][0]["session_id"] == 3

def test_cycle_becomes_safe_roots():
    rows = [_edge(10, 11, head=0), _edge(11, 10, head=0)]
    trees = build_blocking_trees(rows)
    assert len(trees) >= 1  # no hang; finite

def test_blast_dedupe_across_roots():
    # same victim under two roots in racy snapshot
    rows = [_edge(1, 99, head=1), _edge(2, 99, head=1)]
    trees = build_blocking_trees(rows)
    summary = summarize_blocking_trees(trees)
    assert summary["blast_radius"] == 1
    assert summary["head_blockers"] == 2
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/test_blocking_tree.py -v`

- [ ] **Step 3: Implement `core/blocking_tree.py`**

- Dedupe edges; drop self-edges
- Build adjacency + reverse; detect roots (`is_head_blocker` or not blocked)
- DFS/BFS children with path-set cycle break
- Attach display fields needed by UI onto nodes
- `summarize_blocking_trees`: union of all `blocked_spids`

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add core/blocking_tree.py tests/test_blocking_tree.py
git commit -m "feat: build nested blocking trees from DMV edges"
```

---

### Task 3: Wire resolve + trees into Activity fetch path

**Files:**
- Modify: `modules/activity/service.py`
- Optionally thin: keep `fetch_blocking` returning same envelope but add `summary` keys + `trees` list on result dict

**Interfaces:**
- Consumes: `build_blocking_trees`, `summarize_blocking_trees`, `resolve_wait_objects_batch`
- Produces: result dict with `trees`, updated `summary` (`blast_radius`, `head_blockers`, `chain_age_sec`, keep legacy keys if useful)

- [ ] **Step 1: Extend `fetch_blocking`**

After provider returns rows:

1. `trees = build_blocking_trees(rows)`
2. Collect `(wait_resource, wait_type)` from every node
3. `amap = resolve_wait_objects_batch(...)` (real DB executor; on total failure empty map)
4. Walk trees; set `node["wait_object"] = amap.get(resource)`
5. `summary = {**old_summary, **summarize_blocking_trees(trees)}`
6. Attach `result["trees"] = trees` (rows can remain for debugging)

- [ ] **Step 2: Manual / unit smoke** (mock provider if tests exist)

If no integration DB: unit-test a small pure function `enrich_blocking_result(rows) -> dict` extracted for testability.

- [ ] **Step 3: Commit**

```bash
git add modules/activity/service.py
git commit -m "feat: enrich blocking fetch with trees and wait_object"
```

---

### Task 4: Health strip + tree UI + CSS

**Files:**
- Modify: `modules/activity/layout.py` (`render_health_strip` for `tab=="blocking"`, replace body of `render_blocking_table`)
- Modify: `assets/custom.css`

**Interfaces:**
- Consumes: `result["trees"]`, summary keys `blast_radius`, `head_blockers`, `chain_age_sec`
- Collapse: show first 2 children; button expands rest (Dash `html.Details`/`summary` or pattern-matching Button + Store; prefer **`html.Details`** to avoid new callbacks)

- [ ] **Step 1: Health strip cards for blocking**

Labels: **Blast radius** (value = blast_radius), **Head blockers**, **Chain age** (`fmt_duration_hms(chain_age_sec * 1000)` or `fmt_running_label`).

- [ ] **Step 2: Render one card per root**

Structure (Dash html):

- Header row: head badge (spid) + `{login} — head blocker` + age on the right
- SQL one-liner + humanized resource (`wait_object` or humanize raw)
- Nested children with indent / tree rail
- Each child: badge, login, sql snippet, wait on right
- `html.Details` for overflow: summary text `+ {n} session دیگر under this root`

- [ ] **Step 3: CSS** for `.blk-tree`, `.blk-node`, `.blk-node.is-head`, `.blk-rail`, `.blk-sql`, `.blk-obj`, collapse pill (match dark theme; head red / victims orange per mock)

- [ ] **Step 4: Empty / permission paths unchanged**

- [ ] **Step 5: Commit**

```bash
git add modules/activity/layout.py assets/custom.css
git commit -m "feat: render blocking as nested trees with blast strip"
```

---

### Task 5: Humanize raw resource (UI-only fallback)

**Files:**
- Modify: `core/wait_resource.py` add `format_wait_resource_display(raw: str, wait_object: str | None) -> str`  
  OR keep formatter in layout as `_humanize_wait_resource`

Rule: if `wait_object`: show that; else show cleaned raw (spaces, drop useless suffixes) — **must not** feed this string into resolve return values.

- [ ] **Step 1: Small unit test for display helper**
- [ ] **Step 2: Use in tree node render**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat: humanize unresolved wait_resource in blocking UI"
```

---

### Task 6: Verification

- [ ] **Step 1:** `pytest tests/test_wait_resource.py tests/test_blocking_tree.py -v`
- [ ] **Step 2:** Manually open Activity → Blocking with auto-refresh; confirm strip labels, tree nesting, collapse, no crash when no blocking
- [ ] **Step 3:** Confirm resolve batching logs / debugger: round-trips ≤ distinct db_ids
- [ ] **Step 4:** Final commit if polish needed

---

## Spec coverage check

| Spec item | Task |
|-----------|------|
| Nested tree / head root | 2, 4 |
| Blast radius + global SPID dedupe | 2, 4 |
| Chain age max elapsed | 2, 4 |
| SQL snippet | 4 |
| Resolve schema.table / None + try/except | 1 |
| Batch per db_id | 1, 3 |
| Self-block + cycle | 2 |
| UI humanize raw fallback | 5 |
| Collapse +N | 4 |
| No Metric Store | Global constraint |
| V1.5-ready resolve API | 1 |

## Placeholder scan

None intentional — executor SQL details are specified for OBJECT/KEY; PAGE/RID may return None until extended (allowed by spec best-effort).
