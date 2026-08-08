# Installation Guide / راهنمای نصب

Complete setup on a **fresh Windows PC** with nothing pre-installed.

---

## Checklist (install in this order)

| # | Component | Required | Link |
|---|-----------|----------|------|
| 1 | **Python 3.9+** (64-bit) | Yes | https://www.python.org/downloads/ |
| 2 | **pip** (included with Python) | Yes | — |
| 3 | **ODBC Driver 17 or 18** for SQL Server | Yes | https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server |
| 4 | **SQL login** with SELECT on `msdb` | Yes | Ask your DBA |
| 5 | **Git** (optional, to clone repo) | No | https://git-scm.com/download/win |

---

## Step 1 — Install Python

1. Download **Python 3.11 or 3.12** from https://www.python.org/downloads/
2. Run the installer.
3. **Important — check these boxes:**
   - `[x] Add python.exe to PATH`
   - `[x] Install pip`
4. Click **Install Now**.

### Disable Windows Store alias (very common issue)

Windows may show *"Python was not found… Microsoft Store"* even after install.

1. Open **Settings** → **Apps** → **Advanced app settings**
2. Click **App execution aliases**
3. Turn **OFF**:
   - `python.exe`
   - `python3.exe`
4. Close all Command Prompt windows and open a **new** one.

### Verify Python

```bat
py --version
```

You should see something like `Python 3.12.x`.

---

## Step 2 — Clone or copy the project

```bat
git clone https://github.com/RezaHakimi1921/SqlServerJobStatus.git
cd SqlServerJobStatus
```

Or unzip the project folder.

---

## Step 3 — Run setup.bat

Double-click **`setup.bat`** or:

```bat
setup.bat
```

**No Python installed?** `setup.bat` will automatically download and install:

- Python 3.12 (via winget, or direct download from python.org)
- ODBC Driver 17 for SQL Server (via winget, or Microsoft MSI)

Internet access is required on first run.

It will also:

- Install Python packages from `requirements.txt`
- Verify ODBC drivers

---

## Step 4 — Run the app

```bat
run.bat
```

Browser opens at http://localhost:8050

On first run, open **Settings** and enter:

- SQL Server name / IP
- Username
- Password (stored in Windows Credential Manager, not in files)

---

## Step 5 — ODBC Driver (if setup warns)

Download and install **ODBC Driver 17 for SQL Server** (or 18):

https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

Run `setup.bat` again after install.

---

## SQL permissions needed

App login from Settings / `.env` (`SQL_USER`) — example name below is `AgentGraph`.  
Replace with the **exact** login name if yours differs.

```sql
-- 0) Find the real login name (run as admin)
SELECT name, type_desc
FROM sys.server_principals
WHERE name LIKE '%Agent%' OR name LIKE '%Graph%';

-- 1) Activity Monitor — server-level (LOGIN, not database user)
GRANT VIEW SERVER STATE TO [AgentGraph];

-- Optional but recommended: resolve lock wait_resource → schema.table in Blocking tree
-- This is a SERVER-level grant (not only on master database):
GRANT VIEW ANY DEFINITION TO [AgentGraph];
-- For KEY locks, also need CONNECT on each user database (or use a higher-privilege login).

-- Optional: live PRINT / RAISERROR message history in Session Lookup
-- Full script: scripts/sql/SqlMonitor_PrintMessages.sql
-- (run as admin once; monitor login needs VIEW SERVER STATE to read the ring buffer)
IF EXISTS (SELECT 1 FROM sys.dm_xe_sessions WHERE name = N'SqlMonitor_PrintMessages')
BEGIN
    ALTER EVENT SESSION SqlMonitor_PrintMessages ON SERVER STATE = STOP;
    DROP EVENT SESSION SqlMonitor_PrintMessages ON SERVER;
END
GO
CREATE EVENT SESSION SqlMonitor_PrintMessages ON SERVER
ADD EVENT sqlserver.error_reported (
    ACTION (sqlserver.session_id, sqlserver.client_app_name, sqlserver.username)
    WHERE (
        [severity] <= 10  -- PRINT / info / low severity
        AND [sqlserver].[is_system] = 0
    )
)
ADD TARGET package0.ring_buffer (SET max_memory = 4096)
WITH (STARTUP_STATE = ON);
ALTER EVENT SESSION SqlMonitor_PrintMessages ON SERVER STATE = START;
GO

-- 2) Jobs — need a USER inside msdb mapped to that LOGIN
USE msdb;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'AgentGraph')
    CREATE USER [AgentGraph] FOR LOGIN [AgentGraph];

GRANT SELECT ON dbo.sysjobs TO [AgentGraph];
GRANT SELECT ON dbo.sysjobsteps TO [AgentGraph];
GRANT SELECT ON dbo.sysjobhistory TO [AgentGraph];
GRANT SELECT ON dbo.sysjobactivity TO [AgentGraph];
```

If step 0 returns no rows, the login does not exist on this instance — create it or use the name shown in the app Settings (`SQL_USER`).

**Activity DMVs used (covered by `VIEW SERVER STATE`):**
`sys.dm_exec_sessions`, `sys.dm_exec_requests`, `sys.dm_exec_connections`,
`sys.dm_exec_sql_text`, `sys.dm_tran_session_transactions` (blocking).

**Realtime (Activity Live):** app uses Socket.IO WebSocket ticks (~1.5s) for
Running / Blocking / Lookup. Requires `flask-socketio` from `requirements.txt`
(run `setup.bat` after pull). Interval remains as a slow fallback.

### 3) Indexes module (DB / table picker + tag glance)

Activity uses **server-level** `VIEW SERVER STATE`. Indexes needs **database-level**
rights on each database you want to inspect (example: `RasBankAccountingCloud`).

```sql
-- Server-level: list databases in the Indexes dropdown
GRANT VIEW ANY DATABASE TO [AgentGraph];
-- (Alternatively: map the user + CONNECT on each DB you want listed.)

-- Per target database (repeat for each DB you monitor)
USE [RasBankAccountingCloud];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'AgentGraph')
    CREATE USER [AgentGraph] FOR LOGIN [AgentGraph];

GRANT VIEW DEFINITION TO [AgentGraph];      -- sys.indexes / columns / objects
GRANT VIEW DATABASE STATE TO [AgentGraph];  -- usage stats + LIMITED fragmentation
-- CONNECT is implied by a mapped database user
```

**What each grant unlocks**

| Grant | Used for |
|-------|----------|
| `VIEW ANY DATABASE` (server) | Database dropdown |
| `VIEW DEFINITION` (per DB) | Index / column / filter metadata |
| `VIEW DATABASE STATE` (per DB) | `dm_db_index_usage_stats`, `dm_db_partition_stats`, `dm_db_index_physical_stats` (LIMITED, selected table only), missing-index DMVs |

If the Indexes page shows a permission error, grant the block above on that database and click Refresh.

### 3b) Optional Index Catalog (fast Overview + Table Explorer)

Live multi-database DMV scans make Index Intelligence slow. The **Index Catalog**
caches table/index metadata in the monitor database so the app can read locally
instead of hitting every user DB on each click.

#### Why it exists

| Goal | Detail |
|------|--------|
| **Speed** | Overview and table search become catalog reads (milliseconds) instead of multi-DB DMV scans |
| **Load control** | Heavy work runs on a schedule (or on demand), not on every UI refresh |
| **Selective refresh** | You can update only tables, only index definitions, or only usage/size states |
| **Soft-fail** | If catalog objects are missing, the app still works via live DMVs |

#### Scripts to install (run in order)

Install both scripts in / against the **monitor database** (`MONITOR_DATABASE`, often `SmartMonitorDB`).

##### 1) `scripts/sql/SqlMonitor_IndexCatalog.sql`

| | |
|--|--|
| **Purpose** | Creates `insight` catalog objects and the refresh procedure |
| **Why built** | Give Index Intelligence a durable cache of tables + indexes without Extended Events |
| **Creates** | `insight.IdxCat_Table`, `insight.IdxCat_Index`, `insight.IdxCat_RefreshLog`, `insight.USP_Insight_IndexCatalog_Refresh` |
| **When to run** | Once at setup; re-run after upgrades (script is idempotent / `CREATE OR ALTER`) |

**Refresh parts** (any combination):

| Parameter | Meaning | Typical use |
|-----------|---------|-------------|
| `@RefreshTables = 1` | Table list + heap / row_count / size | Morning full / when tables change |
| `@RefreshIndexDefs = 1` | Index definitions (keys, includes, filters) — full replace | Morning full / after index DDL |
| `@RefreshIndexStats = 1` | Index states (reads / writes / size) on existing rows | Hourly (light) |

```sql
-- Morning / full
EXEC insight.USP_Insight_IndexCatalog_Refresh
    @RefreshTables = 1, @RefreshIndexDefs = 1, @RefreshIndexStats = 1;

-- Hourly states only (lighter)
EXEC insight.USP_Insight_IndexCatalog_Refresh
    @RefreshTables = 0, @RefreshIndexDefs = 0, @RefreshIndexStats = 1;

-- One database only
EXEC insight.USP_Insight_IndexCatalog_Refresh
    @DatabaseName = N'RasBankAccountingCloud',
    @RefreshTables = 1, @RefreshIndexDefs = 1, @RefreshIndexStats = 1;
```

##### 2) `scripts/sql/SqlMonitor_IndexCatalog_Jobs.sql` (optional)

| | |
|--|--|
| **Purpose** | Creates two SQL Agent jobs that keep the catalog fresh automatically |
| **Why built** | Operators should not rely only on the in-app **Update catalog** button |
| **Creates** | `SqlMonitor_IndexCatalog_DailyFull` (06:00 — full), `SqlMonitor_IndexCatalog_HourlyStats` (every hour — states) |
| **When to run** | After the catalog script; edit `@monitor_db` (and optional `@preferred`) at the top if needed |
| **Requires** | SQL Agent permission to create jobs |

#### Grants (app login)

Run on the **same database** where the catalog script was installed
(`MONITOR_DATABASE` / `SmartMonitorDB` — not `msdb` unless you intentionally installed there):

```sql
USE [SmartMonitorDB];  -- change if MONITOR_DATABASE differs
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'AgentGraph')
    CREATE USER [AgentGraph] FOR LOGIN [AgentGraph];
GRANT SELECT ON insight.IdxCat_Table TO [AgentGraph];
GRANT SELECT ON insight.IdxCat_Index TO [AgentGraph];
GRANT SELECT ON insight.IdxCat_RefreshLog TO [AgentGraph];
GRANT EXECUTE ON insight.USP_Insight_IndexCatalog_Refresh TO [AgentGraph];
```

If Update catalog shows a **collation conflict** (`Persian_100_CI_AS` vs
`Persian_100_CI_AI_SC_UTF8`), re-run the latest
`scripts/sql/SqlMonitor_IndexCatalog_FullInstall.sql` (joins use
`COLLATE DATABASE_DEFAULT`). Timestamps use `GETDATE()` (server local time), not UTC.

#### In the app

**Index Intelligence → Update catalog** opens a confirm dialog where you choose:

- which parts (tables / definitions / states)
- scope (all DBs vs selected Table Explorer database)

If the catalog is missing, Index Intelligence soft-fails back to live DMVs.

### 3c) Optional Object Size History (Tables & Growth)

Daily table size/row snapshots for growth deltas. Sibling to Index Catalog — **not** a unified Object Catalog.

#### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/sql/SqlMonitor_ObjSizeHistory.sql` | `insight.ObjSize_History` + `insight.USP_Insight_ObjSize_Capture` |
| `scripts/sql/SqlMonitor_ObjSizeHistory_Jobs.sql` | Agent job `SqlMonitor_ObjSize_DailyCapture` (06:30) |

Install in **MONITOR_DATABASE** (`SmartMonitorDB`). Capture prefers `IdxCat_Table` when present; otherwise live-scans user DBs.

```sql
USE [SmartMonitorDB];
GO
-- after SqlMonitor_ObjSizeHistory.sql
EXEC insight.USP_Insight_ObjSize_Capture @RetentionDays = 90;
```

#### Grants (app login)

```sql
USE [SmartMonitorDB];
GO
GRANT SELECT ON insight.ObjSize_History TO [AgentGraph];
GRANT EXECUTE ON insight.USP_Insight_ObjSize_Capture TO [AgentGraph];
```

#### In the app

**Tables & Growth** shows current sizes (catalog-first / live fallback). Use **Capture today** or the daily job to fill history; after a few days, 1d / 7d / 30d deltas appear. Soft-fail if history objects are missing.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Python was not found` | Install Python + disable Store aliases (Step 1) |
| `pip is not recognized` | Reinstall Python with "Install pip" checked |
| `IM002` ODBC error | Install ODBC Driver 17/18 |
| Port 8050 in use | Change `DASH_PORT` in `.env` |
| Blank page | Run `setup.bat` again |

---

# راهنمای فارسی (خلاصه)

1. **Python 3.9+** نصب کنید — حتماً `Add to PATH` را تیک بزنید  
2. **alias** های `python.exe` در تنظیمات ویندوز را خاموش کنید  
3. **`setup.bat`** را اجرا کنید  
4. **`run.bat`** را اجرا کنید  
5. در تنظیمات برنامه، Server / User / Password را وارد کنید  
6. اگر خطای ODBC دیدید، **ODBC Driver 17** را نصب کنید  

### کاتالوگ ایندکس (اختیاری ولی توصیه‌شده)

| فایل | علت / هدف |
|------|-----------|
| `scripts/sql/SqlMonitor_IndexCatalog.sql` | ساخت جداول و SP کش ایندکس در schemaی `insight` تا Overview و جستجوی جدول سریع شود و لود هر بار روی همه دیتابیس‌ها نرود |
| `scripts/sql/SqlMonitor_IndexCatalog_Jobs.sql` | ساخت Job روزانه (فول) و ساعتی (فقط state ایندکس‌ها) تا داده بدون دخالت دستی تازه بماند |

هر دو را روی دیتابیس مانیتور (`SmartMonitorDB` / `MONITOR_DATABASE`) اجرا کنید. در برنامه با **Update catalog** می‌توانید انتخاب کنید کدام بخش‌ها آپدیت شوند.

رمز عبور در فایل `.env` ذخیره **نمی‌شود** — فقط در Windows Credential Manager.
