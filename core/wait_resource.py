"""Parse SQL Server wait_resource strings and resolve to schema.table (batched per db_id)."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.logging_setup import get_logger

logger = get_logger(__name__)

_OBJECT_RE = re.compile(r"^OBJECT:\s*(\d+):(\d+):(\d+)", re.IGNORECASE)
_KEY_RE = re.compile(r"^KEY:\s*(\d+):(\d+)", re.IGNORECASE)
_PAGE_RE = re.compile(r"^PAGE:\s*(\d+):(\d+):(\d+)", re.IGNORECASE)
_RID_RE = re.compile(r"^RID:\s*(\d+):(\d+):(\d+):(\d+)", re.IGNORECASE)
_RAW_RESOURCE_RE = re.compile(r"^(OBJECT|KEY|PAGE|RID):", re.IGNORECASE)
_DISPLAY_SUFFIX_RE = re.compile(r"\s+\([^)]*\)\s*$")

DbExecutor = Callable[[int, List[Dict[str, Any]]], Dict[str, Optional[str]]]


def format_wait_resource_display(raw: str | None, wait_object: str | None) -> str:
    """Return a UI-only object label or compact, humanized raw resource."""
    resolved = (wait_object or "").strip()
    if resolved:
        return resolved

    text = " ".join((raw or "").strip().split())
    if not text:
        return "—"

    text = _DISPLAY_SUFFIX_RE.sub("", text)
    parsed = parse_wait_resource(text)
    if parsed:
        kind = parsed["kind"].upper()
        if kind == "OBJECT":
            return f"{parsed['db_id']}:{parsed['object_id']}"
        if kind == "KEY":
            return f"KEY {parsed['db_id']}:{parsed['hobt_id']}"
        if kind == "PAGE":
            return f"PAGE {parsed['db_id']}:{parsed['file_id']}:{parsed['page_id']}"
        return (
            f"RID {parsed['db_id']}:{parsed['file_id']}:"
            f"{parsed['page_id']}:{parsed['slot_id']}"
        )

    return re.sub(r"^([A-Za-z_]+):\s*", r"\1 ", text)


def parse_wait_resource(wait_resource: str | None) -> dict | None:
    """Best-effort parse of sys.dm_exec_requests.wait_resource. Unknown shapes → None."""
    if not wait_resource or not isinstance(wait_resource, str):
        return None
    text = wait_resource.strip()
    if not text:
        return None

    m = _OBJECT_RE.match(text)
    if m:
        return {
            "kind": "object",
            "db_id": int(m.group(1)),
            "object_id": int(m.group(2)),
        }

    m = _KEY_RE.match(text)
    if m:
        return {
            "kind": "key",
            "db_id": int(m.group(1)),
            "hobt_id": int(m.group(2)),
        }

    m = _PAGE_RE.match(text)
    if m:
        return {
            "kind": "page",
            "db_id": int(m.group(1)),
            "file_id": int(m.group(2)),
            "page_id": int(m.group(3)),
        }

    m = _RID_RE.match(text)
    if m:
        return {
            "kind": "rid",
            "db_id": int(m.group(1)),
            "file_id": int(m.group(2)),
            "page_id": int(m.group(3)),
            "slot_id": int(m.group(4)),
        }

    return None


def _validate_schema_table(value: Any, *, raw_resource: str | None = None) -> str | None:
    """Accept only schema.table; never pass through raw wait_resource."""
    if value is None or not isinstance(value, str):
        return None
    val = value.strip()
    if not val:
        return None
    if raw_resource and val == raw_resource.strip():
        return None
    if _RAW_RESOURCE_RE.match(val):
        return None
    if val.count(".") != 1:
        return None
    schema, name = val.split(".", 1)
    if not schema or not name:
        return None
    return val


def _default_db_executor(db_id: int, specs: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """One batched SQL round-trip per db_id for OBJECT and KEY resources.

    Requires VIEW ANY DEFINITION (or CONNECT + VIEW DEFINITION on each DB)
    for OBJECT_NAME / schema resolution. Without it, OBJECT_NAME returns NULL
    and we leave wait_object as None (UI falls back to humanized raw).
    """
    from core.connection import connect

    results: Dict[str, Optional[str]] = {s["resource"]: None for s in specs}
    objects = [s for s in specs if s.get("kind") == "object"]
    keys = [s for s in specs if s.get("kind") == "key"]

    if not objects and not keys:
        return results

    conn = connect()
    try:
        cur = conn.cursor()

        if objects:
            try:
                values = ", ".join(f"({int(s['object_id'])})" for s in objects)
                sql = f"""
                    SELECT v.object_id,
                           OBJECT_SCHEMA_NAME(v.object_id, ?) + N'.' + OBJECT_NAME(v.object_id, ?) AS full_name
                    FROM (VALUES {values}) AS v(object_id)
                """
                cur.execute(sql, (db_id, db_id))
                oid_map: Dict[int, str] = {}
                null_hits = 0
                for row in cur.fetchall():
                    oid, full_name = row[0], row[1]
                    validated = _validate_schema_table(full_name)
                    if validated:
                        oid_map[int(oid)] = validated
                    else:
                        null_hits += 1
                for s in objects:
                    resolved = oid_map.get(int(s["object_id"]))
                    if resolved:
                        results[s["resource"]] = resolved
                if null_hits and not oid_map:
                    logger.warning(
                        "OBJECT_NAME returned NULL for all %s object(s) in db_id=%s — "
                        "grant VIEW ANY DEFINITION (or CONNECT+VIEW DEFINITION on that DB) "
                        "to the monitor login",
                        null_hits,
                        db_id,
                    )
            except Exception:
                logger.exception("OBJECT resolve failed for db_id=%s", db_id)

        if keys:
            try:
                db_name_row = cur.execute("SELECT DB_NAME(?)", (db_id,)).fetchone()
                db_name = db_name_row[0] if db_name_row else None
                if not db_name:
                    logger.warning("DB_NAME(%s) returned NULL — cannot resolve KEY locks", db_id)
                else:
                    hobt_values = ", ".join(f"({int(s['hobt_id'])})" for s in keys)
                    sql = f"""
                        SELECT p.hobt_id,
                               OBJECT_SCHEMA_NAME(p.object_id, ?) + N'.' + OBJECT_NAME(p.object_id, ?) AS full_name
                        FROM { _quote_db(db_name) }.sys.partitions AS p
                        INNER JOIN (VALUES {hobt_values}) AS v(hobt_id) ON p.hobt_id = v.hobt_id
                    """
                    cur.execute(sql, (db_id, db_id))
                    hobt_map: Dict[int, str] = {}
                    for row in cur.fetchall():
                        hobt_id, full_name = row[0], row[1]
                        validated = _validate_schema_table(full_name)
                        if validated:
                            hobt_map[int(hobt_id)] = validated
                    for s in keys:
                        resolved = hobt_map.get(int(s["hobt_id"]))
                        if resolved:
                            results[s["resource"]] = resolved
            except Exception as ex:
                # 916 = cannot access database under current security context
                msg = str(ex)
                if "916" in msg or "not able to access the database" in msg.lower():
                    logger.warning(
                        "KEY resolve skipped for db_id=%s — login cannot CONNECT to that database (%s)",
                        db_id,
                        msg.split("]")[-1].strip()[:160],
                    )
                else:
                    logger.exception("KEY resolve failed for db_id=%s", db_id)
    finally:
        conn.close()

    return results


def _quote_db(name: str) -> str:
    escaped = name.replace("]", "]]")
    return f"[{escaped}]"


def resolve_wait_object(
    wait_resource: str,
    wait_type: str | None = None,
    *,
    executor: DbExecutor | None = None,
) -> str | None:
    """Resolve a single wait_resource to schema.table or None (never raw resource)."""
    parsed = parse_wait_resource(wait_resource)
    if not parsed:
        return None

    spec = {**parsed, "resource": wait_resource.strip(), "wait_type": wait_type}
    exec_fn = executor or _default_db_executor

    try:
        result_map = exec_fn(spec["db_id"], [spec])
        value = result_map.get(spec["resource"])
        return _validate_schema_table(value, raw_resource=wait_resource)
    except Exception:
        logger.exception("resolve_wait_object failed for %r", wait_resource)
        return None


def resolve_wait_objects_batch(
    items: List[Tuple[str, str | None]],
    *,
    executor: DbExecutor | None = None,
) -> Dict[str, str | None]:
    """Batch resolve unique wait_resource keys, one executor call per distinct db_id."""
    exec_fn = executor or _default_db_executor
    unique: Dict[str, str | None] = {}
    for resource, wait_type in items:
        key = (resource or "").strip()
        if key and key not in unique:
            unique[key] = wait_type

    results: Dict[str, str | None] = {resource: None for resource in unique}
    by_db: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    for resource, wait_type in unique.items():
        parsed = parse_wait_resource(resource)
        if not parsed:
            continue
        by_db[parsed["db_id"]].append(
            {**parsed, "resource": resource, "wait_type": wait_type}
        )

    for db_id, specs in by_db.items():
        try:
            db_results = exec_fn(db_id, specs)
            for spec in specs:
                resource = spec["resource"]
                value = db_results.get(resource)
                results[resource] = _validate_schema_table(value, raw_resource=resource)
        except Exception:
            logger.exception("resolve_wait_objects_batch failed for db_id=%s", db_id)

    return results
