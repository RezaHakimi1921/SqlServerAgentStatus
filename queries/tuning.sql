--===== میزان فضاهای اشغال شده توسط یک جدول=====--
/*

exec sys.sp_spaceused unified_customers

*/
--====بررسی وضعیت سلامت ایندکس های یک جدول در یک دیتابس =====--
/*

SELECT
	page_count,*
FROM sys.dm_db_index_physical_stats(
DB_ID('archivedb'),
OBJECT_ID('customersmslog'),
NULL,
NULL,
NULL
)
order by index_id

*/
--======بررسی با جزئیات بیشتر ایندکس ها fragmentations======--
/*


-- کوئری کامل برای نمایش همه ایندکس‌های جدول (Clustered, Nonclustered, Heap)

SELECT 
    ps.page_count,
    ps.index_depth,
    ps.avg_fragmentation_in_percent,
    ps.index_id,
    ps.index_type_desc,
    i.name AS index_name,
    i.type_desc AS index_type,
    -- محاسبه اندازه به MB
    CAST((ps.page_count * 8.0 / 1024) AS DECIMAL(10,2)) AS size_in_mb,
    -- محاسبه اندازه به Page
    ps.page_count AS size_in_pages,
    STUFF((
        SELECT ', ' + c.name + ' ' + 
               CASE WHEN ic.is_descending_key = 1 THEN 'DESC' ELSE 'ASC' END
        FROM sys.index_columns ic
        INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE ic.object_id = i.object_id 
          AND ic.index_id = i.index_id 
          AND ic.is_included_column = 0
        ORDER BY ic.key_ordinal
        FOR XML PATH('')
    ), 1, 2, '') AS index_key_columns,
    STUFF((
        SELECT ', ' + c.name 
        FROM sys.index_columns ic
        INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE ic.object_id = i.object_id 
          AND ic.index_id = i.index_id 
          AND ic.is_included_column = 1
        ORDER BY ic.index_column_id
        FOR XML PATH('')
    ), 1, 2, '') AS included_columns,
    CASE WHEN i.type = 0 THEN 'Heap' 
         WHEN i.type = 1 THEN 'Clustered' 
         WHEN i.type = 2 THEN 'Nonclustered' 
         WHEN i.type = 3 THEN 'XML'
         WHEN i.type = 4 THEN 'Spatial'
         WHEN i.type = 5 THEN 'Columnstore Clustered'
         WHEN i.type = 6 THEN 'Columnstore Nonclustered'
         ELSE 'Other'
    END AS index_category,
    -- وضعیت Fragmentation
    CASE 
        WHEN ps.avg_fragmentation_in_percent < 5 THEN 'Low Fragmentation'
        WHEN ps.avg_fragmentation_in_percent BETWEEN 5 AND 30 THEN 'Medium Fragmentation'
        WHEN ps.avg_fragmentation_in_percent > 30 THEN 'High Fragmentation - Rebuild Recommended'
        ELSE 'N/A'
    END AS fragmentation_status,
    i.is_unique,
    i.is_primary_key,
    i.is_disabled,
    i.fill_factor
FROM sys.dm_db_index_physical_stats(
    DB_ID('adventureworks2022'),
    OBJECT_ID('Production.TestProduct'),
    NULL,
    NULL,
    'DETAILED'  -- برای اطلاعات کامل‌تر
) ps
INNER JOIN sys.indexes i ON ps.object_id = i.object_id AND ps.index_id = i.index_id
ORDER BY ps.index_id, ps.index_depth DESC;

*/

--وضعیت ایندکس ها 
/*
exec sp_helpindex production.Product
*/

-- وضعیت صفحات داده 
/*


SELECT
	s.page_type_desc
   ,s.allocated_page_page_id
   ,s.allocated_page_iam_page_id
   ,s.next_page_page_id
   ,s.previous_page_page_id
   ,s.is_iam_page
   ,s.is_allocated
FROM sys.dm_db_database_page_allocations
(
DB_ID('AdventureWorks2022'),     
OBJECT_ID('Production.Product'),  
NULL,                         
NULL,                           
'DETAILED'                        
) AS s;

*/

--دیتا فایل های یک دیتابیس
/*
use DB
exec sp_helpfile
*/



/*

--بررسی سطح برگ در زمان آپدیت و 
SELECT o.name AS TableName,i.name AS IndexName, op.leaf_insert_count,leaf_update_count,leaf_ghost_count ,nonleaf_insert_count,nonleaf_update_count 
FROM sys.dm_db_index_operational_stats(db_id('AdventureWorks2022'),object_id('SalesOrderDetail2'),null,null) op
JOIN sys.objects o ON o.object_id=op.object_id
JOIN sys.indexes i ON i.object_id=o.object_id AND i.index_id=op.index_id


*/

--======Read & write Of index In DB
/*

DECLARE @dbid INT
DECLARE @Drop_DDL NVARCHAR(MAX)
SET @Drop_DDL=''
    SELECT @dbid = db_id()

;WITH tmp AS (
    SELECT 'Table Name' = object_name(s.object_id), 'Index Name' =i.name, i.index_id,
           'Total Writes' =  user_updates, 
           'Total Reads' = user_seeks + user_scans + user_lookups+system_scans+system_lookups+system_seeks,
           'DROP INDEX '+i.name +' ON '+object_name(s.object_id) AS Drop_DDL,
           (SELECT MAX(LastReadTime) FROM (SELECT last_user_lookup AS LastReadTime UNION ALL SELECT last_user_seek UNION ALL SELECT last_user_scan UNION ALL 
			SELECT last_system_lookup UNION ALL	SELECT last_system_scan UNION ALL SELECT last_system_seek) x) AS LastAnyReadTime,
			last_user_lookup ,last_user_seek,last_user_scan,last_system_lookup,last_system_scan,last_system_seek
           
    FROM sys.dm_db_index_usage_stats AS s 
    INNER JOIN sys.indexes AS i
    ON s.object_id = i.object_id
    AND i.index_id = s.index_id
    WHERE objectproperty(s.object_id,'IsUserTable') = 1
    AND s.database_id = @dbid
    AND user_seeks + user_scans + user_lookups<500
    AND i.type_desc<>'CLUSTERED' 
    AND i.type_desc<>'HEAP'
    AND i.is_unique=0
    AND user_updates > (user_seeks + user_scans + user_lookups)
    AND (user_seeks + user_scans + user_lookups+system_scans+system_lookups+system_seeks)<user_updates--/50--the read is less than 1/50 of writes
    )
    SELECT * FROM tmp
    ORDER BY  'Total Writes' DESC, 'Total Reads' ASC;

	TotalWrite : درخت ایندکس چند بار تغییر کرده

*/


/*

SELECT mig.index_group_handle,mid.index_handle,migs.avg_total_user_cost AS AvgTotalUserCostThatCouldbeReduced,
       migs.avg_user_impact AS AvgPercentageBenefit,'CREATE INDEX missing_index_' + CONVERT (varchar, mig.index_group_handle)      
       + '_' + CONVERT (varchar, mid.index_handle)+ ' ON ' + mid.statement           
       + ' (' + ISNULL (mid.equality_columns,'')+ 
       CASE WHEN mid.equality_columns IS NOT NULL AND mid.inequality_columns             
       IS NOT NULL THEN ',' ELSE ''        
       END               
       + ISNULL (mid.inequality_columns, '') + ')' + 
       ISNULL (' INCLUDE (' + mid.included_columns + ')', '') AS create_index_statement   
       FROM sys.dm_db_missing_index_groups mig 
       INNER JOIN sys.dm_db_missing_index_group_stats migs ON migs.group_handle = mig.index_group_handle 
       INNER JOIN sys.dm_db_missing_index_details mid ON mig.index_handle = mid.index_handle
GO

*/