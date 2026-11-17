/*
  Index Advisor — Phase 0 schema (SmartMonitorDB / insight)
  ========================================================
  Target DB must already exist — does NOT CREATE DATABASE.

  Creates (if missing):
    insight.ServerTarget
    insight.CollectionBatch
    insight.CollectionRun
    insight.IndexSnapshot
    insight.MissingIndexSnapshot  -- populated in Phase 2

  Also gap-fixes CollectionRun.Status CHECK so Capture may insert Running.

  Idempotent: safe to re-run for gap-check on labs / upgrades.
  If tables already exist on production, re-run only for the gap-fix block.

  Next:
    1) SqlMonitor_IndexAdvisor_Capture.sql
    2) SqlMonitor_IndexAdvisor_Jobs.sql
*/

USE [SmartMonitorDB];
GO

SET NOCOUNT ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'insight')
    EXEC(N'CREATE SCHEMA insight');
GO

/* ---------------------------------------------------------------------------
   ServerTarget — static scan targets (AG-ready from day 1)
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'insight.ServerTarget', N'U') IS NULL
BEGIN
    CREATE TABLE insight.ServerTarget
    (
        TargetId        INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_insight_ServerTarget PRIMARY KEY,
        ServerName      NVARCHAR(256)     NOT NULL,
        ConnectionKey   NVARCHAR(128)     NOT NULL,  -- maps to env: SQL_CONN_<ConnectionKey>
        ReplicaRole     NVARCHAR(32)      NOT NULL
            CONSTRAINT DF_insight_ServerTarget_ReplicaRole DEFAULT (N'Standalone'),
        AGName          NVARCHAR(256)     NULL,
        IsActive        BIT               NOT NULL
            CONSTRAINT DF_insight_ServerTarget_IsActive DEFAULT (1),
        Notes           NVARCHAR(500)     NULL,
        CreatedAtUtc    DATETIME2(3)      NOT NULL
            CONSTRAINT DF_insight_ServerTarget_CreatedAtUtc DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_insight_ServerTarget_ReplicaRole
            CHECK (ReplicaRole IN (N'Standalone', N'Primary', N'Secondary')),
        CONSTRAINT UQ_insight_ServerTarget_ConnectionKey UNIQUE (ConnectionKey)
    );
END
GO

/* ---------------------------------------------------------------------------
   CollectionBatch — one wall-clock collector orchestration across targets
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'insight.CollectionBatch', N'U') IS NULL
BEGIN
    CREATE TABLE insight.CollectionBatch
    (
        BatchId         UNIQUEIDENTIFIER  NOT NULL
            CONSTRAINT PK_insight_CollectionBatch PRIMARY KEY
            CONSTRAINT DF_insight_CollectionBatch_BatchId DEFAULT (NEWSEQUENTIALID()),
        StartedAtUtc    DATETIME2(3)      NOT NULL,
        FinishedAtUtc   DATETIME2(3)      NULL,
        Status          NVARCHAR(32)      NOT NULL
            CONSTRAINT DF_insight_CollectionBatch_Status DEFAULT (N'Running'),
        CollectorHost   NVARCHAR(256)     NULL,
        CONSTRAINT CK_insight_CollectionBatch_Status
            CHECK (Status IN (N'Running', N'Success', N'PartialFail', N'Failed'))
    );
END
GO

/* ---------------------------------------------------------------------------
   CollectionRun — one target within a batch (uptime + observed replica role)
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'insight.CollectionRun', N'U') IS NULL
BEGIN
    CREATE TABLE insight.CollectionRun
    (
        RunId               UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT PK_insight_CollectionRun PRIMARY KEY
            CONSTRAINT DF_insight_CollectionRun_RunId DEFAULT (NEWSEQUENTIALID()),
        BatchId             UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT FK_insight_CollectionRun_Batch
                REFERENCES insight.CollectionBatch (BatchId),
        TargetId            INT              NOT NULL
            CONSTRAINT FK_insight_CollectionRun_Target
                REFERENCES insight.ServerTarget (TargetId),
        CollectedAtUtc      DATETIME2(3)     NOT NULL,
        SqlServerStartTime  DATETIME2(3)     NULL,
        UptimeHours         INT              NULL,
        Edition             NVARCHAR(128)    NULL,
        ObservedReplicaRole NVARCHAR(32)     NOT NULL
            CONSTRAINT DF_insight_CollectionRun_ObservedRole DEFAULT (N'Standalone'),
        AGName              NVARCHAR(256)    NULL,
        ReplicaId           NVARCHAR(64)     NULL,
        Status              NVARCHAR(32)     NOT NULL
            CONSTRAINT DF_insight_CollectionRun_Status DEFAULT (N'Running'),
        ErrorMessage        NVARCHAR(2000)   NULL,
        CONSTRAINT CK_insight_CollectionRun_ObservedRole
            CHECK (ObservedReplicaRole IN (N'Standalone', N'Primary', N'Secondary')),
        CONSTRAINT CK_insight_CollectionRun_Status
            CHECK (Status IN (N'Running', N'Success', N'PartialFail', N'Failed')),
        CONSTRAINT UQ_insight_CollectionRun_Batch_Target UNIQUE (BatchId, TargetId)
    );

    CREATE INDEX IX_insight_CollectionRun_Target_Collected
        ON insight.CollectionRun (TargetId, CollectedAtUtc DESC)
        INCLUDE (UptimeHours, ObservedReplicaRole, Status);
END
GO

/* Gap-fix: older Phase0 omitted Running from CollectionRun.Status CHECK.
   Capture inserts Status = N'Running' then flips to Success/Failed. */
IF OBJECT_ID(N'insight.CollectionRun', N'U') IS NOT NULL
BEGIN
    DECLARE @ck SYSNAME = (
        SELECT TOP (1) cc.name
        FROM sys.check_constraints AS cc
        INNER JOIN sys.tables AS t ON t.object_id = cc.parent_object_id
        INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE s.name = N'insight'
          AND t.name = N'CollectionRun'
          AND (
              cc.name IN (N'CK_CollectionRun_Status', N'CK_insight_CollectionRun_Status')
              OR cc.definition LIKE N'%Status%'
          )
        ORDER BY CASE
            WHEN cc.name IN (N'CK_CollectionRun_Status', N'CK_insight_CollectionRun_Status') THEN 0
            ELSE 1
        END
    );

    IF @ck IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM sys.check_constraints AS cc
           INNER JOIN sys.tables AS t ON t.object_id = cc.parent_object_id
           INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
           WHERE s.name = N'insight'
             AND t.name = N'CollectionRun'
             AND cc.name = @ck
             AND cc.definition LIKE N'%Running%'
       )
    BEGIN
        DECLARE @sql NVARCHAR(500) =
            N'ALTER TABLE insight.CollectionRun DROP CONSTRAINT ' + QUOTENAME(@ck) + N';';
        EXEC sys.sp_executesql @sql;

        ALTER TABLE insight.CollectionRun
            ADD CONSTRAINT CK_insight_CollectionRun_Status
            CHECK (Status IN (N'Running', N'Success', N'PartialFail', N'Failed'));
    END
END
GO

/* ---------------------------------------------------------------------------
   IndexSnapshot — cumulative DMV values; delta = t2 - t1 in API
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'insight.IndexSnapshot', N'U') IS NULL
BEGIN
    CREATE TABLE insight.IndexSnapshot
    (
        SnapshotId           BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_insight_IndexSnapshot PRIMARY KEY,
        RunId                UNIQUEIDENTIFIER     NOT NULL
            CONSTRAINT FK_insight_IndexSnapshot_Run
                REFERENCES insight.CollectionRun (RunId),
        TargetId             INT                  NOT NULL
            CONSTRAINT FK_insight_IndexSnapshot_Target
                REFERENCES insight.ServerTarget (TargetId),
        CollectedAtUtc       DATETIME2(3)         NOT NULL,
        DatabaseName         NVARCHAR(128)        NOT NULL,
        SchemaName           NVARCHAR(128)        NOT NULL,
        TableName            NVARCHAR(256)        NOT NULL,
        IndexName            NVARCHAR(256)        NOT NULL,
        IndexType            NVARCHAR(60)         NOT NULL,
        FragmentationPercent DECIMAL(5,2)         NULL,
        PageCount            BIGINT               NULL,
        SizeMB               DECIMAL(18,2)        NULL,
        UserSeeks            BIGINT               NOT NULL
            CONSTRAINT DF_insight_IndexSnapshot_UserSeeks DEFAULT (0),
        UserScans            BIGINT               NOT NULL
            CONSTRAINT DF_insight_IndexSnapshot_UserScans DEFAULT (0),
        UserLookups          BIGINT               NOT NULL
            CONSTRAINT DF_insight_IndexSnapshot_UserLookups DEFAULT (0),
        UserUpdates          BIGINT               NOT NULL
            CONSTRAINT DF_insight_IndexSnapshot_UserUpdates DEFAULT (0),
        [FillFactor]         TINYINT              NULL,
        DataCompression      NVARCHAR(32)         NULL,
        CONSTRAINT UQ_insight_IndexSnapshot_Logical
            UNIQUE (RunId, TargetId, DatabaseName, SchemaName, TableName, IndexName)
    );

    CREATE INDEX IX_insight_IndexSnapshot_Identity_Time
        ON insight.IndexSnapshot
        (TargetId, DatabaseName, SchemaName, TableName, IndexName, CollectedAtUtc DESC)
        INCLUDE (UserSeeks, UserScans, UserUpdates, FragmentationPercent, PageCount, SizeMB, RunId);

    CREATE INDEX IX_insight_IndexSnapshot_Run
        ON insight.IndexSnapshot (RunId)
        INCLUDE (TargetId, DatabaseName, SchemaName, TableName, IndexName);
END
GO

/* ---------------------------------------------------------------------------
   MissingIndexSnapshot — Phase 2 populate; create shell now for FK readiness
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'insight.MissingIndexSnapshot', N'U') IS NULL
BEGIN
    CREATE TABLE insight.MissingIndexSnapshot
    (
        MissingSnapshotId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_insight_MissingIndexSnapshot PRIMARY KEY,
        RunId             UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT FK_insight_MissingIndexSnapshot_Run
                REFERENCES insight.CollectionRun (RunId),
        TargetId          INT              NOT NULL
            CONSTRAINT FK_insight_MissingIndexSnapshot_Target
                REFERENCES insight.ServerTarget (TargetId),
        CollectedAtUtc    DATETIME2(3)     NOT NULL,
        DatabaseName      NVARCHAR(128)    NOT NULL,
        SchemaName        NVARCHAR(128)    NOT NULL,
        TableName         NVARCHAR(256)    NOT NULL,
        Fingerprint       CHAR(64)         NOT NULL,  -- see docs/index-advisor/FINGERPRINT.md
        EqualityColumns   NVARCHAR(1000)   NULL,
        InequalityColumns NVARCHAR(1000)   NULL,
        IncludedColumns   NVARCHAR(2000)   NULL,
        AvgUserImpact     DECIMAL(8,2)     NULL,
        AvgUserCost       DECIMAL(18,4)    NULL,
        UserSeeks         BIGINT           NULL,
        UserScans         BIGINT           NULL,
        ImprovementScore  BIGINT           NULL,
        LastUserSeek      DATETIME2(3)     NULL,
        Statement         NVARCHAR(1000)   NULL,
        CONSTRAINT UQ_insight_MissingIndexSnapshot_Logical
            UNIQUE (RunId, TargetId, Fingerprint)
    );

    CREATE INDEX IX_insight_MissingIndex_Identity_Time
        ON insight.MissingIndexSnapshot
        (TargetId, DatabaseName, SchemaName, TableName, Fingerprint, CollectedAtUtc DESC)
        INCLUDE (ImprovementScore, AvgUserImpact, AvgUserCost, RunId);
END
GO

/* Seed example target (edit ConnectionKey to match env var suffix) */
IF NOT EXISTS (
    SELECT 1
    FROM insight.ServerTarget
    WHERE ConnectionKey = N'DEV_PRIMARY'
)
BEGIN
    INSERT INTO insight.ServerTarget
    (
        ServerName,
        ConnectionKey,
        ReplicaRole,
        AGName,
        IsActive,
        Notes
    )
    VALUES
    (N'localhost', N'DEV_PRIMARY', N'Standalone', NULL, 1, N'Dev / staging seed');
END
GO

/* Extended properties (optional metadata) */
DECLARE @Schema SYSNAME = N'insight';
DECLARE @Table  SYSNAME;
DECLARE @Desc   NVARCHAR(500);

DECLARE @Tables TABLE (TableName SYSNAME NOT NULL, Description NVARCHAR(500) NOT NULL);
INSERT INTO @Tables (TableName, Description) VALUES
    (N'ServerTarget',         N'Scan targets for Index Advisor collector (static config).'),
    (N'CollectionBatch',      N'One collector wall-clock batch across active targets.'),
    (N'CollectionRun',        N'Per-target run inside a batch; uptime + observed replica role.'),
    (N'IndexSnapshot',        N'Cumulative index usage/size snapshot; delta computed in API.'),
    (N'MissingIndexSnapshot', N'Missing-index DMV snapshot (Phase 2); fingerprint per FINGERPRINT.md.');

DECLARE c CURSOR LOCAL FAST_FORWARD FOR
    SELECT TableName, Description FROM @Tables;
OPEN c;
FETCH NEXT FROM c INTO @Table, @Desc;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF OBJECT_ID(QUOTENAME(@Schema) + N'.' + QUOTENAME(@Table), N'U') IS NOT NULL
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM sys.extended_properties AS ep
            INNER JOIN sys.tables AS t ON ep.major_id = t.object_id
            INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
            WHERE ep.name = N'MS_Description'
              AND ep.minor_id = 0
              AND s.name = @Schema
              AND t.name = @Table
        )
            EXEC sys.sp_updateextendedproperty
                @name = N'MS_Description', @value = @Desc,
                @level0type = N'SCHEMA', @level0name = @Schema,
                @level1type = N'TABLE',  @level1name = @Table;
        ELSE
            EXEC sys.sp_addextendedproperty
                @name = N'MS_Description', @value = @Desc,
                @level0type = N'SCHEMA', @level0name = @Schema,
                @level1type = N'TABLE',  @level1name = @Table;
    END
    FETCH NEXT FROM c INTO @Table, @Desc;
END
CLOSE c;
DEALLOCATE c;
GO
