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
