"""Mocked tests for table-scoped index snapshot provider methods."""
from unittest.mock import MagicMock, patch

from core.providers.sqlserver_provider import SqlServerProvider


@patch("core.providers.sqlserver_provider.connect")
def test_list_user_databases(mock_connect):
    conn = MagicMock()
    mock_connect.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.description = [("database_name",)]
    cur.fetchall.return_value = [("RasBankAccountingCloud",), ("OtherDb",)]

    out = SqlServerProvider().list_user_databases()
    assert "RasBankAccountingCloud" in out["databases"]
    assert out["errors"] == {}


@patch.object(SqlServerProvider, "_open_catalog_connection", return_value=(None, None))
@patch("core.providers.sqlserver_provider._connect_to_database")
def test_list_tables_search_capped(mock_conn_db, _mock_cat):
    # Catalog absent → live path
    conn = MagicMock()
    mock_conn_db.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.description = [("schema_name",), ("table_name",), ("full_name",)]
    cur.fetchall.return_value = [("dbo", "Facture", "dbo.Facture")]

    out = SqlServerProvider().list_tables("RasBankAccountingCloud", search="fac")
    assert out["tables"][0]["full_name"] == "dbo.Facture"
    sql = cur.execute.call_args[0][0]
    assert "TOP (30)" in sql or "TOP (30)" in sql.replace(" ", "")


def test_list_tables_prefers_catalog():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur

    def execute(sql, *args):
        if "FROM insight.IdxCat_Table" in str(sql):
            cur.description = [("schema_name",), ("table_name",), ("full_name",)]
            cur.fetchall.return_value = [("dbo", "Facture", "dbo.Facture")]

    cur.execute.side_effect = execute
    with patch.object(
        SqlServerProvider, "_open_catalog_connection", return_value=(conn, "SmartMonitorDB")
    ):
        out = SqlServerProvider().list_tables("RasBankAccountingCloud", search="fac")
    assert out["source"] == "catalog"
    assert out["tables"][0]["table_name"] == "Facture"


@patch("core.providers.sqlserver_provider._connect_to_database")
def test_get_table_index_snapshot_fast_path_no_frag(mock_conn_db):
    conn = MagicMock()
    mock_conn_db.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value = cur
    calls = []

    def execute(sql, *args):
        calls.append(sql)
        if "sqlserver_start_time" in sql:
            cur.fetchone.return_value = (None,)
            cur.description = None
            cur.fetchall.return_value = []
        elif "is_heap" in sql:
            cur.fetchone.return_value = (0,)
            cur.description = None
            cur.fetchall.return_value = []
        elif "missing_index" in sql:
            cur.description = [
                ("object_id",),
                ("equality_columns",),
                ("inequality_columns",),
                ("included_columns",),
                ("user_seeks",),
                ("avg_user_impact",),
                ("avg_total_user_cost",),
                ("impact_score",),
            ]
            cur.fetchall.return_value = []
            cur.fetchone.return_value = None
        elif "row_count" in sql or "clustered_index_name" in sql:
            cur.description = [
                ("schema_name",),
                ("table_name",),
                ("row_count",),
                ("size_mb",),
                ("clustered_index_name",),
                ("primary_key_name",),
                ("index_count",),
            ]
            cur.fetchall.return_value = [("dbo", "Facture", 100, 1.0, "PK", "PK", 1)]
            cur.fetchone.return_value = None
        else:
            assert "dm_db_index_physical_stats" not in sql
            cur.description = [
                ("index_id",),
                ("index_name",),
                ("type_desc",),
                ("is_unique",),
                ("is_primary_key",),
                ("is_unique_constraint",),
                ("is_disabled",),
                ("is_hypothetical",),
                ("has_filter",),
                ("filter_def",),
                ("reads",),
                ("writes",),
                ("size_mb",),
                ("page_count",),
                ("avg_fragmentation_in_percent",),
                ("key_cols",),
                ("include_cols",),
            ]
            cur.fetchall.return_value = [
                (
                    2, "IX_a", "NONCLUSTERED", False, False, False, False, False, False,
                    "", 0, 10, 1.0, 10, None, "a", "",
                )
            ]
            cur.fetchone.return_value = None

    cur.execute.side_effect = execute

    out = SqlServerProvider().get_table_index_snapshot(
        "RasBankAccountingCloud", "dbo", "Facture"
    )
    assert out["database_name"] == "RasBankAccountingCloud"
    assert out["index_rows"]
    assert out["index_rows"][0].get("avg_fragmentation_in_percent") is None
    assert not any("dm_db_index_physical_stats" in s for s in calls)
    assert out.get("table_meta")


@patch("core.providers.sqlserver_provider._connect_to_database")
def test_get_table_index_frag_soft_fails(mock_conn_db):
    conn = MagicMock()
    mock_conn_db.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value = cur

    def execute(sql, *args):
        if "dm_db_index_physical_stats" in sql:
            raise TimeoutError("Query timeout expired")

    cur.execute.side_effect = execute
    out = SqlServerProvider().get_table_index_frag("Db", "dbo", "Facture")
    assert out["frag_rows"] == []
    assert "frag" in out["errors"]


@patch("core.insight.store.get_monitor_connection")
@patch("core.insight.store.monitor_database_name", return_value="SmartMonitorDB")
def test_refresh_index_catalog_passes_parts(mock_mon_name, mock_mon_conn):
    conn = MagicMock()
    mock_mon_conn.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value = cur
    executed = []

    def execute(sql, *args):
        executed.append((sql, args))
        sql_s = str(sql)
        if "IdxCat_Table" in sql_s and "sys.tables" in sql_s:
            cur.fetchone.return_value = (1,)
        elif "sys.parameters" in sql_s:
            cur.fetchone.return_value = (3,)
        elif "COUNT(*)" in sql_s and "IdxCat_" in sql_s:
            cur.fetchone.return_value = (5,)
        elif "IdxCat_RefreshLog" in sql_s and "TOP (1)" in sql_s and "refresh_parts" not in sql_s:
            cur.description = [
                ("refresh_id",),
                ("database_name",),
                ("started_at",),
                ("finished_at",),
                ("status",),
                ("message",),
                ("tables_upserted",),
                ("indexes_upserted",),
            ]
            cur.fetchall.return_value = [
                (1, None, None, None, "ok", "Completed", 1, 2)
            ]
        elif "refresh_parts" in sql_s:
            cur.fetchone.return_value = ("tables=0;defs=0;stats=1",)
        elif "DISTINCT database_name" in sql_s:
            cur.fetchone.return_value = (1,)

    cur.execute.side_effect = execute

    out = SqlServerProvider().refresh_index_catalog(
        None, tables=False, index_defs=False, index_stats=True
    )
    assert out["ok"] is True
    assert out["parts"]["index_stats"] is True
    assert out["parts"]["tables"] is False
    exec_sql = " ".join(str(s[0]) for s in executed)
    assert "@RefreshIndexStats" in exec_sql or "RefreshIndexStats" in exec_sql


@patch("core.insight.store.get_monitor_connection")
@patch("core.insight.store.monitor_database_name", return_value="SmartMonitorDB")
def test_refresh_index_catalog_execute_denied_message(mock_mon_name, mock_mon_conn):
    conn = MagicMock()
    mock_mon_conn.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value = cur

    def execute(sql, *args):
        sql_s = str(sql)
        if "IdxCat_Table" in sql_s and "sys.tables" in sql_s:
            cur.fetchone.return_value = (1,)
        elif "sys.parameters" in sql_s:
            cur.fetchone.return_value = (3,)
        elif "EXEC" in sql_s.upper() or "USP_Insight" in sql_s:
            raise Exception(
                "[42000] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]"
                "The EXECUTE permission was denied on the object "
                "'USP_Insight_IndexCatalog_Refresh', database 'SmartMonitorDB', "
                "schema 'insight'. (229)"
            )

    cur.execute.side_effect = execute
    out = SqlServerProvider().refresh_index_catalog(None, index_stats=True, tables=False, index_defs=False)
    assert out["ok"] is False
    assert "GRANT EXECUTE" in out["error"]
    assert "SmartMonitorDB" in out["error"] or "insight.USP" in out["error"]
