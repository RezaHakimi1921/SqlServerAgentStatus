INDEX_USAGE_MIN_UPTIME_DAYS = 7
INDEX_WRITE_HEAVY_MIN_WRITES = 1000
INDEX_WRITE_HEAVY_MIN_DIFF = 10000
INDEX_WRITE_HEAVY_MIN_RATIO = 10
INDEX_CAP_UNUSED = 50
INDEX_CAP_WRITE_HEAVY = 50
INDEX_CAP_MISSING = 25

INDEX_HIGH_FRAG_PCT = 30.0
INDEX_HIGH_FRAG_MIN_PAGES = 1000
INDEX_FRAG_QUERY_TIMEOUT_SEC = 5
INDEX_SNAPSHOT_QUERY_TIMEOUT_SEC = 15
# Show copyable T-SQL only when confidence score is at least this
INDEX_CONFIDENCE_SCRIPT_MIN = 70

INDEX_PREFERRED_DATABASE = "RasBankAccountingCloud"
# Explorer DB picker sentinel — all catalog databases
INDEX_DB_ALL = "__all__"

# Table search typeahead
INDEX_TABLE_SEARCH_MIN_CHARS = 2
INDEX_TABLE_SEARCH_CAP = 30
# Unused without a search string (Explorer never dumps a big list)
INDEX_TABLE_LIST_CAP = 0
# Prefetch all tables for selected DB (catalog-backed typeahead)
INDEX_TABLE_CACHE_CAP = 20000
INDEX_EXPLORER_PAGE_SIZE = 25

# Overview environment scan caps (finding-oriented, not full inventory)
INDEX_OVERVIEW_QUICK_MAX_DATABASES = 2  # preferred DB first — fast path
INDEX_OVERVIEW_MAX_DATABASES = 15       # deep scan
INDEX_OVERVIEW_FINDING_ROWS = 15
INDEX_OVERVIEW_DB_TIMEOUT_SEC = 8

# Advisor Overview: max age of latest successful CollectionRun (spec §7.2)
INDEX_ADVISOR_FRESHNESS_MINUTES = 90

INDEX_INVENTORY_MAX_ROWS = 5000
INDEX_INVENTORY_MAX_MS = 3000

# Optional daily catalog (soft-fail if missing) — always insight schema
INDEX_CATALOG_SCHEMA = "insight"
INDEX_CATALOG_TABLES = "IdxCat_Table"
INDEX_CATALOG_INDEXES = "IdxCat_Index"
INDEX_CATALOG_REFRESH_LOG = "IdxCat_RefreshLog"
INDEX_CATALOG_REFRESH_PROC = "USP_Insight_IndexCatalog_Refresh"
INDEX_CATALOG_REFRESH_TIMEOUT_SEC = 300
