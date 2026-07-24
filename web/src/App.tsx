import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  LineChart, Line, Legend,
} from "recharts";
import {
  LayoutDashboard, Users, HardHat, AlertTriangle, Settings, RefreshCw,
  Search, TrendingUp, TrendingDown, FileText, CheckCircle2, Radio, Moon, Sun,
  Cable, Ruler, Building2, Network, Gauge, ShieldAlert, FileWarning,
  Clock, Server, Send, Bell, CalendarDays, Mic,
} from "lucide-react";
import { fetchReports, patchReport, fetchHealth, Report, Health } from "./api";
import { useI18n, LANGS, type Lang } from "./i18n";
import { useTheme, type ChartTheme } from "./theme";

// columns the manager can correct inline (writes back to the Sheet)
const EDITABLE = [
  "technicien", "chantier", "client", "type_activite", "goulottes_m", "cables_m",
  "bureaux_termines", "panneaux_raccordes", "autres_travaux", "observations", "resume",
] as const;

const isFlagged = (r: Report) => String(r.flag_review).toLowerCase() === "true";
const isVoice = (r: Report) => Boolean(r.lien_audio); // lien_audio set only for Darija voice notes
const today = () => new Date().toISOString().slice(0, 10); // YYYY-MM-DD
const num = (s: string) => { const n = parseFloat(String(s ?? "").replace(",", ".")); return isFinite(n) ? n : 0; };
const tsOf = (r: Report) => {
  const t = Date.parse(`${r.date}T${(r.heure || "00:00").slice(0, 5)}:00`);
  return isNaN(t) ? 0 : t;
};
function fmtUptime(s: number): string {
  if (s < 60) return `${Math.floor(s)}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}j ${h % 24}h`;
}

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
  const [health, setHealth] = useState<Health | null>(null);
  const [healthErr, setHealthErr] = useState(false);

  const load = () => {
    setLoading(true);
    fetchReports()
      .then((r) => { setReports(r); setError(""); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  // poll /health for the API uptime / online status tile
  useEffect(() => {
    let alive = true;
    const poll = () => fetchHealth()
      .then((h) => { if (alive) { setHealth(h); setHealthErr(false); } })
      .catch(() => { if (alive) setHealthErr(true); });
    poll();
    const id = setInterval(poll, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  const online = !!health && !healthErr;

  const techs = useMemo(() => [...new Set(reports.map((r) => r.technicien).filter(Boolean))], [reports]);
  const chantiers = useMemo(() => [...new Set(reports.map((r) => r.chantier).filter(Boolean))], [reports]);

  // ── windows + week-over-week ────────────────────────────────────────
  const dayIndex = (r: Report) => Math.floor((Date.parse(today()) - Date.parse(r.date)) / 86400000);
  const last7 = reports.filter((r) => r.date && dayIndex(r) >= 0 && dayIndex(r) <= 6);
  const prev7 = reports.filter((r) => r.date && dayIndex(r) >= 7 && dayIndex(r) <= 13);
  const sumField = (rows: Report[], f: keyof Report) => rows.reduce((a, r) => a + num(r[f] as string), 0);
  const wow = (metric: (rows: Report[]) => number): number | null => {
    const c = metric(last7), p = metric(prev7);
    return p === 0 ? null : Math.round(((c - p) / p) * 100);
  };
  const wowReports = wow((r) => r.length);
  const wowCables = wow((r) => sumField(r, "cables_m"));
  const wowGoulottes = wow((r) => sumField(r, "goulottes_m"));
  const wowBureaux = wow((r) => sumField(r, "bureaux_termines"));
  const wowPanneaux = wow((r) => sumField(r, "panneaux_raccordes"));

  // ── KPIs ────────────────────────────────────────────────────────────
  const kTotal = reports.length;
  const kToday = reports.filter((r) => r.date === today()).length;
  const kWeek = last7.length;
  const kFlagged = reports.filter(isFlagged).length;
  const kTechs = techs.length;

  const pCables = Math.round(sumField(reports, "cables_m"));
  const pGoulottes = Math.round(sumField(reports, "goulottes_m"));
  const pBureaux = Math.round(sumField(reports, "bureaux_termines"));
  const pPanneaux = Math.round(sumField(reports, "panneaux_raccordes"));

  const scored = reports.filter((r) => r.confidence !== "" && isFinite(parseFloat(r.confidence)));
  const avgConf = scored.length
    ? Math.round((scored.reduce((a, r) => a + parseFloat(r.confidence), 0) / scored.length) * 100) : 0;
  const pctReview = kTotal ? Math.round((kFlagged / kTotal) * 100) : 0;
  const incomplete = reports.filter((r) => !r.chantier || !r.type_activite).length;
  const pctIncomplete = kTotal ? Math.round((incomplete / kTotal) * 100) : 0;
  const voiceN = reports.filter(isVoice).length;
  const pctVoice = kTotal ? Math.round((voiceN / kTotal) * 100) : 0;

  // cadence
  const avgPerTech = kTechs ? (kTotal / kTechs) : 0;
  const busiest = useMemo(() => {
    const m = new Map<string, number>();
    reports.forEach((r) => { if (r.date) m.set(r.date, (m.get(r.date) ?? 0) + 1); });
    let best = { date: "", n: 0 };
    m.forEach((n, date) => { if (n > best.n) best = { date, n }; });
    return best;
  }, [reports]);
  const lastTs = useMemo(() => reports.reduce((mx, r) => Math.max(mx, tsOf(r)), 0), [reports]);

  // ── chart data ──────────────────────────────────────────────────────
  const perDay = useMemo(() => {
    const m = new Map<string, number>();
    reports.forEach((r) => { if (r.date) m.set(r.date, (m.get(r.date) ?? 0) + 1); });
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-7)
      .map(([date, count]) => ({ label: date.slice(5), count }));
  }, [reports]);
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

  // per-technician summary (production + Darija-voice share)
  const perTech = useMemo(() => {
    const m = new Map<string, { rapports: number; cables: number; goulottes: number; voice: number }>();
    reports.forEach((r) => {
      if (!r.technicien) return;
      const e = m.get(r.technicien) ?? { rapports: 0, cables: 0, goulottes: 0, voice: 0 };
      e.rapports++; e.cables += num(r.cables_m); e.goulottes += num(r.goulottes_m);
      if (isVoice(r)) e.voice++;
      m.set(r.technicien, e);
    });
    return [...m.entries()].map(([tech, e]) => ({
      tech, rapports: e.rapports, cables: Math.round(e.cables), goulottes: Math.round(e.goulottes),
      darija: e.rapports ? Math.round((e.voice / e.rapports) * 100) : 0,
    })).sort((a, b) => b.rapports - a.rapports);
  }, [reports]);

  // recent reports + activity feed
  const recent = useMemo(() => [...reports].sort((a, b) => tsOf(b) - tsOf(a)).slice(0, 5), [reports]);
  const activity = useMemo(() => [...reports].sort((a, b) => tsOf(b) - tsOf(a)).slice(0, 6), [reports]);

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
      <Sidebar reviewOnly={reviewOnly} setReviewOnly={setReviewOnly} flagged={kFlagged}
        online={online} uptime={health?.uptime_seconds} />

      <div className="flex-1 min-w-0 flex flex-col">
        <Topbar onRefresh={load} loading={loading} query={query} setQuery={setQuery} />

        <main className="flex-1 px-6 py-6 space-y-6">
          {error && (
            <div className="rounded-lg border border-down/40 bg-down/10 px-4 py-3 text-sm text-down">
              {error}
            </div>
          )}

          {/* Activité */}
          <KpiSection title={t("section.activity")}>
            <StatCell icon={<FileText size={16} />} label={t("kpi.total")} value={kTotal} delta={wowReports} />
            <StatCell icon={<CalendarDays size={16} />} label={t("kpi.week")} value={kWeek} delta={wowReports} />
            <StatCell icon={<TrendingUp size={16} />} label={t("kpi.today")} value={kToday} hint={today()} tone="up" />
            <StatCell icon={<AlertTriangle size={16} />} label={t("kpi.review")} value={kFlagged}
              hint={t("kpi.review.hint", { n: pctReview })} tone={kFlagged ? "down" : "up"} />
          </KpiSection>

          {/* Production */}
          <KpiSection title={t("section.production")}>
            <StatCell icon={<Cable size={16} />} label={t("prod.cables")}
              value={`${pCables.toLocaleString()} ${t("prod.unit.m")}`} delta={wowCables} />
            <StatCell icon={<Ruler size={16} />} label={t("prod.goulottes")}
              value={`${pGoulottes.toLocaleString()} ${t("prod.unit.m")}`} delta={wowGoulottes} />
            <StatCell icon={<Building2 size={16} />} label={t("prod.bureaux")} value={pBureaux} delta={wowBureaux} />
            <StatCell icon={<Network size={16} />} label={t("prod.panneaux")} value={pPanneaux} delta={wowPanneaux} />
          </KpiSection>

          {/* Qualité */}
          <KpiSection title={t("section.quality")}>
            <StatCell icon={<Gauge size={16} />} label={t("quality.confidence")} value={`${avgConf}%`}
              hint={t("quality.confidence.hint", { n: scored.length })} tone={avgConf >= 70 ? "up" : "down"} />
            <StatCell icon={<ShieldAlert size={16} />} label={t("quality.review")} value={`${pctReview}%`}
              hint={t("quality.review.hint", { n: kFlagged })} tone={pctReview <= 15 ? "up" : "down"} />
            <StatCell icon={<FileWarning size={16} />} label={t("quality.incomplete")} value={`${pctIncomplete}%`}
              hint={t("quality.incomplete.hint")} tone={pctIncomplete <= 15 ? "up" : "down"} />
            <StatCell icon={<Mic size={16} />} label={t("quality.voice")} value={`${pctVoice}%`}
              hint={t("quality.voice.hint", { n: voiceN })} tone="up" />
          </KpiSection>

          {/* Cadence & système */}
          <KpiSection title={t("section.system")}>
            <StatCell icon={<Clock size={16} />} label={t("sys.lastReport")}
              value={lastTs ? <RelTime ts={lastTs} /> : dash} hint={t("sys.lastReport.hint")} tone="up" />
            <StatCell icon={<CalendarDays size={16} />} label={t("sys.busiestDay")}
              value={busiest.date ? busiest.date.slice(5) : dash} hint={t("sys.busiestDay.hint", { n: busiest.n })} tone="up" />
            <StatCell icon={<Users size={16} />} label={t("sys.avgPerTech")}
              value={avgPerTech ? avgPerTech.toFixed(1) : dash} hint={t("sys.avgPerTech.hint")} tone="up" />
            <StatCell icon={<Server size={16} />} label={t("sys.uptime")}
              value={online && health && Number.isFinite(health.uptime_seconds)
                ? fmtUptime(health.uptime_seconds) : (online ? t("sys.online") : dash)}
              status={online ? "online" : "offline"} />
          </KpiSection>

          {/* charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ChartCard title={t("chart.perDay.title")} subtitle={t("chart.perDay.subtitle")} delta={wowReports}>
              <PerDayChart data={perDay} />
            </ChartCard>
            <ChartCard title={t("chart.channel.title")} subtitle={t("chart.channel.subtitle")}>
              <ChannelChart data={perChannel} />
            </ChartCard>
          </div>

          {/* per-technician summary */}
          <PerTechTable rows={perTech} />

          {/* bottom row: recent reports · health · activity */}
          <section className="rounded-xl border border-line bg-card overflow-hidden grid grid-cols-1 lg:grid-cols-3 divide-y lg:divide-y-0 lg:divide-x divide-line">
            <RecentReports rows={recent} dash={dash} />
            <HealthPanel flagged={kFlagged} />
            <ActivityFeed rows={activity} />
          </section>

          {/* reports table */}
          <section className="rounded-xl border border-line bg-card">
            <div className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-line">
              <h2 className="text-sm font-semibold mr-auto">{t("table.title")}</h2>
              <Select value={fTech} onChange={setFTech} placeholder={t("filter.allTechs")} options={techs} />
              <Select value={fChantier} onChange={setFChantier} placeholder={t("filter.allChantiers")} options={chantiers} />
              <input type="date" value={fDate} onChange={(e) => setFDate(e.target.value)}
                className="h-9 rounded-md border border-line bg-panel px-2 text-sm text-ink [color-scheme:light] dark:[color-scheme:dark]" />
              <label className="flex items-center gap-2 text-sm text-muted select-none cursor-pointer">
                <input type="checkbox" checked={reviewOnly} onChange={(e) => setReviewOnly(e.target.checked)}
                  className="accent-[rgb(var(--ink))]" />
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

// ── relative time ───────────────────────────────────────────────────────
function RelTime({ ts }: { ts: number }) {
  const { t } = useI18n();
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60000);
  if (min < 1) return <>{t("time.now")}</>;
  if (min < 60) return <>{t("time.min", { n: min })}</>;
  const h = Math.floor(min / 60);
  if (h < 24) return <>{t("time.hour", { n: h })}</>;
  return <>{t("time.day", { n: Math.floor(h / 24) })}</>;
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
            <stop offset="100%" stopColor={c.accent} stopOpacity={0.25} />
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
function Sidebar({ reviewOnly, setReviewOnly, flagged, online, uptime }: {
  reviewOnly: boolean; setReviewOnly: (v: boolean) => void; flagged: number;
  online: boolean; uptime?: number;
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

      <div className="px-4 py-4 border-t border-line text-[11px] text-faint space-y-1.5">
        <div className="flex items-center gap-1.5 text-up">
          <CheckCircle2 size={13} /> {t("sidebar.status")}
        </div>
        <div className="flex items-center gap-1.5">
          <span className={"inline-block w-1.5 h-1.5 rounded-full " + (online ? "bg-up" : "bg-down")} />
          {online ? t("sys.online") : t("sys.offline")}
          {online && uptime != null && Number.isFinite(uptime) && <span className="text-faint">· {fmtUptime(uptime)}</span>}
        </div>
        © 2026 aznet.ma
      </div>
    </aside>
  );
}
function NavItem({ icon, label, active, muted, badge, onClick }: {
  icon: ReactNode; label: string; active?: boolean; muted?: boolean; badge?: number; onClick?: () => void;
}) {
  return (
    <button onClick={onClick} disabled={muted}
      className={"w-full flex items-center gap-3 px-2 py-2 rounded-md transition-colors " +
        (active ? "bg-cardhi text-ink font-medium"
          : muted ? "text-faint cursor-default" : "text-muted hover:bg-cardhi hover:text-ink")}>
      {icon}
      <span className="flex-1 text-left">{label}</span>
      {badge != null && (
        <span className="grid place-items-center min-w-5 h-5 px-1 rounded-full bg-down/20 text-down text-[11px] font-semibold">{badge}</span>
      )}
    </button>
  );
}

// ── Topbar ────────────────────────────────────────────────────────────
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
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("topbar.search")}
          className="w-full h-9 rounded-md border border-line bg-card pl-9 pr-3 text-sm text-ink placeholder:text-faint focus:outline-none focus:border-faint" />
      </div>
      <button className="hidden sm:grid place-items-center w-9 h-9 rounded-md text-muted hover:text-ink hover:bg-cardhi transition-colors"><Send size={16} /></button>
      <button className="hidden sm:grid place-items-center w-9 h-9 rounded-md text-muted hover:text-ink hover:bg-cardhi transition-colors"><Bell size={16} /></button>
      <LanguageToggle />
      <ThemeToggle />
      <button onClick={onRefresh} title={t("topbar.refresh")}
        className="flex items-center gap-2 h-9 px-3 rounded-md bg-ink text-bg text-sm font-medium hover:opacity-90 transition">
        <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
        <span className="hidden sm:inline">{t("topbar.refresh")}</span>
      </button>
    </header>
  );
}
function LanguageToggle() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="flex items-center rounded-md border border-line bg-card p-0.5" role="group" aria-label={t("topbar.lang")}>
      {LANGS.map((l: Lang) => (
        <button key={l} onClick={() => setLang(l)}
          className={"px-2 h-7 rounded text-xs font-medium uppercase transition-colors " +
            (lang === l ? "bg-ink text-bg" : "text-muted hover:text-ink")}>
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

// ── KPI section (framed panel with internal dividers) ───────────────────
function KpiSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-[11px] font-medium uppercase tracking-wider text-faint mb-2 px-0.5">{title}</h2>
      <div className="rounded-xl border border-line bg-card overflow-hidden grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 divide-y sm:divide-x divide-line">
        {children}
      </div>
    </section>
  );
}
function StatCell({ icon, label, value, hint, tone, delta, status }: {
  icon: ReactNode; label: string; value: ReactNode;
  hint?: string; tone?: "up" | "down"; delta?: number | null; status?: "online" | "offline";
}) {
  const { t } = useI18n();
  let footer: ReactNode;
  if (status) {
    const on = status === "online";
    footer = (
      <span className={"flex items-center gap-1.5 " + (on ? "text-up" : "text-down")}>
        <span className={"inline-block w-1.5 h-1.5 rounded-full " + (on ? "bg-up" : "bg-down")} />
        {on ? t("sys.online") : t("sys.offline")}
      </span>
    );
  } else if (delta !== undefined) {
    if (delta === null) footer = <span className="text-faint">{t("kpi.wow.na")}</span>;
    else {
      const up = delta >= 0; const Arrow = up ? TrendingUp : TrendingDown;
      footer = (
        <span className={"flex items-center gap-1.5 " + (up ? "text-up" : "text-down")}>
          <Arrow size={13} /> {t("kpi.wow", { d: (up ? "+" : "") + delta })}
        </span>
      );
    }
  } else {
    const Arrow = tone === "down" ? TrendingDown : TrendingUp;
    footer = (
      <span className={"flex items-center gap-1.5 " + (tone === "down" ? "text-down" : "text-up")}>
        <Arrow size={13} /> <span className="text-faint">{hint}</span>
      </span>
    );
  }
  return (
    <div className="p-5 transition-colors">
      <div className="flex items-center gap-2 text-muted text-sm">
        <span className="text-faint">{icon}</span>{label}
      </div>
      <div className="mt-3 text-3xl font-semibold tabular-nums">{value}</div>
      <div className="mt-3 text-xs">{footer}</div>
    </div>
  );
}

// ── Chart card (with optional WoW badge) ────────────────────────────────
function ChartCard({ title, subtitle, delta, children }: {
  title: string; subtitle: string; delta?: number | null; children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <div className="rounded-xl border border-line bg-card p-5">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {delta != null && (
          <span className={"inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium " +
            (delta >= 0 ? "bg-up/15 text-up" : "bg-down/15 text-down")}>
            {delta >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            {(delta >= 0 ? "+" : "") + delta}%
          </span>
        )}
      </div>
      <p className="text-xs text-faint mt-0.5 mb-4">{subtitle}</p>
      {children}
    </div>
  );
}

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

// ── Per-technician summary ──────────────────────────────────────────────
function PerTechTable({ rows }: {
  rows: { tech: string; rapports: number; cables: number; goulottes: number; darija: number }[];
}) {
  const { t } = useI18n();
  if (rows.length === 0) return null;
  return (
    <section className="rounded-xl border border-line bg-card">
      <div className="px-5 py-4 border-b border-line">
        <h2 className="text-sm font-semibold">{t("techtable.title")}</h2>
        <p className="text-xs text-faint mt-0.5">{t("techtable.subtitle")}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="px-5 py-3 font-medium">{t("techtable.tech")}</th>
              <th className="px-4 py-3 font-medium text-right">{t("techtable.reports")}</th>
              <th className="px-4 py-3 font-medium text-right">{t("techtable.cables")}</th>
              <th className="px-4 py-3 font-medium text-right">{t("techtable.goulottes")}</th>
              <th className="px-5 py-3 font-medium">{t("techtable.darija.head")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.tech} className="border-t border-line hover:bg-cardhi/50">
                <td className="px-5 py-3 text-ink">{r.tech}</td>
                <td className="px-4 py-3 text-right tabular-nums text-muted">{r.rapports}</td>
                <td className="px-4 py-3 text-right tabular-nums text-muted">{r.cables.toLocaleString()}</td>
                <td className="px-4 py-3 text-right tabular-nums text-muted">{r.goulottes.toLocaleString()}</td>
                <td className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-24 rounded-full bg-line overflow-hidden" title={t("techtable.darija")}>
                      <div className="h-full rounded-full bg-ink" style={{ width: `${r.darija}%` }} />
                    </div>
                    <span className="tabular-nums text-xs text-faint w-20">{r.darija}% / {100 - r.darija}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ── Recent reports panel ────────────────────────────────────────────────
function RecentReports({ rows, dash }: { rows: Report[]; dash: string }) {
  const { t } = useI18n();
  return (
    <div className="p-5">
      <h2 className="text-sm font-semibold">{t("recent.title")}</h2>
      <p className="text-xs text-faint mt-0.5 mb-3">{t("recent.subtitle")}</p>
      {rows.length === 0 ? (
        <p className="text-sm text-muted py-6 text-center">{t("recent.none")}</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((r) => (
            <li key={r._row} className="flex items-center gap-3 py-2.5">
              <span className="text-xs">{r.canal === "whatsapp" ? "🟢" : "🔵"}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-ink truncate">{r.technicien || dash}</div>
                <div className="text-xs text-faint truncate">{r.chantier || dash}</div>
              </div>
              <span className="text-xs text-faint tabular-nums shrink-0">{(r.heure || "").slice(0, 5)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Health empty-state panel ────────────────────────────────────────────
function HealthPanel({ flagged }: { flagged: number }) {
  const { t } = useI18n();
  const ok = flagged === 0;
  return (
    <div className="p-5 flex flex-col">
      <h2 className="text-sm font-semibold">{t("health.title")}</h2>
      <div className="flex-1 flex flex-col items-center justify-center text-center py-6 gap-3">
        <span className={"grid place-items-center w-12 h-12 rounded-full " + (ok ? "bg-up/15 text-up" : "bg-down/15 text-down")}>
          {ok ? <CheckCircle2 size={22} /> : <AlertTriangle size={22} />}
        </span>
        <div className="text-base font-semibold">{ok ? t("health.caughtUp") : t("health.pending", { n: flagged })}</div>
        <p className="text-xs text-muted max-w-[16rem]">{ok ? t("health.caughtUp.sub") : t("health.pending.sub")}</p>
      </div>
    </div>
  );
}

// ── Activity feed panel ─────────────────────────────────────────────────
function ActivityFeed({ rows }: { rows: Report[] }) {
  const { t } = useI18n();
  return (
    <div className="p-5">
      <h2 className="text-sm font-semibold">{t("activity.title")}</h2>
      <p className="text-xs text-faint mt-0.5 mb-3">{t("activity.subtitle")}</p>
      {rows.length === 0 ? (
        <p className="text-sm text-muted py-6 text-center">{t("activity.none")}</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((r) => {
            const flagged = isFlagged(r);
            const ts = tsOf(r);
            return (
              <li key={r._row} className="flex gap-3">
                <span className={"grid place-items-center w-7 h-7 rounded-full shrink-0 " +
                  (flagged ? "bg-down/15 text-down" : "bg-cardhi text-muted")}>
                  {flagged ? <AlertTriangle size={14} /> : <FileText size={14} />}
                </span>
                <div className="min-w-0">
                  <div className="text-sm text-ink">
                    {flagged ? t("activity.flagged", { tech: r.technicien || "?" }) : t("activity.sent", { tech: r.technicien || "?" })}
                  </div>
                  <div className="text-xs text-faint">{ts ? <RelTime ts={ts} /> : ""}</div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ── Reports table row ───────────────────────────────────────────────────
function Row({ r, edit, dash, expanded, toggle }: {
  r: Report; edit: (r: Report, field: string) => void; dash: string; expanded: boolean; toggle: () => void;
}) {
  const { t } = useI18n();
  const flagged = isFlagged(r);
  const cell = "px-4 py-3 whitespace-nowrap";
  const ed = cell + " cursor-pointer hover:text-ink";
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
            <div><span className="text-faint">{t("detail.otherWork")}</span>{" "}
              <span className="cursor-pointer hover:text-ink" onClick={() => edit(r, "autres_travaux")}>{r.autres_travaux || dash}</span></div>
            <div><span className="text-faint">{t("detail.observations")}</span>{" "}
              <span className="cursor-pointer hover:text-ink" onClick={() => edit(r, "observations")}>{r.observations || dash}</span></div>
            <div><span className="text-faint">{t("detail.audio")}</span> {r.lien_audio || dash} <em className="text-faint">{t("detail.audioNote")}</em></div>
          </td>
        </tr>
      )}
    </>
  );
}
