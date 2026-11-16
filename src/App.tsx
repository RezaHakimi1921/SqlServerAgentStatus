import { useMemo, useState } from "react";
import FleetView from "./FleetView";

type IconName =
  | "grid"
  | "database"
  | "jobs"
  | "timeline"
  | "alert"
  | "history"
  | "health"
  | "settings"
  | "search"
  | "bell"
  | "refresh"
  | "chevron"
  | "close"
  | "check"
  | "clock"
  | "play"
  | "more"
  | "pause"
  | "server"
  | "calendar"
  | "filter"
  | "external"
  | "trend"
  | "layers"
  | "menu"
  | "warning";

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="2" />
        <rect x="14" y="3" width="7" height="7" rx="2" />
        <rect x="3" y="14" width="7" height="7" rx="2" />
        <rect x="14" y="14" width="7" height="7" rx="2" />
      </>
    ),
    database: (
      <>
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
        <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
      </>
    ),
    jobs: (
      <>
        <rect x="4" y="3" width="16" height="18" rx="3" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </>
    ),
    timeline: (
      <>
        <path d="M4 18V6M4 15h4V9h4v3h4V5h4" />
        <path d="M3 19h18" />
      </>
    ),
    alert: (
      <>
        <path d="M12 3 2.8 19h18.4L12 3Z" />
        <path d="M12 9v4M12 17h.01" />
      </>
    ),
    history: (
      <>
        <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
        <path d="M3 3v5h5M12 7v5l3 2" />
      </>
    ),
    health: (
      <>
        <path d="M3 12h4l2.2-5 4.1 10 2.2-5H21" />
        <path d="M19.7 5.2a4.5 4.5 0 0 0-6.4 0L12 6.5l-1.3-1.3a4.5 4.5 0 0 0-6.4 6.4L12 19l7.7-7.4a4.5 4.5 0 0 0 0-6.4Z" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    bell: (
      <>
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 7V3l-2 2a9 9 0 1 0 2.2 9" />
        <path d="M20 3h-4" />
      </>
    ),
    chevron: <path d="m9 18 6-6-6-6" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    check: <path d="m5 12 4 4L19 6" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    play: <path d="m8 5 11 7-11 7V5Z" />,
    more: (
      <>
        <circle cx="5" cy="12" r="1" />
        <circle cx="12" cy="12" r="1" />
        <circle cx="19" cy="12" r="1" />
      </>
    ),
    pause: (
      <>
        <path d="M9 5v14M15 5v14" />
      </>
    ),
    server: (
      <>
        <rect x="3" y="4" width="18" height="6" rx="2" />
        <rect x="3" y="14" width="18" height="6" rx="2" />
        <path d="M7 7h.01M7 17h.01M11 7h6M11 17h6" />
      </>
    ),
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="3" />
        <path d="M8 3v4M16 3v4M3 10h18" />
      </>
    ),
    filter: <path d="M3 5h18l-7 8v5l-4 2v-7L3 5Z" />,
    external: (
      <>
        <path d="M14 3h7v7M10 14 21 3" />
        <path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5" />
      </>
    ),
    trend: (
      <>
        <path d="m3 17 6-6 4 4 8-9" />
        <path d="M15 6h6v6" />
      </>
    ),
    layers: (
      <>
        <path d="m12 2 9 5-9 5-9-5 9-5Z" />
        <path d="m3 12 9 5 9-5M3 17l9 5 9-5" />
      </>
    ),
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    warning: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v6M12 17h.01" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
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

const jobs = [
  {
    id: 1,
    name: "Daily_Sales_ETL",
    group: "فروش و عملیات",
    server: "SQL-PROD-01",
    status: "running",
    statusFa: "در حال اجرا",
    duration: "۱۲:۴۶",
    next: "هر روز، ۰۲:۰۰",
    last: "امروز، ۰۹:۴۲",
    progress: 68,
    owner: "تیم داده",
    step: "انتقال داده‌های فروش",
  },
  {
    id: 2,
    name: "Backup_Full_Production",
    group: "پشتیبان‌گیری",
    server: "SQL-PROD-01",
    status: "success",
    statusFa: "موفق",
    duration: "۰۸:۲۱",
    next: "فردا، ۰۱:۰۰",
    last: "امروز، ۰۱:۰۹",
    progress: 100,
    owner: "DBA",
    step: "Verify backup",
  },
  {
    id: 3,
    name: "Sync_CRM_Customers",
    group: "یکپارچه‌سازی",
    server: "SQL-PROD-02",
    status: "failed",
    statusFa: "ناموفق",
    duration: "۰۳:۱۴",
    next: "امروز، ۱۰:۳۰",
    last: "امروز، ۰۹:۱۵",
    progress: 42,
    owner: "تیم CRM",
    step: "Merge customers",
  },
  {
    id: 4,
    name: "Index_Maintenance_Weekly",
    group: "نگه‌داری",
    server: "SQL-REPORT-01",
    status: "success",
    statusFa: "موفق",
    duration: "۲۶:۰۵",
    next: "جمعه، ۲۳:۰۰",
    last: "جمعه، ۲۳:۲۶",
    progress: 100,
    owner: "DBA",
    step: "Rebuild indexes",
  },
  {
    id: 5,
    name: "Calculate_Daily_KPIs",
    group: "هوش تجاری",
    server: "SQL-REPORT-01",
    status: "retry",
    statusFa: "در حال تلاش مجدد",
    duration: "۰۶:۳۸",
    next: "امروز، ۱۰:۱۵",
    last: "امروز، ۱۰:۰۲",
    progress: 25,
    owner: "BI",
    step: "Calculate revenue KPI",
  },
  {
    id: 6,
    name: "Archive_Audit_Logs",
    group: "نگه‌داری",
    server: "SQL-PROD-02",
    status: "disabled",
    statusFa: "غیرفعال",
    duration: "—",
    next: "بدون زمان‌بندی",
    last: "۳ روز پیش",
    progress: 0,
    owner: "امنیت",
    step: "Archive logs",
  },
];

const nav = [
  { key: "overview", label: "نمای کلی", icon: "grid" as IconName },
  { key: "health", label: "مدیریت سرورها", icon: "server" as IconName, badge: "۳" },
  { key: "jobs", label: "جاب‌ها", icon: "jobs" as IconName, badge: "۸۷" },
  { key: "timeline", label: "خط زمانی", icon: "timeline" as IconName },
  { key: "incidents", label: "رخدادها", icon: "alert" as IconName, badge: "۴" },
  { key: "history", label: "تاریخچه و روند", icon: "history" as IconName },
];

const statusMeta: Record<string, { label: string; className: string }> = {
  all: { label: "همه وضعیت‌ها", className: "" },
  running: { label: "در حال اجرا", className: "running" },
  success: { label: "موفق", className: "success" },
  failed: { label: "ناموفق", className: "failed" },
  retry: { label: "تلاش مجدد", className: "retry" },
  disabled: { label: "غیرفعال", className: "disabled" },
};

function App() {
  const [activeNav, setActiveNav] = useState("overview");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [selectedJob, setSelectedJob] = useState<(typeof jobs)[number] | null>(null);
  const [notifications, setNotifications] = useState(false);
  const [settings, setSettings] = useState(false);
  const [paused, setPaused] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [toast, setToast] = useState("");

  const filteredJobs = useMemo(
    () =>
      jobs.filter(
        (j) =>
          (filter === "all" || j.status === filter) &&
          (j.name.toLowerCase().includes(query.toLowerCase()) ||
            j.group.includes(query) ||
            j.server.toLowerCase().includes(query.toLowerCase())),
      ),
    [query, filter],
  );

  const showToast = (text: string) => {
    setToast(text);
    window.setTimeout(() => setToast(""), 2400);
  };

  const switchNav = (key: string) => {
    setActiveNav(key);
    setMobileNav(false);
    if (key !== "overview" && key !== "jobs" && key !== "health")
      showToast("این نما در نسخه نمایشی به نمای کلی متصل است");
  };

  return (
    <div className="app-shell" dir="rtl">
      {mobileNav && (
        <button
          className="mobile-overlay"
          aria-label="بستن منو"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <Icon name="database" size={22} />
          </div>
          <div>
            <strong>SQL Agent</strong>
            <span>مرکز پایش عملیات</span>
          </div>
        </div>

        <div className="sidebar-section-label">فضای کاری</div>
        <nav className="side-nav" aria-label="منوی اصلی">
          {nav.map((item) => (
            <button
              key={item.key}
              className={activeNav === item.key ? "active" : ""}
              onClick={() => switchNav(item.key)}
            >
              <Icon name={item.icon} size={19} />
              <span>{item.label}</span>
              {item.badge && (
                <b className={item.key === "incidents" ? "danger" : ""}>{item.badge}</b>
              )}
            </button>
          ))}
        </nav>

        <div className="sidebar-spacer" />
        <div className="connection-card">
          <div className="connection-head">
            <span className="status-light" />
            <b>اتصال پایدار</b>
            <span>۳/۳</span>
          </div>
          <div className="mini-progress">
            <i />
          </div>
          <small>آخرین واکشی موفق: ۱۸ ثانیه پیش</small>
        </div>
        <button className="sidebar-settings" onClick={() => setSettings(true)}>
          <Icon name="settings" size={19} />
          <span>تنظیمات سامانه</span>
          <Icon name="chevron" size={17} />
        </button>
        <div className="user-card">
          <div className="avatar">رح</div>
          <div>
            <b>رضا حکیمی</b>
            <span>مدیر سیستم</span>
          </div>
          <Icon name="more" size={18} />
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileNav(true)}>
            <Icon name="menu" />
          </button>
          <div className="server-select">
            <Icon name="server" size={18} />
            <div>
              <small>محدوده نمایش</small>
              <b>همه سرورها</b>
            </div>
            <Icon name="chevron" size={16} />
          </div>
          <div className="topbar-actions">
            <div className={`live-pill ${paused ? "paused" : ""}`}>
              <i />
              {paused ? "پایش متوقف است" : "پایش زنده"}
            </div>
            <button
              className="icon-button has-badge"
              aria-label="اعلان‌ها"
              onClick={() => setNotifications(true)}
            >
              <Icon name="bell" size={19} />
              <span>۴</span>
            </button>
            <button
              className="refresh-button"
              onClick={() => showToast("اطلاعات با موفقیت بروزرسانی شد")}
            >
              <Icon name="refresh" size={17} /> بروزرسانی
            </button>
          </div>
        </header>

        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">سه‌شنبه ۲۸ آبان، ساعت ۱۰:۱۲</div>
              <h1>
                {activeNav === "jobs"
                  ? "فهرست جاب‌ها"
                  : activeNav === "health"
                    ? "مدیریت سرورها"
                    : "صبح بخیر، رضا"}
              </h1>
              <p>
                {activeNav === "health"
                  ? "سلامت، دسترس‌پذیری و تازگی داده تمام SQL Serverها را مدیریت کنید."
                  : "وضعیت SQL Server Agentهای شما در یک نگاه؛ همه‌چیز تحت کنترل است."}
              </p>
            </div>
            <div className="heading-actions">
              <button className="button secondary" onClick={() => setPaused(!paused)}>
                <Icon name={paused ? "play" : "pause"} size={17} />
                {paused ? "ادامه پایش" : "توقف موقت"}
              </button>
              <button className="button primary" onClick={() => setSettings(true)}>
                <Icon name="settings" size={17} /> مدیریت اتصال‌ها
              </button>
            </div>
          </div>

          {activeNav === "health" ? (
            <FleetView />
          ) : (
            <>
              <section className="freshness-banner">
                <div className="freshness-icon">
                  <Icon name="check" size={18} />
                </div>
                <div>
                  <b>داده‌ها به‌روز و قابل اعتماد هستند</b>
                  <span>هر ۳۰ ثانیه از ۳ سرور واکشی می‌شود؛ آخرین پاسخ موفق در ۱۰:۱۱:۴۲</span>
                </div>
                <button onClick={() => switchNav("health")}>
                  مشاهده سلامت سرورها <Icon name="chevron" size={15} />
                </button>
              </section>

              <section className="stats-grid">
                <button
                  className={`stat-card running ${filter === "running" ? "selected" : ""}`}
                  onClick={() => setFilter("running")}
                >
                  <div className="stat-top">
                    <span className="stat-icon">
                      <Icon name="play" size={19} />
                    </span>
                    <span className="trend up">
                      +۲ از دیروز <Icon name="trend" size={14} />
                    </span>
                  </div>
                  <strong>۱۲</strong>
                  <span>در حال اجرا</span>
                  <small>از مجموع ۸۷ جاب فعال</small>
                  <div className="spark bars">
                    {[5, 8, 6, 12, 9, 15, 13, 18, 14, 20, 17, 22].map((h, i) => (
                      <i key={i} style={{ height: h }} />
                    ))}
                  </div>
                </button>
                <button
                  className={`stat-card success ${filter === "success" ? "selected" : ""}`}
                  onClick={() => setFilter("success")}
                >
                  <div className="stat-top">
                    <span className="stat-icon">
                      <Icon name="check" size={19} />
                    </span>
                    <span className="trend">۹۶٫۸٪ نرخ موفقیت</span>
                  </div>
                  <strong>۶۸</strong>
                  <span>اجرای موفق امروز</span>
                  <small>۴ اجرای بیشتر از میانگین</small>
                  <svg className="spark line" viewBox="0 0 140 30">
                    <path d="M2 25C15 22 18 12 31 17S48 23 58 13s18 7 29-1 16-7 24-3 18-3 27-7" />
                    <path
                      className="fill"
                      d="M2 25C15 22 18 12 31 17S48 23 58 13s18 7 29-1 16-7 24-3 18-3 27-7V30H2Z"
                    />
                  </svg>
                </button>
                <button
                  className={`stat-card failed ${filter === "failed" ? "selected" : ""}`}
                  onClick={() => setFilter("failed")}
                >
                  <div className="stat-top">
                    <span className="stat-icon">
                      <Icon name="warning" size={19} />
                    </span>
                    <span className="trend down">۲ مورد جدید</span>
                  </div>
                  <strong>۴</strong>
                  <span>نیازمند رسیدگی</span>
                  <small>۱ مورد با شدت بحرانی</small>
                  <div className="incident-mini">
                    <span />
                    <span />
                    <span />
                    <i />
                    <i />
                  </div>
                </button>
                <button className="stat-card duration" onClick={() => switchNav("history")}>
                  <div className="stat-top">
                    <span className="stat-icon">
                      <Icon name="clock" size={19} />
                    </span>
                    <span className="trend">−۱۲٪ این هفته</span>
                  </div>
                  <strong>۰۶:۳۲</strong>
                  <span>میانگین مدت اجرا</span>
                  <small>۲۱ ثانیه بهتر از هفته قبل</small>
                  <svg className="spark line" viewBox="0 0 140 30">
                    <path d="M2 7c12 2 17 13 30 8s19-2 29 3 20 2 30 4 18-9 26-7 12-4 21 2" />
                    <path
                      className="fill"
                      d="M2 7c12 2 17 13 30 8s19-2 29 3 20 2 30 4 18-9 26-7 12-4 21 2v13H2Z"
                    />
                  </svg>
                </button>
              </section>

              <section className="workspace-card">
                <div className="section-head">
                  <div>
                    <h2>وضعیت جاب‌ها</h2>
                    <p>آخرین وضعیت اجرا در تمام سرورها</p>
                  </div>
                  <div className="view-tabs">
                    <button className="active">
                      <Icon name="jobs" size={16} /> فهرست
                    </button>
                    <button onClick={() => switchNav("timeline")}>
                      <Icon name="timeline" size={16} /> خط زمانی
                    </button>
                  </div>
                </div>
                <div className="table-toolbar">
                  <div className="status-filters">
                    {Object.entries(statusMeta)
                      .slice(0, 5)
                      .map(([key, value]) => (
                        <button
                          key={key}
                          className={filter === key ? "active" : ""}
                          onClick={() => setFilter(key)}
                        >
                          {value.label}
                          {key !== "all" && (
                            <span>{jobs.filter((j) => j.status === key).length}</span>
                          )}
                        </button>
                      ))}
                  </div>
                  <div className="toolbar-tools">
                    <label className="search">
                      <Icon name="search" size={18} />
                      <input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="جستجوی نام جاب یا سرور..."
                      />
                      {query && (
                        <button onClick={() => setQuery("")}>
                          <Icon name="close" size={14} />
                        </button>
                      )}
                    </label>
                    <button className="icon-button">
                      <Icon name="filter" size={17} />
                    </button>
                  </div>
                </div>

                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>نام جاب</th>
                        <th>وضعیت</th>
                        <th>سرور</th>
                        <th>مدت / پیشرفت</th>
                        <th>آخرین اجرا</th>
                        <th>اجرای بعدی</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredJobs.map((job) => (
                        <tr key={job.id} onClick={() => setSelectedJob(job)}>
                          <td>
                            <div className="job-name">
                              <span className={`job-symbol ${job.status}`}>
                                <Icon
                                  name={
                                    job.status === "running"
                                      ? "play"
                                      : job.status === "failed"
                                        ? "warning"
                                        : "layers"
                                  }
                                  size={17}
                                />
                              </span>
                              <div>
                                <b>{job.name}</b>
                                <small>
                                  {job.group} · {job.owner}
                                </small>
                              </div>
                            </div>
                          </td>
                          <td>
                            <span className={`status-badge ${job.status}`}>
                              <i />
                              {job.statusFa}
                            </span>
                          </td>
                          <td>
                            <span className="server-name">{job.server}</span>
                          </td>
                          <td>
                            <div className="duration-cell">
                              <span>{job.duration}</span>
                              <div className="progress">
                                <i className={job.status} style={{ width: `${job.progress}%` }} />
                              </div>
                              {job.status === "running" && <small>برآورد</small>}
                            </div>
                          </td>
                          <td>{job.last}</td>
                          <td>{job.next}</td>
                          <td>
                            <button className="row-action">
                              <Icon name="chevron" size={17} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!filteredJobs.length && (
                    <div className="empty-state">
                      <Icon name="search" size={30} />
                      <b>نتیجه‌ای پیدا نشد</b>
                      <span>عبارت جستجو یا فیلتر وضعیت را تغییر دهید.</span>
                    </div>
                  )}
                </div>
                <div className="table-footer">
                  <span>نمایش {filteredJobs.length} مورد از ۸۷ جاب</span>
                  <button>
                    مشاهده همه جاب‌ها <Icon name="chevron" size={15} />
                  </button>
                </div>
              </section>

              <div className="lower-grid">
                <section className="workspace-card incidents-card">
                  <div className="section-head">
                    <div>
                      <h2>رخدادهای نیازمند توجه</h2>
                      <p>موارد جدید و تأییدنشده</p>
                    </div>
                    <button className="text-button" onClick={() => switchNav("incidents")}>
                      مشاهده همه <Icon name="chevron" size={15} />
                    </button>
                  </div>
                  {[
                    [
                      "Sync_CRM_Customers",
                      "خطا در Step «Merge customers»",
                      "بحرانی",
                      "۹ دقیقه پیش",
                      "critical",
                    ],
                    [
                      "Calculate_Daily_KPIs",
                      "مدت اجرا ۲٫۴ برابر مقدار معمول است",
                      "هشدار",
                      "۲۴ دقیقه پیش",
                      "warning",
                    ],
                    ["SQL-PROD-02", "تأخیر در آخرین واکشی داده", "اطلاع", "۳۸ دقیقه پیش", "info"],
                  ].map((x, i) => (
                    <button className="incident-row" key={i}>
                      <span className={`incident-icon ${x[4]}`}>
                        <Icon name={x[4] === "critical" ? "alert" : "warning"} size={18} />
                      </span>
                      <div>
                        <b>{x[0]}</b>
                        <span>{x[1]}</span>
                      </div>
                      <div className="incident-meta">
                        <em className={x[4]}>{x[2]}</em>
                        <small>{x[3]}</small>
                      </div>
                      <Icon name="chevron" size={16} />
                    </button>
                  ))}
                </section>
                <section className="workspace-card servers-card">
                  <div className="section-head">
                    <div>
                      <h2>سلامت سرورها</h2>
                      <p>وضعیت اتصال و تازگی داده</p>
                    </div>
                    <button className="text-button" onClick={() => switchNav("health")}>
                      جزئیات <Icon name="chevron" size={15} />
                    </button>
                  </div>
                  {[
                    ["SQL-PROD-01", "Production", "سالم", "۱۲ms", "online", 48],
                    ["SQL-PROD-02", "Production", "کند", "۱۲۰ms", "slow", 76],
                    ["SQL-REPORT-01", "Reporting", "سالم", "۱۸ms", "online", 61],
                  ].map((s, i) => (
                    <div className="server-row" key={i}>
                      <span className={`server-icon ${s[4]}`}>
                        <Icon name="server" size={19} />
                      </span>
                      <div>
                        <b>{s[0]}</b>
                        <small>{s[1]}</small>
                      </div>
                      <div className="server-load">
                        <span>
                          بار Agent <b>{s[5]}٪</b>
                        </span>
                        <i>
                          <em style={{ width: `${s[5]}%` }} />
                        </i>
                      </div>
                      <span className={`health-badge ${s[4]}`}>
                        <i />
                        {s[2]} · {s[3]}
                      </span>
                    </div>
                  ))}
                </section>
              </div>
            </>
          )}
        </div>
      </main>

      {selectedJob && (
        <div
          className="drawer-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setSelectedJob(null);
          }}
        >
          <aside className="drawer">
            <div className="drawer-head">
              <div>
                <span className={`job-symbol ${selectedJob.status}`}>
                  <Icon name="jobs" size={18} />
                </span>
                <div>
                  <small>جزئیات جاب</small>
                  <h2>{selectedJob.name}</h2>
                </div>
              </div>
              <button className="icon-button" onClick={() => setSelectedJob(null)}>
                <Icon name="close" />
              </button>
            </div>
            <div className="drawer-body">
              <div className="detail-status">
                <span className={`status-badge ${selectedJob.status}`}>
                  <i />
                  {selectedJob.statusFa}
                </span>
                <small>آخرین بروزرسانی: همین حالا</small>
              </div>
              <div className="detail-grid">
                <div>
                  <span>سرور</span>
                  <b>{selectedJob.server}</b>
                </div>
                <div>
                  <span>مالک</span>
                  <b>{selectedJob.owner}</b>
                </div>
                <div>
                  <span>مدت اجرا</span>
                  <b>{selectedJob.duration}</b>
                </div>
                <div>
                  <span>اجرای بعدی</span>
                  <b>{selectedJob.next}</b>
                </div>
              </div>
              <div className="detail-section">
                <div className="detail-title">
                  <h3>اجرای جاری</h3>
                  <span>{selectedJob.progress}٪</span>
                </div>
                <div className="large-progress">
                  <i className={selectedJob.status} style={{ width: `${selectedJob.progress}%` }} />
                </div>
                <div className="step-line">
                  <span className="step-check">
                    <Icon name="check" size={14} />
                  </span>
                  <div>
                    <b>دریافت و اعتبارسنجی داده</b>
                    <small>با موفقیت در ۲ دقیقه تکمیل شد</small>
                  </div>
                </div>
                <div className="step-line active">
                  <span>۲</span>
                  <div>
                    <b>{selectedJob.step}</b>
                    <small>در حال پردازش...</small>
                  </div>
                </div>
                <div className="step-line muted">
                  <span>۳</span>
                  <div>
                    <b>ثبت نتیجه و پاکسازی</b>
                    <small>در انتظار اجرا</small>
                  </div>
                </div>
              </div>
              <div className="detail-section">
                <div className="detail-title">
                  <h3>اجراهای اخیر</h3>
                  <button>مشاهده تاریخچه</button>
                </div>
                {["امروز، ۰۹:۴۲", "دیروز، ۰۲:۰۶", "۲۶ آبان، ۰۲:۰۵"].map((d, i) => (
                  <div className="run-row" key={d}>
                    <span
                      className={i === 0 && selectedJob.status === "failed" ? "failed" : "success"}
                    >
                      <Icon
                        name={i === 0 && selectedJob.status === "failed" ? "close" : "check"}
                        size={14}
                      />
                    </span>
                    <b>{d}</b>
                    <small>{i === 0 ? selectedJob.duration : "۰۵:۴۲"}</small>
                    <Icon name="chevron" size={15} />
                  </div>
                ))}
              </div>
            </div>
            <div className="drawer-footer">
              <button className="button secondary" onClick={() => setSelectedJob(null)}>
                بستن
              </button>
              <button className="button primary">
                <Icon name="external" size={16} /> مشاهده جزئیات کامل
              </button>
            </div>
          </aside>
        </div>
      )}

      {notifications && (
        <div className="popover notification-popover">
          <div className="popover-head">
            <div>
              <b>اعلان‌ها</b>
              <span>۴ مورد خوانده‌نشده</span>
            </div>
            <button onClick={() => setNotifications(false)}>
              <Icon name="close" />
            </button>
          </div>
          <div className="popover-body">
            <div className="notif-item unread">
              <span className="critical">
                <Icon name="alert" size={17} />
              </span>
              <div>
                <b>اجرای ناموفق جاب CRM</b>
                <p>Sync_CRM_Customers در SQL-PROD-02 ناموفق بود.</p>
                <small>۹ دقیقه پیش</small>
              </div>
            </div>
            <div className="notif-item unread">
              <span className="warning">
                <Icon name="clock" size={17} />
              </span>
              <div>
                <b>اجرای طولانی‌تر از معمول</b>
                <p>Calculate_Daily_KPIs از baseline عبور کرده است.</p>
                <small>۲۴ دقیقه پیش</small>
              </div>
            </div>
            <div className="notif-item">
              <span>
                <Icon name="server" size={17} />
              </span>
              <div>
                <b>اتصال بازیابی شد</b>
                <p>ارتباط SQL-REPORT-01 به حالت عادی بازگشت.</p>
                <small>۱ ساعت پیش</small>
              </div>
            </div>
          </div>
          <button
            className="popover-footer"
            onClick={() => {
              setNotifications(false);
              switchNav("incidents");
            }}
          >
            رفتن به مرکز رخدادها
          </button>
        </div>
      )}

      {settings && (
        <div
          className="modal-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setSettings(false);
          }}
        >
          <div className="modal">
            <div className="popover-head">
              <div>
                <b>مدیریت اتصال‌ها</b>
                <span>تنظیم سرورها و دوره بروزرسانی</span>
              </div>
              <button onClick={() => setSettings(false)}>
                <Icon name="close" />
              </button>
            </div>
            <div className="modal-body">
              <label>
                نام سرور
                <span>
                  <input defaultValue="SQL-PROD-01" />
                  <Icon name="server" size={17} />
                </span>
              </label>
              <div className="form-row">
                <label>
                  پایگاه داده
                  <span>
                    <input defaultValue="msdb" />
                  </span>
                </label>
                <label>
                  دوره بروزرسانی
                  <span>
                    <select defaultValue="30">
                      <option value="15">هر ۱۵ ثانیه</option>
                      <option value="30">هر ۳۰ ثانیه</option>
                      <option value="60">هر یک دقیقه</option>
                    </select>
                  </span>
                </label>
              </div>
              <div className="test-result">
                <Icon name="check" size={17} />
                <div>
                  <b>اتصال با موفقیت برقرار است</b>
                  <span>زمان پاسخ: ۱۲ میلی‌ثانیه · دسترسی فقط خواندنی</span>
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button className="button secondary" onClick={() => showToast("تست اتصال موفق بود")}>
                تست اتصال
              </button>
              <button
                className="button primary"
                onClick={() => {
                  setSettings(false);
                  showToast("تنظیمات ذخیره شد");
                }}
              >
                ذخیره تغییرات
              </button>
            </div>
          </div>
        </div>
      )}
      {toast && (
        <div className="toast">
          <Icon name="check" size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}

export default App;
