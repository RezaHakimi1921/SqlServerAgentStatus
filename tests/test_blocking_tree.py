"""Unit tests for blocking tree builder."""
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
    spids = set(trees[0]["blocked_spids"])
    assert spids == {1156, 1101}


def test_nested_indirect():
    rows = [
        _edge(1, 2, head=1, elapsed=50),
        _edge(2, 3, head=0, elapsed=30),
    ]
    trees = build_blocking_trees(rows)
    assert len(trees) == 1
    assert trees[0]["head_session_id"] == 1
    assert trees[0]["blast_radius"] == 2
    kids = trees[0]["children"]
    assert kids[0]["session_id"] == 2
    assert kids[0]["children"][0]["session_id"] == 3


def test_cycle_becomes_safe_roots():
    rows = [_edge(10, 11, head=0), _edge(11, 10, head=0)]
    trees = build_blocking_trees(rows)
    assert len(trees) >= 1
    assert all(t["blast_radius"] >= 0 for t in trees)


def test_blast_dedupe_across_roots():
    rows = [_edge(1, 99, head=1), _edge(2, 99, head=1)]
    trees = build_blocking_trees(rows)
    assert len(trees) == 2
    assert all(t["blast_radius"] == 1 for t in trees)
    summary = summarize_blocking_trees(trees)
    assert summary["blast_radius"] == 1
    assert summary["head_blockers"] == 2


def test_summarize_chain_age_max():
    rows = [
        _edge(1, 10, head=1, elapsed=100),
        _edge(2, 20, head=1, elapsed=200),
    ]
    trees = build_blocking_trees(rows)
    summary = summarize_blocking_trees(trees)
    assert summary["chain_age_sec"] == 200


def test_dedupes_identical_edges():
    row = _edge(1, 2, head=1)
    trees = build_blocking_trees([row, row])
    assert len(trees) == 1
    assert trees[0]["blast_radius"] == 1


def test_per_root_blast_excludes_head():
    rows = [_edge(1, 2, head=1), _edge(1, 3, head=1)]
    trees = build_blocking_trees(rows)
    assert trees[0]["blast_radius"] == 2
    assert 1 not in set(trees[0]["blocked_spids"])
