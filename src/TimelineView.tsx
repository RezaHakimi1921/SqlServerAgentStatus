import { useMemo, useState } from "react";

const runs = [
  {
    id: 1,
    name: "Daily_Sales_ETL",
    server: "SQL-PROD-01",
    status: "running",
    statusFa: "در حال اجرا",
    start: 7.4,
    duration: 3.2,
    time: "۰۷:۲۴",
    end: "در حال اجرا",
    step: "انتقال داده‌های فروش",
  },
  {
    id: 2,
    name: "Backup_Full_Production",
    server: "SQL-PROD-01",
    status: "success",
    statusFa: "موفق",
    start: 1,
    duration: 2.1,
    time: "۰۱:۰۰",
    end: "۰۳:۰۶",
    step: "Verify backup",
  },
  {
    id: 3,
    name: "Sync_CRM_Customers",
    server: "SQL-PROD-02",
    status: "failed",
    statusFa: "ناموفق",
    start: 9.15,
    duration: 1.3,
    time: "۰۹:۰۹",
    end: "۱۰:۲۷",
    step: "Merge customers",
  },
  {
    id: 4,
    name: "Index_Maintenance_Weekly",
    server: "SQL-REPORT-01",
    status: "success",
    statusFa: "موفق",
    start: 2.7,
    duration: 3.8,
    time: "۰۲:۴۲",
    end: "۰۶:۳۰",
    step: "Rebuild indexes",
  },
  {
    id: 5,
    name: "Calculate_Daily_KPIs",
    server: "SQL-REPORT-01",
    status: "retry",
    statusFa: "تلاش مجدد",
    start: 10.2,
    duration: 2.5,
    time: "۱۰:۱۲",
    end: "در حال اجرا",
    step: "Calculate revenue KPI",
  },
  {
    id: 6,
    name: "Cleanup_Staging_Data",
    server: "SQL-PROD-02",
    status: "success",
    statusFa: "موفق",
    start: 4.5,
    duration: 1.2,
    time: "۰۴:۳۰",
    end: "۰۵:۴۲",
    step: "Delete expired rows",
  },
  {
    id: 7,
    name: "Load_DWH_Facts",
    server: "SQL-REPORT-01",
    status: "success",
    statusFa: "موفق",
    start: 6.3,
    duration: 2.7,
    time: "۰۶:۱۸",
    end: "۰۹:۰۰",
    step: "Load fact tables",
  },
];

type Run = (typeof runs)[number];
type IconName =
  | "calendar"
  | "left"
  | "right"
  | "minus"
  | "plus"
  | "filter"
  | "clock"
  | "close"
  | "check"
  | "warning";

function TIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="3" />
        <path d="M8 3v4M16 3v4M3 10h18" />
      </>
    ),
    left: <path d="m15 18-6-6 6-6" />,
    right: <path d="m9 18 6-6-6-6" />,
    minus: <path d="M5 12h14" />,
    plus: <path d="M12 5v14M5 12h14" />,
    filter: <path d="M3 5h18l-7 8v5l-4 2v-7L3 5Z" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    close: <path d="m6 6 12 12M18 6 6 18" />,
    check: <path d="m5 12 4 4L19 6" />,
    warning: (
      <>
        <path d="M12 3 2.8 19h18.4L12 3Z" />
        <path d="M12 9v4M12 17h.01" />
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

export default function TimelineView() {
  const [filter, setFilter] = useState("all");
  const [zoom, setZoom] = useState(100);
  const [selected, setSelected] = useState<Run | null>(null);
  const filtered = useMemo(
    () => runs.filter((run) => filter === "all" || run.status === filter),
    [filter],
  );
  const hours = Array.from({ length: 13 }, (_, index) => index * 2);

  return (
    <>
      <section className="timeline-summary">
        <div>
          <i className="running" />
          <span>
            <b>۳</b> اجرای جاری
          </span>
          <small>۲ اجرا طبق برنامه</small>
        </div>
        <div>
          <i className="success" />
          <span>
            <b>۲۸</b> اجرای موفق
          </span>
          <small>از ابتدای امروز</small>
        </div>
        <div>
          <i className="failed" />
          <span>
            <b>۱</b> اجرای ناموفق
          </span>
          <small>نیازمند بررسی</small>
        </div>
        <div>
          <i className="overlap" />
          <span>
            <b>۲</b> هم‌پوشانی سنگین
          </span>
          <small>ساعت ۰۸ تا ۱۰</small>
        </div>
      </section>

      <section className="timeline-panel">
        <header className="timeline-head">
          <div>
            <h2>خط زمانی اجرای Jobها</h2>
            <p>مقایسه اجرای واقعی امروز با برنامه زمان‌بندی‌شده</p>
          </div>
          <div className="timeline-date">
            <button>
              <TIcon name="right" />
            </button>
            <span>
              <TIcon name="calendar" />
              <b>امروز، سه‌شنبه ۲۸ آبان</b>
            </span>
            <button>
              <TIcon name="left" />
            </button>
            <button className="today">امروز</button>
          </div>
        </header>
        <div className="timeline-toolbar">
          <div className="timeline-filters">
            {[
              ["all", "همه"],
              ["running", "در حال اجرا"],
              ["success", "موفق"],
              ["failed", "ناموفق"],
              ["retry", "تلاش مجدد"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={filter === key ? "active" : ""}
                onClick={() => setFilter(key)}
              >
                {key !== "all" && <i className={key} />} {label}
                <b>{key === "all" ? runs.length : runs.filter((r) => r.status === key).length}</b>
              </button>
            ))}
          </div>
          <div className="timeline-tools">
            <button>
              <TIcon name="filter" /> فیلتر پیشرفته
            </button>
            <span>
              <button onClick={() => setZoom(Math.max(70, zoom - 10))}>
                <TIcon name="minus" />
              </button>
              <b>{zoom}٪</b>
              <button onClick={() => setZoom(Math.min(140, zoom + 10))}>
                <TIcon name="plus" />
              </button>
            </span>
          </div>
        </div>
        <div className="gantt-legend">
          <span>
            <i className="schedule" /> اجرای برنامه‌ریزی‌شده
          </span>
          <span>
            <i className="running" /> در حال اجرا
          </span>
          <span>
            <i className="success" /> موفق
          </span>
          <span>
            <i className="failed" /> ناموفق
          </span>
          <span>
            <i className="retry" /> تلاش مجدد
          </span>
          <em>خط قرمز: زمان فعلی</em>
        </div>
        <div className="gantt-shell">
          <div className="gantt-labels">
            <div className="gantt-label-title">
              <span>نام Job و سرور</span>
              <small>{filtered.length} مورد</small>
            </div>
            {filtered.map((run) => (
              <button key={run.id} onClick={() => setSelected(run)}>
                <i className={run.status} />
                <div>
                  <b>{run.name}</b>
                  <span>{run.server}</span>
                </div>
                <em>{run.time}</em>
              </button>
            ))}
          </div>
          <div className="gantt-scroll">
            <div className="gantt-stage" style={{ width: `${zoom}%`, minWidth: 780 }}>
              <div className="gantt-hours">
                {hours.map((hour) => (
                  <span key={hour} style={{ right: `${(hour / 24) * 100}%` }}>
                    {String(hour).padStart(2, "0")}:۰۰
                  </span>
                ))}
              </div>
              <div className="gantt-grid-lines">
                {hours.map((hour) => (
                  <i key={hour} style={{ right: `${(hour / 24) * 100}%` }} />
                ))}
              </div>
              <div className="gantt-now" style={{ right: `${(10.2 / 24) * 100}%` }}>
                <span>۱۰:۱۲</span>
              </div>
              <div className="gantt-rows">
                {filtered.map((run) => (
                  <button className="gantt-row" key={run.id} onClick={() => setSelected(run)}>
                    <span
                      className="scheduled-marker"
                      style={{ right: `${(Math.floor(run.start) / 24) * 100}%` }}
                    />
                    <span
                      className={`gantt-run ${run.status}`}
                      style={{
                        right: `${(run.start / 24) * 100}%`,
                        width: `${Math.max((run.duration / 24) * 100, 1.3)}%`,
                      }}
                    >
                      {run.duration > 2 && <b>{run.status === "running" ? "۶۸٪" : run.statusFa}</b>}
                      {run.status === "running" && <i />}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
        <footer className="timeline-foot">
          <span>
            <TIcon name="clock" /> داده‌ها مربوط به ۱۸ ثانیه پیش هستند
          </span>
          <div>
            <b>بازه نمایش:</b> ۰۰:۰۰ تا ۲۴:۰۰ · منطقه زمانی Asia/Tehran
          </div>
        </footer>
      </section>

      <section className="overlap-card">
        <div className="overlap-icon">
          <TIcon name="warning" />
        </div>
        <div>
          <b>هم‌پوشانی قابل توجه بین Jobها</b>
          <span>بین ساعت ۰۸:۱۰ تا ۰۹:۰۰ سه Job سنگین هم‌زمان روی SQL-REPORT-01 اجرا شده‌اند.</span>
        </div>
        <button>مشاهده تحلیل هم‌پوشانی</button>
      </section>

      {selected && (
        <div
          className="run-popover-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setSelected(null);
          }}
        >
          <aside className="run-popover">
            <header>
              <div>
                <i className={selected.status}>
                  {selected.status === "failed" ? <TIcon name="warning" /> : <TIcon name="clock" />}
                </i>
                <span>
                  <small>جزئیات اجرا</small>
                  <b>{selected.name}</b>
                </span>
              </div>
              <button onClick={() => setSelected(null)}>
                <TIcon name="close" />
              </button>
            </header>
            <main>
              <div className="run-state">
                <em className={selected.status}>
                  <i />
                  {selected.statusFa}
                </em>
                <span>{selected.server}</span>
              </div>
              <div className="run-info">
                <div>
                  <span>زمان شروع</span>
                  <b>{selected.time}</b>
                </div>
                <div>
                  <span>زمان پایان</span>
                  <b>{selected.end}</b>
                </div>
                <div>
                  <span>مدت</span>
                  <b>{Math.round(selected.duration * 60)} دقیقه</b>
                </div>
                <div>
                  <span>Step جاری</span>
                  <b>{selected.step}</b>
                </div>
              </div>
              <h3>وضعیت مراحل</h3>
              <div className="run-step done">
                <i>
                  <TIcon name="check" />
                </i>
                <div>
                  <b>آماده‌سازی و اعتبارسنجی</b>
                  <span>با موفقیت تکمیل شد</span>
                </div>
              </div>
              <div className={`run-step ${selected.status === "failed" ? "error" : "active"}`}>
                <i>{selected.status === "failed" ? <TIcon name="warning" /> : "۲"}</i>
                <div>
                  <b>{selected.step}</b>
                  <span>
                    {selected.status === "failed" ? "اجرا با خطا متوقف شد" : "در حال پردازش..."}
                  </span>
                </div>
              </div>
            </main>
            <footer>
              <button onClick={() => setSelected(null)}>بستن</button>
              <button className="primary">مشاهده جزئیات کامل</button>
            </footer>
          </aside>
        </div>
      )}
    </>
  );
}
