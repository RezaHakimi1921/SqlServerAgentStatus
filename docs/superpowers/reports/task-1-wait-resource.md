# Task 1 Report: Wait-resource parse + resolve API

**Date:** 2026-08-01  
**Status:** DONE  
**Commit:** `77ec67e` — feat: add batched wait_resource resolve helper

---

## Deliverables

| File | Purpose |
|------|---------|
| `core/wait_resource.py` | `parse_wait_resource`, `resolve_wait_object`, `resolve_wait_objects_batch` |
| `tests/test_wait_resource.py` | 12 unit tests (parser, resolve safety, batch grouping) |

---

## API Summary

### `parse_wait_resource(wait_resource) -> dict | None`

Parses SQL Server `wait_resource` strings for:

- **OBJECT** — `db_id`, `object_id`
- **KEY** — `db_id`, `hobt_id`
- **PAGE** — `db_id`, `file_id`, `page_id`
- **RID** — `db_id`, `file_id`, `page_id`, `slot_id`

Unknown / empty / invalid input → `None`.

### `resolve_wait_object(wait_resource, wait_type=None, *, executor=None) -> str | None`

- Returns **only** `schema.table` or `None`.
- Default executor uses `core.connection.connect` with batched SQL per resource kind.
- Full path wrapped in `try/except`; exceptions logged and return `None`.
- `_validate_schema_table` rejects raw resource strings, missing dot, or multi-dot values.

### `resolve_wait_objects_batch(items, *, executor) -> dict[str, str | None]`

- Dedupes unique `wait_resource` keys from `(resource, wait_type)` tuples.
- Groups parsed specs **by `db_id`**; one `executor(db_id, specs)` call per distinct database.
- Per-db failures are isolated (other db groups still resolve).
- Map keyed by original `wait_resource` string.

---

## Test Results

```
pytest tests/test_wait_resource.py -v
12 passed in 0.30s
```

| Test | Coverage |
|------|----------|
| `test_parse_object` | OBJECT prefix parsing |
| `test_parse_key_hobt` | KEY + hobt_id + hash suffix |
| `test_parse_page` / `test_parse_rid` | PAGE/RID best-effort parse |
| `test_parse_unknown_returns_none` | Unknown / empty / None |
| `test_resolve_returns_none_on_unknown` | Unparseable → None |
| `test_resolve_swallows_executor_errors` | Exception → None |
| `test_resolve_never_returns_raw_resource` | Echo-raw executor → None |
| `test_batch_groups_by_db_id` | 2 db groups, dup dedupe within db 5 |
| `test_batch_multi_db_three_groups` | 3 db_ids; db 1 batches OBJECT+KEY together |
| `test_batch_duplicate_keys_same_value` | Duplicate keys same map entry |
| `test_batch_executor_error_returns_none_for_db` | Failed db → None; other db OK |

---

## Self-Review (spec §5)

| Requirement | Met? | Notes |
|-------------|------|-------|
| Returns only `schema.table` or `None | ✅ | `_validate_schema_table` gate on all outputs |
| Never return raw `wait_resource` | ✅ | Explicit rejection of resource-shaped strings and raw echo |
| Exceptions → log + None | ✅ | Both single and batch paths |
| Batch group by `db_id` | ✅ | `defaultdict` grouping; one executor call per db |
| Not global cross-db query | ✅ | Separate SQL per db_id in default executor |
| Not per-node round-trips | ✅ | VALUES-clause batch for OBJECT and KEY within each db |
| No Dash / layout deps | ✅ | Only `core.connection`, `core.logging_setup` |
| V1.5-ready standalone helper | ✅ | Injectable `executor` for tests and future collectors |

---

## Default SQL Strategy

**OBJECT (per db_id):**

```sql
SELECT v.object_id,
       OBJECT_SCHEMA_NAME(v.object_id, @dbid) + N'.' + OBJECT_NAME(v.object_id, @dbid)
FROM (VALUES (...)) AS v(object_id)
```

**KEY (per db_id):**

```sql
SELECT p.hobt_id,
       OBJECT_SCHEMA_NAME(p.object_id, @dbid) + N'.' + OBJECT_NAME(p.object_id, @dbid)
FROM [DbName].sys.partitions p
INNER JOIN (VALUES (...)) AS v(hobt_id) ON p.hobt_id = v.hobt_id
```

**PAGE / RID:** Parsed but resolve returns `None` (best-effort; allowed by spec).

---

## Concerns / Follow-ups

1. **PAGE/RID resolve** — Not implemented in default executor (returns `None`). Spec allows best-effort deferral; Task 5/UI handles humanized raw fallback.
2. **No integration test against live SQL Server** — All resolve tests use injectable fake executors; default SQL path is untested without a configured instance.
3. **Bracketed identifiers** — Validation accepts simple `schema.table`; SQL Server names with brackets or special chars may need relaxed validation later.

---

## Out of Scope (unchanged)

- `core/blocking_tree.py` — Task 2
- `modules/activity/service.py` / layout — Task 3+
- Metric Store / collector changes
