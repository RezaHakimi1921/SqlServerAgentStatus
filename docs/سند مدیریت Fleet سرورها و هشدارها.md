# سند مدیریت Fleet سرورها و هشدارها

**موضوع:** مدیریت چند SQL Server، پایش رخدادهای حیاتی و اعلان از طریق Email/Webhook
**تهیه‌کننده:** Manus AI
**تاریخ:** ۱۶ نوامبر ۲۰۲۶
**وضعیت:** نیازمندی مصوب؛ پیاده‌سازی backend foundation آغاز شده است. رجیستری/health، alert store/outbox و transportهای Email/Webhook نمونه اولیه دارند؛ UI، API routes، scheduler، ورود و مدیریت مقصدها و اتصال production هنوز باقی است.
**مکمل:** «سند نیازمندی از سمت مانوس»، «سند اینسایت و پیش‌بینی DBA»، «سند معماری و پیاده‌سازی بک‌اند اینسایت» و «نقشه راه توسعه با هوش مصنوعی».

## ۱. هدف

کاربر باید بتواند همه SQL Serverهای ثبت‌شده را در یک نمای Fleet ببیند، بداند هر کدام در دسترس است یا نه، آخرین جمع‌آوری داده چه زمانی انجام شده، چه رخدادهای باز و مهمی دارد و برای خطاهای مهم خارج از مرورگر اعلان دریافت کند. این قابلیت‌ها باید از ابتدای معماری لحاظ شوند؛ اما تحویل آن‌ها چند مرحله دارد: ابتدا رجیستری و health مستقل هر server، سپس قواعد/مرکز رخداد، بعد Email و Webhook قابل‌اعتماد.

این سامانه در این scope یک **کنسول پایش و رخداد DBA** است، نه جایگزین ابزار مدیریت سیستم‌عامل، شبکه یا patching. دستورات تغییردهنده SQL Server، restart سرویس یا مدیریت فایل/دیسک از داخل برنامه فعلاً خارج از scope هستند.

## ۲. واژه‌ها و دسته‌بندی خطا

- **Server/Instance:** هدف SQL Server مستقل با شناسه داخلی پایدار و نام نمایشی.
- **Health check:** مشاهده اتصال/پاسخ یک instance در یک زمان.
- **Observation:** داده‌ای مانند شکست Job، فضای کم، یا خطای collection.
- **Alert event:** رخداد نرمال‌شده‌ای که با rule و severity تولید و در history نگه‌داری می‌شود.
- **Notification:** تلاش برای ارسال alert event به یک مقصد (Email یا Webhook). یک alert می‌تواند چند delivery داشته باشد.
- **Critical error:** رخداد severity بحرانی که نیازمند اقدام فوری است؛ تعریف rule و threshold باید قابل تنظیم و قابل مشاهده باشد.

شدت‌ها: `critical`, `high`, `warning`, `info`. شدت از قاعده/مقدار/دامنه تعیین شود، نه از متن خطا یا نام Job به‌تنهایی. «اتصال ناموفق» به‌تنهایی نشان‌دهنده down بودن کل SQL Server نیست؛ ابتدا با چند poll ناموفق/timeout و health evidence معتبر به «عدم دسترسی پایدار» تبدیل شود.

## ۳. نمای Fleet سرورها

### ۳.۱ اطلاعات هر Server

هر رکورد شامل شناسه پایدار، نام نمایشی، endpoint (server/instance/port در قالب قابل‌پیکربندی)، database پیش‌فرض پایش، login، ODBC driver، timeout، محیط (production/staging/dev)، گروه/برچسب، timezone، enabled و timestamp آخرین تغییر است. Password فقط در Secret Store/Windows Credential Manager ذخیره شود؛ در SQLite/JSON config، response API، log یا export قرار نگیرد.

سازگاری با تنظیمات تک‌سروره فعلی لازم است: اتصال موجود باید به‌عنوان default/legacy instance نمایش‌پذیر باشد و upgrade نباید پیکربندی یا Credential فعلی را پاک کند.

### ۳.۲ نمای کلی

برای هر instance این موارد نمایش داده شوند:

- وضعیت health: `healthy`, `degraded`, `unreachable`, `disabled`, `unknown`.
- زمان آخرین poll موفق، آخرین poll ناموفق، علت خلاصه و سن داده.
- وضعیت SQL Agent/دسترسی `msdb` جدا از خود اتصال instance.
- تعداد Jobهای running و failureهای اخیر، اگر collector مربوطه موفق باشد.
- تعداد alertهای باز به تفکیک severity.
- نسخه SQL Server در صورت دسترسی و collector health.

فیلترهای گروه، environment، health، severity و جستجوی نام داشته باشد. انتخاب یک کارت سرور به جزئیات همان instance و منبع رخداد باز شود. failure یک instance نباید بقیه Fleet را پنهان کند.

### ۳.۳ health policy

هر check شامل start/end، duration، status، source و error code ذخیره شود. خطای authentication، timeout، DNS/network، database unavailable، permission denied و unsupported version از هم تفکیک شوند. تعداد retry و آستانه stale per-instance قابل تنظیم باشد. stale data نباید به‌صورت وضعیت زنده نمایش داده شود.

در prototype فعلی، یک connection failure نتیجه `degraded` می‌دهد و فقط پس از سه failure متوالی با category اتصال، وضعیت `unreachable` می‌شود؛ خطای credential/permission به‌تنهایی outage حساب نمی‌شود. threshold باید در تنظیمات نهایی per-instance یا per-environment قابل تغییر شود.

## ۴. رخدادهای قابل پایش و خطاهای حیاتی

### مرحله پایه (MVP)

1. **اتصال و collector:** چند failure متوالی، timeout پایدار، خطای auth/permission، stale شدن داده و بازگشت اتصال.
2. **SQL Agent Job:** failure نهایی، retry/failure تکراری، overdue/no run تا موعد، duration غیرعادی و disabled شدن Job منتخب.
3. **Database/file capacity:** نزدیک‌شدن به max size یا low free volume در صورتی که منبع volume معتبر پیکربندی شده باشد؛ growth غیرعادی فایل و log pressure در صورت داشتن داده معتبر.
4. **انطباق داده:** شکست یا عقب‌افتادگی collector؛ این رخداد از مشکل خود SQL Server جدا باشد.

### مراحل بعدی

Database offline/suspect، backup freshness، availability group/replication، blocking/deadlock، TempDB، CPU/memory/I/O/waits، OS service health و certificate expiry فقط پس از تعریف منبع داده، مجوز، cadence و اثر collection اضافه شوند. برخی نیازمند Windows/OS agent یا API زیرساخت هستند و از SQL DMV به‌تنهایی قابل تشخیص قطعی نیستند.

### طبقه‌بندی اولیه شدت

- **Critical:** رخداد با احتمال outage یا از دست‌رفتن سرویس در افق کوتاه، مثل volume تقریباً پر با رشد پیوسته، دیتابیس ضروری unavailable، یا failure مکرر health check روی production همراه با evidence.
- **High:** Job حیاتی از SLA عبور کرده، data/log space در آستانه تعریف‌شده است، یا Query/Agent signal نشان‌دهنده اختلال عمده است.
- **Warning:** ریسک در حال افزایش، collector stale کوتاه یا failure غیرتکراری با recovery نامشخص.
- **Info:** recovery، تغییر وضعیت یا پیام اطلاع‌رسانی.

thresholdها نمونه آغازین‌اند؛ DBA باید براساس SLA و محیط قابل تنظیم کند. UI باید rule و شواهد تعیین severity را قابل مشاهده کند.

## ۵. چرخه عمر و جلوگیری از طوفان هشدار

چرخه پیشنهادی:

`new → acknowledged → investigating → resolved`؛ رخداد باز در صورت بازگشت condition از `resolved` به رخداد جدید یا `reopened` تبدیل شود؛ `suppressed` فقط در maintenance window ثبت شود و حذف history نباشد.

هر alert دارای `event_id`, `instance_id`, source, rule id/version, scope, severity, first/last seen, evidence window, status, owner, dedup key و timestamps باشد. نمونه dedup key: instance + rule + scope (database/job/file) + normalized condition. چند مشاهده مشابه در یک event به‌صورت `last_seen` و count ثبت شود، نه چند ده ایمیل.

سیاست‌های لازم:

- Dedup/coalescing برای رخداد باز؛ تنظیم repeat reminder برای critical/high.
- Cooldown per rule/target، recovery notice و نگه‌داری رخدادهای suppressed.
- maintenance window به تفکیک instance/group/timezone با expiry.
- retry محدود با exponential backoff، ثبت attempt، status code و خطای sanitized.
- صف delivery پایدار و idempotency؛ restart برنامه ارسال‌های pending را گم نکند.
- باز بودن رخداد از موفق/ناموفق بودن ارسال جدا باشد؛ acknowledge ایمیل رخداد را پاک نکند.

**تضمین تحویل:** outbox از semantics حداقل یک‌بار (at-least-once) استفاده می‌کند. اگر receiver پیام را پذیرفته باشد و process پیش از ثبت نتیجه crash کند، retry ممکن است پیام را دوباره تحویل دهد؛ تضمین exactly-once بین دو سیستم مستقل ممکن نیست. برای Webhook، receiver باید `X-SqlAgent-Event-Id` را idempotently deduplicate کند. برای Email، `Message-ID` ثابت در retry کمک‌کننده است اما dedup سمت SMTP/گیرنده تضمین‌شده نیست؛ این edge case در history قابل مشاهده بماند.

## ۶. مقصدها و Email

یک یا چند destination قابل تعریف باشد. Email destination شامل host, port, from, to/cc, TLS mode (STARTTLS یا SSL مشخص)، username و secret reference است. از TLS verification استاندارد استفاده شود؛ ارسال credential در متن log ممنوع است. پشتیبانی SMTP authentication و timeout/retry لازم است. برای تست تنظیمات، ابتدا فقط `test notification` به گیرنده تأییدشده ارسال شود.

قالب پیام باید شامل severity، server/instance، environment، عنوان، زمان first/last seen، توضیح/evidence خلاصه، لینک داخلی/مسیر رخداد، وضعیت رسیدگی و اقدام پیشنهادی باشد. متن query، Job command، password و raw connection error نباید در اعلان افشا شود؛ طول/محتوا redact شود. تنظیم quiet hours و انتخاب severity/channel به ازای مقصد تعریف شود.

## ۷. مقصدها و Webhook

Webhook عمومی برای Teams/Slack/ticketing/custom receiver با event schema نسخه‌دار ارائه شود. Payload حداقل شامل `event_id`, `event_type`, `schema_version`, `occurred_at_utc`, `severity`, `status`, `instance`, `scope`, `summary`, `evidence`, `dedup_key`, `url` و `delivery_attempt` باشد. Payloadها باید size-limit و redaction داشته باشند.

امنیت و تحویل:

- فقط HTTPS به‌صورت پیش‌فرض؛ هر استثنای HTTP باید صریحاً برای محیط داخلی و با کنترل شبکه تصویب شود.
- امضای HMAC روی raw body با secret جدا، مثلاً header `X-SqlAgent-Signature: sha256=...`؛ receiver بتواند timestamp را برای replay protection کنترل کند.
- Timeout محدود، response code ثبت‌شده، retry با backoff و سقف attempt؛ پاسخ‌های 2xx success محسوب شوند.
- URL مقصد در سطح مدیر تنظیم شود، secret در vault/keyring نگه‌داری شود، امکان rotate و disable باشد. در deployment شبکه‌ای خطر SSRF بررسی و egress allowlist/validation اضافه شود.
- redirectها بررسی شوند؛ secret یا payload به host ناشناخته forward نشود.
- test endpoint قبل از فعال‌کردن rule موجود باشد و مقصد/نمونه داده در UI نمایش داده شود.

## ۸. API و UI موردنیاز

APIهای مفهومی:

- `GET/POST /api/v1/instances`, `GET/PATCH/DELETE /api/v1/instances/{id}` — CRUD با role مدیر؛ حذف soft/disable و حفظ تاریخچه.
- `POST /api/v1/instances/{id}/test-connection` — یک check امن با timeout؛ credential در body فقط روی HTTPS و never echo.
- `GET /api/v1/fleet/summary` — status counts، open alerts، last poll.
- `GET /api/v1/instances/{id}/health` — poll status و خطاهای sanitized.
- `GET /api/v1/alerts` و `GET /api/v1/alerts/{event_id}` — filters/pagination/evidence.
- `POST /api/v1/alerts/{event_id}/acknowledge|resolve` — تغییر وضعیت با actor/audit.
- `GET/POST/PATCH /api/v1/notification-targets` — metadata destination بدون secret.
- `POST /api/v1/notification-targets/{id}/test` — test delivery با target تأییدشده.

UI حداقل یک Fleet overview، صفحه جزئیات server با status/health/history، مرکز رخدادها و تنظیمات rule/destination داشته باشد. notification bell فعلی فقط نمایش failureهای امروز است و باید تا زمان اتصال به alert repository به‌عنوان local UI indicator شناخته شود، نه سامانه اعلان خارجی.

## ۹. ذخیره‌سازی و معماری پیاده‌سازی

- سرورها با `instance_id` پایدار و اتصال/credential مستقل تعریف شوند.
- metadata، alert lifecycle، rule config و delivery attempts باید در store ماندگار خارج از SQL Serverهای تحت پایش ذخیره شوند؛ SQLite قابل قبول برای تک‌کاربر محلی است، اما انتخاب production و multi-worker باید قبل از rollout با ADR مشخص شود.
- Secretها جدا از SQLite و app logs باشند؛ از Credential Manager/keyring یا secret vault متناسب با deployment استفاده شود.
- Collector، rule evaluator، alert lifecycle، notification dispatcher و UI از هم جدا باشند. ارسال Email/Webhook از Dash callback یا browser request انجام نشود.
- شروع worker دوباره نباید باعث duplicate event یا lost delivery شود. Unique dedup key و queue outbox/attempt log به کار رود.
- هر instance به‌صورت مستقل poll شود؛ concurrency، timeout، circuit breaker/backoff و سقف query cost پیکربندی‌پذیر باشند.
- برای deployment غیرمحلی، authentication/RBAC، CSRF، TLS و audit پیش‌شرط بهره‌برداری است.

## ۱۰. معیارهای پذیرش

- حداقل دو instance آزمایشی در Fleet قابل ثبت و مستقل disable/test/health-check باشند؛ secret در store/API/log ظاهر نشود.
- خراب‌بودن اتصال یک instance وضعیت و داده server دیگر را مختل نکند.
- هر کارت server سن poll را نشان دهد و stale را از healthy تازه تفکیک کند.
- یک condition مکرر در dedup window یک alert event باز داشته باشد و شمارنده/last_seen افزایش یابد؛ تلاش ارسال تکراری کنترل شود و semantics at-least-once/edge case crash مستند باشد.
- وقتی condition رفع شد، recovery state ثبت شود؛ history حذف نشود.
- severity و threshold قابل مشاهده/configurable و دارای test باشند.
- Notification queue/attemptها با restart حفظ شوند؛ retry محدود، dedup/idempotency-key دار، قابل پیگیری و با semantics تحویل روشن باشد.
- Email با SMTP mock و Webhook با HTTP client mock تست شوند؛ unit tests واقعی به اینترنت/SMTP سازمانی وصل نشوند.
- Webhook signature قابل اعتبارسنجی باشد؛ URL/secret در UI/log/event payload افشا نشود.
- notification test از event production جدا باشد و به مقصد صریح و مجاز ارسال شود.
- critical alerts مطابق rule چند channel را هدف بگیرند؛ warningها قابل محدودکردن باشند.
- health events خود collector از خطای SQL Server مجزا نمایش داده شوند.
- هیچ تغییر DDL، restart یا اقدام نوشتنی روی سرور تحت پایش از مسیر پایش اجرا نشود.

## ۱۱. ترتیب تحویل پیشنهادی

1. **Fleet foundation:** مدل/registry، import بدون از دست‌دادن config قبلی، secret reference، test connection، health status مستقل.
2. **Fleet read-only view:** summary چندسروره، freshness، per-instance failure isolation، drill-down محدود.
3. **Alert core:** normalized event, severity, dedup, lifecycle, persistent history, maintenance/suppression پایه.
4. **Notification settings:** SMTP/Webhook target metadata، secret integration، test delivery فقط به مقصد تأییدشده.
5. **Outbox dispatcher:** queue پایدار، HMAC، retry/backoff, delivery log, repeat/cooldown.
6. **Rule coverage:** Job failures/overdue، collector stale/unreachable، capacity thresholds؛ سپس گسترش به سایر سلامت‌ها.
7. **Fleet critical dashboard:** view بر حسب severity و environment، acknowledgment و runbook links.

هر گام مستقل تست شود. شروع با «تمام errorهای سیستم‌عامل و SQL Server» بدون تعریف source/permission/SLA پذیرفته نیست؛ پوشش health باید با فهرست ruleهای مشخص گسترش یابد.
