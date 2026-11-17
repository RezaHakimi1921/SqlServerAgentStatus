import { useMemo, useState } from "react";

type SessionState = "running" | "suspended" | "sleeping" | "blocked";

type Session = {
  id: number;
  login: string;
  host: string;
  database: string;
  status: SessionState;
  statusFa: string;
  command: string;
  elapsed: string;
  cpu: number;
  reads: string;
  wait: string;
  blocker?: number;
  query: string;
};

const sessions: Session[] = [
  {
    id: 87,
    login: "app_sales",
    host: "API-SALES-02",
    database: "SalesCore",
    status: "running",
    statusFa: "در حال اجرا",
    command: "SELECT",
    elapsed: "۰۰:۱۸",
    cpu: 34,
    reads: "۱۲٫۴K",
    wait: "—",
    query: "SELECT o.OrderId, o.Status, c.CustomerName FROM Sales.Orders o ...",
  },
  {
    id: 112,
    login: "etl_service",
    host: "ETL-WORKER-01",
    database: "DataWarehouse",
    status: "blocked",
    statusFa: "مسدود",
    command: "INSERT",
    elapsed: "۰۲:۴۱",
    cpu: 8,
    reads: "۸٫۱K",
    wait: "LCK_M_IX",
    blocker: 74,
    query: "INSERT INTO fact.DailySales (...) SELECT ... FROM stage.SalesDelta",
  },
  {
    id: 74,
    login: "reporting",
    host: "BI-GATEWAY-01",
    database: "SalesCore",
    status: "suspended",
    statusFa: "در انتظار",
    command: "SELECT",
    elapsed: "۰۶:۱۲",
    cpu: 61,
    reads: "۴۸٫۷K",
    wait: "PAGEIOLATCH_SH",
    query: "SELECT Region, SUM(NetAmount) FROM Sales.OrderLines GROUP BY Region",
  },
  {
    id: 58,
    login: "crm_app",
    host: "CRM-WEB-03",
    database: "CRM",
    status: "running",
    statusFa: "در حال اجرا",
    command: "UPDATE",
    elapsed: "۰۰:۰۹",
    cpu: 12,
    reads: "۲٫۳K",
    wait: "WRITELOG",
    query: "UPDATE dbo.CustomerActivity SET LastSeenAt = SYSUTCDATETIME() ...",
  },
  {
    id: 132,
    login: "sql_agent",
    host: "SQL-PROD-01",
    database: "msdb",
    status: "sleeping",
    statusFa: "خواب",
    command: "AWAITING COMMAND",
    elapsed: "۱۲:۴۴",
    cpu: 1,
    reads: "۱۲۶",
    wait: "BROKER_RECEIVE_WAITFOR",
    query: "WAITFOR (RECEIVE TOP(1) ...)",
  },
  {
    id: 143,
    login: "inventory_api",
    host: "INV-API-01",
    database: "Inventory",
    status: "sleeping",
    statusFa: "خواب",
    command: "AWAITING COMMAND",
    elapsed: "۰۳:۲۸",
    cpu: 0,
    reads: "۳۸",
    wait: "—",
    query: "آخرین درخواست پایان یافته است.",
  },
];

const cpuHistory = [32, 37, 35, 42, 48, 44, 51, 58, 54, 62, 57, 64, 68, 61, 59, 55, 52, 47];

const waits = [
  { name: "PAGEIOLATCH_SH", value: 38, time: "۱٫۸ ثانیه", tone: "warning" },
  { name: "LCK_M_IX", value: 27, time: "۱٫۳ ثانیه", tone: "danger" },
  { name: "WRITELOG", value: 18, time: "۸۶۰ ms", tone: "normal" },
  { name: "CXPACKET", value: 11, time: "۵۲۰ ms", tone: "normal" },
];

type GlyphName =
  | "pulse"
  | "sessions"
  | "lock"
  | "clock"
  | "search"
  | "chevron"
  | "close"
  | "database"
  | "cpu"
  | "refresh"
  | "warning";

function Glyph({ name }: { name: GlyphName }) {
  const paths: Record<GlyphName, React.ReactNode> = {
    pulse: <path d="M3 12h4l2-6 4 12 2-6h6" />,
    sessions: (
      <>
        <circle cx="9" cy="8" r="3" />
        <circle cx="17" cy="9" r="2" />
        <path d="M3 19c0-3 2.7-5 6-5s6 2 6 5M15 15c3 0 5 1.5 5 4" />
      </>
    ),
    lock: (
      <>
        <rect x="4" y="10" width="16" height="11" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    chevron: <path d="m9 18 6-6-6-6" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    database: (
      <>
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
      </>
    ),
    cpu: (
      <>
        <rect x="6" y="6" width="12" height="12" rx="2" />
        <path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3M10 10h4v4h-4z" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 7V3l-2 2a9 9 0 1 0 2.2 9" />
        <path d="M20 3h-4" />
      </>
    ),
    warning: (
      <>
        <path d="M12 3 2.8 19h18.4L12 3Z" />
        <path d="M12 9v4M12 17h.01" />
      </>
    ),
  };

  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden>
      {paths[name]}
    </svg>
  );
}

export default function ActivityView() {
  const [view, setView] = useState<"activity" | "sessions">("activity");
  const [filter, setFilter] = useState<"all" | SessionState>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Session | null>(null);
  const [paused, setPaused] = useState(false);
  const [interval, setIntervalValue] = useState("5");

  const visibleSessions = useMemo(
    () =>
      sessions.filter(
        (session) =>
          (filter === "all" || session.status === filter) &&
          `${session.id} ${session.login} ${session.host} ${session.database} ${session.command}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [filter, query],
  );

  const openSession = (id: number) => {
    setSelected(sessions.find((session) => session.id === id) ?? null);
  };

  return (
    <div className="activity-view">
      <section className="activity-livebar">
        <div className={`activity-live-state ${paused ? "paused" : ""}`}>
          <i />
          <div>
            <b>{paused ? "نمونه‌برداری متوقف است" : "Activity لحظه‌ای SQL-PROD-01"}</b>
            <span>
              {paused
                ? "داده نمایش‌داده‌شده Snapshot ساعت ۱۰:۱۲:۲۴ است"
                : "آخرین نمونه موفق: همین حالا · منبع: DMVهای SQL Server"}
            </span>
          </div>
        </div>
        <div className="activity-live-actions">
          <label>
            بازه بروزرسانی
            <select value={interval} onChange={(event) => setIntervalValue(event.target.value)}>
              <option value="5">۵ ثانیه</option>
              <option value="15">۱۵ ثانیه</option>
              <option value="30">۳۰ ثانیه</option>
            </select>
          </label>
          <button className="activity-action" onClick={() => setPaused((value) => !value)}>
            {paused ? "ادامه پایش" : "توقف و بررسی"}
          </button>
          <button className="activity-icon-action" aria-label="بروزرسانی نمونه">
            <Glyph name="refresh" />
          </button>
        </div>
      </section>

      <section className="activity-kpis">
        <article>
          <i className="cpu">
            <Glyph name="cpu" />
          </i>
          <div>
            <span>مصرف CPU</span>
            <b>۴۷٪</b>
            <small>میانگین ۵ دقیقه: ۵۳٪</small>
          </div>
          <em className="stable">پایدار</em>
        </article>
        <article>
          <i className="sessions">
            <Glyph name="sessions" />
          </i>
          <div>
            <span>Session فعال</span>
            <b>۲۴</b>
            <small>از ۱۴۶ اتصال باز</small>
          </div>
          <em>۶ درخواست جاری</em>
        </article>
        <article className="attention">
          <i className="blocked">
            <Glyph name="lock" />
          </i>
          <div>
            <span>Session مسدود</span>
            <b>۱</b>
            <small>بیشترین انتظار: ۲:۴۱</small>
          </div>
          <button onClick={() => openSession(112)}>بررسی</button>
        </article>
        <article>
          <i className="wait">
            <Glyph name="clock" />
          </i>
          <div>
            <span>Wait در ثانیه</span>
            <b>۴٫۸s</b>
            <small>بیشترین: PAGEIOLATCH_SH</small>
          </div>
          <em className="warning">+۱۸٪</em>
        </article>
      </section>

      <section className="activity-workspace">
        <header className="activity-workspace-head">
          <div className="activity-tabs" role="tablist" aria-label="نمای مانیتورینگ">
            <button
              className={view === "activity" ? "active" : ""}
              onClick={() => setView("activity")}
              role="tab"
              aria-selected={view === "activity"}
            >
              <Glyph name="pulse" />
              Activity زنده
            </button>
            <button
              className={view === "sessions" ? "active" : ""}
              onClick={() => setView("sessions")}
              role="tab"
              aria-selected={view === "sessions"}
            >
              <Glyph name="sessions" />
              Sessionها
              <b>۱۴۶</b>
            </button>
          </div>
          <span>این نما تاریخچه ذخیره نمی‌کند و وضعیت لحظه‌ای را نشان می‌دهد.</span>
        </header>

        {view === "activity" ? (
          <div className="activity-dashboard">
            <div className="activity-primary-column">
              <section className="activity-panel cpu-panel">
                <header>
                  <div>
                    <b>بار پردازنده و درخواست‌های جاری</b>
                    <span>۶۰ ثانیه اخیر · SQL Server Process</span>
                  </div>
                  <em>اکنون ۴۷٪</em>
                </header>
                <div className="cpu-chart" aria-label="نمودار مصرف CPU در ۶۰ ثانیه اخیر">
                  <div className="chart-scale">
                    <span>۱۰۰٪</span>
                    <span>۵۰٪</span>
                    <span>۰٪</span>
                  </div>
                  <div className="chart-bars">
                    {cpuHistory.map((value, index) => (
                      <i key={index} style={{ height: `${value}%` }} />
                    ))}
                  </div>
                </div>
                <div className="chart-legend">
                  <span>
                    <i /> SQL Process CPU
                  </span>
                  <b>بیشینه ۶۸٪</b>
                </div>
              </section>

              <section className="activity-panel requests-panel">
                <header>
                  <div>
                    <b>درخواست‌های فعال</b>
                    <span>مرتب‌شده بر اساس مدت اجرا</span>
                  </div>
                  <button onClick={() => setView("sessions")}>
                    مشاهده همه Sessionها <Glyph name="chevron" />
                  </button>
                </header>
                <div className="activity-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Session</th>
                        <th>وضعیت</th>
                        <th>دیتابیس / دستور</th>
                        <th>مدت</th>
                        <th>CPU</th>
                        <th>Wait</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {sessions.slice(0, 4).map((session) => (
                        <tr key={session.id} onClick={() => setSelected(session)}>
                          <td>
                            <b className="session-id">#{session.id}</b>
                            <small>{session.login}</small>
                          </td>
                          <td>
                            <span className={`session-state ${session.status}`}>
                              <i />
                              {session.statusFa}
                            </span>
                          </td>
                          <td>
                            <b>{session.database}</b>
                            <small>{session.command}</small>
                          </td>
                          <td>{session.elapsed}</td>
                          <td>{session.cpu}٪</td>
                          <td>
                            <span className={session.blocker ? "wait-danger" : ""}>
                              {session.wait}
                            </span>
                          </td>
                          <td>
                            <button
                              className="row-action"
                              aria-label={`جزئیات Session ${session.id}`}
                            >
                              <Glyph name="chevron" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>

            <aside className="activity-secondary-column">
              <section className="activity-panel blocking-panel">
                <header>
                  <div>
                    <b>Blocking فعال</b>
                    <span>یک زنجیره نیازمند بررسی</span>
                  </div>
                  <i className="danger-indicator" />
                </header>
                <button className="blocking-chain" onClick={() => openSession(112)}>
                  <span className="blocker-node">
                    <i>#74</i>
                    <b>reporting</b>
                    <small>۶:۱۲ · suspended</small>
                  </span>
                  <span className="blocking-link">
                    <i />
                    ۲:۴۱ انتظار
                  </span>
                  <span className="blocked-node">
                    <i>#112</i>
                    <b>etl_service</b>
                    <small>LCK_M_IX</small>
                  </span>
                </button>
                <div className="blocking-note">
                  <Glyph name="warning" />
                  Session #74 یک تراکنش باز روی SalesCore دارد.
                </div>
              </section>

              <section className="activity-panel waits-panel">
                <header>
                  <div>
                    <b>بیشترین Waitها</b>
                    <span>مجموع انتظار در نمونه فعلی</span>
                  </div>
                </header>
                <div className="wait-list">
                  {waits.map((wait) => (
                    <div key={wait.name}>
                      <span>
                        <b>{wait.name}</b>
                        <small>{wait.time}</small>
                      </span>
                      <i>
                        <em
                          className={wait.tone}
                          style={{ width: `${Math.max(wait.value * 2, 14)}%` }}
                        />
                      </i>
                      <strong>{wait.value}٪</strong>
                    </div>
                  ))}
                </div>
              </section>
            </aside>
          </div>
        ) : (
          <div className="sessions-view">
            <div className="sessions-toolbar">
              <div className="session-filters">
                {(
                  [
                    ["all", "همه", sessions.length],
                    ["running", "در حال اجرا", 2],
                    ["blocked", "مسدود", 1],
                    ["suspended", "در انتظار", 1],
                    ["sleeping", "خواب", 2],
                  ] as const
                ).map(([key, label, count]) => (
                  <button
                    key={key}
                    className={filter === key ? "active" : ""}
                    onClick={() => setFilter(key)}
                  >
                    {label}
                    <b>{count}</b>
                  </button>
                ))}
              </div>
              <label className="session-search">
                <Glyph name="search" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Session، Login، Host یا Database..."
                />
                {query && (
                  <button onClick={() => setQuery("")} aria-label="پاک کردن جستجو">
                    <Glyph name="close" />
                  </button>
                )}
              </label>
            </div>
            <div className="activity-table-wrap sessions-table">
              <table>
                <thead>
                  <tr>
                    <th>Session</th>
                    <th>Login / Host</th>
                    <th>وضعیت</th>
                    <th>Database</th>
                    <th>Command</th>
                    <th>مدت</th>
                    <th>CPU</th>
                    <th>Logical Reads</th>
                    <th>Wait / Blocker</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visibleSessions.map((session) => (
                    <tr key={session.id} onClick={() => setSelected(session)}>
                      <td>
                        <b className="session-id">#{session.id}</b>
                      </td>
                      <td>
                        <b>{session.login}</b>
                        <small>{session.host}</small>
                      </td>
                      <td>
                        <span className={`session-state ${session.status}`}>
                          <i />
                          {session.statusFa}
                        </span>
                      </td>
                      <td>{session.database}</td>
                      <td>
                        <code>{session.command}</code>
                      </td>
                      <td>{session.elapsed}</td>
                      <td>{session.cpu}٪</td>
                      <td>{session.reads}</td>
                      <td>
                        <b className={session.blocker ? "wait-danger" : ""}>{session.wait}</b>
                        {session.blocker && <small>مسدود توسط #{session.blocker}</small>}
                      </td>
                      <td>
                        <button className="row-action" aria-label={`جزئیات Session ${session.id}`}>
                          <Glyph name="chevron" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visibleSessions.length && (
                <div className="session-empty">
                  <Glyph name="search" />
                  <b>Session مطابق فیلتر پیدا نشد</b>
                  <span>فیلتر یا عبارت جستجو را تغییر دهید.</span>
                </div>
              )}
            </div>
            <footer className="sessions-footer">
              <span>{visibleSessions.length} Session در این نمونه · ۱۴۶ اتصال روی سرور</span>
              <span>System sessionها به‌صورت پیش‌فرض پنهان هستند.</span>
            </footer>
          </div>
        )}
      </section>

      {selected && (
        <div
          className="session-drawer-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelected(null);
          }}
        >
          <aside className="session-drawer">
            <header>
              <div>
                <i className={selected.status}>
                  <Glyph name="sessions" />
                </i>
                <div>
                  <span>جزئیات Session</span>
                  <b>Session #{selected.id}</b>
                </div>
              </div>
              <button onClick={() => setSelected(null)} aria-label="بستن جزئیات Session">
                <Glyph name="close" />
              </button>
            </header>
            <main>
              <div className="session-drawer-state">
                <span className={`session-state ${selected.status}`}>
                  <i />
                  {selected.statusFa}
                </span>
                <small>نمونه ساعت ۱۰:۱۲:۲۴</small>
              </div>

              {selected.blocker && (
                <section className="session-alert">
                  <Glyph name="lock" />
                  <div>
                    <b>این Session مسدود شده است</b>
                    <span>
                      Session #{selected.blocker} به مدت {selected.elapsed} مانع ادامه اجراست.
                    </span>
                  </div>
                  <button onClick={() => openSession(selected.blocker!)}>مشاهده Blocker</button>
                </section>
              )}

              <section className="session-info-grid">
                <div>
                  <span>Login</span>
                  <b>{selected.login}</b>
                </div>
                <div>
                  <span>Host</span>
                  <b>{selected.host}</b>
                </div>
                <div>
                  <span>Database</span>
                  <b>{selected.database}</b>
                </div>
                <div>
                  <span>Command</span>
                  <b>{selected.command}</b>
                </div>
                <div>
                  <span>مدت اجرا</span>
                  <b>{selected.elapsed}</b>
                </div>
                <div>
                  <span>Wait Type</span>
                  <b>{selected.wait}</b>
                </div>
              </section>

              <section className="session-resource-section">
                <header>
                  <b>مصرف منابع در درخواست جاری</b>
                  <span>از شروع درخواست</span>
                </header>
                <div>
                  <article>
                    <span>CPU</span>
                    <b>{selected.cpu}٪</b>
                    <i>
                      <em style={{ width: `${selected.cpu}%` }} />
                    </i>
                  </article>
                  <article>
                    <span>Logical Reads</span>
                    <b>{selected.reads}</b>
                    <i>
                      <em className="reads" style={{ width: "64%" }} />
                    </i>
                  </article>
                </div>
              </section>

              <section className="session-query">
                <header>
                  <div>
                    <b>Query جاری</b>
                    <span>متن برای جلوگیری از نمایش داده حساس کوتاه شده است.</span>
                  </div>
                  <code>{selected.command}</code>
                </header>
                <pre dir="ltr">{selected.query}</pre>
              </section>

              <section className="session-context">
                <b>راهنمای بررسی</b>
                <ol>
                  <li>ابتدا Wait Type و مدت انتظار را بررسی کنید.</li>
                  <li>در Blocking، Session مسدودکننده و تراکنش باز آن را باز کنید.</li>
                  <li>مصرف CPU و Reads را با baseline همان Query مقایسه کنید.</li>
                </ol>
              </section>
            </main>
            <footer>
              <span>این نسخه فقط خواندنی است و Session را Kill نمی‌کند.</span>
              <button className="activity-action" onClick={() => setSelected(null)}>
                بستن
              </button>
            </footer>
          </aside>
        </div>
      )}
    </div>
  );
}
