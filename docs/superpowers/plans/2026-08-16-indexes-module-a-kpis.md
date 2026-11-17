# Indexes Module A — Overview KPI + Confidence Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align Indexes Overview metric strip with the four v1 KPIs (no Consolidation), wire i18n labels, and audit confidence ≥ 70 copy-script gating on Explorer recommendations — without changing Advisor capture wiring (that is **B**).

**Architecture:** Pure KPI computation in `modules/indexes/service.py` from the existing overview payload; `panels.render_overview` only renders; Explorer rec cards show `script_blocked_reason` when gated. Consolidation remains out of Overview KPIs; Explorer `CONSOLIDATE` category is relabeled to overlap/duplicate signal (no Super Index scripts).

**Tech Stack:** Python 3, Dash/HTML components, `core.i18n`, pytest

**Spec:** `docs/superpowers/specs/2026-08-16-index-module-v1-design.md` §5, §4.2, §8, §9A  
**Out of scope (B / later):** Preferring Advisor freshness window, delta usage from two runs, Phase 2 MissingIndexSnapshot, new frag Agent job

## Global Constraints

- Read-only: never execute DDL/DML on customer DBs  
- No Consolidation / Super Index KPI or merge script packages  
- Confidence copy gate: `INDEX_CONFIDENCE_SCRIPT_MIN = 70`  
- No emoji in tags/KPI labels  
- Numbers: `fmt_int` / `fmt_compact` / `fmt_size_mb` from `core.formatters`  
- Do not remount Indexes module on locale change (existing `apply_locale_chrome` rule)  
- Commit only if the user explicitly asks (otherwise skip commit steps)

---

## File map

| File | Responsibility |
|------|----------------|
| `modules/indexes/service.py` | `compute_overview_kpis()`; extend `build_overview_payload` with `kpis` |
| `modules/indexes/panels.py` | Render four KPI cards + frag “—” state |
| `modules/indexes/layout.py` | Explorer rec cards: blocked reason; relabel `CONSOLIDATE` |
| `modules/indexes/intelligence.py` | Ensure overlap recs stay script-empty; wording without Super Index |
| `core/i18n.py` | EN/FA strings for KPI + blocked-script chrome |
| `tests/test_index_overview_kpis.py` | New unit tests for KPI pure function |
| `tests/test_index_layout.py` | Overview/Explorer smoke assertions |
| `tests/test_index_health_service.py` | Gate regression if missing |

---

### Task 1: Pure KPI builder + tests

**Files:**
- Create: `tests/test_index_overview_kpis.py`
- Modify: `modules/indexes/service.py` (add `compute_overview_kpis` near `build_overview_payload`)

**Interfaces:**
- Consumes: overview-shaped dict with `totals`, `sections` / raw lists (`unused`, `write_heavy`, `missing_by_table`), optional `frag_loaded` / `totals.high_frag`
- Produces:

```python
def compute_overview_kpis(raw_or_payload: dict) -> dict:
    """
    Returns:
      {
        "missing_impact": {"value": int|float|None, "display": "int"| "dash", "sub_key": str, "tone": str},
        "high_frag": {"value": int|None, "display": "int"|"dash", "sub_key": str, "tone": str},
        "dead_unused_writes": {"value": int, "display": "int", "sub_key": str, "tone": str, "writes": int},
        "duplicate_debt": {"value": int, "display": "int", "sub_key": str, "tone": str},
      }
    sub_key = i18n key suffix under indexes.kpi.* (resolved in UI)
    """
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_index_overview_kpis.py
from modules.indexes.service import compute_overview_kpis


def test_kpis_missing_impact_sums_scores():
    k = compute_overview_kpis(
        {
            "totals": {"missing_suggestions": 2, "high_frag": 0},
            "unused": [{"writes": 50000, "size_mb": 10}],
            "missing_by_table": [
                {"impact_score": 1000, "avg_user_impact": 50},
                {"impact_score": 500},
            ],
            "duplicates": [{"database_name": "D", "table_name": "T"}],
            "frag_loaded": False,
        }
    )
    assert k["missing_impact"]["display"] == "int"
    assert k["missing_impact"]["value"] == 1500
    assert k["dead_unused_writes"]["value"] == 1
    assert k["dead_unused_writes"]["writes"] == 50000
    assert k["duplicate_debt"]["value"] == 1
    assert k["high_frag"]["display"] == "dash"
    assert k["high_frag"]["value"] is None


def test_kpis_high_frag_when_loaded():
    k = compute_overview_kpis(
        {
            "totals": {"high_frag": 12},
            "frag_loaded": True,
            "unused": [],
            "missing_by_table": [],
            "duplicates": [],
        }
    )
    assert k["high_frag"]["display"] == "int"
    assert k["high_frag"]["value"] == 12


def test_kpis_no_consolidation_key():
    k = compute_overview_kpis({"totals": {}, "unused": [], "missing_by_table": [], "duplicates": []})
    assert "consolidation" not in k
    assert set(k) == {
        "missing_impact",
        "high_frag",
        "dead_unused_writes",
        "duplicate_debt",
    }
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_index_overview_kpis.py -v`  
Expected: `ImportError` or `compute_overview_kpis` not defined

- [ ] **Step 3: Implement `compute_overview_kpis`**

Logic (exact):

```python
def compute_overview_kpis(raw: dict) -> dict:
    totals = raw.get("totals") or {}
    unused = raw.get("unused") or (raw.get("sections") or {}).get("unused") or []
    missing = raw.get("missing_by_table") or (raw.get("sections") or {}).get("missing_by_table") or []
    duplicates = raw.get("duplicates") or (raw.get("sections") or {}).get("duplicates") or []

    # missing_impact: sum impact scores; fallback count * 0 display still int 0
    impact = 0.0
    for row in missing:
        impact += float(_missing_impact_score(row) or 0)
    missing_value = int(round(impact)) if missing else int(totals.get("missing_suggestions") or 0)

    # high_frag: only when frag evidence exists
    frag_loaded = bool(raw.get("frag_loaded"))
    high_frag_total = totals.get("high_frag")
    if frag_loaded or high_frag_total is not None and raw.get("source") == "advisor":
        # Advisor may store NULL frag on rows but still expose high_frag count from probe — 
        # Prefer: show int only if frag_loaded OR (high_frag_total is not None AND raw.get("frag_available"))
        pass
```

**Clarify in implementation (locked rule from spec):**

- If `raw.get("frag_available")` is True **or** `frag_loaded` is True → `high_frag.display = "int"`, value = `int(totals.get("high_frag") or 0)`  
- Else → `display = "dash"`, `value = None`, `sub_key = "frag_pending"` (UI: “Load frag” / “Frag not loaded”)  
- Do **not** treat missing key as 0 critical indexes  

```python
    dead_rows = [r for r in unused if int(r.get("writes") or 0) > 0]
    dead_writes = sum(int(r.get("writes") or 0) for r in dead_rows)

    dup_n = len(duplicates)
    if dup_n == 0:
        dup_n = int(totals.get("duplicates") or totals.get("duplicate_tables") or 0)

    return {
        "missing_impact": {
            "value": missing_value,
            "display": "int",
            "sub_key": "missing_sub",
            "tone": "is-warn" if missing_value else "",
        },
        "high_frag": (
            {
                "value": int(totals.get("high_frag") or 0),
                "display": "int",
                "sub_key": "frag_sub",
                "tone": "is-warn" if int(totals.get("high_frag") or 0) else "",
            }
            if (raw.get("frag_available") or raw.get("frag_loaded"))
            else {
                "value": None,
                "display": "dash",
                "sub_key": "frag_pending",
                "tone": "",
            }
        ),
        "dead_unused_writes": {
            "value": len(dead_rows),
            "writes": dead_writes,
            "display": "int",
            "sub_key": "unused_writes_sub",
            "tone": "is-warn" if dead_rows else "",
        },
        "duplicate_debt": {
            "value": dup_n,
            "display": "int",
            "sub_key": "duplicate_sub",
            "tone": "is-warn" if dup_n else "",
        },
    }
```

Also set in `build_overview_payload`:

```python
payload["kpis"] = compute_overview_kpis({
    **raw,
    "unused": payload["sections"]["unused"],
    "missing_by_table": payload["sections"]["missing_by_table"],
    "duplicates": raw.get("duplicates") or [],
    "frag_available": bool(raw.get("frag_available") or raw.get("frag_loaded")),
    "frag_loaded": bool(raw.get("frag_loaded")),
    "totals": payload["totals"],
    "source": payload.get("source"),
})
```

Pass through `totals["duplicates"]` from raw when present:

```python
"duplicates": totals.get("duplicates") or 0,
"high_frag": totals.get("high_frag"),  # keep None if absent — do not coerce to 0 before KPI
```

Fix `build_overview_payload` so `high_frag` is not forced with `or 0` before KPI sees availability — store raw value and let KPI decide.

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_index_overview_kpis.py -v`  
Expected: all PASS

- [ ] **Step 5: Commit** (only if user requested commits)

```bash
git add modules/indexes/service.py tests/test_index_overview_kpis.py
git commit -m "feat(indexes): add overview KPI pure builder for v1 strip"
```

---

### Task 2: Render four Overview KPI cards + i18n

**Files:**
- Modify: `modules/indexes/panels.py` (`render_overview` metrics_grid ~240–279)
- Modify: `core/i18n.py` (EN + FA keys)
- Modify: `tests/test_index_layout.py` (assert KPI labels / structure)

**Interfaces:**
- Consumes: `payload["kpis"]` from Task 1; `locale` optional — today `render_overview(payload)` has no locale; add `locale: str = DEFAULT_LOCALE` and thread from callbacks if already available, else default `en` and rely on chrome locale later
- Produces: four `.idx-metric-card` nodes with ids for tests: `indexes-kpi-missing`, `indexes-kpi-frag`, `indexes-kpi-unused-writes`, `indexes-kpi-duplicates`

- [ ] **Step 1: Add i18n keys** (both `en` and `fa` dicts in `STRINGS`)

```python
"indexes.kpi.missing_impact": "Missing index impact",
"indexes.kpi.high_frag": "High frag (>30%)",
"indexes.kpi.dead_unused_writes": "Dead unused writes",
"indexes.kpi.duplicate_debt": "Duplicate indexes",
"indexes.kpi.missing_sub": "Optimizer hint score (sum)",
"indexes.kpi.frag_sub": "Indexes above 30% frag",
"indexes.kpi.frag_pending": "Frag not loaded — use Load fragmentation",
"indexes.kpi.unused_writes_sub": "{writes} writes on unused indexes",
"indexes.kpi.duplicate_sub": "Exact / overlap twins (no merge in v1)",
"indexes.kpi.dash": "—",
```

FA equivalents (natural Persian, no emoji).

- [ ] **Step 2: Replace metrics_grid in `render_overview`**

Remove cards: Unused Indexes / Write-Heavy / Heap Tables / Missing Index Hints as the **primary four**.  
Keep health ring as-is.

```python
from core.i18n import DEFAULT_LOCALE, normalize_locale, t
from core.formatters import fmt_compact, fmt_int

def render_overview(payload: dict | None, locale: str = DEFAULT_LOCALE):
    loc = normalize_locale(locale)
    ...
    kpis = payload.get("kpis") or compute_overview_kpis(payload)

    def kpi_card(kpi_id: str, title_key: str, cell: dict):
        if cell.get("display") == "dash":
            value_child = t("indexes.kpi.dash", loc)
        else:
            value_child = fmt_compact(cell.get("value") or 0) if kpi_id == "missing_impact" else fmt_int(cell.get("value") or 0)
        sub = t(f"indexes.kpi.{cell.get('sub_key')}", loc, writes=fmt_int(cell.get("writes") or 0))
        return html.Div(
            id=f"indexes-kpi-{kpi_id}",
            className=f"idx-metric-card {cell.get('tone') or ''}".strip(),
            children=[
                html.Div(value_child, className="idx-metric-value"),
                html.Div(t(title_key, loc), className="idx-metric-label"),
                html.Div(sub, className="idx-metric-sub"),
            ],
        )

    metrics_grid = html.Div(
        className="idx-metrics-grid",
        children=[
            kpi_card("missing", "indexes.kpi.missing_impact", kpis["missing_impact"]),
            kpi_card("frag", "indexes.kpi.high_frag", kpis["high_frag"]),
            kpi_card("unused-writes", "indexes.kpi.dead_unused_writes", kpis["dead_unused_writes"]),
            kpi_card("duplicates", "indexes.kpi.duplicate_debt", kpis["duplicate_debt"]),
        ],
    )
```

- [ ] **Step 3: Thread locale into overview render from callbacks**

In `modules/indexes/callbacks.py`, wherever `render_overview(payload)` is called, pass `locale=normalize_locale(locale)` from existing `store-locale` State (already on `load_overview`).

- [ ] **Step 4: Layout smoke test**

```python
def test_overview_has_four_v1_kpi_ids():
    from modules.indexes.service import build_overview_payload
    from modules.indexes.panels import render_overview

    payload = build_overview_payload({
        "sqlserver_start_time": "2026-01-01T00:00:00",
        "totals": {"indexes": 10, "need_review": 1, "unused": 1, "write_heavy": 0, "heaps": 0, "missing_suggestions": 1},
        "unused": [{"writes": 10, "database_name": "D", "schema_name": "dbo", "table_name": "T", "index_name": "IX"}],
        "write_heavy": [],
        "heaps": [],
        "missing_by_table": [{"impact_score": 100, "database_name": "D", "schema_name": "dbo", "table_name": "T"}],
        "frag_loaded": False,
    })
    tree = render_overview(payload, locale="en")
    ids = _ids(tree)
    assert "indexes-kpi-missing" in ids
    assert "indexes-kpi-frag" in ids
    assert "indexes-kpi-unused-writes" in ids
    assert "indexes-kpi-duplicates" in ids
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_index_overview_kpis.py tests/test_index_layout.py tests/test_index_triage.py -v`  
Expected: PASS

- [ ] **Step 6: Commit** (only if user requested)

```bash
git add modules/indexes/panels.py modules/indexes/callbacks.py core/i18n.py tests/test_index_layout.py
git commit -m "feat(indexes): Overview v1 KPI strip without consolidation"
```

---

### Task 3: Confidence ≥ 70 gate audit on Explorer copy UI

**Files:**
- Modify: `modules/indexes/layout.py` (`_rec_card`)
- Modify: `modules/indexes/intelligence.py` (overlap wording)
- Test: `tests/test_index_health_service.py` and/or new assertions in `tests/test_index_tags.py`

**Interfaces:**
- Consumes: recommendation dict may include `confidence_score`, `scripts`, `script_blocked_reason` (from table-health path); intelligence recs today often omit score — apply `_gated_scripts` when attaching scripts in intelligence OR gate in `_rec_card` if score present
- Produces: copy buttons only when `scripts` non-empty; always show blocked reason paragraph when `script_blocked_reason` set

- [ ] **Step 1: Failing test for gate helper still strips scripts below 70**

```python
# tests/test_index_health_service.py (append)
from modules.indexes.constants import INDEX_CONFIDENCE_SCRIPT_MIN
from modules.indexes.service import _gated_scripts

def test_gated_scripts_blocks_below_70():
    scripts, blocked = _gated_scripts(55, [{"label": "Copy", "tsql": "SELECT 1"}])
    assert scripts == []
    assert blocked and str(INDEX_CONFIDENCE_SCRIPT_MIN) in blocked

def test_gated_scripts_allows_at_70():
    scripts, blocked = _gated_scripts(70, [{"label": "Copy", "tsql": "SELECT 1"}])
    assert len(scripts) == 1
    assert blocked is None
```

- [ ] **Step 2: Run — may already PASS; if helper private, export via testing the public finding builders instead**

If importing `_gated_scripts` is undesirable, test via `assign_confidence` + a small public wrapper:

```python
def apply_script_gate(score: int, scripts: list[dict]) -> tuple[list[dict], str | None]:
    return _gated_scripts(score, scripts)
```

Prefer keeping `_gated_scripts` and importing in tests (already module-private by convention elsewhere).

- [ ] **Step 3: Update `_rec_card` in `layout.py`**

```python
def _rec_card(r: dict, i: int, *, open_first: bool = False, locale: str = DEFAULT_LOCALE) -> html.Details:
    loc = normalize_locale(locale)
    scripts = []
    for j, s in enumerate(r.get("scripts") or []):
        if not (s.get("tsql") or "").strip():
            continue
        scripts.append( ... existing button/pre ... )

    blocked = r.get("script_blocked_reason")
    body_children = [
        html.P(... why ...),
        html.Div(... evidence ...),
        html.P(... action ...),
    ]
    if blocked:
        body_children.append(html.P(blocked, className="indexes-script-blocked"))
    elif not scripts and r.get("confidence_score") is not None:
        score = int(r.get("confidence_score") or 0)
        if score < INDEX_CONFIDENCE_SCRIPT_MIN:
            body_children.append(
                html.P(
                    t("indexes.script.blocked", loc, score=score, min=INDEX_CONFIDENCE_SCRIPT_MIN),
                    className="indexes-script-blocked",
                )
            )
    body_children.append(html.Div(scripts))
    ...
```

Add i18n:

```python
"indexes.script.blocked": "Confidence {score} < {min} — T-SQL copy hidden until evidence is stronger.",
# fa: equivalent
```

- [ ] **Step 4: Relabel Consolidation in Explorer (no Super Index)**

In `layout.py`:

```python
"CONSOLIDATE": "Overlap signal",  # was "Consolidate / overlap"
```

In `intelligence.py` for `covered_by` / `prefix_overlap` recommendations:

- Keep `category: "CONSOLIDATE"` as internal key **or** rename to `OVERLAP` — prefer **keep key** to avoid breaking CSS, change label only  
- `scripts`: must remain `[]`  
- `suggested_action` / `why`: must **not** propose creating a Super Index or dropping multiple indexes as one package; phrase as “review overlapping leading keys — v1 does not auto-merge”

Example action string:

```text
Review overlapping leading columns; decide manually whether to drop a redundant NC. No consolidated Super Index script in v1.
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_index_health_service.py tests/test_index_layout.py tests/test_index_overview_kpis.py -v`  
Expected: PASS

- [ ] **Step 6: Commit** (only if user requested)

```bash
git add modules/indexes/layout.py modules/indexes/intelligence.py core/i18n.py tests/test_index_health_service.py
git commit -m "fix(indexes): confidence gate UX + no Super Index wording"
```

---

### Task 4: Spec checklist + smoke

**Files:**
- Modify: `docs/superpowers/specs/2026-08-16-index-module-v1-design.md` §9A checkboxes  
- Optional: one-line note in `docs/index-advisor/BUILD-PLAN.md` Phase 3 that Overview KPIs follow the v1 spec

- [ ] **Step 1: Mark §9A items done in the design spec** after code lands

```markdown
### A — UI / tag polish
- [x] Align Overview strip to the four KPIs in §5
- [x] Keep tag set §4; no emoji; FA via i18n
- [x] Confidence ≥ 70 gate audited on Recommendations copy actions
```

- [ ] **Step 2: Manual smoke (dev)**

1. Open Indexes → Overview after Refresh  
2. Confirm four cards: Missing impact, High frag, Dead unused writes, Duplicate indexes  
3. With frag not loaded, High frag shows `—` and pending subtext  
4. Open Explorer → Recommendations: below-70 findings show blocked text; no Super Index CREATE package  
5. Locale FA: KPI labels Persian  

- [ ] **Step 3: Full related pytest**

Run: `pytest tests/test_index_overview_kpis.py tests/test_index_layout.py tests/test_index_triage.py tests/test_index_health_service.py -q`  
Expected: all PASS

---

## Self-review (plan vs spec)

| Spec § | Covered by |
|--------|------------|
| §5 four KPIs, no Consolidation | Task 1–2 |
| §4 simple tags / no emoji | Task 2–3 (labels only; tag keys unchanged) |
| §4.2 / §8 confidence ≥ 70 | Task 3 |
| §9A sequence | Tasks 1–4 |
| §9B Advisor wire | Explicitly out of scope |
| Consolidation locked out | Task 2 (no KPI) + Task 3 (no Super Index scripts) |

**Placeholder scan:** none intentional beyond optional commit steps.  
**Type consistency:** `compute_overview_kpis` → `payload["kpis"]` → `render_overview` uses same four keys.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-08-16-indexes-module-a-kpis.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

Which approach?
