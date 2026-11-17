/*
  SqlMonitor Object Size History (Tables & Growth)
  -----------------------------------------------
  Schema: insight (sibling to IdxCat_* — not a unified Object Catalog)

  Creates:
    insight.ObjSize_History
    insight.USP_Insight_ObjSize_Capture

  Capture ALWAYS reads live sys.partitions / dm_db_partition_stats.
  Do NOT copy insight.IdxCat_Table — catalog row_count/size_mb can be stale
  (refreshed on a different schedule), which made daily history wrong after DELETE/INSERT.
  Install in MONITOR_DATABASE / SmartMonitorDB. Soft-fail in the app if missing.
*/

SET NOCOUNT ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'insight')
    EXEC(N'CREATE SCHEMA insight');
GO

IF OBJECT_ID(N'insight.ObjSize_History', N'U') IS NULL
BEGIN
    CREATE TABLE insight.ObjSize_History (
        captured_date  DATE NOT NULL,
        database_name  SYSNAME NOT NULL,
        schema_name    SYSNAME NOT NULL,
        table_name     SYSNAME NOT NULL,
        row_count      BIGINT NULL,
        size_mb        FLOAT NULL,
        is_heap        BIT NOT NULL
            CONSTRAINT DF_insight_ObjSize_History_heap DEFAULT (0),
        source         VARCHAR(20) NOT NULL,
        captured_at    DATETIME2(0) NOT NULL
            CONSTRAINT DF_insight_ObjSize_History_at DEFAULT (GETDATE()),
        CONSTRAINT PK_insight_ObjSize_History PRIMARY KEY
            (captured_date, database_name, schema_name, table_name)
    );
    CREATE INDEX IX_insight_ObjSize_History_db_size
        ON insight.ObjSize_History (captured_date, database_name, size_mb DESC);
END
GO

CREATE OR ALTER PROCEDURE insight.USP_Insight_ObjSize_Capture
    @RetentionDays INT = 30  -- keep ~1 month of daily snapshots; older rows deleted each run
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @today DATE = CAST(GETDATE() AS DATE);
    DECLARE @now DATETIME2(0) = GETDATE();
    DECLARE @source VARCHAR(20) = 'live';
    DECLARE @rows INT = 0;
    DECLARE @db SYSNAME;
    DECLARE @sql NVARCHAR(MAX);

    IF ISNULL(@RetentionDays, 0) < 1
        SET @RetentionDays = 30;

    DELETE FROM insight.ObjSize_History WHERE captured_date = @today;

    /* Always live — IdxCat_Table is a UI cache and may lag DELETEs/INSERTs. */
    DECLARE dbs CURSOR LOCAL FAST_FORWARD FOR
    SELECT d.name
    FROM sys.databases d
    WHERE d.state = 0
      AND d.database_id > 4
      AND HAS_DBACCESS(d.name) = 1;

    OPEN dbs;
    FETCH NEXT FROM dbs INTO @db;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @sql = N'
        INSERT INTO insight.ObjSize_History (
            captured_date, database_name, schema_name, table_name,
            row_count, size_mb, is_heap, source, captured_at
        )
        SELECT
            @today,
            @db,
            s.name COLLATE DATABASE_DEFAULT,
            t.name COLLATE DATABASE_DEFAULT,
            (SELECT SUM(p.rows) FROM ' + QUOTENAME(@db) + N'.sys.partitions p
             WHERE p.object_id = t.object_id AND p.index_id IN (0,1)),
            CAST((
                SELECT SUM(ps.used_page_count) * 8.0 / 1024.0
                FROM ' + QUOTENAME(@db) + N'.sys.dm_db_partition_stats ps
                WHERE ps.object_id = t.object_id
            ) AS float),
            CASE WHEN EXISTS (
                SELECT 1 FROM ' + QUOTENAME(@db) + N'.sys.indexes i
                WHERE i.object_id = t.object_id AND i.index_id = 0
            ) AND NOT EXISTS (
                SELECT 1 FROM ' + QUOTENAME(@db) + N'.sys.indexes i
                WHERE i.object_id = t.object_id AND i.index_id = 1
            ) THEN 1 ELSE 0 END,
            @source,
            @now
        FROM ' + QUOTENAME(@db) + N'.sys.tables t
        INNER JOIN ' + QUOTENAME(@db) + N'.sys.schemas s ON s.schema_id = t.schema_id
        WHERE t.is_ms_shipped = 0;';

        BEGIN TRY
            EXEC sp_executesql
                @sql,
                N'@today DATE, @db SYSNAME, @source VARCHAR(20), @now DATETIME2(0)',
                @today=@today, @db=@db, @source=@source, @now=@now;
            SET @rows += @@ROWCOUNT;
        END TRY
        BEGIN CATCH
            -- Skip inaccessible / permission-denied DBs; continue others
        END CATCH;

        FETCH NEXT FROM dbs INTO @db;
    END
    CLOSE dbs;
    DEALLOCATE dbs;

    DELETE FROM insight.ObjSize_History
    WHERE captured_date < DATEADD(day, -@RetentionDays, @today);

    SELECT
        @rows AS rows_captured,
        @source AS source,
        @today AS captured_date,
        @RetentionDays AS retention_days;
END
GO

/*
  Permissions for the app login (replace AgentGraph with your MONITOR / app user).
  Error 229 "EXECUTE permission was denied" means the proc exists but GRANT is missing.
*/
-- GRANT SELECT, INSERT, DELETE ON insight.ObjSize_History TO [AgentGraph];
-- GRANT EXECUTE ON insight.USP_Insight_ObjSize_Capture TO [AgentGraph];
-- GRANT SELECT ON insight.IdxCat_Table TO [AgentGraph];
GO
