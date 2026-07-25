import { Activity, AlertTriangle, ChevronDown, Clock, Inbox, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchLogs, type LogEntry, type LogsResponse } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";

const POLL_MS = 5000;

const LEVELS = ["", "info", "warn", "error"] as const;
const CHANNELS = ["", "telegram", "whatsapp"] as const;
const STAGES = [
  "", "received", "authorized", "denied", "transcribed", "extracted",
  "replied", "sheet_written", "sheet_failed", "duplicate", "api", "workflow_error",
] as const;

function levelVariant(level: string) {
  if (level === "error") return "error" as const;
  if (level === "warn") return "warn" as const;
  return "info" as const;
}

/** Live tail of the n8n pipeline. Every stage of every voice note lands here,
 *  plus the API's own errors — joined by correlation_id across both processes. */
export function LogsPanel() {
  const { t, lang } = useI18n();
  const [data, setData] = useState<LogsResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState(true);
  const [level, setLevel] = useState("");
  const [channel, setChannel] = useState("");
  const [stage, setStage] = useState("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const reqId = useRef(0);

  // Typing must not fire a request per keystroke: `search` drives the input,
  // `debounced` drives the fetch. Without this, every character also restarted
  // the 5s poll timer, so a fast typist could starve the poll entirely.
  useEffect(() => {
    const id = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  const load = useCallback(async () => {
    // Guard against out-of-order responses: a slow request for older filters
    // must not overwrite fresher data that already landed.
    const mine = ++reqId.current;
    try {
      const res = await fetchLogs({ level, channel, stage, search: debounced, limit: 200 });
      if (mine !== reqId.current) return;
      setData(res);
      setError("");
    } catch (e) {
      if (mine !== reqId.current) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (mine === reqId.current) setLoading(false);
    }
  }, [level, channel, stage, debounced]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!live) return;
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [live, load]);

  const logs = data?.logs ?? [];
  const stats = data?.stats;
  const errors24h = stats?.last_24h.error ?? 0;
  const warns24h = stats?.last_24h.warn ?? 0;
  const infos24h = stats?.last_24h.info ?? 0;
  const pending = stats?.pending_sheet_writes ?? 0;

  // t() falls back to the raw key when a translation is missing, which would
  // leak "logs.stage.foo" into the UI the moment the backend adds a stage the
  // frontend does not know yet. Show the raw stage name instead.
  const stageLabel = (stage: string) => {
    const key = `logs.stage.${stage}`;
    const label = t(key);
    return label === key ? stage : label;
  };

  const fmtTime = (iso: string) => {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleTimeString(lang === "ar" ? "ar-MA" : lang);
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-sm font-medium text-muted">{t("logs.title")}</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setLive((v) => !v)}
            className={cn(
              "flex items-center gap-2 h-8 px-2.5 rounded-md border border-line text-[13px] transition",
              live ? "text-up" : "text-muted hover:bg-cardhi",
            )}
            aria-pressed={live}
          >
            <span className="relative inline-flex w-2 h-2">
              {live && <span className="absolute inline-flex w-full h-full rounded-full bg-up opacity-60 animate-ping" />}
              <span className={cn("relative inline-flex w-2 h-2 rounded-full", live ? "bg-up" : "bg-faint")} />
            </span>
            {live ? t("logs.live") : t("logs.paused")}
          </button>
          <button
            onClick={load}
            className="flex items-center gap-2 h-8 px-2.5 rounded-md border border-line text-[13px] text-muted hover:bg-cardhi transition"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            {t("logs.refresh")}
          </button>
        </div>
      </div>

      {/* counters */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile icon={<Activity size={15} />} label={t("logs.stat.events")} value={infos24h + warns24h + errors24h} />
        <StatTile icon={<AlertTriangle size={15} />} label={t("logs.stat.errors")} value={errors24h} tone={errors24h ? "down" : "up"} />
        <StatTile icon={<Clock size={15} />} label={t("logs.stat.warns")} value={warns24h} tone={warns24h ? "warn" : "up"} />
        <StatTile icon={<Inbox size={15} />} label={t("logs.stat.pending")} value={pending} tone={pending ? "down" : "up"} />
      </div>

      <Card>
        <CardHeader className="border-b border-line">
          <CardTitle className="flex items-center gap-2 text-muted">{t("logs.stream")}</CardTitle>
          <div className="flex flex-wrap items-center gap-2 pt-2">
            <Select value={level} onChange={setLevel} options={LEVELS} labelKey="logs.filter.level" />
            <Select value={channel} onChange={setChannel} options={CHANNELS} labelKey="logs.filter.channel" />
            <Select value={stage} onChange={setStage} options={STAGES} labelKey="logs.filter.stage" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("logs.filter.search")}
              className="h-8 px-2.5 rounded-md border border-line bg-card text-[13px] placeholder:text-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-faint"
            />
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {error ? (
            <p className="p-5 text-sm text-down">{error}</p>
          ) : logs.length === 0 ? (
            <p className="p-8 text-center text-sm text-faint">{loading ? t("logs.loading") : t("logs.empty")}</p>
          ) : (
            <ScrollArea className="h-[420px]">
              <ul className="divide-y divide-line">
                {logs.map((l) => (
                  <LogRow
                    key={l.id}
                    log={l}
                    open={open === l.id}
                    onToggle={() => setOpen(open === l.id ? null : l.id)}
                    time={fmtTime(l.ts)}
                    stageLabel={stageLabel(l.stage)}
                  />
                ))}
              </ul>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function StatTile({ icon, label, value, tone }: {
  icon: React.ReactNode; label: string; value: number; tone?: "up" | "down" | "warn";
}) {
  const color = tone === "down" ? "text-down" : tone === "warn" ? "text-accent" : tone === "up" ? "text-up" : "text-ink";
  return (
    <div className="rounded-lg border border-line bg-card p-4">
      <div className="flex items-center gap-2 text-muted text-sm">
        {icon} {label}
      </div>
      <div className={cn("mt-2 text-2xl font-semibold tabular-nums", color)}>{value}</div>
    </div>
  );
}

function Select({ value, onChange, options, labelKey }: {
  value: string; onChange: (v: string) => void; options: readonly string[]; labelKey: string;
}) {
  const { t } = useI18n();
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={t(labelKey)}
      className="h-8 px-2 rounded-md border border-line bg-card text-[13px] text-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-faint"
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o === "" ? t(labelKey) : o}
        </option>
      ))}
    </select>
  );
}

function LogRow({ log, open, onToggle, time, stageLabel }: {
  log: LogEntry; open: boolean; onToggle: () => void; time: string; stageLabel: string;
}) {
  return (
    <li>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-cardhi/50 transition-colors"
        aria-expanded={open}
      >
        <span className="text-[12px] tabular-nums text-faint w-20 shrink-0">{time}</span>
        <Badge variant={levelVariant(log.level)}>{log.level}</Badge>
        <span className="text-[12px] text-muted w-28 shrink-0 truncate">{stageLabel}</span>
        <span className="flex-1 min-w-0 truncate text-[13px]">{log.message}</span>
        {log.technicien && <span className="text-[12px] text-faint shrink-0">{log.technicien}</span>}
        {log.duration_ms != null && (
          <span className="text-[12px] tabular-nums text-faint shrink-0">{log.duration_ms} ms</span>
        )}
        <ChevronDown size={14} className={cn("shrink-0 text-faint transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <pre className="mx-4 mb-3 overflow-x-auto rounded-md border border-line bg-bg p-3 text-[12px] text-muted">
{JSON.stringify({ correlation_id: log.correlation_id, channel: log.channel, payload: log.payload }, null, 2)}
        </pre>
      )}
    </li>
  );
}
