import { useEffect, useMemo, useState } from "react";
import { fetchReports, patchReport, Report } from "./api";
import "./App.css";

// columns the manager can correct inline (writes back to the Sheet)
const EDITABLE = [
  "technicien", "chantier", "client", "type_activite", "goulottes_m", "cables_m",
  "bureaux_termines", "panneaux_raccordes", "autres_travaux", "observations", "resume",
] as const;

export default function App() {
  return <Dashboard />;
}

function Dashboard() {
  const [reports, setReports] = useState<Report[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [fTech, setFTech] = useState("");
  const [fChantier, setFChantier] = useState("");
  const [fDate, setFDate] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
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

  const filtered = reports.filter((r) =>
    (!fTech || r.technicien === fTech) &&
    (!fChantier || r.chantier === fChantier) &&
    (!fDate || r.date === fDate) &&
    (!reviewOnly || String(r.flag_review).toLowerCase() === "true")
  );

  const edit = async (r: Report, field: string) => {
    const current = (r as unknown as Record<string, string>)[field] ?? "";
    const next = window.prompt(`Corriger « ${field} » (ligne ${r._row})`, current);
    if (next === null || next === current) return;
    try {
      await patchReport(r._row, field, next);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="dash">
      <header>
        <h1>Rapports journaliers</h1>
        <div className="actions">
          <button onClick={load}>Rafraîchir</button>
        </div>
      </header>

      <div className="filters">
        <select value={fTech} onChange={(e) => setFTech(e.target.value)}>
          <option value="">Tous les techniciens</option>
          {techs.map((t) => <option key={t}>{t}</option>)}
        </select>
        <select value={fChantier} onChange={(e) => setFChantier(e.target.value)}>
          <option value="">Tous les chantiers</option>
          {chantiers.map((c) => <option key={c}>{c}</option>)}
        </select>
        <input type="date" value={fDate} onChange={(e) => setFDate(e.target.value)} />
        <label className="review-toggle">
          <input type="checkbox" checked={reviewOnly} onChange={(e) => setReviewOnly(e.target.checked)} />
          À vérifier uniquement
        </label>
        <span className="count">{filtered.length} rapport(s)</span>
      </div>

      {error && <p className="error">{error}</p>}
      {loading ? <p>Chargement…</p> : (
        <table>
          <thead>
            <tr>
              <th>Date</th><th>Heure</th><th>Canal</th><th>Technicien</th><th>Chantier</th>
              <th>Activité</th><th>Goulottes (m)</th><th>Câbles (m)</th><th>Bureaux</th>
              <th>Panneaux</th><th>Résumé</th><th>Confiance</th><th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <>
                <tr key={r._row} className={String(r.flag_review).toLowerCase() === "true" ? "flagged" : ""}>
                  <td>{r.date}</td>
                  <td>{r.heure}</td>
                  <td>{r.canal === "whatsapp" ? "🟢 WA" : "🔵 TG"}</td>
                  <td className="editable" onClick={() => edit(r, "technicien")}>{r.technicien}</td>
                  <td className="editable" onClick={() => edit(r, "chantier")}>{r.chantier || "—"}</td>
                  <td className="editable" onClick={() => edit(r, "type_activite")}>{r.type_activite || "—"}</td>
                  <td className="editable num" onClick={() => edit(r, "goulottes_m")}>{r.goulottes_m || "—"}</td>
                  <td className="editable num" onClick={() => edit(r, "cables_m")}>{r.cables_m || "—"}</td>
                  <td className="editable num" onClick={() => edit(r, "bureaux_termines")}>{r.bureaux_termines || "—"}</td>
                  <td className="editable num" onClick={() => edit(r, "panneaux_raccordes")}>{r.panneaux_raccordes || "—"}</td>
                  <td className="editable resume" onClick={() => edit(r, "resume")}>{r.resume}</td>
                  <td className="num">
                    {r.confidence ? `${Math.round(parseFloat(r.confidence) * 100)}%` : "—"}
                    {String(r.flag_review).toLowerCase() === "true" && <span className="badge">à vérifier</span>}
                  </td>
                  <td>
                    <button className="small" onClick={() => setExpanded(expanded === r._row ? null : r._row)}>
                      {expanded === r._row ? "▲" : "▼"}
                    </button>
                  </td>
                </tr>
                {expanded === r._row && (
                  <tr className="details">
                    <td colSpan={13}>
                      <strong>Transcription complète :</strong> {r.rapport_complet || "—"}<br />
                      <strong>Autres travaux :</strong>{" "}
                      <span className="editable" onClick={() => edit(r, "autres_travaux")}>{r.autres_travaux || "—"}</span><br />
                      <strong>Observations :</strong>{" "}
                      <span className="editable" onClick={() => edit(r, "observations")}>{r.observations || "—"}</span><br />
                      <strong>Audio :</strong> {r.lien_audio || "—"} <em>(lien durable: à venir — Drive upload)</em>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}
      <footer>Cliquer une cellule pour corriger — écrit directement dans Google Sheets. Colonnes éditables : {EDITABLE.join(", ")}.</footer>
    </div>
  );
}
