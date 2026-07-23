import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  LineChart, Line, Legend,
} from "recharts";
import {
  LayoutDashboard, Users, HardHat, AlertTriangle, Settings, RefreshCw,
  Search, TrendingUp, TrendingDown, FileText, CheckCircle2, Radio, Moon, Sun,
} from "lucide-react";
import { fetchReports, patchReport, Report } from "./api";
import { useI18n, type Lang } from "./i18n";
import { useTheme, type ChartTheme } from "./theme";

// columns the manager can correct inline (writes back to the Sheet)
const EDITABLE = [
  "technicien", "chantier", "client", "type_activite", "goulottes_m", "cables_m",
  "bureaux_termines", "panneaux_raccordes", "autres_travaux", "observations", "resume",
] as const;

const isFlagged = (r: Report) => String(r.flag_review).toLowerCase() === "true";
const today = () => new Date().toISOString().slice(0, 10); // YYYY-MM-DD

export default function App() {
  return <Dashboard />;
}

function Dashboard() {
  const { t } = useI18n();
  const [reports, setReports] = useState<Report[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [fTech, setFTech] = useState("");
  const [fChantier, setFChantier] = useState("");
  const [fDate, setFDate] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = () => {
    setLoading(true);
    fetchReports()
      .then((r) => { setReports(r); setError(""); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const techs = useMemo(() => [...new Set(reports.map((r) => r.technicien).filter(Boolean))], [reports]);
  const chantiers = useMemo(() => [...new Set(reports.map((r) => r.chantier).filter(Boolean))], [reports]);

  // ── KPIs (all computed from real rows) ──────────────────────────────
  const kTotal = reports.length;
  const kToday = reports.filter((r) => r.date === today()).length;
  const kFlagged = reports.filter(isFlagged).length;
  const kTechs = techs.length;

  // ── chart data ──────────────────────────────────────────────────────
  const perDay = useMemo(() => {
    const m = new Map<string, number>();
    reports.forEach((r) => { if (r.date) m.set(r.date, (m.get(r.date) ?? 0) + 1); });
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-7)
      .map(([date, count]) => ({ label: date.slice(5), count })); // MM-DD
  }, [reports]);

  // per-day split by channel → glowing step lines (WhatsApp vs Telegram)
  const perChannel = useMemo(() => {
    const days = [...new Set(reports.map((r) => r.date).filter(Boolean))].sort().slice(-7);
    return days.map((d) => {
      const rows = reports.filter((r) => r.date === d);
      return {
        label: d.slice(5),
        wa: rows.filter((r) => r.canal === "whatsapp").length,
        tg: rows.filter((r) => r.canal !== "whatsapp").length,
      };
    });
  }, [reports]);

  // ── filtered table rows ─────────────────────────────────────────────
  const filtered = reports.filter((r) => {
    if (fTech && r.technicien !== fTech) return false;
    if (fChantier && r.chantier !== fChantier) return false;
    if (fDate && r.date !== fDate) return false;
    if (reviewOnly && !isFlagged(r)) return false;
    if (query) {
      const hay = `${r.technicien} ${r.chantier} ${r.resume} ${r.type_activite}`.toLowerCase();
      if (!hay.includes(query.toLowerCase())) return false;
    }
    return true;
  });

  const edit = async (r: Report, field: string) => {
    const current = (r as unknown as Record<string, string>)[field] ?? "";
    const next = window.prompt(t("prompt.edit", { field, row: r._row }), current);
    if (next === null || next === current) return;
    try {
      await patchReport(r._row, field, next);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const dash = t("empty.dash");

  return (
    <div className="flex min-h-screen bg-bg text-ink font-sans">
      <Sidebar reviewOnly={reviewOnly} setReviewOnly={setReviewOnly} flagged={kFlagged} />

      <div className="flex-1 min-w-0 flex flex-col">
        <Topbar onRefresh={load} loading={loading} query={query} setQuery={setQuery} />

        <main className="flex-1 px-6 py-6 space-y-6">
          {error && (
            <div className="rounded-lg border border-down/40 bg-down/10 px-4 py-3 text-sm text-down">
              {error}
            </div>
          )}

          {/* KPI row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <StatCard icon={<FileText size={16} />} label={t("kpi.total")} value={kTotal}
              hint={t("kpi.total.hint", { n: perDay.length })} tone="up" />
            <StatCard icon={<TrendingUp size={16} />} label={t("kpi.today")} value={kToday}
              hint={today()} tone="up" />
            <StatCard icon={<AlertTriangle size={16} />} label={t("kpi.review")} value={kFlagged}
              hint={kTotal ? t("kpi.review.hint", { n: Math.round((kFlagged / kTotal) * 100) }) : dash}
              tone={kFlagged ? "down" : "up"} />
            <StatCard icon={<Users size={16} />} label={t("kpi.techs")} value={kTechs}
              hint={t("kpi.techs.hint", { n: chantiers.length })} tone="up" />
          </div>

          {/* charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ChartCard title={t("chart.perDay.title")} subtitle={t("chart.perDay.subtitle")}>
              <PerDayChart data={perDay} />
            </ChartCard>
            <ChartCard title={t("chart.channel.title")} subtitle={t("chart.channel.subtitle")}>
              <ChannelChart data={perChannel} />
            </ChartCard>
          </div>

          {/* table */}
          <section className="rounded-xl border border-line bg-card">
            <div className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-line">
              <h2 className="text-sm font-semibold mr-auto">{t("table.title")}</h2>
              <Select value={fTech} onChange={setFTech} placeholder={t("filter.allTechs")} options={techs} />
              <Select value={fChantier} onChange={setFChantier} placeholder={t("filter.allChantiers")} options={chantiers} />
              <input type="date" value={fDate} onChange={(e) => setFDate(e.target.value)}
                className="h-9 rounded-md border border-line bg-panel px-2 text-sm text-ink [color-scheme:light] dark:[color-scheme:dark]" />
              <label className="flex items-center gap-2 text-sm text-muted select-none cursor-pointer">
                <input type="checkbox" checked={reviewOnly} onChange={(e) => setReviewOnly(e.target.checked)}
                  className="accent-accent" />
                {t("filter.review")}
              </label>
              <span className="text-xs text-faint tabular-nums">{t("table.rows", { n: filtered.length })}</span>
            </div>

            {loading ? (
              <p className="px-5 py-10 text-center text-muted text-sm">{t("state.loading")}</p>
            ) : filtered.length === 0 ? (
              <p className="px-5 py-10 text-center text-muted text-sm">{t("state.empty")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-faint">
                      {[t("th.date"), t("th.channel"), t("th.technician"), t("th.chantier"), t("th.activity"),
                        t("th.goulottes"), t("th.cables"), t("th.bureaux"), t("th.panneaux"), t("th.resume"), t("th.confidence"), ""]
                        .map((h, i) => <th key={i} className="px-4 py-3 font-medium whitespace-nowrap">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((r) => (
                      <Row key={r._row} r={r} edit={edit} dash={dash}
                        expanded={expanded === r._row}
                        toggle={() => setExpanded(expanded === r._row ? null : r._row)} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <p className="px-5 py-3 border-t border-line text-xs text-faint">
              {t("footer.editable", { cols: EDITABLE.join(", ") })}
            </p>
          </section>
        </main>
      </div>
    </div>
  );
}

// ── Charts ────────────────────────────────────────────────────────────
function tooltipStyle(c: ChartTheme) {
  return { background: c.tooltipBg, border: `1px solid ${c.tooltipBorder}`, borderRadius: 8, color: c.tooltipInk, fontSize: 12 };
}

function PerDayChart({ data }: { data: { label: string; count: number }[] }) {
  const { chart: c } = useTheme();
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="barFade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={c.accentTop} stopOpacity={0.95} />
            <stop offset="100%" stopColor={c.accent} stopOpacity={0.35} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={c.grid} />
        <XAxis dataKey="label" tick={{ fill: c.axis, fontSize: 12 }} axisLine={false} tickLine={false} />
        <YAxis allowDecimals={false} tick={{ fill: c.axis, fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
        <Tooltip cursor={{ fill: "rgba(127,127,127,0.08)" }} contentStyle={tooltipStyle(c)} />
        <Bar dataKey="count" radius={[5, 5, 0, 0]} fill="url(#barFade)" maxBarSize={44} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function ChannelChart({ data }: { data: { label: string; wa: number; tg: number }[] }) {
  const { chart: c } = useTheme();
  const { t } = useI18n();
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }} className="glow-line">
        <CartesianGrid vertical={false} stroke={c.grid} />
        <XAxis dataKey="label" tick={{ fill: c.axis, fontSize: 12 }} axisLine={false} tickLine={false} />
        <YAxis allowDecimals={false} tick={{ fill: c.axis, fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
        <Tooltip cursor={{ stroke: c.grid }} contentStyle={tooltipStyle(c)} />
        <Legend wrapperStyle={{ fontSize: 12, color: c.axisStrong }} iconType="plainline" />
        <Line type="step" dataKey="wa" name={t("legend.whatsapp")} stroke={c.wa} strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} />
        <Line type="step" dataKey="tg" name={t("legend.telegram")} stroke={c.tg} strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────
function Sidebar({ reviewOnly, setReviewOnly, flagged }: {
  reviewOnly: boolean; setReviewOnly: (v: boolean) => void; flagged: number;
}) {
  const { t } = useI18n();
  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-line bg-panel">
      <div className="flex items-center gap-2.5 px-5 h-16 border-b border-line">
        <img src="/az-bot.png" alt="aznet" className="w-9 h-9 rounded-full shadow-sm" />
        <div className="leading-tight">
          <div className="text-sm font-semibold">aznet</div>
          <div className="text-[11px] text-faint">{t("brand.subtitle")}</div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 text-sm">
        <p className="px-2 pb-1 text-[11px] uppercase tracking-wide text-faint">{t("nav.supervision")}</p>
        <NavItem icon={<LayoutDashboard size={16} />} label={t("nav.dashboard")}
          active={!reviewOnly} onClick={() => setReviewOnly(false)} />
        <NavItem icon={<AlertTriangle size={16} />} label={t("nav.review")} badge={flagged || undefined}
          active={reviewOnly} onClick={() => setReviewOnly(true)} />

        <p className="px-2 pt-4 pb-1 text-[11px] uppercase tracking-wide text-faint">{t("nav.reference")}</p>
        <NavItem icon={<Users size={16} />} label={t("nav.technicians")} muted />
        <NavItem icon={<HardHat size={16} />} label={t("nav.chantiers")} muted />
        <NavItem icon={<Radio size={16} />} label={t("nav.channels")} muted />

        <p className="px-2 pt-4 pb-1 text-[11px] uppercase tracking-wide text-faint">{t("nav.admin")}</p>
        <NavItem icon={<Settings size={16} />} label={t("nav.settings")} muted />
      </nav>

      <div className="px-4 py-4 border-t border-line text-[11px] text-faint">
        <div className="flex items-center gap-1.5 text-up mb-1">
          <CheckCircle2 size={13} /> {t("sidebar.status")}
        </div>
        © 2026 aznet.ma
      </div>
    </aside>
  );
}

function NavItem({ icon, label, active, muted, badge, onClick }: {
  icon: ReactNode; label: string; active?: boolean; muted?: boolean;
  badge?: number; onClick?: () => void;
}) {
  return (
    <button onClick={onClick} disabled={muted}
      className={
        "w-full flex items-center gap-3 px-2 py-2 rounded-md transition-colors " +
        (active ? "bg-cardhi text-ink font-medium"
          : muted ? "text-faint cursor-default"
          : "text-muted hover:bg-cardhi hover:text-ink")
      }>
      {icon}
      <span className="flex-1 text-left">{label}</span>
      {badge != null && (
        <span className="grid place-items-center min-w-5 h-5 px-1 rounded-full bg-down/20 text-down text-[11px] font-semibold">
          {badge}
        </span>
      )}
    </button>
  );
}

// ── Topbar (with language + theme controls, top right) ──────────────────
function Topbar({ onRefresh, loading, query, setQuery }: {
  onRefresh: () => void; loading: boolean; query: string; setQuery: (v: string) => void;
}) {
  const { t } = useI18n();
  return (
    <header className="sticky top-0 z-10 flex items-center gap-3 h-16 px-6 border-b border-line bg-panel/80 backdrop-blur">
      <div className="flex items-center gap-2 text-sm text-muted">
        <LayoutDashboard size={16} /> {t("topbar.title")}
      </div>
      <div className="relative ml-auto w-full max-w-xs">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
        <input value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder={t("topbar.search")}
          className="w-full h-9 rounded-md border border-line bg-card pl-9 pr-3 text-sm text-ink placeholder:text-faint focus:outline-none focus:border-accent" />
      </div>
      <LanguageToggle />
      <ThemeToggle />
      <button onClick={onRefresh} title={t("topbar.refresh")}
        className="flex items-center gap-2 h-9 px-3 rounded-md bg-accent text-white text-sm font-medium hover:brightness-110 transition">
        <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
        <span className="hidden sm:inline">{t("topbar.refresh")}</span>
      </button>
    </header>
  );
}

function LanguageToggle() {
  const { lang, setLang, t } = useI18n();
  const langs: Lang[] = ["fr", "en"];
  return (
    <div className="flex items-center rounded-md border border-line bg-card p-0.5" role="group" aria-label={t("topbar.lang")}>
      {langs.map((l) => (
        <button key={l} onClick={() => setLang(l)}
          className={"px-2 h-7 rounded text-xs font-medium uppercase transition-colors " +
            (lang === l ? "bg-accent text-white" : "text-muted hover:text-ink")}>
          {l}
        </button>
      ))}
    </div>
  );
}

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const { t } = useI18n();
  const label = theme === "dark" ? t("topbar.theme.toLight") : t("topbar.theme.toDark");
  return (
    <button onClick={toggle} title={label} aria-label={label}
      className="grid place-items-center w-9 h-9 rounded-md border border-line bg-card text-muted hover:text-ink transition-colors">
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────
function StatCard({ icon, label, value, hint, tone }: {
  icon: ReactNode; label: string; value: number; hint: string; tone: "up" | "down";
}) {
  const Arrow = tone === "up" ? TrendingUp : TrendingDown;
  return (
    <div className="rounded-xl border border-line bg-card p-5 transition-colors">
      <div className="flex items-center gap-2 text-muted text-sm">
        <span className="text-faint">{icon}</span>{label}
      </div>
      <div className="mt-3 text-3xl font-semibold tabular-nums">{value}</div>
      <div className={"mt-3 flex items-center gap-1.5 text-xs " + (tone === "up" ? "text-up" : "text-down")}>
        <Arrow size={13} /> <span className="text-faint">{hint}</span>
      </div>
    </div>
  );
}

// ── Chart card ────────────────────────────────────────────────────────
function ChartCard({ title, subtitle, children }: {
  title: string; subtitle: string; children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-line bg-card p-5">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="text-xs text-faint mt-0.5 mb-4">{subtitle}</p>
      {children}
    </div>
  );
}

// ── Select ────────────────────────────────────────────────────────────
function Select({ value, onChange, placeholder, options }: {
  value: string; onChange: (v: string) => void; placeholder: string; options: string[];
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border border-line bg-panel px-2 text-sm text-ink max-w-[11rem]">
      <option value="">{placeholder}</option>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

// ── Table row ─────────────────────────────────────────────────────────
function Row({ r, edit, dash, expanded, toggle }: {
  r: Report; edit: (r: Report, field: string) => void; dash: string; expanded: boolean; toggle: () => void;
}) {
  const { t } = useI18n();
  const flagged = isFlagged(r);
  const cell = "px-4 py-3 whitespace-nowrap";
  const ed = cell + " cursor-pointer hover:text-accent";
  return (
    <>
      <tr className={"border-t border-line " + (flagged ? "bg-down/5" : "hover:bg-cardhi/50")}>
        <td className={cell + " text-muted"}>{r.date}<span className="text-faint"> {r.heure}</span></td>
        <td className={cell}>{r.canal === "whatsapp" ? "🟢 WA" : "🔵 TG"}</td>
        <td className={ed + " text-ink"} onClick={() => edit(r, "technicien")}>{r.technicien}</td>
        <td className={ed + " text-muted"} onClick={() => edit(r, "chantier")}>{r.chantier || dash}</td>
        <td className={ed + " text-muted"} onClick={() => edit(r, "type_activite")}>{r.type_activite || dash}</td>
        <td className={ed + " text-right tabular-nums"} onClick={() => edit(r, "goulottes_m")}>{r.goulottes_m || dash}</td>
        <td className={ed + " text-right tabular-nums"} onClick={() => edit(r, "cables_m")}>{r.cables_m || dash}</td>
        <td className={ed + " text-right tabular-nums"} onClick={() => edit(r, "bureaux_termines")}>{r.bureaux_termines || dash}</td>
        <td className={ed + " text-right tabular-nums"} onClick={() => edit(r, "panneaux_raccordes")}>{r.panneaux_raccordes || dash}</td>
        <td className={ed + " max-w-[18rem] truncate text-muted"} onClick={() => edit(r, "resume")} title={r.resume}>{r.resume}</td>
        <td className={cell}>
          <div className="flex items-center gap-1.5">
            <span className="tabular-nums text-muted">{r.confidence ? `${Math.round(parseFloat(r.confidence) * 100)}%` : dash}</span>
            {flagged && <span className="rounded bg-down/20 text-down text-[10px] px-1.5 py-0.5">{t("badge.review")}</span>}
          </div>
        </td>
        <td className={cell}>
          <button onClick={toggle} className="text-faint hover:text-ink">{expanded ? "▲" : "▼"}</button>
        </td>
      </tr>
      {expanded && (
        <tr className="border-t border-line bg-panel/60">
          <td colSpan={12} className="px-4 py-4 text-sm text-muted space-y-1.5">
            <div><span className="text-faint">{t("detail.transcription")}</span> {r.rapport_complet || dash}</div>
            <div>
              <span className="text-faint">{t("detail.otherWork")}</span>{" "}
              <span className="cursor-pointer hover:text-accent" onClick={() => edit(r, "autres_travaux")}>{r.autres_travaux || dash}</span>
            </div>
            <div>
              <span className="text-faint">{t("detail.observations")}</span>{" "}
              <span className="cursor-pointer hover:text-accent" onClick={() => edit(r, "observations")}>{r.observations || dash}</span>
            </div>
            <div><span className="text-faint">{t("detail.audio")}</span> {r.lien_audio || dash} <em className="text-faint">{t("detail.audioNote")}</em></div>
          </td>
        </tr>
      )}
    </>
  );
}
