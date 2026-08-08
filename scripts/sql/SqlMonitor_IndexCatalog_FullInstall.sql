/*
  SqlMonitor Index Catalog — FULL install for SmartMonitorDB
  -----------------------------------------------------------
  Collation-safe joins (COLLATE DATABASE_DEFAULT) + GETDATE() timestamps.
  Run as sysadmin in SSMS (entire script, F5).
*/
USE [SmartMonitorDB];
GO

SET NOCOUNT ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'insight')
    EXEC(N'CREATE SCHEMA insight');
GO

IF OBJECT_ID(N'insight.IdxCat_RefreshLog', N'U') IS NULL
BEGIN
    CREATE TABLE insight.IdxCat_RefreshLog (
        refresh_id       BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_insight_IdxCat_RefreshLog PRIMARY KEY,
        started_at       DATETIME2(0) NOT NULL
            CONSTRAINT DF_insight_IdxCat_RefreshLog_started DEFAULT (GETDATE()),
        finished_at      DATETIME2(0) NULL,
        database_name    SYSNAME NULL,           -- NULL = all accessible
        status           VARCHAR(20) NOT NULL,   -- running | ok | error
        message          NVARCHAR(1000) NULL,
        tables_upserted  INT NULL,
        indexes_upserted INT NULL,
        refresh_parts    NVARCHAR(100) NULL
    );
END
GO

IF COL_LENGTH(N'insight.IdxCat_RefreshLog', N'refresh_parts') IS NULL
    ALTER TABLE insight.IdxCat_RefreshLog ADD refresh_parts NVARCHAR(100) NULL;
GO

IF OBJECT_ID(N'insight.IdxCat_Table', N'U') IS NULL
BEGIN
    CREATE TABLE insight.IdxCat_Table (
        database_name SYSNAME NOT NULL,
        schema_name   SYSNAME NOT NULL,
        table_name    SYSNAME NOT NULL,
        object_id     INT NOT NULL,
        is_heap       BIT NOT NULL
            CONSTRAINT DF_insight_IdxCat_Table_heap DEFAULT (0),
        row_count     BIGINT NULL,
        size_mb       FLOAT NULL,
        refreshed_at  DATETIME2(0) NOT NULL,
        CONSTRAINT PK_insight_IdxCat_Table PRIMARY KEY (database_name, schema_name, table_name)
    );
    CREATE INDEX IX_insight_IdxCat_Table_search
        ON insight.IdxCat_Table (database_name, table_name);
END
GO

IF OBJECT_ID(N'insight.IdxCat_Index', N'U') IS NULL
BEGIN
    CREATE TABLE insight.IdxCat_Index (
        database_name        SYSNAME NOT NULL,
        schema_name          SYSNAME NOT NULL,
        table_name           SYSNAME NOT NULL,
        index_id             INT NOT NULL,
        index_name           SYSNAME NULL,
        type_desc            NVARCHAR(60) NULL,
        is_unique            BIT NOT NULL
            CONSTRAINT DF_insight_IdxCat_Index_uq DEFAULT (0),
        is_primary_key       BIT NOT NULL
            CONSTRAINT DF_insight_IdxCat_Index_pk DEFAULT (0),
        is_unique_constraint BIT NOT NULL
            CONSTRAINT DF_insight_IdxCat_Index_uc DEFAULT (0),
        has_filter           BIT NOT NULL
            CONSTRAINT DF_insight_IdxCat_Index_hf DEFAULT (0),
        filter_def           NVARCHAR(MAX) NULL,
        key_cols             NVARCHAR(MAX) NULL,
        include_cols         NVARCHAR(MAX) NULL,
        reads                BIGINT NULL,
        writes               BIGINT NULL,
        size_mb              FLOAT NULL,
        page_count           BIGINT NULL,
        refreshed_at         DATETIME2(0) NOT NULL,
        CONSTRAINT PK_insight_IdxCat_Index PRIMARY KEY (database_name, schema_name, table_name, index_id)
    );
    CREATE INDEX IX_insight_IdxCat_Index_usage
        ON insight.IdxCat_Index (database_name, writes DESC, reads);
END
GO

CREATE OR ALTER PROCEDURE insight.USP_Insight_IndexCatalog_Refresh
    @DatabaseName      SYSNAME = NULL,  -- NULL = all user DBs with access
    @RefreshTables     BIT = 1,
    @RefreshIndexDefs  BIT = 1,
    @RefreshIndexStats BIT = 1
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @refresh_id BIGINT;
    DECLARE @db SYSNAME;
    DECLARE @sql NVARCHAR(MAX);
    DECLARE @tables INT = 0, @indexes INT = 0;
    DECLARE @parts NVARCHAR(100);

    IF ISNULL(@RefreshTables, 0) = 0
       AND ISNULL(@RefreshIndexDefs, 0) = 0
       AND ISNULL(@RefreshIndexStats, 0) = 0
    BEGIN
        RAISERROR(N'At least one of @RefreshTables / @RefreshIndexDefs / @RefreshIndexStats must be 1.', 16, 1);
        RETURN;
    END;

    SET @parts =
          N'tables=' + CASE WHEN @RefreshTables = 1 THEN N'1' ELSE N'0' END
        + N';defs=' + CASE WHEN @RefreshIndexDefs = 1 THEN N'1' ELSE N'0' END
        + N';stats=' + CASE WHEN @RefreshIndexStats = 1 THEN N'1' ELSE N'0' END;

    INSERT INTO insight.IdxCat_RefreshLog (database_name, status, message, refresh_parts)
    VALUES (@DatabaseName, 'running', N'Started', @parts);
    SET @refresh_id = SCOPE_IDENTITY();

    BEGIN TRY
        DECLARE dbs CURSOR LOCAL FAST_FORWARD FOR
        SELECT d.name
        FROM sys.databases d
        WHERE d.state = 0
          AND d.database_id > 4
          AND HAS_DBACCESS(d.name) = 1
          AND (@DatabaseName IS NULL OR d.name COLLATE DATABASE_DEFAULT = @DatabaseName COLLATE DATABASE_DEFAULT);

        OPEN dbs;
        FETCH NEXT FROM dbs INTO @db;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            /* ---- Tables (full replace for this DB) ---- */
            IF @RefreshTables = 1
            BEGIN
                SET @sql = N'
                DELETE FROM insight.IdxCat_Table WHERE database_name = @db;
                INSERT INTO insight.IdxCat_Table
                    (database_name, schema_name, table_name, object_id, is_heap, row_count, size_mb, refreshed_at)
                SELECT
                    @db,
                    s.name COLLATE DATABASE_DEFAULT,
                    t.name COLLATE DATABASE_DEFAULT,
                    t.object_id,
                    CASE WHEN EXISTS (
                        SELECT 1 FROM ' + QUOTENAME(@db) + N'.sys.indexes i
                        WHERE i.object_id = t.object_id AND i.index_id = 0
                    ) AND NOT EXISTS (
                        SELECT 1 FROM ' + QUOTENAME(@db) + N'.sys.indexes i
                        WHERE i.object_id = t.object_id AND i.index_id = 1
                    ) THEN 1 ELSE 0 END,
                    (SELECT SUM(p.rows) FROM ' + QUOTENAME(@db) + N'.sys.partitions p
                     WHERE p.object_id = t.object_id AND p.index_id IN (0,1)),
                    CAST((
                        SELECT SUM(ps.used_page_count) * 8.0 / 1024.0
                        FROM ' + QUOTENAME(@db) + N'.sys.dm_db_partition_stats ps
                        WHERE ps.object_id = t.object_id
                    ) AS float),
                    GETDATE()
                FROM ' + QUOTENAME(@db) + N'.sys.tables t
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.schemas s ON s.schema_id = t.schema_id
                WHERE t.is_ms_shipped = 0;';
                EXEC sp_executesql @sql, N'@db SYSNAME', @db=@db;
                SET @tables += @@ROWCOUNT;
            END
            ELSE IF @RefreshIndexStats = 1
            BEGIN
                /* Light table state only (row/size/heap) without reshuffling list */
                SET @sql = N'
                UPDATE cat
                SET
                    is_heap = CASE WHEN EXISTS (
                        SELECT 1 FROM ' + QUOTENAME(@db) + N'.sys.indexes i
                        WHERE i.object_id = t.object_id AND i.index_id = 0
                    ) AND NOT EXISTS (
                        SELECT 1 FROM ' + QUOTENAME(@db) + N'.sys.indexes i
                        WHERE i.object_id = t.object_id AND i.index_id = 1
                    ) THEN 1 ELSE 0 END,
                    row_count = (SELECT SUM(p.rows) FROM ' + QUOTENAME(@db) + N'.sys.partitions p
                                 WHERE p.object_id = t.object_id AND p.index_id IN (0,1)),
                    size_mb = CAST((
                        SELECT SUM(ps.used_page_count) * 8.0 / 1024.0
                        FROM ' + QUOTENAME(@db) + N'.sys.dm_db_partition_stats ps
                        WHERE ps.object_id = t.object_id
                    ) AS float),
                    refreshed_at = GETDATE()
                FROM insight.IdxCat_Table cat
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.tables t
                    ON t.object_id = cat.object_id
                   AND t.name COLLATE DATABASE_DEFAULT = cat.table_name COLLATE DATABASE_DEFAULT
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.schemas s
                    ON s.schema_id = t.schema_id
                   AND s.name COLLATE DATABASE_DEFAULT = cat.schema_name COLLATE DATABASE_DEFAULT
                WHERE cat.database_name = @db AND t.is_ms_shipped = 0;';
                EXEC sp_executesql @sql, N'@db SYSNAME', @db=@db;
                SET @tables += @@ROWCOUNT;
            END;

            /* ---- Index definitions (full replace for this DB) ---- */
            IF @RefreshIndexDefs = 1
            BEGIN
                SET @sql = N'
                DELETE FROM insight.IdxCat_Index WHERE database_name = @db;
                INSERT INTO insight.IdxCat_Index (
                    database_name, schema_name, table_name, index_id, index_name, type_desc,
                    is_unique, is_primary_key, is_unique_constraint, has_filter, filter_def,
                    key_cols, include_cols, reads, writes, size_mb, page_count, refreshed_at
                )
                SELECT
                    @db,
                    s.name COLLATE DATABASE_DEFAULT,
                    o.name COLLATE DATABASE_DEFAULT,
                    i.index_id,
                    i.name COLLATE DATABASE_DEFAULT,
                    i.type_desc COLLATE DATABASE_DEFAULT,
                    i.is_unique,
                    i.is_primary_key,
                    i.is_unique_constraint,
                    i.has_filter,
                    i.filter_definition COLLATE DATABASE_DEFAULT,
                    STUFF((
                        SELECT N'','' + (c.name COLLATE DATABASE_DEFAULT)
                        FROM ' + QUOTENAME(@db) + N'.sys.index_columns ic
                        INNER JOIN ' + QUOTENAME(@db) + N'.sys.columns c
                            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
                        WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
                          AND ic.is_included_column = 0
                        ORDER BY ic.key_ordinal
                        FOR XML PATH(''''), TYPE
                    ).value(N''.[1]'', N''nvarchar(max)''), 1, 1, N''''),
                    STUFF((
                        SELECT N'','' + (c.name COLLATE DATABASE_DEFAULT)
                        FROM ' + QUOTENAME(@db) + N'.sys.index_columns ic
                        INNER JOIN ' + QUOTENAME(@db) + N'.sys.columns c
                            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
                        WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
                          AND ic.is_included_column = 1
                        ORDER BY ic.index_column_id
                        FOR XML PATH(''''), TYPE
                    ).value(N''.[1]'', N''nvarchar(max)''), 1, 1, N''''),
                    ISNULL(us.user_seeks,0)+ISNULL(us.user_scans,0)+ISNULL(us.user_lookups,0),
                    ISNULL(us.user_updates,0),
                    CAST(ISNULL(ps.used_page_count,0)*8.0/1024.0 AS float),
                    ISNULL(ps.used_page_count,0),
                    GETDATE()
                FROM ' + QUOTENAME(@db) + N'.sys.indexes i
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.objects o ON o.object_id = i.object_id
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.schemas s ON s.schema_id = o.schema_id
                LEFT JOIN ' + QUOTENAME(@db) + N'.sys.dm_db_index_usage_stats us
                    ON us.database_id = DB_ID(@db) AND us.object_id = i.object_id AND us.index_id = i.index_id
                LEFT JOIN (
                    SELECT object_id, index_id, SUM(used_page_count) AS used_page_count
                    FROM ' + QUOTENAME(@db) + N'.sys.dm_db_partition_stats
                    GROUP BY object_id, index_id
                ) ps ON ps.object_id = i.object_id AND ps.index_id = i.index_id
                WHERE o.type = ''U'' AND i.is_hypothetical = 0 AND i.index_id > 0;';
                EXEC sp_executesql @sql, N'@db SYSNAME', @db=@db;
                SET @indexes += @@ROWCOUNT;
            END
            ELSE IF @RefreshIndexStats = 1
            BEGIN
                /* Update usage/size on existing catalog index rows only */
                SET @sql = N'
                UPDATE cat
                SET
                    reads = ISNULL(us.user_seeks,0)+ISNULL(us.user_scans,0)+ISNULL(us.user_lookups,0),
                    writes = ISNULL(us.user_updates,0),
                    size_mb = CAST(ISNULL(ps.used_page_count,0)*8.0/1024.0 AS float),
                    page_count = ISNULL(ps.used_page_count,0),
                    refreshed_at = GETDATE()
                FROM insight.IdxCat_Index cat
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.objects o
                    ON o.name COLLATE DATABASE_DEFAULT = cat.table_name COLLATE DATABASE_DEFAULT
                   AND o.type = ''U''
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.schemas s
                    ON s.schema_id = o.schema_id
                   AND s.name COLLATE DATABASE_DEFAULT = cat.schema_name COLLATE DATABASE_DEFAULT
                INNER JOIN ' + QUOTENAME(@db) + N'.sys.indexes i
                    ON i.object_id = o.object_id AND i.index_id = cat.index_id
                LEFT JOIN ' + QUOTENAME(@db) + N'.sys.dm_db_index_usage_stats us
                    ON us.database_id = DB_ID(@db) AND us.object_id = i.object_id AND us.index_id = i.index_id
                LEFT JOIN (
                    SELECT object_id, index_id, SUM(used_page_count) AS used_page_count
                    FROM ' + QUOTENAME(@db) + N'.sys.dm_db_partition_stats
                    GROUP BY object_id, index_id
                ) ps ON ps.object_id = i.object_id AND ps.index_id = i.index_id
                WHERE cat.database_name = @db;';
                EXEC sp_executesql @sql, N'@db SYSNAME', @db=@db;
                SET @indexes += @@ROWCOUNT;
            END;

            FETCH NEXT FROM dbs INTO @db;
        END
        CLOSE dbs; DEALLOCATE dbs;

        UPDATE insight.IdxCat_RefreshLog
        SET finished_at = GETDATE(),
            status = 'ok',
            message = N'Completed',
            tables_upserted = @tables,
            indexes_upserted = @indexes,
            refresh_parts = @parts
        WHERE refresh_id = @refresh_id;
    END TRY
    BEGIN CATCH
        IF CURSOR_STATUS('local','dbs') >= 0
        BEGIN
            CLOSE dbs; DEALLOCATE dbs;
        END
        UPDATE insight.IdxCat_RefreshLog
        SET finished_at = GETDATE(),
            status = 'error',
            message = ERROR_MESSAGE(),
            refresh_parts = @parts
        WHERE refresh_id = @refresh_id;
        THROW;
    END CATCH
END
GO


IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'AgentGraph')
    CREATE USER [AgentGraph] FOR LOGIN [AgentGraph];
GO

GRANT SELECT ON insight.IdxCat_Table TO [AgentGraph];
GRANT SELECT ON insight.IdxCat_Index TO [AgentGraph];
GRANT SELECT ON insight.IdxCat_RefreshLog TO [AgentGraph];
GRANT EXECUTE ON insight.USP_Insight_IndexCatalog_Refresh TO [AgentGraph];
GO

EXEC insight.USP_Insight_IndexCatalog_Refresh
    @RefreshTables     = 1,
    @RefreshIndexDefs  = 1,
    @RefreshIndexStats = 1;
GO

SELECT TOP (5) refresh_id, started_at, finished_at, status, message,
       tables_upserted, indexes_upserted, refresh_parts
FROM insight.IdxCat_RefreshLog
ORDER BY refresh_id DESC;

SELECT COUNT(*) AS table_rows FROM insight.IdxCat_Table;
SELECT COUNT(*) AS index_rows FROM insight.IdxCat_Index;
GO
