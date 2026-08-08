"""Unit tests for Index Intelligence Triage findings."""
from modules.indexes.service import build_overview_payload
from modules.indexes.triage import (
    build_triage_findings,
    filter_triage_findings,
    triage_filter_counts,
)


def _sample_payload():
    return build_overview_payload(
        {
            "sqlserver_start_time": "2026-01-01T00:00:00",
            "databases_available": 3,
            "databases_scanned_list": ["SalesDB"],
            "scan_mode": "quick",
            "source": "catalog",
            "totals": {
                "databases_scanned": 1,
                "indexes": 100,
                "need_review": 5,
                "unused": 1,
                "write_heavy": 1,
                "heaps": 1,
                "missing_suggestions": 2,
            },
            "unused": [
                {
                    "database_name": "SalesDB",
                    "schema_name": "dbo",
                    "table_name": "Orders",
                    "index_name": "IX_Dead",
                    "writes": 50000,
                    "size_mb": 12,
                }
            ],
            "write_heavy": [
                {
                    "database_name": "SalesDB",
                    "schema_name": "dbo",
                    "table_name": "Facture",
                    "index_name": "IX_Date",
                    "writes": 45000000,
                    "reads": 100,
                    "size_mb": 12,
                }
            ],
            "heaps": [
                {
                    "database_name": "SalesDB",
                    "schema_name": "dbo",
                    "table_name": "Staging",
                    "row_count": 1_000_000,
                }
            ],
            "missing_by_table": [
                {
                    "database_name": "SalesDB",
                    "schema_name": "dbo",
                    "table_name": "Customer",
                    "suggestion_count": 3,
                    "equality_columns": "[CustomerId]",
                    "avg_user_impact": 80,
                    "user_seeks": 200,
                }
            ],
        }
    )


def test_build_triage_findings_shape_and_sort():
    payload = _sample_payload()
    findings = payload["findings"]
    assert len(findings) == 4
    assert findings == build_triage_findings(payload)

    # Highest severity first (critical write-heavy / unused with big writes)
    severities = [f["severity"] for f in findings]
    assert severities[0] in ("critical", "warning")
    assert all(f["impact_score"] >= 0 for f in findings)
    assert all("id" in f and "why" in f and "action" in f for f in findings)

    # Scores descending within same severity band is best-effort; overall list sorted
    ranks = {"critical": 0, "warning": 1, "watch": 2, "ok": 3}
    rank_seq = [ranks[f["severity"]] for f in findings]
    assert rank_seq == sorted(rank_seq)


def test_triage_scripts_present():
    findings = _sample_payload()["findings"]
    by_cat = {f["category"]: f for f in findings}
    assert by_cat["unused"]["scripts"]
    assert "DISABLE" in by_cat["unused"]["scripts"][0]["tsql"]
    assert by_cat["write_heavy"]["scripts"]
    assert by_cat["missing"]["scripts"]
    assert "CREATE" in by_cat["missing"]["scripts"][0]["tsql"]
    assert by_cat["heap"]["scripts"] == []


def test_filter_and_counts():
    findings = _sample_payload()["findings"]
    counts = triage_filter_counts(findings)
    assert counts["all"] == 4
    assert counts["missing"] == 1
    assert counts["heap"] == 1
    assert len(filter_triage_findings(findings, "missing")) == 1
    assert len(filter_triage_findings(findings, "all")) == 4
    assert filter_triage_findings([], "all") == []
    assert build_triage_findings(None) == []
    assert build_triage_findings({}) == []


def test_severity_mapping_watch_for_missing():
    findings = _sample_payload()["findings"]
    missing = next(f for f in findings if f["category"] == "missing")
    assert missing["severity"] == "watch"
