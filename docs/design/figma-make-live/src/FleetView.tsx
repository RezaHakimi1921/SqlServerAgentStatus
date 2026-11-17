import { useMemo, useState } from "react";

const servers = [
  {
    id: 1,
    name: "SQL-PROD-01",
    title: "هسته تراکنش‌های تولید",
    env: "Production",
    group: "مالی و فروش",
    status: "healthy",
    statusFa: "سالم",
    response: "۱۲ms",
    fresh: "۱۸ ثانیه پیش",
    version: "SQL Server 2022",
    databases: 18,
    jobs: 34,
    running: 6,
    alerts: 0,
    cpu: 42,
    storage: 68,
  },
  {
    id: 2,
    name: "SQL-PROD-02",
    title: "سرویس‌های مشتریان",
    env: "Production",
    group: "CRM",
    status: "degraded",
    statusFa: "نیازمند توجه",
    response: "۱۲۰ms",
    fresh: "۲ دقیقه پیش",
    version: "SQL Server 2019",
    databases: 12,
    jobs: 28,
    running: 3,
    alerts: 3,
    cpu: 73,
    storage: 84,
  },
  {
    id: 3,
    name: "SQL-REPORT-01",
    title: "انبار داده و گزارش‌گیری",
    env: "Reporting",
    group: "هوش تجاری",
    status: "healthy",
    statusFa: "سالم",
    response: "۱۸ms",
    fresh: "۳۱ ثانیه پیش",
    version: "SQL Server 2022",
    databases: 9,
    jobs: 25,
    running: 3,
    alerts: 1,
    cpu: 58,
    storage: 61,
  },
];

type Server = (typeof servers)[number];

function Glyph({
  name,
}: {
  name:
    | "server"
    | "check"
    | "warning"
    | "trend"
    | "search"
    | "grid"
    | "list"
    | "plus"
    | "close"
    | "arrow"
    | "refresh";
}) {
  const paths = {
    server: (
      <>
        <rect x="3" y="4" width="18" height="6" rx="2" />
        <rect x="3" y="14" width="18" height="6" rx="2" />
        <path d="M7 7h.01M7 17h.01M11 7h6M11 17h6" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    warning: (
      <>
        <path d="M12 3 2.8 19h18.4L12 3Z" />
        <path d="M12 9v4M12 17h.01" />
      </>
    ),
    trend: (
      <>
        <path d="m3 17 6-6 4 4 8-9" />
        <path d="M15 6h6v6" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="2" />
        <rect x="14" y="3" width="7" height="7" rx="2" />
        <rect x="3" y="14" width="7" height="7" rx="2" />
        <rect x="14" y="14" width="7" height="7" rx="2" />
      </>
    ),
    list: (
      <>
        <path d="M9 6h12M9 12h12M9 18h12" />
        <path d="M4 6h.01M4 12h.01M4 18h.01" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    arrow: <path d="m9 18 6-6-6-6" />,
    refresh: (
      <>
        <path d="M20 7V3l-2 2a9 9 0 1 0 2.2 9" />
        <path d="M20 3h-4" />
      </>
    ),
  };
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {paths[name]}
    </svg>
  );
}

export default function FleetView() {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [layout, setLayout] = useState<"cards" | "list">("cards");
  const [selected, setSelected] = useState<Server | null>(null);
  const [adding, setAdding] = useState(false);
  const visible = useMemo(
    () =>
      servers.filter(
        (server) =>
          (filter === "all" || server.status === filter) &&
          `${server.name} ${server.title} ${server.group}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [filter, query],
  );

  return (
    <>
      <section className="fleet-kpis">
        <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
          <i className="all">
            <Glyph name="server" />
          </i>
          <div>
            <b>۳</b>
            <span>کل سرورها</span>
            <small>۱۰۰٪ تحت پایش</small>
          </div>
        </button>
        <button
          className={filter === "healthy" ? "active" : ""}
          onClick={() => setFilter("healthy")}
        >
          <i className="ok">
            <Glyph name="check" />
          </i>
          <div>
            <b>۲</b>
            <span>سالم و به‌روز</span>
            <small className="good">بدون رخداد حیاتی</small>
          </div>
        </button>
        <button
          className={filter === "degraded" ? "active" : ""}
          onClick={() => setFilter("degraded")}
        >
          <i className="warn">
            <Glyph name="warning" />
          </i>
          <div>
            <b>۱</b>
            <span>نیازمند توجه</span>
            <small className="warn">۳ رخداد باز</small>
          </div>
        </button>
        <div>
          <i className="up">
            <Glyph name="trend" />
          </i>
          <div>
            <b>۹۹٫۹۸٪</b>
            <span>دسترس‌پذیری Fleet</span>
            <small>۳۰ روز گذشته</small>
          </div>
        </div>
      </section>

      <section className="fleet-notice">
        <i>
          <Glyph name="warning" />
        </i>
        <div>
          <b>یک سرور نیازمند بررسی است</b>
          <span>SQL-PROD-02 با افزایش زمان پاسخ و فضای ذخیره‌سازی بالا مواجه شده است.</span>
        </div>
        <button onClick={() => setSelected(servers[1])}>
          بررسی سرور <Glyph name="arrow" />
        </button>
      </section>

      <section className="fleet-panel">
        <header>
          <div>
            <h2>سرورهای تحت مدیریت</h2>
            <p>سلامت اتصال، تازگی داده و وضعیت Agent در تمام محیط‌ها</p>
          </div>
          <button className="fleet-primary" onClick={() => setAdding(true)}>
            <Glyph name="plus" /> افزودن سرور
          </button>
        </header>
        <div className="fleet-toolbar">
          <div className="fleet-filters">
            <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
              همه <b>۳</b>
            </button>
            <button
              className={filter === "healthy" ? "active" : ""}
              onClick={() => setFilter("healthy")}
            >
              <i className="ok" /> سالم <b>۲</b>
            </button>
            <button
              className={filter === "degraded" ? "active" : ""}
              onClick={() => setFilter("degraded")}
            >
              <i className="warn" /> نیازمند توجه <b>۱</b>
            </button>
            <button>
              <i className="down" /> خارج از دسترس <b>۰</b>
            </button>
          </div>
          <div className="fleet-tools">
            <label>
              <Glyph name="search" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="جستجوی سرور یا گروه..."
              />
            </label>
            <span>
              <button
                className={layout === "cards" ? "active" : ""}
                onClick={() => setLayout("cards")}
              >
                <Glyph name="grid" />
              </button>
              <button
                className={layout === "list" ? "active" : ""}
                onClick={() => setLayout("list")}
              >
                <Glyph name="list" />
              </button>
            </span>
          </div>
        </div>

        {layout === "cards" ? (
          <div className="fleet-cards">
            {visible.map((server) => (
              <button
                className={`fleet-server ${server.status}`}
                key={server.id}
                onClick={() => setSelected(server)}
              >
                <div className="fleet-server-head">
                  <i className={server.status}>
                    <Glyph name="server" />
                  </i>
                  <div>
                    <b>{server.name}</b>
                    <span>{server.title}</span>
                  </div>
                  <em className={server.status}>
                    <i />
                    {server.statusFa}
                  </em>
                </div>
                <div className="fleet-tags">
                  <span>{server.env}</span>
                  <span>{server.group}</span>
                  <small>{server.version}</small>
                </div>
                <div className="fleet-metrics">
                  <div>
                    <span>پاسخ اتصال</span>
                    <b>{server.response}</b>
                  </div>
                  <div>
                    <span>آخرین داده</span>
                    <b>{server.fresh}</b>
                  </div>
                  <div>
                    <span>دیتابیس</span>
                    <b>{server.databases}</b>
                  </div>
                  <div>
                    <span>Job فعال</span>
                    <b>{server.jobs}</b>
                  </div>
                </div>
                <div className="fleet-bars">
                  <div>
                    <span>
                      بار پردازشی <b>{server.cpu}٪</b>
                    </span>
                    <i>
                      <em
                        className={server.cpu > 70 ? "warn" : ""}
                        style={{ width: `${server.cpu}%` }}
                      />
                    </i>
                  </div>
                  <div>
                    <span>
                      فضای مصرفی <b>{server.storage}٪</b>
                    </span>
                    <i>
                      <em
                        className={server.storage > 80 ? "danger" : ""}
                        style={{ width: `${server.storage}%` }}
                      />
                    </i>
                  </div>
                </div>
                <footer>
                  <span>{server.running} Job در حال اجرا</span>
                  <span className={server.alerts ? "alert" : ""}>
                    {server.alerts ? `${server.alerts} رخداد باز` : "بدون رخداد باز"}
                  </span>
                  <Glyph name="arrow" />
                </footer>
              </button>
            ))}
          </div>
        ) : (
          <div className="fleet-list">
            {visible.map((server) => (
              <button key={server.id} onClick={() => setSelected(server)}>
                <i className={server.status}>
                  <Glyph name="server" />
                </i>
                <div>
                  <b>{server.name}</b>
                  <span>{server.title}</span>
                </div>
                <em className={server.status}>
                  <i />
                  {server.statusFa}
                </em>
                <span>
                  {server.env} · {server.group}
                </span>
                <span>{server.fresh}</span>
                <span>{server.storage}٪ فضای مصرفی</span>
                <b className={server.alerts ? "count alert" : "count"}>{server.alerts}</b>
                <Glyph name="arrow" />
              </button>
            ))}
          </div>
        )}
        {!visible.length && (
          <div className="fleet-empty">
            <Glyph name="search" />
            <b>سروری پیدا نشد</b>
            <span>فیلتر یا عبارت جستجو را تغییر دهید.</span>
          </div>
        )}
        <footer className="fleet-panel-foot">
          <span>
            <i /> آخرین همگام‌سازی Fleet: ۱۸ ثانیه پیش
          </span>
          <button>
            <Glyph name="refresh" /> بررسی مجدد همه سرورها
          </button>
        </footer>
      </section>

      <div className="fleet-bottom">
        <section className="fleet-panel fleet-chart">
          <header>
            <div>
              <h2>روند سلامت Fleet</h2>
              <p>دسترس‌پذیری سرورها در ۲۴ ساعت گذشته</p>
            </div>
            <span>۹۹٫۹۸٪ میانگین</span>
          </header>
          <div className="fleet-chart-body">
            <div className="y">
              <span>۱۰۰٪</span>
              <span>۹۵٪</span>
              <span>۹۰٪</span>
            </div>
            <div className="canvas">
              <i />
              <i />
              <i />
              <svg viewBox="0 0 600 110" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="ff" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#28a77b" stopOpacity=".24" />
                    <stop offset="100%" stopColor="#28a77b" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path
                  className="area"
                  d="M0 18C80 17 140 21 210 18S310 17 340 23s18 65 55 31 40-32 90-29 70-7 115-7v92H0Z"
                />
                <path
                  className="line"
                  d="M0 18C80 17 140 21 210 18S310 17 340 23s18 65 55 31 40-32 90-29 70-7 115-7"
                />
              </svg>
              <div>
                <span>۱۲ شب</span>
                <span>۶ صبح</span>
                <span>۱۲ ظهر</span>
                <span>اکنون</span>
              </div>
            </div>
          </div>
        </section>
        <section className="fleet-panel fleet-events">
          <header>
            <div>
              <h2>آخرین تغییرات وضعیت</h2>
              <p>رویدادهای Health و Collector</p>
            </div>
          </header>
          {[
            ["warning", "افزایش زمان پاسخ SQL-PROD-02", "از ۳۴ms به ۱۲۰ms · ۲ دقیقه پیش"],
            ["success", "Collector انبار داده بازیابی شد", "SQL-REPORT-01 · ۱ ساعت پیش"],
            ["info", "Snapshot روزانه ثبت شد", "۳ سرور، ۳۹ دیتابیس · ۲ ساعت پیش"],
          ].map((x) => (
            <div className="fleet-event" key={x[1]}>
              <i className={x[0]}>
                <Glyph
                  name={x[0] === "success" ? "check" : x[0] === "warning" ? "warning" : "server"}
                />
              </i>
              <div>
                <b>{x[1]}</b>
                <span>{x[2]}</span>
              </div>
            </div>
          ))}
        </section>
      </div>

      {selected && (
        <div
          className="fleet-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setSelected(null);
          }}
        >
          <aside className="fleet-drawer">
            <header>
              <div>
                <i className={selected.status}>
                  <Glyph name="server" />
                </i>
                <span>
                  <small>جزئیات سرور</small>
                  <b>{selected.name}</b>
                </span>
              </div>
              <button onClick={() => setSelected(null)}>
                <Glyph name="close" />
              </button>
            </header>
            <main>
              <div className="fleet-hero">
                <div>
                  <em className={selected.status}>
                    <i />
                    {selected.statusFa}
                  </em>
                  <h3>{selected.title}</h3>
                  <span>
                    {selected.env} · {selected.group}
                  </span>
                </div>
                <b>
                  {selected.response}
                  <small>زمان پاسخ</small>
                </b>
              </div>
              {selected.status === "degraded" && (
                <div className="fleet-detail-alert">
                  <Glyph name="warning" />
                  <div>
                    <b>سلامت سرور کاهش یافته است</b>
                    <span>فضای مصرفی و زمان پاسخ از محدوده معمول بالاتر رفته‌اند.</span>
                  </div>
                </div>
              )}
              <div className="fleet-detail-grid">
                <div>
                  <span>نسخه موتور</span>
                  <b>{selected.version}</b>
                </div>
                <div>
                  <span>آخرین Poll موفق</span>
                  <b>{selected.fresh}</b>
                </div>
                <div>
                  <span>دیتابیس‌ها</span>
                  <b>{selected.databases}</b>
                </div>
                <div>
                  <span>Jobهای فعال</span>
                  <b>{selected.jobs}</b>
                </div>
              </div>
              <h4>وضعیت مؤلفه‌ها</h4>
              {[
                ["اتصال SQL Server", "سالم", selected.response],
                ["دسترسی SQL Agent", "سالم", `${selected.jobs} Job`],
                ["Collector داده", "فعال", selected.fresh],
                [
                  "ظرفیت ذخیره‌سازی",
                  selected.storage > 80 ? "نیازمند توجه" : "سالم",
                  `${selected.storage}٪ مصرف`,
                ],
              ].map((row, i) => (
                <div className="fleet-component" key={row[0]}>
                  <i className={i === 3 && selected.storage > 80 ? "warn" : "ok"}>
                    <Glyph name={i === 3 && selected.storage > 80 ? "warning" : "check"} />
                  </i>
                  <div>
                    <b>{row[0]}</b>
                    <span>{row[2]}</span>
                  </div>
                  <em>{row[1]}</em>
                </div>
              ))}
            </main>
            <footer>
              <button onClick={() => setSelected(null)}>بستن</button>
              <button className="primary">
                ورود به نمای سرور <Glyph name="arrow" />
              </button>
            </footer>
          </aside>
        </div>
      )}

      {adding && (
        <div
          className="fleet-overlay modal-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setAdding(false);
          }}
        >
          <div className="fleet-modal">
            <header>
              <div>
                <b>افزودن SQL Server</b>
                <span>اتصال جدیدی به Fleet اضافه کنید</span>
              </div>
              <button onClick={() => setAdding(false)}>
                <Glyph name="close" />
              </button>
            </header>
            <div className="fleet-steps">
              <span className="active">
                <b>۱</b> مشخصات اتصال
              </span>
              <i />
              <span>
                <b>۲</b> بررسی دسترسی
              </span>
              <i />
              <span>
                <b>۳</b> تنظیم پایش
              </span>
            </div>
            <main>
              <div className="fleet-form-row">
                <label>
                  نام نمایشی
                  <input placeholder="مثلاً سرور تولید مالی" />
                </label>
                <label>
                  محیط
                  <select defaultValue="production">
                    <option value="production">Production</option>
                    <option value="staging">Staging</option>
                    <option value="dev">Development</option>
                  </select>
                </label>
              </div>
              <label>
                آدرس Server / Instance
                <input placeholder="SERVER\\INSTANCE یا IP,PORT" />
              </label>
              <div className="fleet-form-row">
                <label>
                  نام کاربری
                  <input placeholder="monitor_user" />
                </label>
                <label>
                  پایگاه داده پیش‌فرض
                  <input defaultValue="msdb" />
                </label>
              </div>
              <div className="fleet-safe">
                <Glyph name="check" />
                <div>
                  <b>اتصال فقط خواندنی</b>
                  <span>رمز عبور در Secret Store نگه‌داری می‌شود و در پنل نمایش داده نخواهد شد.</span>
                </div>
              </div>
            </main>
            <footer>
              <button onClick={() => setAdding(false)}>انصراف</button>
              <button className="primary">
                ادامه و تست اتصال <Glyph name="arrow" />
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
