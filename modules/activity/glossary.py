"""Short Persian tips for Status / Command / Wait."""
from __future__ import annotations

STATUS_TIPS = {
    "running": "در حال اجرای دستور روی CPU است.",
    "runnable": "آماده اجراست و منتظر نوبت CPU می‌ماند.",
    "suspended": "اجرا متوقف شده و منتظر یک منبع است (مثلاً قفل، IO، یا WAITFOR).",
    "sleeping": "اتصال باز است ولی الان دستوری اجرا نمی‌کند.",
    "dormant": "نشست غیرفعال/خوابیده؛ معمولاً مهم نیست مگر باز بماند.",
    "preconnect": "در حال برقراری اتصال اولیه است.",
    "blocked": "توسط نشست دیگری بلاک شده و منتظر آزاد شدن منبع است.",
}

COMMAND_TIPS = {
    "SELECT": "در حال خواندن داده است.",
    "INSERT": "در حال درج ردیف است.",
    "UPDATE": "در حال به‌روزرسانی داده است.",
    "DELETE": "در حال حذف ردیف است.",
    "MERGE": "ادغام Insert/Update/Delete در یک دستور.",
    "EXECUTE": "در حال اجرای Stored Procedure یا دستور پویا است.",
    "WAITFOR": "عمداً منتظر مانده (تأخیر زمان‌بندی‌شده) — اغلب Job یا polling.",
    "BACKUP": "پشتیبان‌گیری از دیتابیس در جریان است.",
    "RESTORE": "بازیابی دیتابیس در جریان است.",
    "DBCC": "دستور بررسی/تعمیر دیتابیس (DBCC).",
    "ALTER": "در حال تغییر ساختار آبجکت.",
    "CREATE": "در حال ساخت آبجکت جدید است (جدول، ایندکس، …).",
    "CREATE INDEX": "در حال ایجاد ایندکس روی جدول است — ONLINE/MAXDOP را در WITH ببین.",
    "INDEX REBUILD": "بازسازی ایندکس (REBUILD) — معمولاً گران‌تر از REORGANIZE.",
    "INDEX REORGANIZE": "بازآرایی برگ‌های ایندکس (REORGANIZE) — سبک‌تر از REBUILD.",
    "DROP INDEX": "در حال حذف ایندکس است.",
    "DROP": "در حال حذف آبجکت است.",
    "TRUNCATE": "خالی‌کردن سریع جدول.",
    "SELECT INTO": "ساخت جدول جدید از نتیجه SELECT.",
    "BULK INSERT": "بارگذاری انبوه داده.",
    "UPDATE STATISTICS": "به‌روزرسانی آمار بهینه‌ساز.",
    "AWAITING COMMAND": "نشست منتظر دستور بعدی از کلاینت است.",
    "SLEEPING": "بدون درخواست فعال.",
}

WAIT_TIPS = {
    "LCK_M_S": "منتظر قفل Shared (خواندن) — معمولاً بلاک توسط writer.",
    "LCK_M_X": "منتظر قفل Exclusive (نوشتن) — بلاکینگ جدی.",
    "LCK_M_U": "منتظر قفل Update است.",
    "LCK_M_IS": "منتظر Intent Shared است.",
    "LCK_M_IX": "منتظر Intent Exclusive است.",
    "LCK_M_SCH_S": "منتظر Schema Stability — معمولاً DDL همزمان.",
    "LCK_M_RS_U": "منتظر قفل Range-Shared / Update روی کلید ایندکس — اغلب به‌خاطر MERGE/UPDATE همزمان.",
    "LCK_M_RS_S": "منتظر قفل Range-Shared — معمولاً اسکن تحت Serializable/Holdlock.",
    "CXPACKET": "همگام‌سازی موازی‌سازی — گاهی اسکیل نامتوازن.",
    "CXCONSUMER": "مصرف‌کننده موازی منتظر داده از worker دیگر است.",
    "CXSYNC_PORT": "همگام‌سازی پورت موازی بین workerها.",
    "PAGEIOLATCH_SH": "منتظر خواندن صفحه از دیسک به حافظه (IO).",
    "PAGEIOLATCH_EX": "منتظر IO صفحه از دیسک.",
    "WRITELOG": "منتظر نوشتن Transaction Log روی دیسک.",
    "LOGBUFFER": "منتظر بافر لاگ — فشار روی log write.",
    "ASYNC_NETWORK_IO": "منتظر کلاینت برای دریافت نتیجه — شبکه/اپ کند.",
    "OLEDB": "منتظر Linked Server / OLE DB.",
    "WAITFOR": "عمداً با WAITFOR معطل شده — معمولاً طراحی‌شده.",
    "SP_SERVER_DIAGNOSTICS_SLEEP": "نشست داخلی مانیتورینگ SQL Server — معمولاً نادیده بگیر.",
    "SOS_SCHEDULER_YIELD": "داوطلبانه CPU را رها کرده تا بقیه اجرا شوند.",
    "THREADPOOL": "worker آزاد نیست — فشار همزمانی بالا.",
    "RESOURCE_SEMAPHORE": "منتظر حافظه برای Query — فشار Memory Grant.",
    "PAGELATCH_EX": "قفل حافظه‌ای صفحه — اغلب TempDB یا hot page.",
    "PAGELATCH_SH": "قفل حافظه‌ای Shared روی صفحه.",
    "IO_COMPLETION": "منتظر اتمام عملیات IO.",
    "SLEEP_TASK": "تسک در خواب کوتاه — اغلب بی‌ضرر.",
    "BROKER_RECEIVE_WAITFOR": "Service Broker منتظر پیام است.",
    "HADR_SYNC_COMMIT": "منتظر تأیید همگام Always On.",
    "REPLICA_WRITE": "منتظر نوشتن روی replica.",
    "CLR_MANUAL_EVENT": "منتظر رویداد CLR.",
    "PREEMPTIVE_OS_PIPEOPS": "منتظر عملیات OS/pipe — گاهی Agent/external.",
}

# Docs نیاز دارد که هر Wait یک متایادیتای dict داشته باشد:
#   { "summary": "...", "detail": "...", "example": "..." }
# فعلاً فقط از WAIT_TIPS (متن کوتاه) استفاده می‌کنیم تا ImportError و رندر Docs درست شود.
WAIT_DOCS = {
    k: {"summary": v, "detail": v}
    for k, v in WAIT_TIPS.items()
}


def tip_status(value: str | None) -> str:
    key = (value or "").strip().lower()
    if key in STATUS_TIPS:
        return STATUS_TIPS[key]
    if not key or key == "—":
        return "وضعیت نشست مشخص نیست."
    return f"وضعیت نشست: {value}"


def tip_command(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw or raw == "—":
        return "نوع دستور فعالی گزارش نشده."
    key = raw.upper()
    if key in COMMAND_TIPS:
        return COMMAND_TIPS[key]
    for name, tip in COMMAND_TIPS.items():
        if key.startswith(name):
            return tip
    return f"دستور در حال اجرا: {raw}"


def tip_wait(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw or raw == "—":
        return "الان روی Wait خاصی متوقف نیست (یا هنوز گزارش نشده)."
    key = raw.upper()
    if key in WAIT_TIPS:
        return WAIT_TIPS[key]
    if key.startswith("LCK_M_"):
        return "منتظر قفل (Lock) است — احتمال بلاکینگ یا همزمانی بالا."
    if key.startswith("PAGEIOLATCH"):
        return "منتظر IO صفحه از دیسک — دیسک/بافر ممکن است تحت فشار باشد."
    if key.startswith("PAGELATCH"):
        return "قفل حافظه‌ای صفحه — اغلب رقابت روی صفحات داغ یا TempDB."
    if key.startswith("LATCH_"):
        return "منتظر Latch داخلی موتور SQL Server."
    if key.startswith("PREEMPTIVE_"):
        return "منتظر فراخوانی خارج از SQL (OS/API) است."
    if "SLEEP" in key:
        return "خواب/تأخیر داخلی — اغلب بی‌ضرر مگر طولانی شود."
    return f"نوع انتظار (Wait): {raw}"
