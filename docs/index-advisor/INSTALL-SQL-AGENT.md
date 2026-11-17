# Index Advisor — نصب Capture روی سرور (نه روی ویندوز شما)

کپی هم‌تراز با محصول:
`E:\SqlserverAgentProject\SqlServerAgentStatus\docs\index-advisor\INSTALL-SQL-AGENT.md`

## جواب کوتاه

| روش | کجا اجرا می‌شود؟ | اگر لپ‌تاپ خاموش باشد؟ |
|-----|------------------|-------------------------|
| Task ویندوز (`SqlMonitor_IndexAdvisor_Hourly`) | PC شما | **Capture نمی‌شود** ❌ |
| **SQL Agent روی سرور** | همان SQL Server | **Capture می‌شود** ✅ |

برای rebuild شبانه (~01:00) باید Job روی **سرور** باشد. Task ویندوز را حذف کنید:

```bat
schtasks /Delete /TN "SqlMonitor_IndexAdvisor_Hourly" /F
```

## فایل‌های اجرا (در ریپوی SmartMonitor)

0. `scripts/sql/SqlMonitor_IndexAdvisor_Phase0.sql` → جداول `insight.*` (+ gap-fix Status=Running)
1. `scripts/sql/SqlMonitor_IndexAdvisor_Capture.sql` → `insight.USP_IndexAdvisor_Capture`
2. `scripts/sql/SqlMonitor_IndexAdvisor_Jobs.sql` → Hourly + PreRebuild (23:30)

## بررسی بعد از نصب

```sql
SELECT TOP 5 * FROM insight.CollectionBatch ORDER BY StartedAtUtc DESC;
SELECT COUNT(*) FROM insight.IndexSnapshot;
SELECT name, enabled FROM msdb.dbo.sysjobs WHERE name LIKE N'SqlMonitor_IndexAdvisor%';
```
