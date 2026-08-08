-- Run as dbo / db_owner on SmartMonitorDB (AgentGraph may lack CREATE TABLE)
USE [SmartMonitorDB];
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'insight')
    EXEC(N'CREATE SCHEMA insight');
GO

IF OBJECT_ID(N'insight.metric_schedule', N'U') IS NULL
BEGIN
    CREATE TABLE insight.metric_schedule
    (
        metric_name   VARCHAR(64) NOT NULL
            CONSTRAINT PK_insight_metric_schedule PRIMARY KEY,
        interval_sec  INT NOT NULL,
        enabled       BIT NOT NULL
            CONSTRAINT DF_insight_metric_schedule_en DEFAULT (1),
        updated_at    DATETIME2(0) NOT NULL
            CONSTRAINT DF_insight_metric_schedule_ts DEFAULT (SYSUTCDATETIME())
    );
END
GO

-- Seed defaults if empty
IF NOT EXISTS (SELECT 1 FROM insight.metric_schedule)
BEGIN
    INSERT INTO insight.metric_schedule (metric_name, interval_sec, enabled) VALUES
        ('blocking_session_count', 10, 1),
        ('blocking_wait_ms', 10, 1),
        ('head_blocker_count', 10, 1),
        ('job_failed', 60, 1);
END
GO

-- Grant app login (adjust login name if needed)
GRANT SELECT, INSERT, UPDATE ON insight.metric_schedule TO [AgentGraph];
GO
