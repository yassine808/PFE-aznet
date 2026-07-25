// Thin client for the FastAPI backend. No auth: dashboard + API live on the
// admin's PC only (localhost), decided 2026-07-23.
const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface Report {
  _row: number;
  date: string;
  heure: string;
  canal: string;
  technicien: string;
  role: string;
  chantier: string;
  client: string;
  type_activite: string;
  goulottes_m: string;
  cables_m: string;
  bureaux_termines: string;
  panneaux_raccordes: string;
  autres_travaux: string;
  observations: string;
  resume: string;
  rapport_complet: string;
  confidence: string;
  flag_review: string;
  lien_audio: string;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const r = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...(init?.headers ?? {}), "Content-Type": "application/json" },
  });
  if (!r.ok) throw new Error(`Erreur ${r.status}: ${await r.text()}`);
  return r;
}

export async function fetchReports(): Promise<Report[]> {
  const r = await request("/reports");
  return (await r.json()).reports;
}

export async function patchReport(row: number, field: string, value: string): Promise<void> {
  await request(`/reports/${row}`, {
    method: "PATCH",
    body: JSON.stringify({ field, value }),
  });
}

export interface Health {
  status: string;
  version: string;
  uptime_seconds: number;
  started_at: number;
  stt_providers: string[];
  stt_default: string;
}

export async function fetchHealth(): Promise<Health> {
  const r = await request("/health");
  return r.json();
}

// ── Pipeline logs (Postgres-backed, written by n8n at every stage) ─────────

export interface LogEntry {
  id: number;
  ts: string;
  correlation_id: string | null;
  channel: string | null;
  technicien: string | null;
  stage: string;
  level: "info" | "warn" | "error";
  message: string | null;
  duration_ms: number | null;
  payload: Record<string, unknown> | null;
}

export interface LogsResponse {
  logs: LogEntry[];
  stats: {
    last_24h: Record<string, number>;
    pending_sheet_writes: number;
    retention_days: number;
  };
}

export interface LogFilters {
  level?: string;
  channel?: string;
  stage?: string;
  search?: string;
  limit?: number;
}

export async function fetchLogs(f: LogFilters = {}): Promise<LogsResponse> {
  const qs = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  const r = await request(`/logs?${qs.toString()}`);
  return r.json();
}
