/*
  Index Advisor — SQL Agent jobs
  ==============================
  Run AFTER Phase0 + SqlMonitor_IndexAdvisor_Capture.sql (as sysadmin).

  WHY SQL AGENT (not Windows Task on your PC)
  - Capture must run on the SQL Server host even if your laptop is off
  - Index rebuild windows (e.g. ~01:00) need fresh snapshots before/around them
  - Delete any local task: schtasks /Delete /TN "SqlMonitor_IndexAdvisor_Hourly" /F

  JOBS
  1) SqlMonitor_IndexAdvisor_HourlyCapture — every hour (history + delta)
  2) SqlMonitor_IndexAdvisor_PreRebuild    — daily 23:30 (before typical night rebuild)

  Adjust times below if your rebuild window differs.
*/

SET NOCOUNT ON;
GO

USE [msdb];
GO

DECLARE @monitor_db SYSNAME = N'SmartMonitorDB';
DECLARE @owner SYSNAME = SUSER_SNAME();

DECLARE @step NVARCHAR(MAX) = N'
USE ' + QUOTENAME(@monitor_db) + N';
EXEC insight.USP_IndexAdvisor_Capture @PageCountMin = 100;
';

/* ---- Hourly ---- */
DECLARE @job_hourly SYSNAME = N'SqlMonitor_IndexAdvisor_HourlyCapture';

IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = @job_hourly)
    EXEC msdb.dbo.sp_delete_job @job_name = @job_hourly, @delete_unused_schedule = 1;

EXEC msdb.dbo.sp_add_job
    @job_name = @job_hourly,
    @enabled = 1,
    @description = N'SqlMonitor Index Advisor: hourly usage/size snapshot into insight.IndexSnapshot.',
    @owner_login_name = @owner;

EXEC msdb.dbo.sp_add_jobstep
    @job_name = @job_hourly,
    @step_name = N'Capture',
    @subsystem = N'TSQL',
    @database_name = @monitor_db,
    @command = @step,
    @on_success_action = 1,
    @on_fail_action = 2;

IF NOT EXISTS (SELECT 1 FROM msdb.dbo.sysschedules WHERE name = N'SqlMonitor_IndexAdvisor_Hourly')
BEGIN
    EXEC msdb.dbo.sp_add_schedule
        @schedule_name = N'SqlMonitor_IndexAdvisor_Hourly',
        @freq_type = 4,
        @freq_interval = 1,
        @freq_subday_type = 8,
        @freq_subday_interval = 1,
        @active_start_time = 0;
END;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = @job_hourly,
    @schedule_name = N'SqlMonitor_IndexAdvisor_Hourly';

EXEC msdb.dbo.sp_add_jobserver @job_name = @job_hourly, @server_name = N'(LOCAL)';

/* ---- Pre-rebuild (23:30 daily) ---- */
DECLARE @job_pre SYSNAME = N'SqlMonitor_IndexAdvisor_PreRebuild';

IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = @job_pre)
    EXEC msdb.dbo.sp_delete_job @job_name = @job_pre, @delete_unused_schedule = 1;

EXEC msdb.dbo.sp_add_job
    @job_name = @job_pre,
    @enabled = 1,
    @description = N'SqlMonitor Index Advisor: snapshot before night index rebuild window (~01:00).',
    @owner_login_name = @owner;

EXEC msdb.dbo.sp_add_jobstep
    @job_name = @job_pre,
    @step_name = N'Capture before rebuild',
    @subsystem = N'TSQL',
    @database_name = @monitor_db,
    @command = @step,
    @on_success_action = 1,
    @on_fail_action = 2;

IF NOT EXISTS (SELECT 1 FROM msdb.dbo.sysschedules WHERE name = N'SqlMonitor_IndexAdvisor_Daily_2330')
BEGIN
    EXEC msdb.dbo.sp_add_schedule
        @schedule_name = N'SqlMonitor_IndexAdvisor_Daily_2330',
        @freq_type = 4,
        @freq_interval = 1,
        @freq_subday_type = 1,
        @active_start_time = 233000;  -- 23:30 — change if rebuild time differs
END;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = @job_pre,
    @schedule_name = N'SqlMonitor_IndexAdvisor_Daily_2330';

EXEC msdb.dbo.sp_add_jobserver @job_name = @job_pre, @server_name = N'(LOCAL)';
GO

/* Optional: first capture now */
USE [SmartMonitorDB];
GO
EXEC insight.USP_IndexAdvisor_Capture @PageCountMin = 100;
GO

/*
  VERIFY
  ------
  SELECT TOP 5 * FROM insight.CollectionBatch ORDER BY StartedAtUtc DESC;
  SELECT COUNT(*) FROM insight.IndexSnapshot;
  SELECT name, enabled FROM msdb.dbo.sysjobs WHERE name LIKE N'SqlMonitor_IndexAdvisor%';

  REMOVE WINDOWS TASK (if created earlier on your PC)
  ----------------------------------------------------
  schtasks /Delete /TN "SqlMonitor_IndexAdvisor_Hourly" /F
*/
