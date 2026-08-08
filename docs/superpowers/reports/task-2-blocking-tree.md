# Task 2 Report: Blocking tree builder

**Date:** 2026-08-01  
**Status:** DONE  
**Commit:** `b58da66` — feat: build nested blocking trees from DMV edges

---

## Deliverables

| File | Purpose |
|------|---------|
| `core/blocking_tree.py` | `build_blocking_trees`, `summarize_blocking_trees` |
| `tests/test_blocking_tree.py` | 8 unit tests (self-edge, cycle, nested, blast dedupe) |

---

## API Summary

### `build_blocking_trees(rows: list[dict]) -> list[dict]`

- Dedupes edges by `(blocked_session_id, blocker_session_id, wait_resource, chain_display)`.
- Drops self-edges (`blocker_session_id == blocked_session_id`).
- Roots = blockers not blocked by anyone; cycle-only blockers become independent roots.
- DFS with path-set cycle guard; no infinite recursion.
- Each root returns `head_session_id`, `head`, `children`, `blast_radius`, `chain_age_sec`, `blocked_spids`.

### `summarize_blocking_trees(trees) -> dict`

- `head_blockers`: count of roots.
- `blast_radius`: **global union** of all `blocked_spids` (deduped).
- `chain_age_sec`: max per-root chain age.

---

## Test Results

```
pytest tests/test_blocking_tree.py -v
8 passed in 0.03s
```

| Test | Coverage |
|------|----------|
| `test_filters_self_block` | Self-edge dropped → empty |
| `test_simple_tree` | Single root, blast=2, chain_age=max elapsed |
| `test_nested_indirect` | A→B→C nested children |
| `test_cycle_becomes_safe_roots` | 10↔11 cycle → finite roots, no hang |
| `test_blast_dedupe_across_roots` | SPID 99 under two roots → global blast=1 |
| `test_summarize_chain_age_max` | Max chain age across roots |
| `test_dedupes_identical_edges` | Duplicate edge rows ignored |
| `test_per_root_blast_excludes_head` | Head SPID not in blocked_spids |

---

## Self-Review (critical behaviors)

| Requirement | Met? | Notes |
|-------------|------|-------|
| Filter self-edges | ✅ | Skipped in `_dedupe_edges` |
| Cycle guard — finite trees | ✅ | Path-set in DFS; cycle roots via `blockers - reachable` |
| Nested indirect blocking | ✅ | Recursive `_build_subtree` on children_map |
| Global blast = union dedupe | ✅ | `summarize_blocking_trees` unions all `blocked_spids` |
| Per-root blast = distinct descendants | ✅ | `_subtree_metrics` excludes head SPID |
| chain_age = max elapsed in subtree | ✅ | Max `request_elapsed_sec` over head + descendants |

---

## Concerns / Follow-ups

1. **Intermediate blockers as roots** — Fixed: only `blockers - blocked_set` plus unreachable cycle blockers become roots; session 2 in 1→2→3 is not promoted.
2. **Head node elapsed** — Head `request_elapsed_sec` comes from a sample blocker edge; DMV rows primarily carry blocked-session elapsed. Chain age uses max over subtree values (matches plan tests).
3. **No integration test with live `get_blocking` rows** — Pure unit tests with synthetic edge dicts only.

---

## Out of Scope (unchanged)

- `modules/activity/service.py` / `layout.py` / CSS — Task 3+
- `core/wait_resource.py` — Task 1 (unchanged)
