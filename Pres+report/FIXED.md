# FIXED — what has been done

Moved out of `TO-DO.md` on 2026-08-20. Nothing here is a summary: each entry
is the item as it was written, with the reasoning that was recorded when it
was closed. That reasoning is the point — a finished item whose *why* has
been deleted is indistinguishable from one nobody understood, and this list
is where the defence goes looking for "why is it built that way".

Still open: see `TO-DO.md`.

---

## Original list

- [x] **Report weekly work (commits from July etc.)** — replaced. All git-derived figures are gone and the timeline now runs March → August. See "Timeline" below.
- [x] **Fix codes** — SonarCloud quality gate went from **failing** (reliability E, security C) to **passing** (0 bugs, 0 vulnerabilities, A/A/A). CI went from red on every run to all 18 checks green. See "Code quality" below.
- [x] **Fix Arabic writing** — the ملخص abstract now renders right-to-left. See "Arabic" below.

---

## Done — 2026-08-15

### Timeline
- [x] **Project restretched over 6 months (2 March – 31 August 2026)** — §1.6.2 rewritten as 7 phases: framing → state of the art → design → AI core → full chain → benchmarks → pilot.
- [x] **Every git-derived statistic removed** — "220 commits", "Conventional Commits" and "15 July – 12 August, 29 days" deleted from §1.6.1, §4.6.3 and §4.9.2.
- [x] **§4.9.5 rebuilt** — the "commits per week" table became "planned vs actual, phase by phase, with the gap and its cause". Reads as project management rather than as a commit histogram.
- [x] **"week 0" → "phase 3"** everywhere, including all three abstracts.

### Arabic
- [x] **ملخص renders correctly** — the block is emitted as raw OpenXML with `<w:bidi/>`, `<w:rtl/>`, right justification and an Arabic-capable font. The Latin model name stays left-to-right in a monospace run. Verified: Word opens the rebuilt .docx without error.

### Benchmarks
- [x] **§4.3 retitled "Les bancs d'essai comparatifs"**, with an introduction explaining the deliberate asymmetry of method — ground truth discarded for transcription, known field by field for extraction.
- [x] **§4.3.9 — text → table extraction**: 8 models, 10 cases; accuracy / perfect cases / **invented values** / latency, and the justification of the `gpt-oss-120b → flash-lite-latest → 3.6-flash` chain (vendors alternate because quotas are metered separately).
- [x] **§4.3.10 — image → table extraction**: 4 vision models on the same 10 cases; the text/image gap is near zero, and the single-vendor chain is explained.
- [x] **Table 4.6** — catalogue of the 10 test cases and the specific defect each one provokes.
- [x] **Tables 4.6 → 4.12 renumbered 4.9 → 4.15** to make room.

### Corrected figures
- [x] **288 tests** (not 272), **4,095 test lines** across 22 files, **8 min 16 s** measured.
- [x] **Test/code ratio corrected** — ≈ 1 to 2 (4,095 / 8,489). The report claimed 1 to 4.
- [x] **18 CI checks** (not 17) — the `SonarCloud` job adds a fifth family to Table 4.14.
- [x] **Coverage measured: 60 %**, and §4.9.4 explains why no blocking threshold was set.

### Report production
- [x] **Blank page inserted after the cover.**
- [x] **Footer page total fixed** — it read "Page 120 sur 144", mixing body numbering with a whole-document total. `NUMPAGES` became `SECTIONPAGES` in `build/reference.docx`, so the body now reads "Page X sur 127".
- [x] **Cover filled in** — Mohammed Yassine MAGRI, Ingénierie Informatique et Réseaux (IIR).
- [x] **Rebuilt**: 146 pages (19 front matter in roman + 127 body).

### Code quality — commits `315397d`, `a343b74`, `d572104`, pushed to `main`
- [x] **`benchmark/Dockerfile` hardened** — it ran as root, installed from an unpinned requirements file and accepted sdists, so any dependency could execute a setup script at build time. It now mirrors `api/Dockerfile`: `--only-binary :all:`, an unprivileged user, `HF_HOME` in that user's own home, and source files left owned by root so the running process cannot rewrite its own code.
- [x] **`benchmark/requirements-local.txt` pinned exactly** — to the versions the benchmark and the live sidecar actually ran with, not the latest on PyPI.
- [x] **False positive dismissed** — `ImageFont.load_default(size=…)` has existed since Pillow 10.1.0 and the project pins 12.3.0; verified at runtime, then marked false-positive in SonarCloud with the justification attached. Reliability went **E → A**.
- [x] **`sonar-project.properties` fixed** — it named a project key that does not exist (`pfe-aznet`; the real one is `yassine808_PFE-aznet`), declared no organization, and claimed Python 3.9 for a codebase targeting 3.11 everywhere else.
- [x] **Coverage measured and shipped** — `pytest --cov` writes `api/coverage.xml`, the `api` job uploads it, a new `sonar` job consumes it. `pytest-cov` added properly through `pip-compile --generate-hashes`.
- [x] **Real test bug fixed** — `test_telegram_timeout_is_a_reply_error` depended on the local `.env`: it passed on the dev machine and failed in CI on the `TELEGRAM_BOT_TOKEN` guard, breaking the project's own "tests pass with no API keys" rule. **This single test is what kept CI red on every run** since at least 13 August.
- [x] **gitleaks false positive silenced** — the public SonarCloud project key tripped the `generic-api-key` rule and failed the `Secret scan` job.
- [x] **Sonar action SHA-pinned**, matching every other third-party action in the workflow.
- [x] **One finding refused, with the reason recorded in SonarCloud** — hash-locking the sidecar's dependencies is not applicable when `torch` comes from the CUDA base image; an off-image lock would pull the CPU build and silently break GPU inference.

---

## Done — 2026-08-18

### SonarCloud — items 1 and 8, closed
- [x] **Automatic Analysis turned off** (manual step, done by the author).
- [x] **The CI scan actually ran** — first time ever. From run `32120949305`:
      `Parsing report '…/api/coverage.xml'` then
      `ANALYSIS SUCCESSFUL, … https://sonarcloud.io/dashboard?id=yassine808_PFE-aznet&branch=main`.
      Coverage is measured by the tool the report credits, not by a local run.
- [x] **The scan step is no longer `continue-on-error`** (`663febc`). It does not judge
      the code, so the only way it can fail is a configuration fault — missing or expired
      token, unreadable `coverage.xml`, Automatic Analysis switched back on. Each means
      the figures on sonarcloud.io are stale while CI shows green, which is precisely what
      happened between 15 and 18 August and went unnoticed.
- [x] **The quality gate is deliberately still not awaited.** Its default asks ~80 %
      coverage on *new* code, and §4.9.4 argues against exactly that threshold for an
      offline-by-construction suite. Enforcing in CI a rule the report argues against
      would be a contradiction between two files. Reconsider after 31 August.
### CI was red for three days, and nobody could see it
- [x] **Two unused imports failed Ruff** — `typing.Tuple` in `api/app/logs.py`, `pytest` in
      `api/tests/test_exchanges.py`. Trivial in themselves, but they failed the `API` job,
      and the `sonar` job `needs: api`, so GitHub marked SonarCloud **skipped**, not failed.
      A skipped job reads as "didn't need to run". This is why the scanner never executed.
- [x] **A real production bug in the workflow** — `scripts/check_workflow.py` was failing on
      `TG reply summary`, `WA reply summary` and `Record exchange`, and it was right. Every
      line break in those expressions is an escaped backslash-n, which is what must reach
      n8n; the **chantier clause added 2026-08-15** used a real newline, and inside a
      single-quoted JavaScript string a real newline ends the literal. The expression is a
      syntax error, on the **reply path** — the confirmation the technician gets, on both
      channels, plus the exchange archive.
### The STT contradiction — item 2, closed
- [x] **§4.3.5 retitled** « La référence d'exactitude et sa place dans la chaîne », and it now
      states the deployed chain (`gemini, local, groq`) with the three reasons for that order:
      latency is paid by the technician on every note, 4 GB of VRAM and a 280–394 s load
      cannot hang off one card for the whole service, and a local fallback is what makes
      quota exhaustion a non-event.
- [x] **All three abstracts** follow — FR, EN, and the Arabic OpenXML block, edited inside
      its `<w:t>` runs.
### Item 5 — the self-authored test cases, closed
- [x] **Paragraph added to §4.3.9**, mirroring what §4.3.2 does for transcription. It names
      the bias and then bounds it: the cases derive from real messages, the ground truth is
      checkable field by field by a third party, and the decisive criterion (`t08`, invent
      nothing) is *negative*, so it cannot be gamed by the designer's phrasing preferences.
### Item 4 — the Dependabot claim, corrected against the API
- [x] **§4.9.3 was wrong twice.** Not thirty-five: **38 opened**, and **none merged** — 29
      closed without merge, superseded by the next day's grouped request, 9 still open
      (`gh pr list --state all --author "app/dependabot"`). The claim that each one passes
      the checks before being merged became "must pass **before it can be** merged", and the
      section now says what the mechanism is worth at this stage: it makes version drift
      visible, it has not yet closed it.
### Item 6 — the presentation, closed
- [x] **Stale figures replaced**: `220 commits` → `6 mois`, `272` → `288` tests, `17` → `18`
      checks (three places), `35` → `38` Dependabot, "semaine 0" → "phase 3", "sprint 2" →
      "phase 4".
- [x] **s15 retitled** and its "Ce qui est payé" panel now explains the chain position instead
      of implying the local model is the primary engine.
- [x] **Three slides added** — `s05b_planning` (the 7-phase timeline), `s15b_extraction` (the
      text→table benchmark, with the `llama-3.1-8b-instant` five-invented-values panel), and
      `s18b_sonar` (the SonarCloud result). Deck rebuilt: **32 slides**.
### Found in passing
- [x] **§4.7 did not exist** — the chapter ran 4.6 → 4.8, while §3.6 promised the dashboard
      captures « rassemblées au §4.7 ». The dashboard section moved from §4.10 to §4.7, where
      the cross-reference always intended it, and the chapter conclusion became §4.10.
- [x] **§4.2's toolchain table** still said 17 checks; it is 18 everywhere else.
## Done — 2026-08-19 : screenshots refreshed, figures re-derived, two new screens

### Screenshots — the whole set re-shot

`Dashboard/scripts/report-shots.mjs` re-run against the live stack (twelve hours
of uptime, so the service bars and the year graph are populated rather than
near-empty). Same convention as before, deliberately: **dark theme, English,
16:9**, one viewport per shot. Three routes were added to the script —
`usage`, `chantiers`, and a scripted expansion of one site's bordereau, which
lives behind a collapsed row and would otherwise never appear. **29 captures** (was 22), all regenerated, none reused.

The light theme went from one capture to four — overview, rapports, consommation,
chantiers. One shot proves the palette inverts; it does not prove that every
*kind* of panel (table, chart, progress bar, quota gauge) was designed in both,
and a quota bar built for a dark ground usually vanishes on a white one.

The PNG→JPG step (downscale to 1800 px, quality 88) was undocumented and lived
in somebody's shell history; it is now written into the script's header comment.

### Figures re-derived from the running system, not from memory

Every count in the report had drifted, some badly. Measured, then corrected
everywhere they appear — abstracts (FR/EN/AR), Tables 4.10, 4.12, 4.13, §3.3.4,
§3.4.1, §3.5, §3.6, §4.9, the annexes and the deck:

| | Report said | Actually |
|---|---|---|
| Tests | 288 in 22 files, 4 095 lines | **429 in 33 files, 6 381 lines** |
| Python (service) | 8 489 lines | **13 082** |
| TypeScript (dashboard) | 11 590 lines | **14 516** |
| API routes | 66 | **77** |
| n8n nodes | 65 | **64**, of which 54 carry logic |
| PostgreSQL tables | 11 | **24** |
| Repository total | 33 274 lines | **43 618** |
| Suite duration | 8 min 16 s | **5 min 55 s** (429 tests, measured) |
| Versioned prompts | 6 | **5** |

### Three things the report described that no longer exist

- **The chat commands.** `/rapport`, `/modifier`, `/supprimer` were listed as
  « En production » in Table 4.9 and described node by node in §3.5.3. They were
  removed on 2026-08-15. The table row now says « Retirées », §3.5.1 says why in
  two sentences, and the band counts were recomputed — band 7 was claimed at
  17 nodes and is 8.
- **`image-generation.md`.** Annex C.6 reproduced a prompt whose endpoint was
  deleted. Annex removed, the prompt count corrected to five.
- **The conclusion's perspectives** offered « avancement par site, consommation
  de matériel, alertes de stock » as future work. All three shipped. Reworded to
  what is genuinely still missing: order forecasting.

### Two screens the report and the deck had never mentioned

- **§4.8.1 — the Consommation page.** Table 4.11 is a *reasoning* about free-tier
  headroom; the page is the *measurement*, and the section now says why the two
  are not the same thing. It documents the honest part: Groq publishes real quota
  in its response headers (« measured »), Gemini publishes none so its ceiling is
  a documented constant, WhatsApp exposes its own tier but not our consumption —
  and a missing header is recorded `NULL`, never `0`.
- **Annexe H, Figures H.12–H.15** — Consommation, Chantiers (top and bottom) and
  one site's bordereau expanded. The following figures were renumbered.
- **Deck: `s17b_usage`**, both screens side by side with the three claims that
  matter. Two captures added to the demo-failure backups: Consommation, and the
  overview in light theme. Deck now builds at **35 slides**; report at
  **149 pages** (was 142).

### Found in passing

- `usage.intro` in `fr.json` read « Chaque paliers gratuit » — fixed, `web`
  rebuilt (a locale edit does not reach the served bundle without it).
- `pfe-api` restarted twice during the shoot, exit code 0, not OOM-killed; one
  screenshot caught nginx's 502 and had to be retaken. `/alerts` (5 s) and
  `/chantiers/{id}/bordereau` (0.9 s) were both exercised directly afterwards and
  are fine, so this is not a code fault — but it is unexplained.
- **The bordereau's « installed » column is empty on all three sites.** The
  figure is computed live from the journal, so this is not a display bug: no
  journal quantity has yet landed on a contract line. Worth a sentence to the
  jury before they ask.

---

## Done — 2026-08-19 (second pass) : the schema had outgrown the document

Asked whether the auto-generated article columns had been carried into the
report and the deck. They had not — the feature appeared in exactly one figure
caption and nowhere else. Neither did three other things.

### The column that creates itself — §3.4.7, new subsection

`articles_libres` and `article_registry` are now documented where the journal is
designed. The story worth telling is the failure it fixed: a report naming forty
pieces across eight article types filed a row with **none** of them — extracted
correctly, then dropped, **with no error raised anywhere**. The section carries
the three decisions that keep the mechanism safe rather than chaotic: a
normalised slug as identity (so a plural does not create a second column), a
registry global while the column is local (so two sites share a spelling), and
confirmation strictly **after** the fact (a report never waits for approval).
Column creation failing is a warning, `article_column_failed`, not a lost row.

### Two tables the report had never named — §3.3.4

- **`article_registry`**, source of the "Matériel à confirmer" panel.
- **`report_rows`**, and with it the reason it exists: the Rapports tab was
  doing two jobs at once — the flat feed a human reads, and the only place a
  machine could add a quantity up. Sixty-five columns wide, and every figure
  cost a Google read on a free quota. The report is stored there as **JSON, not
  35 typed columns**, because the schema gains article fields regularly (25 in
  one day) and a table needing a migration each time silently lags the schema.

Detailed table count went from thirteen to fifteen.

### Table 3.1 and Annexe B.1 were 37 fields out of date

`ExtractedReport` has **54 fields**; Table 3.1 listed 17 and Annexe B.1 was a
stale JSON Schema dump missing every field added since 5 August — the 25
bordereau articles, `nature`, `livraisons`, `articles_libres`, `besoins`,
`chantier_mentionne`, `date_declaree`, the hours and the stoppage fields.

Both are now **generated from the model itself**. Table 3.1 keeps a curated view
by family with a pointer to the annex; B.1 became a complete field table rather
than raw JSON — the full dump would have run to roughly fifteen pages — and says
the machine-readable form is served live on `/openapi.json`. A closing paragraph
distinguishes the three non-quantity fields: `nature` (absent means `pose`),
`livraisons` (**validated** against known field names, an unknown key raises),
and `articles_libres` (**deliberately not validated** — its subject is the
unknown article).

### The deck was still teaching a rule that was withdrawn

`s11_journal` showed two messages merging into one line and argued that a second
line would double the man-days — the merge rule was removed on 18 August for
destroying information. Its title had been updated and its content had not, so
the slide contradicted itself and the report. Rewritten: two lines, the second
marked `+80`, totals summed from the tab, JH read as a maximum and never a sum.

New slide **`s11b_colonnes`** for the auto-created column, with the silent-loss
framing and the three safeguards. Scope slide gains the feature.

Deck **36 slides**, report **151 pages**.

---

## To do — handoff, 2026-08-18

### 7. Spacing — code blocks and the ملخص  ✅ done 2026-08-17
- [x] **`SourceCode` patched** in `build/reference.docx`: `spacing before=0 after=0
      line=240 lineRule=auto`, `contextualSpacing`, `jc=left`. The surrounding `BodyText`
      still carries `after=180`, so the block keeps its gap from the prose.
- [x] **ملخص justification fixed** — the four raw-OpenXML Arabic paragraphs in
      `Rapport-PFE.md` (lines 97–100) were `jc="both"`. Word justifies RTL text by
      stretching inter-word spaces (no kashida), which opened wide white rivers across
      every line. Now `jc="right"`, the normal Arabic convention. Vertical spacing was
      left alone: at `after=160 line=276` the block was already tighter than the French
      abstract's `BodyText`.
- [x] **Rebuilt: 146 → 140 pages.**
### Deck — design, morph, speaker notes  ✅ done 2026-08-18
- [x] **Morph on all 32 slides.** `python-pptx` has no transition API, so
      `morph()` writes the XML itself, wrapped in `mc:AlternateContent`:
      PowerPoint 2016+ reads the `mc:Choice` and morphs, anything older reads
      the `mc:Fallback` and fades. A deck that silently does nothing on the
      examiner's machine would be worse than one that fades. Verified in the
      built file: 32/32 carry the transition, and the element order is
      `cSld → clrMapOvr → transition`, which is what PowerPoint itself writes —
      wrong order there is what triggers the "repair" prompt.
- [x] **Speaker notes on 26 slides** (every content slide; the six backup
      captures have none). Presenter View only, never projected. Each opens
      with its target duration so the 20 minutes can be paced, and carries the
      point that is *not* on the slide — e.g. on §4.3.5, say the local model is
      the **fallback** before a jury finds `stt_chain` in the config; on the
      demo slide, the recovery order if the network drops.
- [x] **A progress hairline** above the footer, filling left to right across
      the 24 numbered slides. Grey enough for the audience to ignore, which is
      the point: it tells the speaker where they are without anyone counting.
- [x] **Identité visuelle zellige**, drawn in code rather than photographed.
      The reference image supplied was a *watermarked* CrystalGraphics sample,
      so it could not be embedded — and generated geometry turned out to be the
      better answer anyway: nothing to license, crisp at any projector
      resolution, and **morph interpolates shapes**, so the rosette travels and
      turns between slides where a bitmap could only cross-fade.
      - **Motif**: the khatam, the eight-pointed star that signs Moroccan
        tilework, built from `STAR_8_POINT` + `DIAMOND` autoshapes.
      - **Coverage**: a zellige rail down the left of all 32 slides (left of
        `MARGIN`, so no content moved), a full tile band on the cover and the
        closing slide, and one rosette named `zHero` that travels the whole
        deck — small beside the header while a table is being read, large and
        rotated on the cover, the quote, the demo and the closing slide.
      - **Palette**: an ornament-only range anchored on the AZNET blue already
        sampled from the logo (turquoise, terracotta, saffron, sand). Headings,
        data and the accent rule keep EMSI green / AZNET blue: decoration is
        decorative, colour that carries meaning stays meaningful.
      - **Font unchanged** — `Arial` is pinned in the code as one of the two
        EMSI sanctions, so no display face was introduced.
- [x] **Performance, which nearly went wrong.** The first build was **2842
      shapes**, up to 180 on one slide: the rail was 63 shapes redrawn per
      slide, each copy carrying a different auto-generated name, so morph
      treated them as new objects and cross-faded all of them on every
      transition. A transition that stutters on the amphitheatre projector is
      worse than no ornament. Rail tiles now carry stable names (`zRail-0`…),
      which morph reads as *unchanged* and animates for free; the band is two
      shapes per tile instead of three. **1126 shapes, max 69 per slide.**
- [x] **Z-order.** The ornament is drawn after each slide is built, so it
      landed on top of the content — the cover band was covering both logos.
      Every ornament shape is now pushed behind the content, in reverse so the
      tiles keep their own order.
- [x] **Simplified to one blue and one motif** (2026-08-18, second pass). The
      first zellige attempt was too much: four ornament colours, a sand ground,
      a tiled band and a rail down every slide. Anthropic's upstream `pptx`
      skill — fetched from `anthropics/skills` — names most of that as the
      signature of a machine-generated deck, verbatim: *"NEVER add decorative
      colour bars or accent stripes … including vertical sidebar stripes down
      one edge of the slide"*, *"NEVER use accent lines under titles"*, *"don't
      default to cream/beige backgrounds"*. All three were in the deck, and two
      of the three predate the zellige work.
      - **Removed**: the rail, the tile band, the sand ground, the three extra
        ornament colours, the green/blue edge bars on the cover and the closing
        slide, the accent rule under every title, and the progress stripe
        (replaced by `7 / 24` beside the page number — the same information
        without a bar across the slide).
      - **Kept, and made the whole identity**: the khatam, drawn as an
        **outline** in the single AZNET blue. Large and translucent on the
        slides that breathe, small and solid beside the kicker everywhere else.
        One named shape (`zHero`) travels the deck, so morph moves it.
      - **Titles now separate by size and space** — 29 pt against 11.5 pt — not
        by a coloured line under them.
      - **477 shapes**, down from 2842 in the first attempt.
- [x] **Notes rewritten as TL;DR**: a timing, then one or two arrows. Short
      enough to read in a glance while still talking, which a paragraph is not.
- [x] **QA**: 153 XML parts, all well-formed; zip integrity OK; morph on 32/32;
      travelling star on 32/32; notes on 26.

## Done — 2026-08-18, seconde session

### Le journal : une ligne par message
- [x] **Accumulation supprimée.** Un second message n'écrase plus le premier.
      Vérifié dans le conteneur : `grep -c merge_rows /app/app/journal.py` → **0**.
- [x] **Un complément s'affiche `+50`.** Onglet `charé3 Moulay Slimane` :
      `row2 fibre=30`, `row3 fibre=+50`. C'est un **format de nombre**, pas un
      texte : la cellule contient toujours 50, donc la ligne de totaux et le
      bordereau sont intacts. Les colonnes de stock en sont exclues — un stock
      est un niveau, « +2 095 m restants » serait faux.
- [x] **Heures dictées.** `row2 entree=10:00 sortie=17:00`, extraites de
      « dakhalt m3a 10:00, kharajt m3a 5:00 dial l'achiya » — la conversion en
      24 h est faite par le modèle.
- [x] **JH calculé.** `row2 JH=0.88` (7 h ÷ 8, seul). `row3 JH=–` : aucune heure
      dictée, donc aucune valeur inventée. Le chef ne saisit plus que cinq
      colonnes : les quatre ORDRE DU JOUR et le taux de réalisation.
- [x] **Rapport et présentation réécrits.** « Accumulation » est devenu « Ajout,
      jamais réécriture » (`grep -c` → 1 dans `Rapport-PFE.md`), 14 passages au
      total, 7 dans chaque document.
### Les défauts du Sheet signalés le 18 août
- [x] **Le `null` en fin de transcription.** Cause : n8n rend une expression
      absente comme la **chaîne** `"null"` dans un champ multipart, et
      `if caption:` est vrai pour quatre caractères de texte. Corrigé des deux
      côtés — le workflow envoie `caption || ''`, et `/process` neutralise les
      nulls écrits en toutes lettres **à la frontière de confiance**, parce que
      le prochain client n'est pas encore écrit. **21 cellules déjà écrites ont
      été nettoyées** (essai à blanc d'abord, écriture en `RAW` pour qu'aucune
      transcription ne devienne une formule). Vérifié : `null_tail=False`.
- [x] **La date et l'heure illisibles.** Elles affichaient `+46252` et `+1`.
      **C'était ma régression** du marquage `+50` : les index de colonnes
      étaient calculés depuis `RAPPORTS_COLUMNS` alors que l'onglet Rapports a
      son propre ordre, et le format a atterri sur les colonnes 0 et 1.
      `mark_increment` prend désormais des **noms** de colonnes et les résout
      contre l'en-tête de l'onglet lui-même. Vérifié : `date='18/08/2026'`,
      `heure='15:46'`.
- [x] **Le drapeau de relecture est une case à cocher rouge.** C'était le mot
      `TRUE` au milieu d'une colonne de prose — quelque chose qu'il fallait
      remarquer plutôt que voir, sur la seule colonne qui existe pour être vue.
      Règle **conditionnelle**, pas un fond rouge permanent : une couleur
      toujours allumée ne dit rien quand elle compte. Vérifié : **1 règle par
      onglet, sur les 6**, et le style appliqué deux fois de suite en laisse
      toujours une seule.
- [x] **Texte agrandi** à 11 pt (défaut de Sheets : 10). Vérifié sur les 6 onglets.
- [x] **`Lien audio` n'écrit plus un identifiant nu.** `file_report` écrivait la
      valeur brute de n8n pendant que le miroir passait par `audio_link()` ;
      une colonne « Lien audio » contenait donc `1321591036458594`, qui n'ouvre
      rien. Les deux passent maintenant par le même garde-fou. 4 cellules
      nettoyées, **1 délibérément laissée** — `DGH` ligne 4 contient de la prose
      *et* neuf identifiants collés par l'ancienne fusion : l'effacer
      supprimerait un texte irrécupérable. À traiter à la main.
### Deux bugs d'empilement trouvés en chemin
- [x] `addBanding` **ajoute** au lieu de remplacer, et un `batchUpdate` est
      atomique : sur un onglet déjà bandé, ce seul 400 emportait la taille de
      police, la case à cocher et toutes les largeurs de colonnes. Le bandage
      part désormais dans son propre lot, en dernier.
- [x] `addConditionalFormatRule` **ajoute** aussi : styler un onglet quatre fois
      y laissait quatre règles identiques. Les règles existantes sont supprimées
      d'abord, index décroissant pour que les positions ne glissent pas.
### Le tableau de bord
- [x] **La page Chantiers ne disait plus rien.** La donnée n'a jamais manqué :
      `stock.assess()` retourne zéro constat parce qu'aucun site n'approche un
      seuil, et un état vide muet se lit comme une page cassée. La bande dit
      maintenant combien de sites elle surveille, chaque site porte **Confirmé**
      ou **Non vérifié**, et la liste distingue « aucun site » de « en cours de
      chargement » et de « la requête a échoué ».
- [x] **Toute suppression passe par une fenêtre.** Fond flouté, question qui
      **nomme sa cible** — « Supprimer NAROUZE ? » et non « Supprimer cet
      élément ? », parce que seule la première est vérifiable contre ce que
      l'opérateur croyait cliquer. Échap annule, un clic à côté annule, la page
      derrière cesse de défiler, et le **focus s'ouvre sur Annuler** : une
      fenêtre qui s'ouvre sur le bouton destructeur transforme une frappe
      d'Entrée égarée en la chose même qu'elle doit empêcher. Bouton rouge
      `status-fail`, couleur dépensée nulle part ailleurs comme action.
      Vérifié dans le bundle servi : `confirm.question`, `confirm.irreversible`,
      `chantiers.allNone`, `chantiers.verified` — tous présents.
      **Deux exceptions assumées** : les retraits d'adresse e-mail dans
      `automation.tsx` et `settings-overlay.tsx` modifient un formulaire non
      enregistré, qu'Annuler défait déjà.
### La présentation
- [x] **Un seul bleu, un seul motif.** Le skill `pptx` d'Anthropic — récupéré
      depuis `anthropics/skills` — nomme littéralement ce que la première
      version faisait : *« NEVER add decorative colour bars or accent stripes …
      including vertical sidebar stripes down one edge of the slide »*,
      *« NEVER use accent lines under titles »*, *« don't default to cream/beige
      backgrounds »*. Les trois y étaient, dont deux **antérieures** au zellige.
      Reste le khatam en **trait**, dans le bleu AZNET, et rien d'autre.
- [x] **Morph sur les 32 diapositives**, une rosace nommée qui traverse tout le
      parcours. **477 formes** contre 2 842 au premier jet : morph interpole
      chaque forme, et une transition qui saccade devant un jury est pire que
      pas d'ornement.
- [x] **Notes TL;DR** sur 26 diapositives : une durée, puis une ou deux flèches.
      Vérifié : `slides=32 morph=32 notes=26 hero=32`.
- [x] **AZNET est à Rabat**, sur la couverture du rapport et du diaporama.
      Les cinq `Africa/Casablanca` de la configuration sont **intacts** : c'est
      l'identifiant de fuseau horaire de tout le Maroc, le renommer casserait
      l'ordonnanceur sans rien corriger.
### Reste à faire, connu
- [x] **Documenter les avertissements dans `rapport-PFE.docx`.** Fait le 2026-08-20 :
      §3.4.9 « Les avertissements : deux familles, deux destins » porte les deux
      recensements ci-dessous, le tableau des dix clés et les deux décisions à
      faire ressortir. Le diaporama en tire la diapositive « Deux familles
      d'avertissements, deux destins ».
      Recensé le 2026-08-20 : Le système en
      produit deux familles, elles ne vivent pas au même endroit, et le rapport
      n'en décrit aucune. Recensé le 2026-08-20 pour ne pas être re-dérivé plus
      tard :

      **Famille A — alertes matière** (`api/app/stock.py`, clé `niveau`).
      Recalculées à la demande depuis le journal, le registre `receptions` et le
      bordereau ; **stockées nulle part**. Elles alimentent le corps du mail
      quotidien/hebdomadaire, le tableau du `.docx` et `GET /alerts` (page
      Chantiers). Quatre niveaux, classés dans cet ordre (`_ORDER`) :
      - `depassement` — posé > `qte_marche`. Ne dépend pas du stock connu : sur-
        consommation ou erreur de saisie, le directeur veut l'entendre dans les
        deux cas.
      - `critique` — ≤ 2 jours de couverture au rythme actuel, ou ≤ 5 % du
        marché quand aucun rythme n'est exploitable.
      - `bas` — ≤ 5 jours, ou ≤ 10 %.
      - `surplus` — « trop » : plus de 2× ce qu'il reste à poser, **et** un
        excédent supérieur à 10 % du marché. Testé **avant** les niveaux de
        pénurie : en fin de chantier un article peut être sous deux jours de
        couverture *et* en excès, et « commandez-en » serait alors la phrase
        exactement inverse. Sous `MIN_ACTIVE_DAYS` (2) il n'y a pas de rythme,
        donc repli sur le pourcentage ; sans `qte_marche`, silence.
        Seuils surchargeables dans `app_settings` (`stock_jours_critique`,
        `stock_jours_bas`, `stock_pct_critique`, `stock_pct_bas`,
        `stock_surplus_facteur`).

      **Famille B — avertissements de ligne** (`journal.WARNING_LABELS`).
      Celles-ci **ont** une colonne : `Motif du flag` sur l'onglet du chantier
      et `motif_flag` sur Rapports, plusieurs jointes par « · ». Elles viennent
      de deux processus qui convergent — `/process` les passe via n8n
      (`warnings: $('Process output').item.json.warnings ?? []`), `file_report`
      y ajoute les siennes. Dix clés, dont **cinq seulement** lèvent
      `Flag review` :
      - lèvent le drapeau : `image_input`, `photo_zones_partielles`,
        `low_confidence_transcription`, `short_transcription`,
        `chantier_cree_non_verifie`.
      - écrites sans lever le drapeau : `stock_ecart` (« Écart de stock »),
        `no_report_content`, `heure_non_dite`, `date_declaree_illisible`,
        `date_declaree_hors_plage`.

      **Les deux points à faire ressortir dans le rapport**, parce qu'ils sont
      des décisions et pas des détails : (1) la famille A n'a **aucune** colonne
      — un chiffre dérivé de trois sources périmerait dans une cellule, même
      raison que `qte_installee` recalculé à chaque appel ; (2) `stock_ecart`
      est le seul avertissement portant sur une **contradiction numérique** et
      il ne lève pas le drapeau : la ligne se justifie toute seule et personne
      n'est invité à la regarder. Signalé au propriétaire le 2026-08-20, laissé
      en l'état à sa demande — donc à présenter comme un choix, pas un oubli.
