# سند الگوریتم رشد و API Collector

**موضوع:** مشخصات فنی پیش‌بینی رشد جدول/ایندکس و قرارداد backend برای داشبورد DBA
**تهیه‌کننده:** Manus AI
**تاریخ:** ۱۶ نوامبر ۲۰۲۶
**ارتباط:** سند مکمل «سند معماری و پیاده‌سازی بک‌اند اینسایت» است. نمونه Collector فقط داده می‌خواند و نتایج را به repository نمی‌نویسد.

## ۱. دامنه

این سند دو جزئیات اجرایی را کنار هم می‌آورد: الگوریتم baseline و forecast برای رشد objectها، و API خواندنی برای رساندن داده/Insight به داشبورد. Collector نمونه در مسیر `collectors/sqlserver_collector.py` پیاده شده و snapshot را به caller تحویل می‌دهد. Persistence، scheduler production و API handler در این نسخه نمونه‌کد/قرارداد هستند و هنوز به برنامه وصل نشده‌اند.

هدف پیش‌بینی، برآورد روند و نزدیک‌شدن به آستانه ظرفیت است؛ نه تضمین رخداد آینده. الگوریتم اولیه با آمار robust و قواعد مشخص عمل می‌کند و در صورت کمبود یا ناپایداری داده از forecast خودداری می‌کند.

## ۲. داده ورودی و تعریف دقیق اندازه

### ۲.۱ اندازه جدول و Index

Collector از `sys.dm_db_partition_stats`، `sys.tables`, `sys.schemas`, `sys.indexes`, `sys.index_columns` و `sys.columns` استفاده می‌کند. صفحه SQL Server برابر ۸۱۹۲ بایت است؛ تعداد page خام ذخیره شود و byte به‌عنوان مقدار مشتق‌شده نگه‌داری شود تا محاسبه قابل بازبینی باشد. DMV partition اندازه و row count تقریبی partition را می‌دهد [1].

برای یک جدول:

- `base_used_pages`: مجموع `used_page_count` برای heap (`index_id=0`) یا clustered index (`index_id=1`).
- `nonclustered_used_pages`: مجموع برای indexهای `index_id > 1`.
- `total_used_pages`: مجموع صفحات استفاده‌شده برای heap/clustered و تمام indexها.
- `row_count_approx`: جمع `row_count` فقط برای index_id 0 یا 1؛ جمع row count برای همه indexها تعداد ردیف‌ها را چندبرابر می‌شمارد.
- `index_used_pages`: فضای یک index، جمع‌شده روی partitionهای همان object/index.

این مقدارها «اندازه تخصیص‌یافته/استفاده‌شده در ساختار داده SQL Server» هستند، نه فضای آزاد volume و نه الزاماً تعداد بایت فیزیکی مصرفی روی دیسک. اندازه ایندکس clustered همان ساختار داده اصلی جدول را در بر می‌گیرد؛ نمودار نباید آن را هم به‌عنوان table data و هم یک index مستقل دوباره جمع کند.

### ۲.۲ فایل و فضای دیسک

برای هر فایل، فیلدهای مستقل لازم است: اندازه تخصیص‌یافته فایل، فضای استفاده‌شده داخل فایل در صورت معتبر بودن منبع، growth policy و max size. فضای آزاد volume باید از collector/permission مناسب سیستم‌عامل یا ابزار زیرساختی جداگانه بیاید. این دو مقدار قابل‌جایگزینی نیستند. در prototype، `FILEPROPERTY(name, 'SpaceUsed')` برای data files نمونه‌برداری می‌شود و مقدار log file اگر در دسترس نباشد NULL باقی می‌ماند؛ `NULL` به صفر تبدیل نشود.

برای پیش‌بینی «پر شدن»، هر هدف جدا تعریف شود:

- **حجم فایل در برابر MAXSIZE:** روند allocated bytes با max size مقایسه شود.
- **فضای آزاد volume:** روند حجم آزاد volume با threshold مقایسه شود.
- **فضای داخلی data file:** روند used bytes با allocated bytes مقایسه شود؛ این پیش‌بینی برابر با پرشدن دیسک نیست.
- **فضای log:** وضعیت reuse/log backup و نرخ growth جدا لازم است؛ فقط روند فایل allocation برای تخمین توقف log کافی نیست.

## ۳. روش جمع‌آوری و snapshot

### ۳.۱ قرارداد Collector نمونه

کلاس `SqlServerCollector` در `collectors/sqlserver_collector.py` connection factory تزریق‌شده می‌گیرد و چهار متد read-only فراهم می‌کند:

- `collect_file_capacity()` — metadata فایل و byteهای allocated/used/free داخل فایل در صورت دسترسی.
- `collect_table_sizes()` — size و row-count تقریبی به تفکیک جدول.
- `collect_index_details()` — metadata index شامل key order/direction، INCLUDE، uniqueness، filter، constraint flags و size.
- `collect_index_usage()` — counterهای cumulative و `sqlserver_start_time` برای restart-aware delta.
- `collect_snapshot()` — اجرای ترتیبی این بخش‌ها و برگرداندن یک payload.

نمونه اتصال از تنظیمات موجود پروژه ساخته می‌شود:

```python
from collectors.sqlserver_collector import (
    SqlServerCollector,
    SqlServerCollectorConfig,
    build_default_connection_factory,
)

collector = SqlServerCollector(
    SqlServerCollectorConfig(
        instance_id="prod-sql-01",
        database_name="SalesDb",
        command_timeout_seconds=30,
    ),
    build_default_connection_factory("SalesDb"),
)
snapshot = collector.collect_snapshot()
# Caller must store this payload in the separate monitoring repository.
```

این کد برای نمونه اولیه است؛ هر query اتصال کوتاه‌مدت جدا می‌گیرد. برای production باید poll orchestration، ثبت start/end/error، retry/backoff، concurrency limit، idempotency و persistence در لایه‌های جدا اضافه شوند.

### ۳.۲ رفتار خطا و مجوز

هر adapter باید `instance_id`, `database_name`, `source`, زمان شروع/پایان، status و error code ثبت کند. در prototype خطای query raise می‌شود و caller باید آن را به health status تبدیل کند. پیش از استقرار، مجوز لازم برای `sys.dm_db_partition_stats`, `sys.dm_db_index_usage_stats`, `sys.dm_os_sys_info` و metadata catalog باید با نسخه/edition واقعی SQL Server بررسی شود. عدم دسترسی به یک DMV نباید به عدد صفر تعبیر شود.

`sys.dm_db_index_usage_stats` شمارنده‌ها را با شروع مجدد Database Engine از نو مقداردهی می‌کند؛ زمان شروع موتور باید همراه هر snapshot ذخیره شود و فقط وقتی startup timestamp بین دو snapshot یکسان است delta محاسبه شود [2]. Metadata و اندازه جدول نیز ممکن است reset نداشته باشند، ولی داده تازه/کهنه بودن هر منبع مستقل ثبت شود.

### ۳.۳ cadence پیشنهادی

| داده | فاصله آغازین پیشنهادی | قید |
|---|---|---|
| File capacity | ۳۰ تا ۶۰ دقیقه | volume free جدا از SQL file metrics |
| Table/index size | ۶ تا ۲۴ ساعت | برای growth کوتاه‌مدت، cadence متناسب با سرعت تغییر |
| Index usage counters | ۱۵ تا ۶۰ دقیقه | delta فقط با engine uptime ثابت |
| Index definition snapshot | روزانه و پس از تغییر | snapshotها immutable باشند |
| Physical fragmentation | در MVP جمع‌آوری عادی نشود | فقط درخواست/زمان‌بندی DBA و با بررسی load/replica |

این cadence نقطه شروع است؛ DBA باید براساس تعداد objectها، نرخ رشد، بار سرور و نیاز پیش‌بینی تغییرش دهد. Queryهای جمع‌آوری باید زمان اجرا و timeout داشته باشند و load واقعی‌شان سنجیده شود.

## ۴. پاکسازی سری زمانی

هر sample به `(instance_id, database_id, object_id, index_id, metric_name, observed_at_utc)` متصل شود. Timestamp UTC ذخیره و timezone نمایشی instance جدا ثبت شود. Duplicateهای یک poll با کلید idempotency حذف شوند، اما source row و زمان آخرین مشاهده حفظ شود.

1. samples بر اساس entity/metric مرتب شوند.
2. مقادیر با quality نامعتبر، واحد ناسازگار یا source error حذف از محاسبه شوند اما در health باقی بمانند.
3. برای کاهش اثر poll jitter، اندازه‌گیری‌ها به bucket روزانه تبدیل شوند؛ مقدار روزانه median نمونه‌های معتبر باشد. برای cadence روزانه، مقدار نمونه معتبر همان روز استفاده شود.
4. فاصله‌های طولانی به‌صورت NULL/gap نگه‌داری شوند؛ interpolation پنهانی انجام نشود.
5. تغییر نسخه، partition switch، index rebuild/recreate، compression، purge یا restore به‌عنوان event علامت‌گذاری شود. در صورت event می‌توان baseline قبلی را segment کرد.
6. استفاده از row count یا page count تقریبی در تمام APIها و نمودارها برچسب `approximate/estimated` داشته باشد.

## ۵. الگوریتم پیش‌بینی رشد

### ۵.۱ ورودی پایه

برای یک entity، روزهای معتبر آخرین window را به شکل `(t_i, y_i)` تعریف کنید؛ `y_i` اندازه bytes/pages و `t_i` تعداد روز از آغاز window باشد. برای forecast ظرفیت، `target` باید threshold مشخص باشد؛ مثل ۸۵٪ max file size یا آستانه آزاد volume. آستانه global مبهم استفاده نشود؛ هر target و واحد باید ذخیره شود.

### ۵.۲ شیب robust با Theil–Sen

برای همه جفت‌های نقاط معتبر با زمان متفاوت، شیب محاسبه شود:

` s(i,j) = (y_j - y_i) / (t_j - t_i) `

شیب اصلی `b` برابر median تمام `s(i,j)`هاست. intercept `a` برابر median مقادیر `y_i - b*t_i` است. مدل پایه:

` y_hat(t) = a + b*t `

برای datasetهای بزرگ، تعداد نقاط با downsampling روزانه محدود شود تا تعداد جفت‌ها (`n*(n-1)/2`) مدیریت‌پذیر بماند. Theil–Sen نسبت به outlier منفرد از least-squares خطی مقاوم‌تر است، اما تغییر رژیم یا رشد فصلی/پله‌ای را خودبه‌خود حل نمی‌کند.

### ۵.۳ نرخ تغییر و تشخیص جهش

برای تشخیص رشد ناپیوسته، deltaهای بین نمونه‌های متوالی محاسبه شوند. اگر یک delta نسبت به median delta و MAD از حد پیکربندی‌شده عبور کند، به‌عنوان «جهش/تغییر ساختاری برای بازبینی» علامت‌گذاری شود. خودکار حذف نمونه مجاز نیست؛ علت ممکن است bulk load، rebuild، compression، partition switch یا purge باشد.

در صورت جهش، forecast بر دو بازه جدا ساخته شود: قبل و بعد از رخداد. اگر بعد از رخداد sample کافی نیست، فقط وضعیت اندازه و روند کوتاه نشان داده شود، نه تاریخ پرشدن قطعی.

### ۵.۴ افق و زمان عبور از آستانه

اگر `b <= 0`، forecast پرشدن بر مبنای مدل خطی ارائه نشود؛ کاهش size ممکن است purge/rebuild باشد. اگر `b > 0` و مقدار جاری `y_now < target` باشد:

`days_to_target = (target - y_now) / b`

و تاریخ تخمینی `forecast_at = now + days_to_target`. اگر target در افق پیکربندی‌شده (مثلاً ۳۰/۹۰/۱۸۰ روز) قطع نشود، خروجی `beyond_horizon` باشد، نه یک تاریخ دور دقیق. اگر مقدار جاری از target گذشته، رخداد «آستانه رد شده» است و دیگر پیش‌بینی محسوب نمی‌شود.

برای رشد object، target می‌تواند سقف دستی، سهم از ظرفیت data file یا target آینده باشد؛ اگر هیچ target معناداری وجود ندارد، نرخ رشد و اندازه احتمالی در افق‌های ثابت نمایش داده شود، نه «زمان تا پرشدن» ساختگی.

### ۵.۵ دامنه عدم‌قطعیت

شیب‌های جفتی به‌عنوان توزیع empirical استفاده شوند. برای سناریوی کم/میانه/زیاد، صدک‌های ۱۰، ۵۰ و ۹۰ شیب را گزارش کنید؛ این‌ها بازه سناریویی‌اند و بدون کالیبراسیون نباید «confidence interval آماری ۹۰٪» نامیده شوند. اگر sampling sparse یا نوسان بالاست، دامنه وسیع‌تر و confidence پایین‌تر نمایش یابد.

Residualها `r_i = y_i - y_hat(t_i)` و MAD آن‌ها برای سنجش fit استفاده شوند. Error metrics (مثل median absolute error) کنار model version ثبت شوند. Forecast threshold crossing را برای slope P10/P50/P90 جدا محاسبه کنید؛ اگر سناریوها به شکل معنادار متفاوت‌اند، UI باید دامنه تاریخ را نشان دهد.

### ۵.۶ شروط حداقل داده و توقف پیش‌بینی

پیش‌فرض اولیه قابل تنظیم:

- حداقل ۱۴ daily observations در span دست‌کم ۱۴ روز برای forecast کوتاه‌مدت.
- برای تشخیص فصل هفتگی/تفاوت روزهای هفته، ترجیحاً ۲۸ روز یا بیشتر.
- حداقل ۸۰٪ پوشش روزهای مورد انتظار در window انتخابی؛ اگر coverage کمتر شد confidence کاهش یابد یا forecast متوقف شود.
- بعد از restore/rebuild/reset ساختاری، history segment جدید آغاز و حداقل داده مجدداً جمع شود.
- اگر size ثابت/پله‌ای، رشد منفی، نوسان غالب، یا مدل baseline error بالا دارد، فقط مشاهده و هشدار threshold ارائه شود.

این اعداد guardrail آغازین‌اند، نه قانون عمومی برای همه workloadها. تنظیم نهایی بر اساس cadence و تغییرات واقعی سیستم تعیین شود.

### ۵.۷ انتخاب مدل به تفکیک داده

- **فایل و table/index size:** ابتدا Theil–Sen روی daily median؛ مدل piecewise پس از event بزرگ.
- **Job runtime:** median/percentile بر اساس همان Job و روز هفته/slot زمانی؛ Theil–Sen size-growth برای duration job کافی نیست.
- **Query performance:** مقایسه بازه‌های مشابه و plan/runtime regressions از Query Store؛ از forecast size برای query duration استفاده نشود.
- **Volume free space:** اگر ورود/خروج فایل‌های غیر SQL هم رخ می‌دهد، trend volume تنها با منبع OS معتبر است؛ مجموع فایل‌های SQL جایگزین free volume نیست.

## ۶. نمونه شبه‌کد forecast

```python
from statistics import median


def theil_sen_daily(points):
    """points: ordered list of (day_number, size_bytes)."""
    slopes = []
    for i, (t1, y1) in enumerate(points):
        for t2, y2 in points[i + 1:]:
            if t2 > t1:
                slopes.append((y2 - y1) / (t2 - t1))
    if not slopes:
        return None
    slope = median(slopes)
    intercept = median(y - slope * t for t, y in points)
    return slope, intercept, slopes


def forecast_threshold(points, current_size, target_size, max_days=180):
    if len(points) < 14:
        return {"status": "insufficient_history"}
    fit = theil_sen_daily(points)
    if fit is None:
        return {"status": "insufficient_points"}
    slope, intercept, slopes = fit
    if slope <= 0:
        return {"status": "no_positive_growth_trend", "slope_bytes_per_day": slope}
    days = (target_size - current_size) / slope
    if days < 0:
        return {"status": "threshold_exceeded"}
    if days > max_days:
        return {"status": "beyond_horizon", "horizon_days": max_days}
    return {
        "status": "forecast_available",
        "slope_bytes_per_day": slope,
        "days_to_target_median_scenario": days,
        "target_size_bytes": target_size,
        "method": "theil_sen_daily_v1",
        "note": "Add coverage, residual and slope-quantile analysis before production use.",
    }
```

این شبه‌کد به‌تنهایی production-ready نیست: باید daily aggregation، coverage/gap، event segmentation، forecast scenarios، unit validation، baseline error، timezone و testهای boundary به آن افزوده شود. از این خروجی بدون ذخیره input window و model version برای تولید اقدام استفاده نشود.

## ۷. API backend برای داشبورد

API باید از repository داده بخواند و از collector مستقیم استفاده نکند. پاسخ‌ها شامل `generated_at_utc`, `data_as_of_utc`, `quality`, `method_version` باشند. `data_as_of` زمان مشاهده منبع است؛ `generated_at` زمان ساخت پاسخ/forecast است.

### ۷.۱ مسیرهای پیشنهادی

- `GET /api/v1/instances` — فهرست instanceها، نسخه، health و آخرین poll.
- `GET /api/v1/instances/{instance_id}/capacity/files?database=SalesDb` — snapshotهای فایل و forecastهایشان.
- `GET /api/v1/instances/{instance_id}/objects/growth?database=SalesDb&schema=dbo&object=Orders&window_days=90` — رشد table/partition/index.
- `GET /api/v1/instances/{instance_id}/indexes?database=SalesDb&schema=dbo&table=Orders` — تعریف کلیدها، include، filter، size و usage summary.
- `GET /api/v1/instances/{instance_id}/insights?type=capacity&severity=high&status=open&limit=50&cursor=...` — فهرست صفحه‌بندی‌شده Insight.
- `GET /api/v1/insights/{insight_id}` — evidence، روش، confidence و پیشنهاد.
- `POST /api/v1/insights/{insight_id}/acknowledge` — تغییر lifecycle با actor مجاز.
- `POST /api/v1/insights/{insight_id}/feedback` — ثبت useful/not useful و توضیح.
- `GET /api/v1/health` — سلامت web, repository و worker؛ بدون connection string یا secret.

تمام مسیرها در MVP read-only هستند، به جز تغییر lifecycle/feedback در repository برنامه. هیچ API برای `CREATE/DROP INDEX` یا اجرای Job در MVP تعریف نشود.

### ۷.۲ نمونه پاسخ growth

```json
{
  "instance_id": "prod-sql-01",
  "database_name": "SalesDb",
  "object": {"schema": "dbo", "name": "Orders", "object_id": 123456},
  "metric": "total_used_bytes",
  "current_value": 21474836480,
  "unit": "bytes",
  "current_as_of_utc": "2026-11-16T09:00:00Z",
  "window": {"from_utc": "2026-10-17T00:00:00Z", "to_utc": "2026-11-16T09:00:00Z", "valid_daily_samples": 28, "coverage": 0.93},
  "trend": {"method": "theil_sen_daily_v1", "slope_p50_bytes_per_day": 52428800, "slope_p10_bytes_per_day": 31457280, "slope_p90_bytes_per_day": 78643200},
  "forecast": {
    "status": "forecast_available",
    "target_value": 32212254720,
    "target_unit": "bytes",
    "days_to_target": {"p10_slope_scenario": 343, "p50_slope_scenario": 205, "p90_slope_scenario": 137},
    "horizon_days": 180,
    "confidence": "medium",
    "limitations": ["Linear trend assumes recent growth regime continues."]
  },
  "quality": {"state": "approximate", "notes": ["Row count and page figures are SQL Server metadata estimates."]},
  "generated_at_utc": "2026-11-16T09:02:12Z",
  "method_version": "growth-forecast-0.1"
}
```

اگر forecast از horizon بیرون باشد، response status باید `beyond_horizon` بگوید و `days_to_target` را null کند. عدم امکان پیش‌بینی باید status معنادار داشته باشد: `insufficient_history`, `low_coverage`, `structural_change`, `no_positive_growth_trend`, `unstable_trend`, `threshold_exceeded`, `source_unavailable`.

### ۷.۳ نمونه پاسخ Insight

```json
{
  "insight_id": "ins_01J...",
  "type": "capacity_forecast",
  "severity": "warning",
  "status": "open",
  "scope": {"instance_id": "prod-sql-01", "database": "SalesDb", "object": "dbo.Orders"},
  "title": "رشد جدول از ظرفیت هدف عبور می‌کند",
  "summary": "با نرخ میانه 50 MiB در روز، آستانه تعریف‌شده در سناریوی میانه حدود 205 روز دیگر لمس می‌شود.",
  "evidence": [{"metric": "total_used_bytes", "window_days": 30, "valid_samples": 28}],
  "method": {"name": "theil_sen_daily_v1", "version": "0.1", "confidence": "medium"},
  "recommendation": {"action": "review_capacity_plan", "automatic_execution": false},
  "first_seen_utc": "2026-11-16T09:02:12Z",
  "last_seen_utc": "2026-11-16T09:02:12Z",
  "data_as_of_utc": "2026-11-16T09:00:00Z"
}
```

### ۷.۴ خطا، صفحه‌بندی و امنیت API

- `400` پارامتر نامعتبر؛ `401/403` هویت یا دسترسی ناکافی؛ `404` موجودیت/Insight پیدا نشد؛ `409` تغییر lifecycle ناسازگار؛ `429` محدودیت درخواست؛ `503` repository/worker موقتاً unavailable.
- فهرست‌های بزرگ با `limit` سقف‌دار و cursor pagination پاسخ دهند؛ sort field از whitelist انتخاب شود.
- شناسه instance/object و نام database/schema/table در query فقط با validation و identifier quoting امن استفاده شوند. SQL valueها parameterized باشند.
- API خارج از localhost نیازمند authentication، RBAC، HTTPS و audit است. متن query، physical path فایل، command و connection error نباید به نقش viewer افشا شود.
- `data_as_of_utc` در پاسخ‌های dashboard الزامی است تا UI داده قدیمی را تازه نمایش ندهد.

## ۸. تست‌های الزامی برای رشد و API

### Forecast unit tests

- رشد خطی بدون نویز؛ شیب و crossing time نزدیک مقدار مورد انتظار.
- یک outlier مثبت/منفی؛ Theil–Sen نباید کاملاً تحت سلطه آن قرار گیرد.
- رشد پله‌ای به‌علت rebuild/purge؛ segment یا `structural_change` و عدم forecast قطعی.
- شیب صفر/منفی؛ پاسخ `no_positive_growth_trend` و عدم تقسیم بر صفر.
- gap/coverage ناکافی؛ `low_coverage` یا `insufficient_history`.
- target گذشته؛ `threshold_exceeded`.
- target بعد از horizon؛ `beyond_horizon` و null days.
- UTC/local timezone، duplicate samples، unit mismatch و byte/page conversion.

### Collector tests

در `tests/test_sqlserver_collector.py` آزمون‌های shaping ترتیب key columns، تفکیک INCLUDE و byte conversion وجود دارند. ادامه تست باید mock cursor/connection برای query response، close-on-error، timeout، NULLهای log، usage restart timestamp و خطای permission را پوشش دهد. Integration tests فقط روی SQL Server آزمایشی/fixture مجاز اجرا شوند.

### API tests

- response schema/version، required timestamps و quality labels.
- pagination/filter allowlist و validation نام instance/database.
- نقش‌های viewer/DBA، redaction و error messages.
- forecast statusهای no-data و stale.
- هیچ مسیر API در read-only scope DDL اجرا نکند.

## ۹. وضعیت و محدودیت نمونه اولیه

Collector حاضر صرفاً نمونه read-only است. هنوز scheduler، storage repository، migrations، API server، authentication، volume free collector، Query Store adapter، algorithm production و feedback calibration اضافه نشده‌اند. Queryهای DMV به permission و نسخه SQL Server وابسته‌اند. `physical_name` در خروجی Collector برای capacity path مفید است اما حساس تلقی می‌شود؛ قبل از ذخیره/نمایش در API باید policy redaction/RBAC داشته باشد.

الگوریتم اولیه اکنون در `analytics/growth_forecast.py` پیاده شده است. این ماژول daily median، Theil–Sen slope، quantile scenarios، coverage، حداقل تاریخچه، UTC timestamp validation، threshold/horizon states و توقف در صورت جهش ساختاری را اجرا می‌کند. unit testهای synthetic در `tests/test_growth_forecast.py` قرار دارند. این implementation هنوز structural event را فقط علامت‌گذاری می‌کند و segment بعد از event را خودکار انتخاب نمی‌کند؛ همچنین scenario percentileها interval کالیبره‌شده نیستند. پیش از استفاده عملیاتی باید علاوه بر integration tests، baseline/error روی داده‌های واقعی بی‌نام‌شده و workload representative ارزیابی شود.

نسخه اولیه forecast باید از ۱۴/۲۸ روز به‌عنوان guardrail قابل تنظیم شروع کند، نه guarantee. رشد جدول ممکن است batchی/فصلی باشد؛ رشد index پس از rebuild یا تغییر تعریف جهش دارد. تنها با داده‌های دارای timestamp و event context می‌توان confidence را معنا‌دار کرد.

## منابع

[1]: https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-objects/sys-dm-db-partition-stats-transact-sql?view=sql-server-ver17 "sys.dm_db_partition_stats"
[2]: https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-objects/sys-dm-db-index-usage-stats-transact-sql?view=sql-server-ver17 "sys.dm_db_index_usage_stats"
[3]: https://learn.microsoft.com/en-us/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store?view=sql-server-ver17 "Monitor performance by using the Query Store"
[4]: https://learn.microsoft.com/en-us/sql/relational-databases/indexes/tune-nonclustered-missing-index-suggestions?view=sql-server-ver17 "Tune nonclustered indexes with missing index suggestions"
