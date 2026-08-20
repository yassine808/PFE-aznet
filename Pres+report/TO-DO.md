# TO-DO — report & defence

What is still open. Everything closed moved to `FIXED.md` on 2026-08-20, with
the reasoning recorded at the time — a finished item whose *why* was deleted is
indistinguishable from one nobody understood.

Section titles say "from the … pass" because that is where these items were
raised; the work done in the same pass is in `FIXED.md` under the same heading.

---

## Still open — from the 2026-08-18 pass

Three commits, all pushed to `main`: `f72d06b` (report + deck), `559a64d` (CI red
for three days), `663febc` (SonarCloud step made fatal). Nothing left uncommitted
except `build/reference.docx.prespacing`, the untracked backup from §7.

### SonarCloud — items 1 and 8, closed

Still open, and it needs the token:

- [ ] **Re-read Table 4.16 against the CI-based scan.** A CI scan analyses a slightly
      different file set than AutoScan did, so `ncloc`, `code_smells` and the debt figure
      may have shifted; the ratings should not have. The public API answers
      `Project doesn't exist` without authentication, so this needs `SONAR_TOKEN`:
      ```bash
      curl -s -u "$SONAR_TOKEN:" \
        "https://sonarcloud.io/api/measures/component?component=yassine808_PFE-aznet&metricKeys=coverage,ncloc,bugs,vulnerabilities,code_smells,sqale_index"
      ```
- [ ] **Screenshot of the SonarCloud dashboard** for the §4.9.4 placeholder
      (`*[FIGURE À INSÉRER — capture du tableau de bord SonarCloud.]*`).

### CI was red for three days, and nobody could see it

Found while checking whether the Sonar job had run. Three separate faults, all in `559a64d`:

- [ ] **PUSH THE WORKFLOW TO n8n.** The repo fix changes nothing in production: n8n keeps
      its own copy in its volume (deploy trap 2 in CLAUDE.md). Until it is re-imported or
      pushed with `PUT /api/v1/workflows/{id}`, every reply that names a chantier is still
      running the broken expression. **This is the only item on this page that affects a
      live technician.**

### The STT contradiction — item 2, closed

Framing **(a)** chosen: the benchmark designates an accuracy reference, the call order is an
operations decision.

### Item 5 — the self-authored test cases, closed

### Item 4 — the Dependabot claim, corrected against the API

- [ ] **The manual-process baseline is still missing** — see the open items below. It remains
      the highest-value missing paragraph in the document.

### Item 6 — the presentation, closed

### Found in passing

Report rebuilt: **142 pages** (140 before; the new prose added two).

---

## To do — handoff, 2026-08-18

State: **CI green**, SonarCloud analysing on every push with coverage, report at 142 pages,
deck at 32 slides. Last commit `663febc`.

**13 days to the deadline (31 August 2026).** Order below is the order I would do it in.

---

### 1. Push the fixed workflow to n8n — the only live-impact item

Covered above. Until this is done, a technician whose report names a chantier gets a reply
built from a broken expression. `n8n/README.md` §7b has the push procedure; the node set is
unchanged, so no `--allow-node-diff` is needed.

- [ ] Workflow re-imported or pushed
- [ ] One real voice note sent end to end, reply checked for the chantier line

---

### 2. The field data — items 4 and 5 of the old list, still open

Deliberately skipped on 18 August; they need the author on site, and they are what turns the
report from a description into an evaluation.

- [ ] **Baseline of the manual process.** The report asserts a gain and never measures what it
      replaced. Even rough figures from the director — "before: ~10 min per report, ~40 % of
      days missing" — close it. One conversation.
- [ ] **End-to-end latency** (§4.6.4). Per-engine numbers exist (1,53 s Groq → 7,7 s local);
      what is missing is "the technician waits N seconds from voice note to reply". A
      stopwatch on five real notes.
- [ ] **Pilot results** (§4.6.5): number of reports processed, technician and management
      feedback, incidents. Same field trip.

### 3. The 12 remaining `[À COMPLÉTER]` in the report

`grep -n "À COMPLÉTER" Pres+report/Rapport-PFE.md` lists them. Grouped by what they need:

**Administrative — you just have to type them (5)**
- [ ] line 38 — cover: academic supervisor, industrial supervisor
- [ ] line 46 — cover: defence date, jury members
- [ ] lines 63, 65 — acknowledgements: same two names
- [ ] line 204 — §1.2 AZNET fact sheet: founding date, headcount, org chart, client references
      (marked "to validate with the industrial supervisor")

**Pilot results — needs field data (4)**
- [ ] lines 81 / EN / AR — one sentence of pilot figures in each abstract
- [ ] line 1365 — the "pilot with technicians" row of the delivered-scope table
- [ ] line 1392 — §4.6.4 end-to-end latency. **Note:** per-engine latencies exist (1.53 s Groq →
      7.7 s local); what is missing is "the technician waits N seconds from voice note to reply".
      A stopwatch on five real notes closes this.
- [ ] line 1396 — §4.6.5 pilot: number of reports processed, technician and management feedback,
      incidents
- [ ] lines 1611, 1613 — the same gap restated in the conclusion and in the limits

**Bibliography (1)**
- [ ] line 1653 — additional academic references on dialectal Arabic ASR, per your filière's
      requirements

---

### 4. Two claims in the report I could not verify  — Dependabot corrected 2026-08-18, baseline still open

> Superseded in part: the Dependabot figure was corrected against the API (38 opened, none
> merged). The manual-process baseline below is still the open half.

- [ ] **"Thirty-five Dependabot pull requests were opened"** (§4.9.3). I found no evidence for the
      number. Either count them (`gh pr list --state all --author "app/dependabot" | wc -l`) and
      correct it, or drop the figure and keep the mechanism, which is verified.
- [ ] **Comparison against the manual process.** The report asserts a gain but never measures the
      baseline. Even rough numbers — "before: ~10 min per report, ~40 % of days missing" — turn an
      assertion into a result. This is probably the highest-value missing paragraph in the whole
      document.

---

### 5. A methodological weakness worth owning before the jury names it  ✅ done 2026-08-18

> The paragraph is in §4.3.9. Kept below for the reasoning that produced it.

The ten extraction test cases (`benchmark/dataset/text_cases.json`, Table 4.6) were written by the
author of the system under test. That is a genuine limitation: the cases encode the same
assumptions as the prompts they evaluate.

§4.3.2 already does exactly the right thing for the transcription benchmark — it states plainly
that ground truth was discarded and why. §4.3.9 should do the same for this. Owning it costs one
paragraph; being caught by it costs credibility.

- [ ] Paragraph added to §4.3.9

---

### 6. Port all of this into the presentation  ✅ done 2026-08-18

> All seven line edits applied and three slides added; the deck builds at 32 slides. The
> table below is kept as the record of what was wrong.

`Pres+report/presentation.py` still carries the figures the report no longer uses. Concretely:

| Line | Currently says | Should say |
|---|---|---|
| 892 | "Dès la semaine 0" | "Dès la phase 3" |
| 893 | "le planning la prévoyait au sprint 2" | "le planning la prévoyait en phase 4" |
| 926 | stat tile `220` / "commits en 29 jours (15 juil. – 12 août 2026)" | replace entirely — no commit statistics. Suggest `6 mois` / "2 mars – 31 août 2026" |
| 928 | stat tile `272` tests | `288` tests |
| 934 | "Les 17 contrôles, par famille" | "Les 18 contrôles, par famille" |
| 936 | "API — ruff, types, 272 tests" | "288 tests" |
| 952 | "chacune franchit les 17 contrôles" | "les 18 contrôles" |

Also missing from the deck entirely:
- [ ] The planning slide needs the 7-phase timeline from §1.6.2, not the 4 sprints.
- [ ] A slide for the **two extraction benchmarks** (§4.3.9 / §4.3.10) — the deck only covers the
      STT benchmark. The strongest single number there is `llama-3.1-8b-instant`: fastest model
      tested, and five invented values.
- [ ] A slide (or a line) for the **SonarCloud result**, now that the gate passes: 0 bugs,
      0 vulnerabilities, A/A/A, 18 green CI checks.

Rebuild with `Pres+report/build.ps1` for the report; the deck is generated by running
`presentation.py`.

---

### 7. Spacing — code blocks and the ملخص  ✅ done 2026-08-17

**Root cause was style inheritance, not figures or spacer paragraphs.**

`SourceCode` in `build/reference.docx` was `basedOn="Normal"` and overrode only
`wordWrap`. So it inherited `Normal`'s `line="360" lineRule="auto"` (1.5 spacing) and
`jc="both"` (justified), plus `docDefaults`' `after="200"`. Every code block — and the
annexes from page ~89 on are almost nothing but code blocks — was therefore set 1.5-spaced
and justified.

**Note on the size of the win.** An earlier estimate of 25–35 pages was wrong. Pandoc emits
a fenced code block as **one** `SourceCode` paragraph with soft line breaks inside, not one
paragraph per line — there are only **11** such paragraphs in the whole document. So
`after="200"` was paid 11 times, and the entire saving came from the line spacing. Six pages.

**If more compaction is wanted from page 89 on**, the remaining candidates are untouched and
unverified: explicit `<w:br w:type="page"/>` blocks in the Markdown (one per annexe), figure
heights in Annexe H, and `keep_with_next` on captions.

Backup of the pre-change reference is `build/reference.docx.prespacing` (untracked).
Fix in `build/reference.docx` or the Markdown, never by hand in the produced `.docx` —
the build overwrites it.

---

### 8. Small, optional

- [ ] **15 SonarCloud code smells** remain (5 of them in `presentation.py`: cognitive complexity,
      duplicated literals, a non-conforming variable name). Maintainability is already A and the
      debt is 121 minutes total, so this is cosmetic.
- [ ] **Dashboard has no test runner**, so `sonar.javascript.lcov.reportPaths` points at a file
      that is never produced. Harmless (Sonar logs a warning), but it means the 60 % coverage
      figure describes the Python service only — worth one clause in §4.9.4 if you want to be
      precise.
- [ ] `Pres+report/build/reference.docx.bak` was removed after patching the footer; if you ever
      need the original `NUMPAGES` footer back, it is in git history before commit `96eaf35`.

---

### Verification commands, for whoever picks this up

```bash
# Test suite with coverage (~8 min, no API keys, no database needed)
cd api && .venv/Scripts/python.exe -m pytest -q --cov=app --cov-report=term

# Current SonarCloud state
curl -s -u "$SONAR_TOKEN:" "https://sonarcloud.io/api/qualitygates/project_status?projectKey=yassine808_PFE-aznet"

# CI status
gh run list --workflow=ci.yml --limit 1

# Rebuild the report (kills Word first; ~1 min, add -ExportPdf for the PDF, ~20 min)
powershell -ExecutionPolicy Bypass -File Pres+report/build.ps1
```

### Deck — design, morph, speaker notes  ✅ done 2026-08-18

Rebuilt: 32 slides. `presentation.py` stays the source of truth — a slide fixed
only in PowerPoint is a fix that disappears on the next build.

---

## Still open — from the 2026-08-18 second-session pass

Chaque case ci-dessous a été **vérifiée sur les données réelles** avant d'être
cochée, jamais sur la foi du code. La preuve est citée à chaque ligne.

### Le journal : une ligne par message

### Les défauts du Sheet signalés le 18 août

### Deux bugs d'empilement trouvés en chemin

### Le tableau de bord

### La présentation

**Suite de tests : 414 passants, ruff propre.** API, workflow n8n et image `web`
redéployés et vérifiés dans les conteneurs.

### Reste à faire, connu

- [ ] `DASHBOARD_BASE_URL` / `dashboard_url` n'est pas défini : sans origine
      publique, ni `Lien audio` ni `Correlation id` ne peuvent devenir des liens
      cliquables. Le nom d'hôte Tailscale ferait l'affaire. Rappel : un `.env`
      modifié n'atteint pas un conteneur déjà lancé — `up -d`, pas `restart`.
- [ ] `DGH` ligne 4 : cellule « Lien audio » mêlant prose et neuf identifiants,
      héritée de l'ancienne fusion. À reprendre à la main.
