/*
  SqlMonitor Index Catalog — SQL Agent job examples
  -------------------------------------------------
  Run against the MONITOR database (SmartMonitorDB) after
  scripts/sql/SqlMonitor_IndexCatalog.sql is installed.

  Jobs created (idempotent by name):
    1) SqlMonitor_IndexCatalog_DailyFull   — 06:00 daily (tables + index defs + stats)
    2) SqlMonitor_IndexCatalog_HourlyStats — every hour (index/table state only)

  Adjust schedule / preferred database below if needed.
  Requires SQL Agent permission to create jobs on this instance.
*/

SET NOCOUNT ON;
GO

USE [msdb];
GO

DECLARE @job_daily SYSNAME = N'SqlMonitor_IndexCatalog_DailyFull';
DECLARE @job_hourly SYSNAME = N'SqlMonitor_IndexCatalog_HourlyStats';
DECLARE @monitor_db SYSNAME = N'SmartMonitorDB';  -- change if MONITOR_DATABASE differs
DECLARE @preferred  SYSNAME = NULL;
-- Optional: limit hourly to one DB, e.g. N'RasBankAccountingCloud'
-- SET @preferred = N'RasBankAccountingCloud';

DECLARE @step_daily NVARCHAR(MAX) = N'
USE ' + QUOTENAME(@monitor_db) + N';
EXEC insight.USP_Insight_IndexCatalog_Refresh
    @DatabaseName = NULL,
    @RefreshTables = 1,
    @RefreshIndexDefs = 1,
    @RefreshIndexStats = 1;
';

DECLARE @step_hourly NVARCHAR(MAX);
IF @preferred IS NULL
    SET @step_hourly = N'
USE ' + QUOTENAME(@monitor_db) + N';
EXEC insight.USP_Insight_IndexCatalog_Refresh
    @DatabaseName = NULL,
    @RefreshTables = 0,
    @RefreshIndexDefs = 0,
    @RefreshIndexStats = 1;
';
ELSE
    SET @step_hourly = N'
USE ' + QUOTENAME(@monitor_db) + N';
EXEC insight.USP_Insight_IndexCatalog_Refresh
    @DatabaseName = N''' + REPLACE(@preferred, '''', '''''') + N''',
    @RefreshTables = 0,
    @RefreshIndexDefs = 0,
    @RefreshIndexStats = 1;
';

DECLARE @owner SYSNAME = SUSER_SNAME();

/* ---- Daily full ---- */
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = @job_daily)
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = @job_daily, @delete_unused_schedule = 1;
END;

EXEC msdb.dbo.sp_add_job
    @job_name = @job_daily,
    @enabled = 1,
    @description = N'SqlMonitor: full rebuild of insight index catalog (tables + defs + stats).',
    @owner_login_name = @owner;

EXEC msdb.dbo.sp_add_jobstep
    @job_name = @job_daily,
    @step_name = N'Refresh catalog full',
    @subsystem = N'TSQL',
    @database_name = @monitor_db,
    @command = @step_daily,
    @on_success_action = 1,
    @on_fail_action = 2;

IF NOT EXISTS (SELECT 1 FROM msdb.dbo.sysschedules WHERE name = N'SqlMonitor_IndexCatalog_Daily_0600')
BEGIN
    EXEC msdb.dbo.sp_add_schedule
        @schedule_name = N'SqlMonitor_IndexCatalog_Daily_0600',
        @freq_type = 4,          -- daily
        @freq_interval = 1,
        @freq_subday_type = 1,   -- at the specified time
        @active_start_time = 60000;  -- 06:00:00
END;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = @job_daily,
    @schedule_name = N'SqlMonitor_IndexCatalog_Daily_0600';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = @job_daily,
    @server_name = N'(LOCAL)';

/* ---- Hourly stats ---- */
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = @job_hourly)
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = @job_hourly, @delete_unused_schedule = 1;
END;

EXEC msdb.dbo.sp_add_job
    @job_name = @job_hourly,
    @enabled = 1,
    @description = N'SqlMonitor: hourly index/table state refresh (usage + size).',
    @owner_login_name = @owner;

EXEC msdb.dbo.sp_add_jobstep
    @job_name = @job_hourly,
    @step_name = N'Refresh catalog stats',
    @subsystem = N'TSQL',
    @database_name = @monitor_db,
    @command = @step_hourly,
    @on_success_action = 1,
    @on_fail_action = 2;

IF NOT EXISTS (SELECT 1 FROM msdb.dbo.sysschedules WHERE name = N'SqlMonitor_IndexCatalog_Hourly')
BEGIN
    EXEC msdb.dbo.sp_add_schedule
        @schedule_name = N'SqlMonitor_IndexCatalog_Hourly',
        @freq_type = 4,              -- daily
        @freq_interval = 1,
        @freq_subday_type = 8,       -- hours
        @freq_subday_interval = 1,   -- every 1 hour
        @active_start_time = 0;
END;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = @job_hourly,
    @schedule_name = N'SqlMonitor_IndexCatalog_Hourly';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = @job_hourly,
    @server_name = N'(LOCAL)';

PRINT N'Created jobs:';
PRINT @job_daily;
PRINT @job_hourly;
GO
