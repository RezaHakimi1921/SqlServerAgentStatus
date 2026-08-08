/*
  SqlMonitor Object Size History — SQL Agent job
  ----------------------------------------------
  Run against msdb after SqlMonitor_ObjSizeHistory.sql is installed
  in MONITOR_DATABASE (SmartMonitorDB).

  Job (idempotent by name):
    SqlMonitor_ObjSize_DailyCapture — 06:30 daily

  Separate from Index Catalog jobs (ownership boundary).
  Optional: add as a second step on SqlMonitor_IndexCatalog_DailyFull instead.
*/

SET NOCOUNT ON;
GO

USE [msdb];
GO

DECLARE @job_name SYSNAME = N'SqlMonitor_ObjSize_DailyCapture';
DECLARE @monitor_db SYSNAME = N'SmartMonitorDB';  -- change if MONITOR_DATABASE differs
DECLARE @owner SYSNAME = SUSER_SNAME();

DECLARE @step NVARCHAR(MAX) = N'
USE ' + QUOTENAME(@monitor_db) + N';
EXEC insight.USP_Insight_ObjSize_Capture @RetentionDays = 90;
';

IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = @job_name)
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = @job_name, @delete_unused_schedule = 1;
END;

EXEC msdb.dbo.sp_add_job
    @job_name = @job_name,
    @enabled = 1,
    @description = N'SqlMonitor: daily capture of table row/size into insight.ObjSize_History.',
    @owner_login_name = @owner;

EXEC msdb.dbo.sp_add_jobstep
    @job_name = @job_name,
    @step_name = N'Capture object sizes',
    @subsystem = N'TSQL',
    @database_name = @monitor_db,
    @command = @step,
    @on_success_action = 1,
    @on_fail_action = 2;

IF NOT EXISTS (SELECT 1 FROM msdb.dbo.sysschedules WHERE name = N'SqlMonitor_ObjSize_Daily_0630')
BEGIN
    EXEC msdb.dbo.sp_add_schedule
        @schedule_name = N'SqlMonitor_ObjSize_Daily_0630',
        @freq_type = 4,
        @freq_interval = 1,
        @freq_subday_type = 1,
        @active_start_time = 63000;  -- 06:30 after Index Catalog DailyFull
END;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = @job_name,
    @schedule_name = N'SqlMonitor_ObjSize_Daily_0630';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = @job_name,
    @server_name = N'(LOCAL)';
GO
