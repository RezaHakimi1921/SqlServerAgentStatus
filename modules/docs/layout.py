"""Docs — in-app glossary; one topic per page (not one long scroll)."""
from __future__ import annotations

from dash import dcc, html

from core.i18n import DEFAULT_LOCALE, normalize_locale, t
from modules.activity.glossary import COMMAND_TIPS, STATUS_TIPS, WAIT_DOCS

DOCS_PAGES = [
    ("overview", "نمای کلی"),
    ("status", "Status"),
    ("command", "Command / Action"),
    ("wait", "Wait types"),
    ("progress", "Progress و Rows"),
    ("eta", "Est. finish"),
    ("lookup", "Session Lookup"),
    ("blocking", "Blocking"),
    ("insights", "Today's Insights"),
    ("tables", "Tables & Growth"),
    ("tips", "نکات عملیاتی"),
]

DOCS_PAGE_IDS = [p[0] for p in DOCS_PAGES]


def _p(*parts):
    return html.P(list(parts), className="docs-p")


def _ul(items: list[str]):
    return html.Ul(
        className="docs-ul",
        children=[html.Li(t) for t in items],
    )


def _kv_table(rows: list[tuple[str, str]], *, ltr_key: bool = True):
    body = []
    for key, tip in rows:
        body.append(html.Tr([
            html.Td(
                key,
                className="docs-key num-ltr" if ltr_key else "docs-key",
            ),
            html.Td(tip, className="docs-val"),
        ]))
    return html.Div(className="docs-table-wrap", children=[
        html.Table(className="docs-table", children=[
            html.Thead(html.Tr([
                html.Th("مقدار"),
                html.Th("معنی"),
            ])),
            html.Tbody(body),
        ]),
    ])


def _docs_accordion(entries: list[tuple[str, dict]], *, hint: str | None = None):
    """Click-to-expand glossary (native <details> — accessible, no callback)."""
    items = []
    for key, meta in entries:
        summary = (meta.get("summary") or "").strip()
        detail = (meta.get("detail") or "").strip()
        example = (meta.get("example") or "").strip()
        body_kids = []
        if detail:
            body_kids.append(html.P(detail, className="docs-acc-detail"))
        if example:
            body_kids.append(
                html.Div(
                    className="docs-acc-example",
                    children=[
                        html.Span("مثال", className="docs-acc-example-label"),
                        html.P(example, className="docs-acc-example-text"),
                    ],
                )
            )
        items.append(
            html.Details(
                className="docs-acc",
                children=[
                    html.Summary(
                        className="docs-acc-sum",
                        children=[
                            html.Span(key, className="docs-acc-key num-ltr"),
                            html.Span(summary, className="docs-acc-brief"),
                            html.Span("▾", className="docs-acc-chevron"),
                        ],
                    ),
                    html.Div(className="docs-acc-body", children=body_kids),
                ],
            )
        )
    kids = []
    if hint:
        kids.append(html.P(hint, className="docs-acc-hint"))
    kids.append(html.Div(className="docs-acc-list", children=items))
    return html.Div(className="docs-acc-wrap", children=kids)


def _callout(kind: str, title: str, text: str):
    return html.Div(className=f"docs-callout is-{kind}", children=[
        html.Div(title, className="docs-callout-title"),
        html.P(text, className="docs-callout-body"),
    ])


def _page_shell(sid: str, title: str, *children):
    return html.Div(
        id={"type": "docs-page", "page": sid},
        className="docs-page",
        children=[
            html.H3(title, className="docs-h3"),
            *children,
        ],
    )


def build_docs_page(sid: str):
    """Single topic page body (pager lives outside host — stable Dash ids)."""
    status_rows = sorted(STATUS_TIPS.items(), key=lambda x: x[0])
    command_rows = sorted(COMMAND_TIPS.items(), key=lambda x: x[0])
    wait_entries = sorted(WAIT_DOCS.items(), key=lambda x: x[0])

    pages = {
        "overview": _page_shell(
            "overview",
            "نمای کلی محصول",
            _p(
                "SmartMonitor وضعیت SQL Server را از DMV می‌خواند "
                "(بدون Extended Events مگر صریحاً تأیید شود)."
            ),
            html.H4("کجا چه چیزی را ببینم؟", className="docs-h4"),
            _ul([
                "Activity — الان چه کوئری‌هایی در حال اجرا / بلاک‌اند (Live)",
                "Insights — خلاصهٔ مشکلات امروز + اقدام پیشنهادی (نه کپی Live)",
                "Agent Jobs — جاب‌های Agent و تایم‌لاین Gantt",
                "Indexes — سلامت ایندکس: triage، پیشنهاد، وضعیت ایندکس روی یک جدول",
                "Tables & Growth — حجم و رشد جداول/دیتابیس‌ها (تاریخچهٔ ObjSize)",
            ]),
            html.H4("دو ماژول آبجکت — عمداً جدا", className="docs-h4"),
            _p(
                html.Strong("Indexes"),
                " = کیفیت ایندکس (heap، unused، missing، frag اختیاری). ",
                html.Strong("Tables & Growth"),
                " = اندازه و رشد فضا. هر دو ممکن است یک جدول را نشان دهند، "
                "ولی سؤال‌شان فرق دارد."
            ),
            _callout(
                "info",
                "Load fragmentation در Indexes",
                "دکمهٔ اختیاری است: یک اسکن LIMITED روی physical stats برای درصد "
                "fragmentation همان جدول. روی جداول خیلی بزرگ ممکن است timeout شود؛ "
                "Recommendations و Index status بدون frag٪ هم کار می‌کنند.",
            ),
            html.H4("ناوبری سریع", className="docs-h4"),
            _ul([
                "Home → ورود به ماژول‌ها",
                "Documentation → همین راهنما (هر موضوع یک صفحه جدا)",
            ]),
        ),
        "status": _page_shell(
            "status",
            "Status (وضعیت نشست)",
            _p(
                "وضعیت از ",
                html.Code("sys.dm_exec_requests"),
                " / ",
                html.Code("sys.dm_exec_sessions"),
                " می‌آید. در UI به‌صورت pill رنگی دیده می‌شود."
            ),
            _kv_table([(k, v) for k, v in status_rows]),
            _callout(
                "info",
                "blocked",
                "اگر نشست منتظر قفل باشد، حتی اگر Status خام suspended باشد، "
                "UI ممکن است pill «blocked» نشان دهد وقتی blocking_session_id > 0 باشد.",
            ),
        ),
        "command": _page_shell(
            "command",
            "Command / Action",
            _p(
                "Command نوع دستور فعلی DMV است (SELECT، INSERT، …). "
                "در Blocking/Lookup برچسب Action از Command و متن SQL حدس زده می‌شود "
                "(مثلاً داخل EXECUTE ممکن است UPDATE دیده شود)."
            ),
            _kv_table([(k, v) for k, v in command_rows]),
            _callout(
                "warn",
                "IDLE + OPEN TRAN",
                "نشست Sleeping/Awaiting Command ولی تراکنش باز دارد — "
                "اغلب Head Blocker واقعی است. متن SQL ممکن است خالی باشد.",
            ),
        ),
        "wait": _page_shell(
            "wait",
            "Wait types",
            _p(
                "وقتی Status = suspended، Wait type می‌گوید نشست منتظر چه منبعی است. "
                "روی هر مورد بزنید تا توضیح کامل و یک مثال باز شود. "
                "در جداول Activity همان خلاصه با hover دیده می‌شود."
            ),
            _p(
                "پیشوندهای رایج: ",
                html.Code("LCK_M_*"),
                " قفل · ",
                html.Code("PAGEIOLATCH_*"),
                " IO دیسک · ",
                html.Code("PAGELATCH_*"),
                " رقابت حافظه · ",
                html.Code("PREEMPTIVE_*"),
                " فراخوانی خارج از SQL.",
            ),
            _docs_accordion(
                wait_entries,
                hint="برای باز/بسته کردن، روی نام Wait کلیک کنید.",
            ),
        ),
        "progress": _page_shell(
            "progress",
            "Progress · Rows done · Rows est.",
            _p(
                "از ",
                html.Code("sys.dm_exec_query_profiles"),
                " (در صورت دسترسی) می‌آید — نه از تخمین دستی."
            ),
            _ul([
                "Rows done: ردیف‌های پردازش‌شده تا این لحظه",
                "Rows est.: برآورد پلن برای همان عملگرها",
                "Progress: نسبت تقریبی done/est یا percent_complete از DMV",
                "وقتی کوئری تمام شده (Sleeping و بدون request فعال)، Progress می‌تواند 100% باشد",
                "اگر هنوز در حال اجرا باشد، UI عمداً 100% واقعی نشان نمی‌دهد",
            ]),
            _callout(
                "info",
                "برآورد پلن غلط است؟",
                "اگر Rows done از Rows est جلو بزند، Progress حالت «estimate exceeded» "
                "می‌گیرد و نوار زیر ۱۰۰٪ می‌ماند تا کوئری واقعاً تمام شود.",
            ),
        ),
        "eta": _page_shell(
            "eta",
            "Est. finish — تخمین ساعت اتمام",
            _p(
                "ساعت تقریبی اتمام فقط وقتی نشست فعال است و سیگنال کافی داریم محاسبه می‌شود "
                "(حداقل حدود ۳ ثانیه اجرا)."
            ),
            html.H4("چگونه حساب می‌شود؟", className="docs-h4"),
            _ul([
                "ترجیح: سرعت فعلی = Rows done ÷ زمان سپری‌شده → باقی‌مانده تا Rows est.",
                "اگر est نباشد: از percent_complete (٪ پیشرفت DMV) استفاده می‌شود",
                "≈ یعنی اعتماد پایین؛ ~ یعنی سیگنال بهتر",
            ]),
            html.H4("Estimate exceeded — ETA unknown", className="docs-h4"),
            _callout(
                "warn",
                "تحت چه شرایطی؟",
                "وقتی Rows done > Rows est باشد و نشست هنوز در حال اجراست. "
                "برآورد پلن رد شده؛ سرعت فعلی دیگر برای ساعت اتمام قابل‌اعتماد نیست. "
                "Progress و Rows done را دنبال کن.",
            ),
            _p("سایر حالت‌هایی که Est. finish خالی (—) است:"),
            _ul([
                "نشست Sleeping / بدون request فعال",
                "هنوز کمتر از چند ثانیه از شروع گذشته",
                "هنوز Rows done و ٪ پیشرفت کافی نیست",
                "تخمین باقی‌مانده غیرواقعی بلند (بیش از ۷ روز) باشد",
            ]),
        ),
        "lookup": _page_shell(
            "lookup",
            "Session Lookup",
            _p(
                "یک SPID را با DMV زنده می‌بیند: Identity، Request (Progress/ETA)، "
                "Resources، و نمودارهای Live منابع سرور + نشست."
            ),
            _ul([
                "دکمه «جزئیات SQL» → Statement فعلی + Batch + پیشرفت",
                "نمودارها فقط بعد از Lookup پر می‌شوند",
                "SPID در Blocking قابل کلیک است و به Lookup می‌رود",
                "Client IP: آدرس/پورت کلاینت + پروتکل (Shared Memory برای local machine) + endpoint سرور",
                "زمان‌ها و Elapsed در Identity با رنگ جدا از اعداد منابع نشان داده می‌شوند",
            ]),
        ),
        "blocking": _page_shell(
            "blocking",
            "Blocking",
            _p(
                "درخت Head blocker → قربانی‌ها از یال‌های DMV ساخته می‌شود. "
                "Blast radius = تعداد نشست‌های بلاک‌شده (بدون شمارش خودِ head)."
            ),
            _ul([
                "Head blocker: ریشهٔ زنجیره (معمولاً تراکنش/قفل باز)",
                "Longest Wait: بیشترین انتظار در درخت‌ها",
                "نام آبجکت قفل ممکن است بدون VIEW ANY DEFINITION resolve نشود",
            ]),
        ),
        "insights": _page_shell(
            "insights",
            "Today's Insights",
            _p(
                "رویدادهای روز از Metric Store — نه کپی Live Monitor. "
                "هر کارت دو خط دارد: مشکل و اقدام. جزئیات و کوئری‌ها پشت «جزئیات بیشتر»."
            ),
            _ul([
                "Critical / Warning / Info از قوانین (مثلاً blocking با wait بالا)",
                "Refresh دستی قوانین را یک‌بار دوباره ارزیابی می‌کند",
                "poll خودکار فقط از Store می‌خواند (فشار کمتر به DMV)",
                "«این مهم نبود» برای feedback آستانه است",
                "Blocking کوتاه‌مدت ممکن است دیگر در Live دیده نشود — snapshot در Insight می‌ماند",
            ]),
        ),
        "tables": _page_shell(
            "tables",
            "Tables & Growth",
            _p(
                "ماژول جدا از Indexes (Object Intelligence). "
                "سایز فعلی جداول/دیتابیس‌ها + رشد وقتی تاریخچهٔ روزانه موجود باشد."
            ),
            html.H4("الان چه چیزی آماده است؟", className="docs-h4"),
            _ul([
                "Overview: KPI حجم کل، ردیف‌ها، رشد پنجره، تعداد DBهای دارای heap",
                "Space by database (نوار سهم از کل)",
                "Top growers برای پنجره‌های 1d / 7d / 30d",
                "All Tables: جستجو، فیلتر DB، فیلتر Type؛ بروزرسانی فقط دستی (Refresh / Capture) — بدون auto-poll",
                "Deleted = جدول فقط در History (دیگر در کاتالوگ نیست): آخرین سایز/ردیف + Last seen + Δ اگر تاریخچه داشته",
                "منبع: کاتالوگ IdxCat_Table در صورت وجود؛ وگرنه live DMV (با سقف DB)",
                "Capture today → EXEC insight.USP_Insight_ObjSize_Capture (+ Job صبحگاهی)",
                "Retention پیش‌فرض ۳۰ روز (پاکسازی روی هر capture)",
            ]),
            html.H4("تاریخچهٔ رشد کجا ذخیره می‌شود؟", className="docs-h4"),
            _p(
                "جدول ",
                html.Code("insight.ObjSize_History"),
                " در MONITOR_DATABASE (معمولاً SmartMonitorDB). "
                "اسکریپت: ",
                html.Code("scripts/sql/SqlMonitor_ObjSizeHistory.sql"),
                " · Job: ",
                html.Code("SqlMonitor_ObjSizeHistory_Jobs.sql"),
                " (ساعت ۰۶:۳۰).",
            ),
            _callout(
                "warn",
                "بدون Capture",
                "اگر History خالی باشد، سایز فعلی کار می‌کند ولی ستون‌های Δ و Top growers خالی می‌مانند. "
                "حداقل دو captured_date متمایز لازم است (Capture در یک روز همان روز را جایگزین می‌کند).",
            ),
            html.H4("رنگ‌بندی رشد (Δ)", className="docs-h4"),
            _p(
                "نسبت به میانگین Δهای مثبت همان پنجره در همهٔ دیتابیس‌ها "
                "(نه آستانهٔ ثابت MB):"
            ),
            _ul([
                "قرمز — Δ ≥ ۲× میانگین",
                "نارنجی — Δ ≥ ۱.۲۵× میانگین",
                "سبز — رشد مثبت زیر ۱.۲۵× میانگین",
                "آبی (drop) — Δ منفی = افت حجم/ردیف",
                "خاکستری — صفر یا بدون prior",
                "Top growers: ۱۰ جدول برتر بدون اسکرول داخلی",
            ]),
            html.H4("چه چیزهایی عمداً جدا / بعدی است؟", className="docs-h4"),
            _ul([
                "Indexes / Triage / Table Explorer ایندکس → ماژول Indexes (ادغام schema نمی‌شود)",
                "Disk & DB Health (فایل، volume free، backup age) → ماژول جدا، Planned",
                "Autogrowth thrashing → فقط بعد از FileSpace_History یا Default Trace تأییدشده (نه Live V1)",
                "LOB / partition map / stale stats → deepeners بعدی در صورت نیاز",
                "پوستهٔ واحد Object Intelligence (فقط ناوبری) → Later؛ نه یکی‌کردن داده",
                "کارت Insight «جدول X رشد کرد» → بعد از vocabulary Metric Store",
            ]),
            html.H4("Approach 2 (مرز محصول)", className="docs-h4"),
            _p(
                "ماژول‌ها مستقل‌اند؛ لایهٔ داده ",
                html.Code("insight"),
                " مشترک و تدریجی است. "
                "جزئیات: docs/superpowers/specs/2026-08-08-tables-growth-design.md و "
                "2026-08-08-disk-db-health-design.md و "
                "2026-08-08-object-intelligence-nav-defer.md"
            ),
        ),
        "tips": _page_shell(
            "tips",
            "نکات عملیاتی",
            _ul([
                "Extended Events برای PRINT/history عمداً استفاده نمی‌شود مگر صریحاً تأیید شود",
                "اعداد شمارشی با جداکننده هزارتایی؛ مدت‌ها به‌صورت HH:MM:SS",
                "Toastهای وضعیت بالا-راست صفحه هستند (نه بنر تمام‌عرض)",
                "Pause همهٔ auto-refreshها را متوقف می‌کند",
            ]),
        ),
    }

    return pages.get(sid) or pages["overview"]


def build_docs_layout(locale: str = DEFAULT_LOCALE):
    loc = normalize_locale(locale)
    return html.Div(className="docs-shell", children=[
        dcc.Store(id="store-docs-page", data="overview"),
        dcc.Location(id="docs-url", refresh=False),
        html.Div(className="docs-hero", children=[
            html.H2(t("docs.title", loc), className="docs-title"),
            html.P(
                "هر موضوع یک صفحه است — از فهرست کنار انتخاب کن یا با دکمه‌های پایین جابه‌جا شو.",
                className="docs-lead",
            ),
        ]),
        html.Div(className="docs-layout", children=[
            html.Nav(className="docs-nav", children=[
                html.Div(t("docs.nav", loc), className="docs-nav-label"),
                html.Div(className="docs-nav-list", children=[
                    html.Button(
                        label,
                        id={"type": "docs-nav", "page": sid},
                        className="docs-nav-link" + (" is-active" if sid == "overview" else ""),
                        n_clicks=0,
                    )
                    for sid, label in DOCS_PAGES
                ]),
            ]),
            html.Div(className="docs-body", children=[
                html.Div(id="docs-page-host", children=build_docs_page("overview")),
                html.Div(className="docs-pager", children=[
                    html.Button(
                        "→",
                        id="docs-pager-prev",
                        className="docs-pager-btn",
                        n_clicks=0,
                    ),
                    html.Span(
                        f"1 / {len(DOCS_PAGES)}",
                        id="docs-pager-pos",
                        className="docs-pager-pos",
                    ),
                    html.Button(
                        "←",
                        id="docs-pager-next",
                        className="docs-pager-btn",
                        n_clicks=0,
                    ),
                ]),
            ]),
        ]),
    ])
