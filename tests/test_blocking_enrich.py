"""Unit tests for blocking fetch enrichment (trees + wait_object)."""
from modules.activity.service import enrich_blocking_result


def _edge(blocker, blocked, *, wait_resource="OBJECT: 5:10:0", **kw):
    return {
        "blocker_session_id": blocker,
        "blocked_session_id": blocked,
        "is_head_blocker": 1,
        "request_elapsed_sec": kw.get("elapsed", 60),
        "wait_time": kw.get("wait_ms", 5000),
        "wait_seconds": kw.get("wait_ms", 5000) / 1000,
        "wait_resource": wait_resource,
        "wait_type": kw.get("wait_type", "LCK_M_S"),
        "blocker_login": "blocker",
        "blocked_login": "victim",
        "blocker_sql": "UPDATE t SET x=1",
        "blocked_sql": "SELECT 1",
        "blocker_command": "UPDATE",
        "blocked_command": "SELECT",
        "chain_display": f"{blocker} -> {blocked}",
        **kw,
    }


def test_enrich_builds_trees_and_merges_summary():
    rows = [_edge(874, 1156, elapsed=160), _edge(874, 1101, elapsed=40)]
    result = {
        "status": "ok",
        "summary": {
            "head_blockers": 1,
            "blocked_sessions": 2,
            "longest_wait_ms": 5000,
        },
        "rows": rows,
    }

    def fake_executor(db_id, specs):
        return {s["resource"]: f"dbo.T{s['object_id']}" for s in specs}

    out = enrich_blocking_result(result, executor=fake_executor)

    assert len(out["trees"]) == 1
    assert out["trees"][0]["head_session_id"] == 874
    assert out["summary"]["head_blockers"] == 1
    assert out["summary"]["blast_radius"] == 2
    assert out["summary"]["chain_age_sec"] == 160
    assert out["summary"]["blocked_sessions"] == 2
    assert out["summary"]["longest_wait_ms"] == 5000


def test_enrich_attaches_wait_object_on_child_nodes():
    resource = "OBJECT: 5:10:0"
    rows = [_edge(1, 2, wait_resource=resource)]

    def fake_executor(db_id, specs):
        return {s["resource"]: "dbo.BlockedTable" for s in specs}

    out = enrich_blocking_result(
        {"status": "ok", "summary": {}, "rows": rows},
        executor=fake_executor,
    )

    child = out["trees"][0]["children"][0]
    assert child["wait_resource_raw"] == resource
    assert child["wait_object"] == "dbo.BlockedTable"


def test_enrich_swallows_total_resolve_failure():
    rows = [_edge(1, 2, wait_resource="OBJECT: 5:99:0")]

    def boom(*a, **k):
        raise RuntimeError("batch down")

    out = enrich_blocking_result(
        {"status": "ok", "summary": {}, "rows": rows},
        executor=boom,
    )

    child = out["trees"][0]["children"][0]
    assert child["wait_object"] is None
    assert out["trees"][0]["blast_radius"] == 1


def test_enrich_empty_rows():
    out = enrich_blocking_result({"status": "empty", "summary": {"head_blockers": 0}, "rows": []})
    assert out["trees"] == []
    assert out["summary"]["blast_radius"] == 0
    assert out["summary"]["chain_age_sec"] == 0
    assert out["summary"]["head_blockers"] == 0
