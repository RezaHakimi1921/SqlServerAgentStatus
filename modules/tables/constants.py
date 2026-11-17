"""Tables & Growth constants."""

TABLES_TOP_N = 50
TABLES_GROWERS_N = 10
TABLES_DB_ROLLUP_CAP = 100
# Relative Δ colors vs mean of positive deltas (all DBs, same window)
TABLES_DELTA_HOT_MULT = 2.0
TABLES_DELTA_WARM_MULT = 1.25
TABLES_DELTA_MEAN_FLOOR_MB = 1.0
TABLES_DELTA_MEAN_FLOOR_ROWS = 1_000.0
TABLES_LIVE_DB_CAP = 15
TABLES_LIVE_DB_TIMEOUT_SEC = 8
TABLES_LIVE_VERIFY_TIMEOUT_SEC = 4
TABLES_LIVE_VERIFY_WORKERS = 8
TABLES_LIVE_VERIFY_CACHE_SEC = 180
TABLES_QUERY_TIMEOUT_SEC = 20
TABLES_PAGE_SIZE = 25
TABLES_SNAPSHOT_CACHE_SEC = 60
TABLES_CAPTURE_TIMEOUT_SEC = 120

# insight schema objects (sibling to IdxCat — not a unified catalog)
TABLES_HISTORY_SCHEMA = "insight"
TABLES_HISTORY_TABLE = "ObjSize_History"
TABLES_HISTORY_CAPTURE_PROC = "USP_Insight_ObjSize_Capture"
# Keep history long-lived for now (SP also uses a high @RetentionDays).
# Raise further or lower later when a real purge policy is decided.
TABLES_HISTORY_RETENTION_DAYS = 3650

TABLES_DELTA_WINDOWS_DAYS = (1, 7, 30)

# All Tables — Type filter (picker values → labels)
TABLES_TYPE_FILTERS = (
    ("all", "All types"),
    ("clustered", "Clustered"),
    ("heap", "Heap"),
    ("deleted", "Deleted"),
)
