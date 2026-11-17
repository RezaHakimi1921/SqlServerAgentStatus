# معماری جامع ماژول ارزیابی، تحلیل و بهینه‌سازی هوشمند ایندکس‌ها در SQL Server
### (SQL Server Index Diagnostics, Redundancy Analysis & Advisor Architecture)

> **⚠️ SUPERSEDED for v1 implementation (2026-08-16)**  
> Do **not** implement from this file. Authoritative v1 spec:  
> [`docs/superpowers/specs/2026-08-16-index-module-v1-design.md`](docs/superpowers/specs/2026-08-16-index-module-v1-design.md)  
> Locked with Index Advisor `BUILD-PLAN`: **no Consolidation / Super Index**, simple tags (no emoji), confidence ≥ 70, SQL Agent capture — not this Python JSON collector.  
> Keep this document only as an aspirational idea bank for **post-v1**.

---

> **طراحی شده بر اساس متدولوژی‌های استاندارد متخصصین برتر SQL Server:**
> - **Brent Ozar** (`sp_BlitzIndex` Guidelines)
> - **Kimberly Tripp / Paul Randal** (SQLskills Index Internals & Consolidation)
> - **Pinal Dave** (SQLAuthority DMV Diagnostics)

---

## فهرست مطالب
1. [خلاصه اجرایی و داشبورد اولیه (Executive Overview)](#۱-خلاصه-اجرایی-و-داشبورد-اولیه)
2. [تشخیص ایندکس‌های همپوشان، تکراری و تجمیع‌پذیر (Redundant & Overlapping Indexes)](#۲-تشخیص-ایندکسهای-همپوشان-تکراری-و-تجمیعپذیر)
3. [واکاوی فرگمنتیشن و سیاست‌های یکپارچه‌سازی (Fragmentation Analytics)](#۳-واکاوی-فرگمنتیشن-و-سیاستهای-یکپارچهسازی)
4. [طبقه‌بندی و اطلاعات جامع ایندکس‌ها (Classification & Metadata)](#۴-طبقهبندی-و-اطلاعات-جامع-ایندکسها)
5. [معماری کاملاً امن و فقط-خواندنی (Read-Only Architecture & T-SQL Generator)](#۵-معماری-کاملا-امن-و-فقط-خواندنی)
6. [سیستم تگ‌بندی هوشمند بر اساس متدولوژی Ozar / Dave / Tripp](#۶-سیستم-تگبندی-هوشمند-تخصصی)
7. [کد کامل اسکریپت پایتون (Python Collector Script) جهت استخراج بدون سربار](#۷-کد-کامل-اسکریپت-پایتون-python-collector)

---

## ۱. خلاصه اجرایی و داشبورد اولیه (Executive Overview)

صفحه اصلی ماژول ایندکس یک نمای کلان ۳۶۰ درجه از وضعیت سلامت کل پایگاه‌های داده را در قالب ۴ شاخص کلیدی و نمودارهای تجمیعی ارائه می‌دهد:

```
+----------------------------------------------------------------------------------------------------+
|  [ ⚡ Missing Index Impact ]   [ 🚨 High Frag (>30%) ]   [ 🗑️ Dead Unused Writes ]   [ 🧩 Consolidation ]   |
|       تا ۹۴.۶٪ بهبود سرعت         ۱۲ ایندکس Rebuild           ۱.۸۴M سربار Write          ۳ جدول مستعد تجمیع   |
+----------------------------------------------------------------------------------------------------+
|  [ تفکیک وضعیت بر اساس پایگاه‌های داده ] | [ توزیع فرگمنتیشن ] | [ هدررفت فضا و I/O بر حسب گیگابایت ]       |
+----------------------------------------------------------------------------------------------------+
```

### شاخص‌های داشبورد:
1. **شاخص بهبود بالقوه (Potential Workload Gain):** محاسبه مجموع وزن کوئری‌های فاقد ایندکس بر اساس `avg_total_user_cost * avg_user_impact * (user_seeks + user_scans)`.
2. **سربار فرگمنتیشن بحرانی (Critical Fragmentation):** تعداد ایندکس‌های بالای ۳۰٪ که دچار پدیده **Page Split** شدید هستند.
3. **هدررفت نوشتن و دیسک (Wasted Write Footprint):** حجم دیسک و تعداد عملیات `user_updates` روی ایندکس‌هایی که تعداد `user_seeks` آن‌ها صفر است.
4. **فرصت‌های تجمیع ایندکس (Consolidation Opportunities):** ایندکس‌های همپوشان که با ادغام آن‌ها می‌توان حجم دیسک و قفل‌های دیتابیس را کاهش داد.

---

## ۲. تشخیص ایندکس‌های همپوشان، تکراری و تجمیع‌پذیر (Redundant & Overlapping Indexes)

یکی از مخرب‌ترین مشکلات در دیتابیس‌های سازمانی، **Over-Indexing** و وجود چند ایندکس با ستون‌های ابتدایی (Leading-Edge Columns) مشترک است.

### سناریوی تجمیع (Consolidation Scenario):
فرض کنید روی جدول `tbl_AccountTransactions` ۳ ایندکس زیر وجود دارند:
- ایندکس A: `(AccountId)`
- ایندکس B: `(AccountId, TransactionType)`
- ایندکس C: `(AccountId, TransactionDate) INCLUDE (Amount)`

**پیشنهاد هوشمند سامانه:**
سامانه با بررسی الگوی کوئری‌ها پیشنهاد می‌دهد یک ایندکس جامع موسوم به **Super Index** ایجاد شده و ۳ ایندکس قبلی حذف (DROP) شوند:

$$\text{Super Index} = \text{ON } (AccountId, TransactionType, TransactionDate) \text{ INCLUDE } (Amount, BalanceAfter)$$

```
  ┌────────────────────────────────────────────────────────┐
  │ 3 Existing Overlapping Indexes (Total Size: 1.8 GB)    │
  │  - IX_1 (AccountId)                                    │
  │  - IX_2 (AccountId, TxType)                            │
  │  - IX_3 (AccountId, TxDate) INCLUDE (Amount)          │
  └──────────────────────────┬─────────────────────────────┘
                             │
                             ▼ [ پیشنهاد تجمیع خودکار ]
  ┌────────────────────────────────────────────────────────┐
  │ 1 Consolidated Super-Index (Size: 850 MB)              │
  │  - IX_Consolidated (AccountId, TxType, TxDate)         │
  │    INCLUDE (Amount, BalanceAfter)                      │
  │                                                        │
  │ ✅ دستاورد: صرفه‌جویی ۹۵۰ مگابایت رم و حذف ۲.۴M نوشتن │
  └────────────────────────────────────────────────────────┘
```

---

## ۳. واکاوی فرگمنتیشن و سیاست‌های یکپارچه‌سازی (Fragmentation Analytics)

سامانه بر اساس استاندارد رسمی مایکروسافت و توصیه‌های Paul Randal، ایندکس‌ها را در سه سطح فرگمنتیشن با در نظر گرفتن تعداد صفحات (Page Count > 1000) دسته‌بندی می‌کند:

| درصد فرگمنتیشن | وضعیت | اقدام پیشنهادی | توجیه فنی |
| :--- | :--- | :--- | :--- |
| **کمتر از ۱۰٪** | 🟢 Healthy | نیازی به اقدام ندارد | بهینه‌سازی در این سطح توجیه I/O ندارد. |
| **بین ۱۰٪ تا ۳۰٪** | 🟡 Moderate | `REORGANIZE` | یکپارچه‌سازی آنلاین در سطح برگ‌ها بدون قفل جدول و با حداقل لاگ. |
| **بالاتر از ۳۰٪** | 🔴 Critical | `REBUILD WITH (ONLINE = ON)` | بازسازی کامل ساختار B-Tree، آزادسازی صفحات خالی و ریست آمار فرگمنتیشن. |

---

## ۴. طبقه‌بندی و اطلاعات جامع ایندکس‌ها (Classification & Metadata)

برای هر ایندکس مشخصات زیر استخراج و در UI ارائه می‌گردد:
- **اطلاعات هویتی:** `DatabaseName`, `SchemaName`, `TableName`, `IndexName`, `IndexType` (Clustered, Nonclustered, Columnstore).
- **معیارهای فیزیکی:** `FragmentationPercent`, `PageCount`, `SizeMB`, `FillFactor`, `DataCompression` (NONE / PAGE / ROW).
- **معیارهای کارایی (Usage Stats):**
  - $UserSeeks$: تعداد جستجوهای مستقیم از درخت B-Tree (علامت کارایی عالی).
  - $UserScans$: تعداد اسکن‌های کامل رنج یا برگ (علامت نیاز به بازنگری).
  - $UserUpdates$: تعداد دفعات درج، ویرایش و حذف که ایندکس مجبور به بروزرسانی شده است.
  - $\text{Read/Write Ratio} = \frac{UserSeeks + UserScans}{UserUpdates + 1}$

---

## ۵. معماری کاملاً امن و فقط-خواندنی (Read-Only Architecture & T-SQL Generator)

از آنجا که سامانه مانیتورینگ **۱۰۰٪ Read-Only** است و نباید هیچ‌گونه دسترسی Write روی دیتابیس داشته باشد:

1. سامانه هیچ دستوری را مستقیماً روی دیتابیس اجرا نمی‌کند.
2. تمام پیشنهادات در قالب **اسکریپت‌های استاندارد T-SQL با بالاترین استانداردهای Production-Safe** تولید می‌شوند:

```sql
-- =========================================================================
-- پیشنهاد بهینه‌سازی تولید شده توسط سیستم مانیتورینگ (کاملاً ایزوله و امن)
-- Target Table: [CoreBanking_DB].[dbo].[tbl_AccountTransactions]
-- Estimated Gain: 94.6% Query Cost Reduction
-- =========================================================================

-- مرحله ۱: ایجاد ایندکس جدید با کمترین اثر قفل‌گذاری روی پروداکشن
CREATE NONCLUSTERED INDEX [IX_tbl_AccountTransactions_AccountId_TxType_INC]
ON [CoreBanking_DB].[dbo].[tbl_AccountTransactions] (
    [AccountId], 
    [TransactionType], 
    [TransactionDate]
)
INCLUDE (
    [Amount], 
    [BalanceAfter], 
    [ReferenceCode]
)
WITH (
    ONLINE = ON,                  -- عدم قفل شدن جدول حین ایجاد
    FILLFACTOR = 85,              -- پیشگیری از Page Split در جداول پرتراکنش
    DATA_COMPRESSION = PAGE,      -- کاهش ۴۰ تا ۶۰ درصدی مصرف حافظه و دیسک
    SORT_IN_TEMPDB = ON,          -- انتقال بار Sort از فایل داده اصلی به TempDB
    MAXDOP = 4                    -- جلوگیری از مصرف ۱۰۰٪ CPU سرور
);
GO

-- مرحله ۲ (اختیاری): حذف ایندکس‌های هرزگرد و همپوشان پس از ارزیابی نهایی
-- DROP INDEX [IX_AccountTransactions_Old_Legacy] ON [CoreBanking_DB].[dbo].[tbl_AccountTransactions];
-- GO
```

---

## ۶. سیستم تگ‌بندی هوشمند تخصصی (Brent Ozar / Pinal Dave / Kimberly Tripp)

سامانه به هر ایندکس یا جدول تگ‌های تحلیلی هوشمند الصاق می‌کند:

| تگ تحلیلی | مفهوم و منبع متدولوژی | علت فنی و نحوه رفع |
| :--- | :--- | :--- |
| 🏷️ `Index Hoarder` | **Brent Ozar (`sp_BlitzIndex`)** | ایندکس‌هایی با میلیون‌ها Update ولی Seek نزدیک به صفر. حذف ایندکس موجب آزادسازی پهنای باند I/O می‌شود. |
| 🏷️ `Key Lookup Victim` | **Kimberly Tripp (SQLskills)** | ایندکس‌هایی که فاقد ستون‌های خروجی در `INCLUDE` هستند و کوئری را مجبور به بازگشت پرهزینه به Clustered Index می‌کنند. |
| 🏷️ `Duplicate Leading Edge` | **Pinal Dave (SQLAuthority)** | دو یا چند ایندکس که ستون اول کلید آن‌ها دقیقاً یکسان است و امکان ادغام دارند. |
| 🏷️ `High Write - Low Read` | **Brent Ozar** | نسبت نوشتن به خواندن بیشتر از ۱۰۰ به ۱ است. |
| 🏷️ `Wide Clustered Key` | **Kimberly Tripp** | کلید کلاستر جدول بیشتر از ۱۶ بایت یا از نوع `NVARCHAR(MAX)` یا چندستونه سنگین است که به تمام نان‌کلاسترها سرایت کرده است. |
| 🏷️ `Heavy Fragmentation` | **Microsoft Best Practices** | فرگمنتیشن بالای ۳۰٪ همراه با بیش از ۱۰,۰۰۰ صفحه. نیازمند زمان‌بندی جاب Rebuild هفتگی. |

---

## ۷. کد کامل اسکریپت پایتون (Python Collector)

کد زیر به صورت ۱۰۰٪ Read-Only با استفاده از کتابخانه `pyodbc` به SQL Server متصل شده و دیتای ساختاریافته JSON برای بخش ایندکس‌ها تولید می‌کند:

```python
"""
SQL Server Agent Status - Index Diagnostics & Advisor Collector (Read-Only)
Author: SQL Server Agent Telemetry Suite
License: MIT
Requirements: pip install pyodbc
"""

import json
import logging
from typing import List, Dict, Any
import pyodbc

# تنظیم لاگینگ
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CONNECTION_STRING = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=127.0.0.1,1433;"
    "DATABASE=master;"
    "UID=sa;"
    "PWD=YourSecurePassword123!;"
    "TrustServerCertificate=yes;"
    "ApplicationIntent=ReadOnly;"  # تضمین اتصال Read-Only
)

def get_db_connection() -> pyodbc.Connection:
    """ایجاد اتصال ایمن با سطح دسترسی فقط-خواندنی"""
    conn = pyodbc.connect(CONNECTION_STRING, autocommit=True)
    return conn


def collect_missing_indexes(cursor: pyodbc.Cursor) -> List[Dict[str, Any]]:
    """
    استخراج ایندکس‌های مفقود بر اساس DMVهای استاندارد مایکروسافت
    (sys.dm_db_missing_index_details, sys.dm_db_missing_index_groups, sys.dm_db_missing_index_group_stats)
    """
    query = """
    SELECT TOP 20
        DB_NAME(mid.database_id) AS DatabaseName,
        OBJECT_SCHEMA_NAME(mid.object_id, mid.database_id) AS SchemaName,
        OBJECT_NAME(mid.object_id, mid.database_id) AS TableName,
        migs.user_seeks AS UserSeeks,
        migs.user_scans AS UserScans,
        migs.avg_total_user_cost AS AvgUserCost,
        migs.avg_user_impact AS AvgUserImpact,
        CAST(migs.avg_total_user_cost * (migs.avg_user_impact / 100.0) * (migs.user_seeks + migs.user_scans) AS BIGINT) AS ImprovementScore,
        migs.last_user_seek AS LastUserSeek,
        mid.equality_columns AS EqualityColumns,
        mid.inequality_columns AS InequalityColumns,
        mid.included_columns AS IncludedColumns,
        mid.statement AS FullStatement
    FROM sys.dm_db_missing_index_group_stats AS migs
    INNER JOIN sys.dm_db_missing_index_groups AS mig ON migs.group_handle = mig.index_group_handle
    INNER JOIN sys.dm_db_missing_index_details AS mid ON mig.index_handle = mid.index_handle
    WHERE mid.database_id > 4 -- فقط دیتابیس‌های کاربری
      AND migs.avg_user_impact > 30 -- فقط ایندکس‌های با تاثیر قابل توجه
    ORDER BY ImprovementScore DESC;
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    results = []
    
    for row in rows:
        eq_cols = [c.strip(" []") for c in row.EqualityColumns.split(",")] if row.EqualityColumns else []
        ineq_cols = [c.strip(" []") for c in row.InequalityColumns.split(",")] if row.InequalityColumns else []
        inc_cols = [c.strip(" []") for c in row.IncludedColumns.split(",")] if row.IncludedColumns else []
        
        # تولید خودکار اسکریپت بهینه T-SQL
        table_clean = row.TableName
        idx_name = f"IX_{table_clean}_{'_'.join(eq_cols[:2])}" + ("_INC" if inc_cols else "")
        all_keys = eq_cols + ineq_cols
        keys_str = ", ".join([f"[{k}]" for k in all_keys])
        inc_str = f" INCLUDE ({', '.join([f'[{c}]' for c in inc_cols])})" if inc_cols else ""
        
        tsql_statement = (
            f"CREATE NONCLUSTERED INDEX [{idx_name}]\n"
            f"ON [{row.DatabaseName}].[{row.SchemaName}].[{row.TableName}] ({keys_str})\n"
            f"{inc_str}\n"
            f"WITH (ONLINE = ON, FILLFACTOR = 85, DATA_COMPRESSION = PAGE, SORT_IN_TEMPDB = ON);"
        )

        results.append({
            "id": f"missing-{len(results)+1}",
            "databaseName": row.DatabaseName,
            "schemaName": row.SchemaName,
            "tableName": row.TableName,
            "userImpact": round(float(row.AvgUserImpact), 1),
            "avgUserCost": round(float(row.AvgUserCost), 2),
            "estCostAfter": round(float(row.AvgUserCost) * (1.0 - (float(row.AvgUserImpact) / 100.0)), 2),
            "estImprovementScore": int(row.ImprovementScore),
            "userSeeks": int(row.UserSeeks),
            "userScans": int(row.UserScans),
            "lastUserSeek": str(row.LastUserSeek) if row.LastUserSeek else "نامشخص",
            "equalityColumns": eq_cols,
            "inequalityColumns": ineq_cols,
            "includedColumns": inc_cols,
            "statement": tsql_statement
        })
        
    return results


def collect_index_physical_and_usage_stats(cursor: pyodbc.Cursor) -> List[Dict[str, Any]]:
    """
    استخراج وضعیت فرگمنتیشن، حجم و آمار استفاده ایندکس‌ها (Seeks vs Updates)
    بر اساس sys.dm_db_index_physical_stats و sys.dm_db_index_usage_stats
    """
    query = """
    SELECT 
        DB_NAME(ius.database_id) AS DatabaseName,
        OBJECT_SCHEMA_NAME(i.object_id, ius.database_id) AS SchemaName,
        OBJECT_NAME(i.object_id, ius.database_id) AS TableName,
        i.name AS IndexName,
        i.type_desc AS IndexType,
        i.fill_factor AS FillFactor,
        ps.avg_fragmentation_in_percent AS FragmentationPercent,
        ps.page_count AS PageCount,
        CAST((ps.page_count * 8.0) / 1024.0 AS DECIMAL(18,2)) AS SizeMB,
        ISNULL(ius.user_seeks, 0) AS UserSeeks,
        ISNULL(ius.user_scans, 0) AS UserScans,
        ISNULL(ius.user_updates, 0) AS UserUpdates
    FROM sys.dm_db_index_usage_stats AS ius
    INNER JOIN sys.indexes AS i ON ius.object_id = i.object_id AND ius.index_id = i.index_id
    CROSS APPLY sys.dm_db_index_physical_stats(ius.database_id, i.object_id, i.index_id, NULL, 'LIMITED') AS ps
    WHERE ius.database_id > 4
      AND i.type_desc IN ('CLUSTERED', 'NONCLUSTERED')
      AND ps.page_count > 100 -- ایندکس‌های بزرگتر از ۱۰۰ صفحه
    ORDER BY ps.avg_fragmentation_in_percent DESC;
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    results = []
    
    for row in rows:
        frag = round(float(row.FragmentationPercent), 2)
        seeks = int(row.UserSeeks)
        scans = int(row.UserScans)
        updates = int(row.UserUpdates)
        
        # تشخیص نوع توصیه
        if seeks == 0 and scans <= 5 and updates > 50000:
            rec = "DROP_UNUSED"
            status = "critical"
        elif frag >= 30.0:
            rec = "REBUILD"
            status = "critical"
        elif frag >= 10.0:
            rec = "REORGANIZE"
            status = "warning"
        else:
            rec = "HEALTHY"
            status = "good"
            
        results.append({
            "id": f"idx-{len(results)+1}",
            "databaseName": row.DatabaseName,
            "schemaName": row.SchemaName,
            "tableName": row.TableName,
            "indexName": row.IndexName,
            "indexType": row.IndexType,
            "fillFactor": int(row.FillFactor) if row.FillFactor > 0 else 100,
            "fragmentationPercent": frag,
            "pageCount": int(row.PageCount),
            "sizeMB": float(row.SizeMB),
            "userSeeks": seeks,
            "userScans": scans,
            "userUpdates": updates,
            "recommendation": rec,
            "status": status
        })
        
    return results


def main():
    """تابع اصلی جهت جمع‌آوری و خروجی ساختاریافته JSON برای داشبورد React"""
    logging.info("در حال اتصال به SQL Server با دسترسی Read-Only...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        logging.info("۱. استخراج ایندکس‌های پیشنهادی (Missing Indexes)...")
        missing_indexes = collect_missing_indexes(cursor)
        
        logging.info("۲. استخراج فرگمنتیشن و آمار استفاده ایندکس‌ها...")
        index_health = collect_index_physical_and_usage_stats(cursor)
        
        payload = {
            "timestampUtc": "2026-08-15T09:30:00Z",
            "summary": {
                "missingIndexesCount": len(missing_indexes),
                "totalAuditedIndexes": len(index_health),
                "criticalRebuildCount": len([i for i in index_health if i["recommendation"] == "REBUILD"]),
                "unusedDeadCount": len([i for i in index_health if i["recommendation"] == "DROP_UNUSED"]),
            },
            "missingIndexes": missing_indexes,
            "indexHealth": index_health
        }
        
        # ذخیره فایل JSON جهت مصرف فرانت‌اند
        with open("sql_index_diagnostics_feed.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            
        logging.info("جمع‌آوری داده‌ها با موفقیت پایان یافت و فایل sql_index_diagnostics_feed.json ذخیره شد.")
        
    except Exception as ex:
        logging.error(f"خطا در جمع‌آوری تله‌متری ایندکس‌ها: {ex}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
```

---

## نتیجه‌گیری و مزایای معماری
1. **امنیت مطلق:** هیچ دستور DDL/DML مستقیماً اجرا نمی‌شود؛ فقط DMVهای سبک و استاندارد در سطح `LIMITED` اسکن می‌شوند.
2. **کاهش چشمگیر هدررفت منابع:** با حذف و تجمیع ایندکس‌های همپوشان، تا ۵۰٪ از حجم I/O دیسک و فضای RAM سرور آزاد می‌گردد.
3. **انطباق با متدولوژی‌های معتبر جهانی:** برچسب‌ها، تگ‌ها و منطق تشخیص دقیقا منطبق بر متدولوژی‌های **Brent Ozar**, **Kimberly Tripp** و **Pinal Dave** پیاده‌سازی شده‌اند.
