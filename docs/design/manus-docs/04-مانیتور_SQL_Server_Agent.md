# مانیتور SQL Server Agent

داشبورد وب سبک برای مشاهده وضعیت **جاب‌های SQL Server Agent** — در حال اجرا، تمام‌شده، Gantt و جزئیات Step.

---

## شروع سریع (ویندوز)

### پیش‌نیاز

راهنمای کامل نصب از صفر: **[INSTALL.md](INSTALL.md)**

| مورد | الزامی |
|------|--------|
| Python 3.9+ | بله |
| ODBC Driver 17 یا 18 | بله |
| SQL Login با SELECT روی msdb | بله |

> اگر پیام *Python was not found* دیدید → Python نصب کنید، alias فروشگاه ویندوز را خاموش کنید، `setup.bat` را دوباره اجرا کنید.

### نصب و اجرا

```bat
setup.bat    REM نصب پکیج‌ها (فقط بار اول)
run.bat      REM اجرا + باز کردن مرورگر
```

در **اولین اجرا**، فرم Setup از شما Server، User و Password می‌گیرد. **رمز عبور** در Windows Credential Manager ذخیره می‌شود (نه در `.env`).

**امنیت:** پیش‌فرض فقط از `127.0.0.1` در دسترس است. تنظیمات اتصال فقط از همان رایانه قابل تغییر است. Gantt و همه بخش‌ها از همان اتصال SQL استفاده می‌کنند — رمز هرگز به مرورگر ارسال نمی‌شود.

---

## امکانات

| تب | توضیح |
|----|-------|
| ⚡ در حال اجرا | جاب‌های live + تخمین پیشرفت |
| 📋 همه جاب‌ها | آخرین اجرای هر جاب + فیلتر تاریخ |
| 📊 Gantt | timeline اجراهای امروز |
| 🔍 جزئیات | تاریخچه step-level |

---

## تنظیمات

| متغیر | پیش‌فرض | توضیح |
|-------|---------|-------|
| `SQL_SERVER` | — | نام سرور |
| `SQL_USER` | — | نام کاربری |
| *(رمز)* | — | Windows Credential Manager |
| `DASH_HOST` | `127.0.0.1` | فقط دسترسی محلی |
| `REFRESH_RUNNING` | `15000` | بروزرسانی جاب‌های در حال اجرا (ms) |
| `REFRESH_HISTORY` | `60000` | بروزرسانی تاریخچه (ms) |

---

## License

MIT — contributions welcome.

--- stderr ---


Use `read` on the stdout/stderr paths above for the full output.