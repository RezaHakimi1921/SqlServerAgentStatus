"""Unit tests for wait_resource parse + batch resolve helpers."""
from core.wait_resource import (
    parse_wait_resource,
    resolve_wait_object,
    resolve_wait_objects_batch,
)


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


def test_parse_page():
    p = parse_wait_resource("PAGE: 3:1:4096")
    assert p["kind"] == "page"
    assert p["db_id"] == 3
    assert p["file_id"] == 1
    assert p["page_id"] == 4096


def test_parse_rid():
    p = parse_wait_resource("RID: 2:1:100:4")
    assert p["kind"] == "rid"
    assert p["db_id"] == 2
    assert p["file_id"] == 1
    assert p["page_id"] == 100
    assert p["slot_id"] == 4


def test_parse_unknown_returns_none():
    assert parse_wait_resource("UNKNOWN: foo") is None
    assert parse_wait_resource("") is None
    assert parse_wait_resource(None) is None


def test_resolve_returns_none_on_unknown():
    assert resolve_wait_object("UNKNOWN: foo", "LCK_M_S") is None


def test_resolve_swallows_executor_errors():
    def boom(*a, **k):
        raise RuntimeError("db down")

    assert resolve_wait_object("OBJECT: 5:1:0", "LCK_M_X", executor=boom) is None


def test_resolve_never_returns_raw_resource():
    def echo_raw(db_id, specs):
        return {s["resource"]: s["resource"] for s in specs}

    raw = "OBJECT: 5:99:0"
    assert resolve_wait_object(raw, "LCK_M_X", executor=echo_raw) is None


def test_batch_groups_by_db_id():
    calls = []

    def fake_executor(db_id, specs):
        calls.append((db_id, tuple(sorted(specs, key=lambda s: s["resource"]))))
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
    assert m["OBJECT: 5:11:0"] == "dbo.T11"

    db5_call = next(c for c in calls if c[0] == 5)
    assert len(db5_call[1]) == 2  # deduped: 10 and 11 only


def test_batch_multi_db_three_groups():
    calls = []

    def fake_executor(db_id, specs):
        calls.append(db_id)
        out = {}
        for s in specs:
            oid = s.get("object_id") or s.get("hobt_id")
            out[s["resource"]] = f"dbo.T{oid}"
        return out

    items = [
        ("OBJECT: 1:100:0", "LCK_M_S"),
        ("OBJECT: 2:200:0", "LCK_M_S"),
        ("OBJECT: 3:300:0", "LCK_M_S"),
        ("KEY: 1:72057594039926784 (abc)", "LCK_M_U"),
    ]
    m = resolve_wait_objects_batch(items, executor=fake_executor)
    assert sorted(calls) == [1, 2, 3]
    assert m["OBJECT: 1:100:0"] == "dbo.T100"
    assert m["OBJECT: 2:200:0"] == "dbo.T200"
    assert m["OBJECT: 3:300:0"] == "dbo.T300"
    assert m["KEY: 1:72057594039926784 (abc)"] == "dbo.T72057594039926784"


def test_batch_duplicate_keys_same_value():
    def fake_executor(db_id, specs):
        return {s["resource"]: "dbo.DupTable" for s in specs}

    resource = "OBJECT: 5:42:0"
    items = [(resource, "LCK_M_X"), (resource, "LCK_M_S")]
    m = resolve_wait_objects_batch(items, executor=fake_executor)
    assert m[resource] == "dbo.DupTable"


def test_batch_executor_error_returns_none_for_db():
    call_count = {"n": 0}

    def flaky(db_id, specs):
        call_count["n"] += 1
        if db_id == 5:
            raise RuntimeError("db 5 down")
        return {s["resource"]: "dbo.Ok" for s in specs}

    items = [
        ("OBJECT: 5:1:0", "LCK_M_X"),
        ("OBJECT: 8:2:0", "LCK_M_X"),
    ]
    m = resolve_wait_objects_batch(items, executor=flaky)
    assert m["OBJECT: 5:1:0"] is None
    assert m["OBJECT: 8:2:0"] == "dbo.Ok"
    assert call_count["n"] == 2
