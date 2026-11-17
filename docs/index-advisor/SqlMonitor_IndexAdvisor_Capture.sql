/*
  Index Advisor — Capture (Phase 1, fast path)
  =============================================
  Target: SmartMonitorDB / schema insight

  WHAT IT DOES
  - Inserts CollectionBatch + CollectionRun + IndexSnapshot
  - Scans all online user DBs this instance can access
  - Uses dm_db_partition_stats (fast). FragmentationPercent = NULL for now
    (expensive physical_stats is a later optional job)

  WHAT IT DOES NOT DO
  - Does not CREATE DATABASE
  - Does not run DDL on user databases
  - Does not need Python / Windows Task Scheduler

  PREREQ
  - Phase 0 tables exist (SqlMonitor_IndexAdvisor_Phase0.sql)
  - insight.ServerTarget has at least one IsActive = 1 row
  - Login needs: INSERT on insight.*, VIEW SERVER STATE, access to user DBs

  RUN (SSMS as login that can CREATE PROCEDURE — usually sysadmin):
    0) SqlMonitor_IndexAdvisor_Phase0.sql   (once / gap-check)
    1) This file
    2) SqlMonitor_IndexAdvisor_Jobs.sql
*/

USE [SmartMonitorDB];
GO

SET NOCOUNT ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'insight')
    EXEC(N'CREATE SCHEMA insight');
GO

CREATE OR ALTER PROCEDURE insight.USP_IndexAdvisor_Capture
    @PageCountMin INT = 100,
    @TargetId     INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @PageCountMin < 1 SET @PageCountMin = 1;

    DECLARE @BatchId UNIQUEIDENTIFIER = NEWID();
    DECLARE @CollectedAt DATETIME2(3) = SYSUTCDATETIME();
    DECLARE @Host NVARCHAR(256) = CONVERT(NVARCHAR(256), SERVERPROPERTY('MachineName'));
    DECLARE @FailCount INT = 0;
    DECLARE @TargetCount INT = 0;
    DECLARE @BatchStatus NVARCHAR(32);

    DECLARE @SqlStart DATETIME2(3);
    DECLARE @UptimeHours INT;
    DECLARE @Edition NVARCHAR(128);
    DECLARE @ObsRole NVARCHAR(32) = N'Standalone';
    DECLARE @AgName NVARCHAR(256) = NULL;
    DECLARE @ReplicaId NVARCHAR(64) = NULL;

    SELECT
        @SqlStart = osi.sqlserver_start_time,
        @UptimeHours = DATEDIFF(HOUR, osi.sqlserver_start_time, SYSUTCDATETIME()),
        @Edition = CONVERT(NVARCHAR(128), SERVERPROPERTY('Edition'))
    FROM sys.dm_os_sys_info AS osi;

    BEGIN TRY
        SELECT TOP (1)
            @AgName = ag.name,
            @ReplicaId = CONVERT(NVARCHAR(64), ar.replica_id),
            @ObsRole = CASE UPPER(ars.role_desc)
                WHEN N'PRIMARY' THEN N'Primary'
                WHEN N'SECONDARY' THEN N'Secondary'
                ELSE N'Standalone' END
        FROM sys.dm_hadr_availability_replica_states AS ars
        INNER JOIN sys.availability_replicas AS ar ON ars.replica_id = ar.replica_id
        INNER JOIN sys.availability_groups AS ag ON ar.group_id = ag.group_id
        WHERE ars.is_local = 1;
    END TRY
    BEGIN CATCH
        SET @ObsRole = N'Standalone';
        SET @AgName = NULL;
        SET @ReplicaId = NULL;
    END CATCH;

    INSERT INTO insight.CollectionBatch (BatchId, StartedAtUtc, Status, CollectorHost)
    VALUES (@BatchId, @CollectedAt, N'Running', @Host);

    DECLARE @Tid INT, @TName NVARCHAR(256);
    DECLARE tcur CURSOR LOCAL FAST_FORWARD FOR
        SELECT TargetId, ServerName
        FROM insight.ServerTarget
        WHERE IsActive = 1
          AND (@TargetId IS NULL OR TargetId = @TargetId);

    OPEN tcur;
    FETCH NEXT FROM tcur INTO @Tid, @TName;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @TargetCount += 1;
        DECLARE @RunId UNIQUEIDENTIFIER = NEWID();
        DECLARE @Err NVARCHAR(2000) = NULL;

        BEGIN TRY
            INSERT INTO insight.CollectionRun (
                RunId, BatchId, TargetId, CollectedAtUtc,
                SqlServerStartTime, UptimeHours, Edition,
                ObservedReplicaRole, AGName, ReplicaId,
                Status, ErrorMessage
            )
            VALUES (
                @RunId, @BatchId, @Tid, @CollectedAt,
                @SqlStart, @UptimeHours, @Edition,
                @ObsRole, @AgName, @ReplicaId,
                N'Running', NULL
            );

            IF OBJECT_ID(N'tempdb..#IdxSnap') IS NOT NULL DROP TABLE #IdxSnap;
            CREATE TABLE #IdxSnap (
                DatabaseName         NVARCHAR(128) NOT NULL,
                SchemaName           NVARCHAR(128) NOT NULL,
                TableName            NVARCHAR(256) NOT NULL,
                IndexName            NVARCHAR(256) NOT NULL,
                IndexType            NVARCHAR(60)  NOT NULL,
                FragmentationPercent DECIMAL(5,2)  NULL,
                PageCount            BIGINT        NULL,
                SizeMB               DECIMAL(18,2) NULL,
                UserSeeks            BIGINT        NOT NULL,
                UserScans            BIGINT        NOT NULL,
                UserLookups          BIGINT        NOT NULL,
                UserUpdates          BIGINT        NOT NULL,
                FillFactorValue      TINYINT       NULL,
                DataCompression      NVARCHAR(32)  NULL
            );

            DECLARE @db SYSNAME, @sql NVARCHAR(MAX);
            DECLARE dbs CURSOR LOCAL FAST_FORWARD FOR
                SELECT d.name
                FROM sys.databases d
                WHERE d.database_id > 4
                  AND d.state_desc = N'ONLINE'
                  AND HAS_DBACCESS(d.name) = 1
                  AND d.name NOT IN (N'msdb');

            OPEN dbs;
            FETCH NEXT FROM dbs INTO @db;
            WHILE @@FETCH_STATUS = 0
            BEGIN
                SET @sql = N'
                INSERT INTO #IdxSnap (
                    DatabaseName, SchemaName, TableName, IndexName, IndexType,
                    FragmentationPercent, PageCount, SizeMB,
                    UserSeeks, UserScans, UserLookups, UserUpdates,
                    FillFactorValue, DataCompression
                )
                SELECT
                    @db COLLATE DATABASE_DEFAULT,
                    OBJECT_SCHEMA_NAME(i.object_id, DB_ID(@db)) COLLATE DATABASE_DEFAULT,
                    OBJECT_NAME(i.object_id, DB_ID(@db)) COLLATE DATABASE_DEFAULT,
                    i.name COLLATE DATABASE_DEFAULT,
                    i.type_desc COLLATE DATABASE_DEFAULT,
                    CAST(NULL AS DECIMAL(5,2)),
                    SUM(ps.used_page_count),
                    CAST(SUM(ps.used_page_count) * 8.0 / 1024.0 AS DECIMAL(18,2)),
                    ISNULL(MAX(ius.user_seeks), 0),
                    ISNULL(MAX(ius.user_scans), 0),
                    ISNULL(MAX(ius.user_lookups), 0),
                    ISNULL(MAX(ius.user_updates), 0),
                    CAST(CASE WHEN i.fill_factor = 0 THEN 100 ELSE i.fill_factor END AS TINYINT),
                    ISNULL(MAX(par.data_compression_desc), N''NONE'')
                FROM ' + QUOTENAME(@db) + N'.sys.indexes AS i
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.objects AS o
                    ON o.object_id = i.object_id AND o.type = ''U'' AND o.is_ms_shipped = 0
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.dm_db_partition_stats AS ps
                    ON ps.object_id = i.object_id AND ps.index_id = i.index_id
                LEFT JOIN sys.dm_db_index_usage_stats AS ius
                    ON ius.database_id = DB_ID(@db)
                   AND ius.object_id = i.object_id AND ius.index_id = i.index_id
                LEFT JOIN ' + QUOTENAME(@db) + N'.sys.partitions AS par
                    ON par.object_id = i.object_id AND par.index_id = i.index_id
                   AND par.partition_number = 1
                WHERE i.type_desc IN (N''CLUSTERED'', N''NONCLUSTERED'')
                  AND i.name IS NOT NULL
                GROUP BY i.object_id, i.name, i.type_desc, i.fill_factor
                HAVING SUM(ps.used_page_count) >= @PageCountMin;';

                BEGIN TRY
                    EXEC sp_executesql
                        @sql,
                        N'@db SYSNAME, @PageCountMin INT',
                        @db = @db,
                        @PageCountMin = @PageCountMin;
                END TRY
                BEGIN CATCH
                END CATCH;

                FETCH NEXT FROM dbs INTO @db;
            END
            CLOSE dbs;
            DEALLOCATE dbs;

            INSERT INTO insight.IndexSnapshot (
                RunId, TargetId, CollectedAtUtc,
                DatabaseName, SchemaName, TableName, IndexName, IndexType,
                FragmentationPercent, PageCount, SizeMB,
                UserSeeks, UserScans, UserLookups, UserUpdates,
                [FillFactor], DataCompression
            )
            SELECT
                @RunId, @Tid, @CollectedAt,
                DatabaseName, SchemaName, TableName, IndexName, IndexType,
                FragmentationPercent, PageCount, SizeMB,
                UserSeeks, UserScans, UserLookups, UserUpdates,
                FillFactorValue, DataCompression
            FROM #IdxSnap
            WHERE SchemaName IS NOT NULL AND TableName IS NOT NULL AND IndexName IS NOT NULL;

            UPDATE insight.CollectionRun
            SET Status = N'Success', ErrorMessage = NULL
            WHERE RunId = @RunId;
        END TRY
        BEGIN CATCH
            SET @FailCount += 1;
            SET @Err = LEFT(ERROR_MESSAGE(), 1900);
            IF EXISTS (SELECT 1 FROM insight.CollectionRun WHERE RunId = @RunId)
                UPDATE insight.CollectionRun
                SET Status = N'Failed', ErrorMessage = @Err
                WHERE RunId = @RunId;
            ELSE
                INSERT INTO insight.CollectionRun (
                    RunId, BatchId, TargetId, CollectedAtUtc,
                    SqlServerStartTime, UptimeHours, Edition,
                    ObservedReplicaRole, AGName, ReplicaId,
                    Status, ErrorMessage
                )
                VALUES (
                    @RunId, @BatchId, @Tid, @CollectedAt,
                    @SqlStart, @UptimeHours, @Edition,
                    @ObsRole, @AgName, @ReplicaId,
                    N'Failed', @Err
                );
        END CATCH;

        FETCH NEXT FROM tcur INTO @Tid, @TName;
    END
    CLOSE tcur;
    DEALLOCATE tcur;

    IF @TargetCount = 0
    BEGIN
        UPDATE insight.CollectionBatch
        SET FinishedAtUtc = SYSUTCDATETIME(), Status = N'Failed'
        WHERE BatchId = @BatchId;
        RAISERROR(N'No active insight.ServerTarget rows.', 16, 1);
        RETURN;
    END;

    SET @BatchStatus = CASE
        WHEN @FailCount = 0 THEN N'Success'
        WHEN @FailCount < @TargetCount THEN N'PartialFail'
        ELSE N'Failed'
    END;

    UPDATE insight.CollectionBatch
    SET FinishedAtUtc = SYSUTCDATETIME(), Status = @BatchStatus
    WHERE BatchId = @BatchId;

    SELECT
        @BatchId AS BatchId,
        @BatchStatus AS Status,
        @TargetCount AS TargetCount,
        @FailCount AS FailCount,
        (SELECT COUNT(*) FROM insight.IndexSnapshot WHERE RunId IN (
            SELECT RunId FROM insight.CollectionRun WHERE BatchId = @BatchId
        )) AS SnapshotRows,
        @UptimeHours AS UptimeHours,
        @ObsRole AS ObservedReplicaRole;
END
GO
