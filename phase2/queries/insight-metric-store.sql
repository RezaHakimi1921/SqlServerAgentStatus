/*
  Insight Discovery — Metric Store (V2)
  Target DB: SmartMonitorDB (or MONITOR_DATABASE in .env) — NOT msdb
  Retention: delete samples/events older than 30 days
*/

USE [jobsettings];  -- rename if needed
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'insight')
    EXEC(N'CREATE SCHEMA insight');
GO

/* ── 1) Time-series samples (small numbers only) ─────────────────────────── */
IF OBJECT_ID(N'insight.metric_samples', N'U') IS NULL
BEGIN
    CREATE TABLE insight.metric_samples
    (
        sample_id     BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_insight_metric_samples PRIMARY KEY,

        -- When the sample was taken (app/server local time or UTC — stay consistent)
        ts            DATETIME2(0) NOT NULL
            CONSTRAINT DF_insight_metric_samples_ts DEFAULT (SYSUTCDATETIME()),

        -- 'server' | 'job' | 'session' | 'database'
        scope         VARCHAR(16) NOT NULL,

        -- e.g. job_id GUID string, database name, or '_' for server-wide
        scope_id      NVARCHAR(128) NOT NULL,

        -- Controlled vocabulary only, e.g.:
        --   job_failed, job_duration_sec, job_running,
        --   blocking_wait_ms, blocking_session_count, head_blocker_count
        metric_name   VARCHAR(64) NOT NULL,

        value         FLOAT NOT NULL,

        -- Tiny JSON only, e.g. {"step":"2"} — never full SQL / error text
        dims_json     NVARCHAR(400) NULL,

        -- Optional human label for UI (job name); keep short
        scope_label   NVARCHAR(200) NULL
    );

    CREATE INDEX IX_insight_metric_samples_ts
        ON insight.metric_samples (ts);

    CREATE INDEX IX_insight_metric_samples_lookup
        ON insight.metric_samples (metric_name, scope, scope_id, ts DESC);

    CREATE INDEX IX_insight_metric_samples_day
        ON insight.metric_samples (ts, metric_name)
        INCLUDE (scope, scope_id, value);
END
GO

/* ── 2) Generated insights (Today's Insights UI) ─────────────────────────── */
IF OBJECT_ID(N'insight.insight_events', N'U') IS NULL
BEGIN
    CREATE TABLE insight.insight_events
    (
        insight_id    BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_insight_insight_events PRIMARY KEY,

        created_at    DATETIME2(0) NOT NULL
            CONSTRAINT DF_insight_insight_events_created DEFAULT (SYSUTCDATETIME()),

        -- First / last time this rule+target was observed in the current streak
        first_seen_at DATETIME2(0) NOT NULL,
        last_seen_at  DATETIME2(0) NOT NULL,

        -- 'info' | 'warning' | 'critical'
        severity      VARCHAR(16) NOT NULL,

        -- Rule id, e.g. 'job_failed_today', 'blocking_wait_high'
        rule_id       VARCHAR(64) NOT NULL,

        scope         VARCHAR(16) NOT NULL,
        scope_id      NVARCHAR(128) NOT NULL,
        scope_label   NVARCHAR(200) NULL,

        -- Short sentence for UI (Persian later OK)
        title         NVARCHAR(300) NOT NULL,
        detail        NVARCHAR(1000) NULL,

        -- How many times aggregated into this insight (digest)
        occurrence_count INT NOT NULL
            CONSTRAINT DF_insight_insight_events_occ DEFAULT (1),

        -- Cooldown / dedupe key: rule_id + scope + scope_id + day
        dedupe_key    VARCHAR(200) NOT NULL,

        -- User feedback: NULL | 0 unimportant | 1 important
        feedback      TINYINT NULL,

        -- Deep link hint for app (not a URL): 'jobs' | 'activity-blocking' | ...
        link_target   VARCHAR(64) NULL
    );

    CREATE UNIQUE INDEX UX_insight_insight_events_dedupe
        ON insight.insight_events (dedupe_key);

    CREATE INDEX IX_insight_insight_events_day
        ON insight.insight_events (created_at DESC, severity);
END
GO

/* ── 3) Retention: purge > 30 days ───────────────────────────────────────── */
CREATE OR ALTER PROCEDURE insight.usp_purge_old_data
    @RetentionDays INT = 30
AS
BEGIN
    SET NOCOUNT ON;

    IF @RetentionDays < 7
        SET @RetentionDays = 7;  -- safety floor

    DECLARE @Cutoff DATETIME2(0) = DATEADD(DAY, -@RetentionDays, SYSUTCDATETIME());

    DELETE FROM insight.metric_samples
    WHERE ts < @Cutoff;

    DELETE FROM insight.insight_events
    WHERE created_at < @Cutoff;

    -- Optional: shrink not required; index maintenance is enough
END
GO

/*
  Optional: per-metric capture intervals (also auto-created by the app)

  CREATE TABLE insight.metric_schedule (...);  -- see core/insight/schedule.py
*/
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

  Soft daily ceiling monitor (optional check):
  SELECT CAST(ts AS date) AS d, COUNT(*) AS rows_n
  FROM insight.metric_samples
  WHERE ts >= DATEADD(DAY, -7, SYSUTCDATETIME())
  GROUP BY CAST(ts AS date)
  ORDER BY d DESC;
*/
GO
