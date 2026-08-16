# TO-DO

Open items only. Everything marked done moves to `FIXED.md` — that file is the done log, this one is the queue.

- [x] Finish STT benchmark → pick default provider — **done 2026-08-07/08**: 13 engines, 3 by API and 12 locally on the RTX 3070, over 11 real clips. `stt_chain = gemini,local,groq`, ordered by accuracy judged against the audio by a native speaker rather than by latency. WER/CER deliberately not computed (`references.csv` stays header-only) — the criterion is preservation of digits and French technical loanwords, because that is all the journal consumes. Results: `benchmark/STT-BENCHMARK-STATUS.md`. The dead `hf-darija` adapter was deleted in the same pass.
- [x] Daily stat: % spoken Darija words vs French (post-PFE, zero cahier value)

## Code audit 2026-08-04 → `docs/audit-2026-08-04.md`
Full-read audit of the backend + the dashboard's data spine. 11 findings, each with file, line, cause and fix; the status table in that file is the source of truth. **3 bugs fixed** (profile never reaching the primary text model; every API restart cancelling that day's report; the scheduler loop being killable). **8 open**: 4 hardening (login timing oracle, unbounded throttle dict, cache-by-reference, uncapped `limit` params), 3 perf (two Sheets calls per write, a DB write per authenticated request, polling a hidden tab), 1 maintainability (daily/weekly report duplication). Coverage gap: `app/logs.py`, the rest of `app/main.py`, and the Dashboard pages were not read.

## Code audit 2026-08-10 → `docs/audit-2026-08-10.md`
Coverage gap from the 04-08 audit closed: full read of `logs.py`, the rest of `main.py`, `imagegen.py`, `prompt_loader.py`, `schemas.py`, the `providers/` package, every Dashboard page, the `lib/` spine and all components. **0 bugs found** — verified `/process` contract, single-query list endpoints (no N+1), the provider registry, the `useApi` cache, and the lazy routes. Three planned perf optimizations (N+1 batching, `/service-samples` aggregation, bundle) measured and dismissed as non-problems. One stale doc line fixed (`api/README.md` listed the deleted `hf-darija` adapter).

## Open before production (found reviewing the `opencode` merge, 2026-08-04)
- [x] **Retention for the archive tables.** Done 2026-08-10 with the owner's policy: `media_files` 30 days, `chat_messages` 90 days, read `notifications` 30 days, `manager_reports` kept forever; env-tunable via `MEDIA_RETENTION_DAYS` / `CHAT_RETENTION_DAYS` / `NOTIF_RETENTION_DAYS`, swept by `logs.prune_meta` at 03:00 — see FIXED.md (Fourth pass)
- [ ] **`INTERNAL_API_KEY` must be set in the deployed n8n environment.** `/process` is auth-gated since this branch, and n8n has no browser, so it authenticates with `X-API-Key`. All 17 n8n HTTP nodes send the header; the key has to exist on *both* sides or every incoming message 401s. Unset on the API means machine access is disabled, never "everyone is a machine" — so the failure is a silent pipeline, not an open door.
- [x] **`SMTP_USER` / `SMTP_PASS` set in `.env`** (2026-08-12) — every mail path is live; remaining action is a real test send via `POST /notify/test`.
- [x] check email
- [] check Automated reports.
- [] check Automated weekly reports
- [] check images
- [x] better sign-in design (profesionnal) — 2026-08-10: rewritten with language switcher, accent glow, AZnet avatar, aria-busy submit — see FIXED.md (Fourth pass)
- [x] adds 404 page — exists and is captured in the report (Annexe H): an unknown address says so explicitly instead of redirecting silently to the home page, where the user would think their link had worked.
- [x] remove image card generating in reports pages (make it auto when generating reports) — 2026-08-10: the card now rides along with the report's "Générer" click on both Daily and Weekly — see FIXED.md (Fourth pass)
- [] Add charging animation in the website, if things are getting charged from the database
- [] Add more columns inspired from the given data
- [x] add techs vertically instead of horizentaly to reduce scroll (in TEAM panel)
  — fait 2026-08-16, **non vérifié dans un navigateur** (pas de Chrome sur cette
  machine ; typecheck + build verts). L'équipe d'un chef était sur trois cartes
  de large (`max-w-[34.5rem]`, retour à la ligne), donc chaque colonne de chef
  faisait trois fois sa largeur utile — et la rangée des chefs est en
  `flex-nowrap`, elle ne peut pas se replier : à quatre chefs le graphe défilait
  latéralement sur un portable. Une colonne fait 11rem, les quatre tiennent.
  On échange de la hauteur, la direction la moins chère : la page défile déjà
  verticalement. Les connecteurs sont dessinés par contenance (`.org-crew`), pas
  par des traits vers chaque enfant, donc rien à recalculer.
  À vérifier : `docker compose up -d --build web` puis la page Équipe avec
  plusieurs chefs et un chef à six techniciens.
## Batch 2026-08-16 (4) — la note vocale muette, et le lien audio qui pointe chez nous

- [x] **Le .docx doit partir avec le mail de chaque rapport automatique.**
  **Prouvé le 2026-08-16** : `jobs.run("daily_report")` exécuté dans le
  conteneur, mail reçu à `ysmagri@gmail.com` avec la pièce jointe ouverte par
  le propriétaire. `jobs._report_mail` joint le document à *chaque* rapport —
  le digest entreprise et celui de chaque chef — et le rendu vit dans l'API
  (`app/docx_report.py`) précisément pour que le courrier programmé, envoyé
  par un fil dans le conteneur sans navigateur, puisse attacher quelque chose.
  L'échec du rendu reste non fatal et imprimé : un document qui ne se construit
  pas ne doit pas coûter le rapport, qui reste lisible dans le corps du mail.
  **Le même passage a révélé deux vrais défauts, corrigés dans la foulée** :
  1. **Le miroir Rapports perdait huit champs.** `journal.RAPPORTS_COLUMNS`
     était une liste tenue à la main : `fibre_m`, `prises_testees`,
     `cables_prepares_m`, `interconnexions`, `connexions_optiques_brins`, les
     trois listes de localisation et les trois colonnes de stock n'atteignaient
     jamais l'onglet plat. Leurs colonnes existent dans la feuille et étaient
     **toutes vides**. La carte est maintenant dérivée de `schemas.DATA_FIELDS`,
     donc un champ ajouté au schéma arrive dans le miroir par construction.
  2. **Le .docx nommait quatre colonnes sur trente-cinq.** Les tuiles ne
     portent plus de quantité, et les trois tableaux (Quantités déclarées,
     Activité par technicien, Activité par chantier) sont construits depuis
     `journal.quantity_columns()`. Les mêmes totaux sont passés au modèle
     (`daily_report._payload`), donc le corps du mail et la pièce jointe ne
     peuvent plus annoncer deux chiffres différents pour la même journée.

- [~] **Alertes matériel — PR1 et PR2 faits, pas encore prouvés en vrai.** Décidé avec le propriétaire
  le 2026-08-16 (entretien `/grill-me`). Le but : que le rapport signale ce qui
  manque, ce qui va manquer, et ce qui a été livré en trop.
  **PR1 — livré et déployé, pas encore prouvé de bout en bout :** `nature` /
  `livraisons` au schéma, les deux prompts corrigés, la table `receptions`, la
  feuille `Livraisons`, `GET /receptions`, 9 tests. **Reste à prouver :**
  photographier un vrai bon de livraison et vérifier que les quantités
  atterrissent dans `receptions` et **pas** dans les colonnes posées.
  **PR2 — livré et déployé le 2026-08-16** (`app/stock.py`, page Chantiers) :
  - `resolve_stock(chantier, champ) -> (qte, source)` avec la précédence
    arrêtée : stock déclaré par le technicien > `Σ receptions − Σ posé` >
    `qte_marche − installé` > inconnu. **La source est toujours nommée** dans
    l'alerte, comme « (repris du dernier rapport) » l'est déjà dans le résumé ;
    un chiffre dont on ne peut pas dire d'où il vient ne se conteste pas.
  - `assess()` : jours de couverture = reste ÷ moyenne posée **par jour actif**
    (pas par jour calendaire, sinon le week-end dilue le rythme). CRITIQUE ≤ 2
    jours ou ≤ 5 % du marché, BAS ≤ 5 jours ou ≤ 10 %, seuils dans
    `app_settings`. Moins de 2 jours actifs d'historique : on retombe sur le
    pourcentage. Dépassement (> 100 %) toujours signalé.
  - Python décide les chiffres, le modèle les rédige — et peut ajouter des
    risques **non chiffrés** lus dans `besoins` / `remarques` / les photos, à
    condition de citer sa source. Jamais un nombre qu'il a calculé lui-même.
  - Diffusion : section `## Alertes matériel` dans le mail, tableau dans le
    .docx, `GET /alerts` + panneau du tableau de bord (rebuild `web`).
  - Un chantier sans bordereau (`مولاي الحسن`) ne produit aucune alerte :
    silence, pas des zéros.
  **Reste à prouver pour les deux :** le système renvoie aujourd'hui `alerts: 0`,
  et c'est la bonne réponse — DGH est à 47 % du marché sur les prises avec un
  seul jour actif d'historique, ACAPS et Extralait n'ont aucune ligne de
  journal, et `مولاي الحسن` n'a pas de bordereau. Rien n'a donc encore franchi
  un seuil **en vrai**. À vérifier quand le chantier tournera : qu'une alerte
  apparaît bien dans le mail, dans le .docx et sur la page Chantiers, et que la
  provenance affichée correspond à la source réellement utilisée.

- [ ] **Une note vocale dont rien n'est extrait n'apparaît pas dans la feuille —
  c'est voulu, mais il faut le vérifier avant de le croire.** Quand l'extraction
  ne trouve aucune donnée (`schemas.has_data` faux), `/process` ajoute
  `no_report_content`, le nœud `Rapport exploitable ?` saute l'appel à
  `/journal`, et le message part dans `exchanges` — donc **dans l'inbox, pas
  dans la feuille**. C'est la règle qui empêche « salam » d'ouvrir une ligne de
  blancs, et elle ignore délibérément `resume` (le modèle en écrit toujours un)
  et `chantier_mentionne` (nommer un site n'est pas du travail fait).
  Ce qui reste à trancher, et qui demande la trace réelle : **est-ce bien ce
  chemin-là**, ou l'extraction échoue-t-elle vraiment ? Les deux se ressemblent
  de l'extérieur (rien dans la feuille) et n'ont pas le même remède. À faire
  côté propriétaire, la machine de dev ne joint pas n8n :
  `GET /api/v1/executions?limit=100` puis `?includeData=true` sur l'id du
  message — ~26 nœuds = message réellement traité ; regarder `warnings` dans la
  sortie de `/process`. Puis l'inbox : si le message y est avec sa transcription,
  c'est la porte `no_report_content` et non une panne. Si la transcription est
  correcte et pleine de chiffres alors que `has_data` dit non, **c'est
  l'extraction qui a échoué et c'est un bug** — garder la transcription.
- [x] **`lien_audio` doit pointer chez nous, pas sur Drive** — fait 2026-08-16,
  **non vérifié** (suite API verte, typecheck et build verts ; ni feuille ni
  navigateur ouverts ici). `journal.audio_link` écrit
  `{DASHBOARD_BASE_URL}/#/inbox?msg={correlation_id}` ; `correlation_id` est
  ajouté aux colonnes du miroir Rapports ; l'inbox lit `?msg=`, sélectionne le
  technicien et le jour de ce message, y défile et l'entoure une fois (l'anneau
  s'efface : un surlignage permanent se lirait comme un état que le message
  n'a pas). Un id qui ne correspond à rien ne déplace rien — le message a pu
  être purgé, et sauter ailleurs en silence serait pire.
  **Action propriétaire : ajouter `DASHBOARD_BASE_URL=https://<hôte public>` au
  `.env`, puis `docker compose up -d api`** (une modification de `.env`
  n'atteint pas un conteneur réutilisé — piège n°4). Tant qu'elle est absente,
  la colonne garde le lien Drive : rien ne casse, la nouveauté n'apparaît
  simplement pas.
  Détail 2026-08-16 : Aujourd'hui la colonne contient l'URL Drive : elle ouvre un
  fichier nu, hors contexte, et dépend d'un service tiers pour lire quelque
  chose qu'on héberge déjà (`media_files` en Postgres). Le lien devient une
  **adresse du dashboard vers ce message précis** dans l'inbox, où il y a le
  lecteur, la transcription corrigeable, le résumé et la réponse envoyée.
  Clé retenue : **`correlation_id`**, pas le numéro de ligne — il existe *avant*
  l'append (donc pas de second appel Sheets pour réécrire la cellule), il est
  déjà porté par le message de bout en bout, et il vaut aussi pour un échange
  qui n'est jamais devenu une ligne. Il faut donc l'ajouter aux colonnes du
  miroir Rapports.
  Base d'URL par `DASHBOARD_BASE_URL` ; **non définie, on retombe sur le lien
  Drive** plutôt que d'écrire une adresse relative que personne ne peut ouvrir
  depuis la feuille. L'upload Drive reste : c'est la copie durable au-delà de
  `MEDIA_RETENTION_DAYS` (30 jours), et `media_files.drive_file_id` reste le
  chemin de repli de la lecture.

## Batch 2026-08-15 (grilled and locked with the owner before starting)
- [x] **1. WhatsApp voice notes come back untagged — CLOSED, not fixable and never was a bug of ours (2026-08-15).** — fixed 2026-08-15: Text replies carry the grey quote, audio ones do not. Cause: the reply/ack nodes dereference `$('Filtrer accès').item`, and the paired-item chain breaks across the media branch (`WA Get media URL` → `WA Download audio`). Fix: carry `chat_id` + `message_id` in each item's own JSON through the media branch and read `$json` in the reply nodes — hardens the text and image paths too.
- [x] **2. Remove the chat commands** — done 2026-08-15; `rapports_row` stayed, because `GET /audio/row/{row}` plays the inbox's voice notes through it. `/rapport`, `/modify`, `/delete` everywhere: the n8n command nodes and their six reply nodes, `POST /modify-command`, and the now write-only message→row link (`processed_messages.sheet_row` / `sheet_tab` / `rapports_row` plus every `logs.link_message_row` call). `processed_messages` itself stays — WhatsApp idempotency lives there.
- [x] **3. Moroccan phone numbers: store `2126…`, always show `06…`/`07…`.** One `toMsisdn()` normalizer on the way in (Team form *and* the API, so `find_technician` cannot miss) and one `formatPhone()` on the way out, used by every place a WhatsApp id renders. — done 2026-08-15: the API already canonicalized (`logs.normalize_external_id`), so this was the display half — `toMsisdn`/`formatPhone` in `lib/utils.ts` with a runnable `utils.selfcheck.ts`, wired into the Team form, the identity chips and the inbox address.
- [x] **4. New settings panel, bottom-left, tabbed full-screen overlay** — Appearance, Pipeline, Automation, Notifications, Account. Mirrors the server settings as well as the local ones, gated by role (the confidence threshold and `/settings` writes stay director-only). — done 2026-08-15 in `components/settings-overlay.tsx`; the gear is now only the trigger. Not verified in a browser — no Chrome on this machine — build, typecheck and locale parity are green.
- [x] **5. Inbox shows new messages by itself, with a ⏳ per sender while their message is being processed.** In-flight is derived from `pipeline_logs` (a `received` row with no matching `replied`/`failed`), so no new table. Polling is adaptive: 5 s while anything is in flight, 30 s otherwise. — done 2026-08-15 (`GET /in-flight` + `HourglassMediumIcon` in the rail)
- [x] **6. Split the notification area: messages vs alerts.** Two tabs in the bell panel; the unread badge counts alerts only. A received message toasts as “Message reçu de {name}” and nothing else, clicking it opens the inbox on that technician. — done 2026-08-15
- [x] **7. WhatsApp-like inbox chat surface** — bubbles with tails, sender right / technician left, date pills, delivery ticks, textured thread background, all in the dashboard's own palette (no WhatsApp green). — done 2026-08-15: tails and the dot-grid ground are CSS (`.bubble`/`.thread-canvas` in `index.css`), the ticks say “sent” and never claim a read receipt the channel never gives us.
- [x] **8. Choose where a reply is sent.** — done 2026-08-15 The composer defaults to the channel and identity the last message arrived on and shows it as a chip; clicking it lists every identity of that person. `POST /reply` gains an optional `identity_id` — omitted, it still broadcasts, so nothing existing breaks.
- [x] **9. Space the n8n nodes on a grid** — done 2026-08-15: layered left-to-right by longest-path depth, 320 px between columns and 150 px of vertical pitch, branches kept next to the node they fork from. 56 nodes, 26 columns, widest column 6.
- [ ] **10. `WHATSAPP_ACCESS_TOKEN` is missing from `.env`.** The dashboard's WhatsApp reply answers "Réponse WhatsApp non configurée" because `reply.py` reads that variable and the API container has it unset — the token currently exists only inside n8n's WhatsApp *credential*, which the API cannot read. Add the System User token to `.env` (the API already loads it via `env_file`) and `docker compose up -d api`.
- [x] **11. Reply quote restored** (2026-08-15). The #1 "fix" caused it. Routing the reply's `chat_id`/`message_id` through `Process output` instead of `$('Filtrer accès')` produced a byte-identical payload in every execution I inspected — and still killed the quoted bubble, so `.item` resolves to something different at send time than the stored run data shows. Known good beats a theory: every message field is back on `$('Filtrer accès')`, and the reply nodes are now byte-identical to commit 047ab64, where it worked. Kept: `/process` still echoes `correlation_id`/`message_id` (free, and a real join key if one is ever needed). **Do not re-route the message fields through `Process output`.**

## WhatsApp quoting of voice notes — settled 2026-08-15, do not re-investigate
`context.message_id` pointing at a **voice note** is accepted by the Cloud API
(HTTP 200, a message id comes back) and then **not rendered as a quote** by
WhatsApp. Proven outside n8n: two messages sent straight to
`graph.facebook.com`, same code path, same recipient, one quoting an audio
`wamid` and one quoting a text `wamid` — only the text one showed the grey
quoted bubble.

So the workflow was never wrong. Three attempts were spent moving the
reference (`$('Filtrer accès').item` → `$('Process output').item` → `$json`)
on the theory that `pairedItem` did not survive the media branch; all three
sent the correct raw id, and none of them could have worked. The expressions
are back on `$('Filtrer accès')`, byte-identical to 047ab64.

What marks the message instead: the bot already reacts ⏳ on arrival and ✅ on
success, and a reaction *does* attach to the voice note itself. That is the
tag, and it is the owner's decision (2026-08-15) to leave it at that.

Kept from the investigation: `/process` echoes `correlation_id` and
`message_id` back in `ProcessResponse` (free, and a real join key if one is
ever needed).
- [] new panel for usage that shows usage for gemini, groq, facebook whatsapp
- [x] **Retirer « 🤖 Moteur STT » de la réponse au technicien** — fait
  2026-08-16 **et poussé en direct** (`--push`, workflow toujours actif,
  0 occurrence de « Moteur STT » dans la copie vivante). Le premier essai avait
  échoué en `getaddrinfo` : `N8N_URL` du `.env` est le nom Tailscale, que cette
  machine ne résout pas — `N8N_URL=http://127.0.0.1:5678` devant la commande
  suffit, le conteneur écoute bien. Trois nœuds nettoyés : `TG reply summary`, `WA reply summary`, et
  `Record exchange` — ce dernier archive le texte de la réponse et doit rester
  identique à ce qui est parti, sinon l'inbox montre une conversation qui n'a
  pas eu lieu. Le nom du moteur reste dans `/journal` (`stt_engine`), dans les
  logs et dans le dashboard : c'est une information d'exploitation, pas une
  information de chantier. La confiance de transcription, elle, reste dans la
  réponse — elle dit au technicien de relire, ce que le nom du moteur ne fait
  pas.
- [x] **Le moteur STT s'affiche dans l'inbox** — fait 2026-08-16, **non vérifié
  dans un navigateur** (typecheck, build, parité des locales et suite API
  verts). Une puce à côté du titre « Transcription », donc collée au texte
  qu'elle qualifie : la chaîne se replie en cas d'échec, donc l'ordre configuré
  ne dit pas ce qui a tourné — `local` ici signifie que les deux moteurs cloud
  étaient indisponibles à cet instant, et un chiffre douteux ne se juge pas
  pareil selon le moteur qui l'a entendu. Deux sources, parce qu'un message
  peut ne jamais devenir une ligne : `STT_model` de la feuille Rapports pour un
  rapport déposé, et une **nouvelle colonne `exchanges.stt_engine`** pour les
  messages « aucun rapport détecté » — ce sont justement ceux qu'on relit.
  Migration `ADD COLUMN IF NOT EXISTS`, donc les échanges antérieurs restent
  sans puce plutôt que de mentir. Le nœud n8n `Record exchange` envoie le champ,
  et il est **poussé** : `stt_engine` est présent dans le nœud vivant. `api` et
  `web` ont été reconstruits et redémarrés le 2026-08-16. Reste à voir la puce
  sur une **nouvelle** note vocale — les échanges antérieurs à la colonne
  n'affichent rien, ce qui est le comportement voulu.
## Batch 2026-08-15 (2) — bordereau columns, vision benchmark, .docx (grilled and locked with the owner)

Decisions locked in the grill, so nobody re-opens them later:
**chantier comes from the voice**, not the org chart — unstated falls back to the
site on that technician's most recent row, with no expiry, and the reply says so
out loud ("chantier : ACAPS (repris du dernier rapport)") so a wrongly inherited
site is visible immediately. The Sheet row stays **one wide line per report**
(the owner's call, twice) rather than long-format movement rows. Synonyms are
collapsed across the three bordereaux — one field per physical thing, not one
per contract line. Benchmarks run **before** the build, and the vision criterion
is **localization accuracy**, fixed before the run as the STT criterion was.

- [x] **1. Bordereau article columns — schema, journal, mirror, seeds.** 25 new
  `ARTICLE_FIELDS` in `schemas.py`, all counted by `has_data`; `ARTICLE_COLUMNS`
  folded into `journal.NUMERIC_COLUMNS` so they merge-by-addition for free;
  identity entries in `RAPPORTS_COLUMNS`; `articles.tache` added for ACAPS's
  grouping; Extralait (13) and ACAPS (17) bordereaux seeded and DGH's 13
  previously unmapped articles wired to the new fields. Prompts updated on both
  the text and image paths. 26 tests in `api/tests/test_bordereau_articles.py`;
  full suite 299 green. The Rapports tab is live at **61 columns** — appended in
  place, nothing renamed, nothing deleted.
  Two traps found on the way, recorded so they are not re-introduced:
  the article seed sat behind `if chantiers is empty`, so on any box that had
  already booted (i.e. the live one) Extralait and ACAPS would silently never
  arrive — the guard is now per chantier *and* per emptiness. And four Rapports
  columns keep **legacy names** (`goulottes_m`, `cables_m`, `bureaux_termines`,
  `panneaux_raccordes`): `RAPPORTS_COLUMNS` is where the two vocabularies meet,
  and renaming a column orphans every historical row in it.
- [x] **2. Vision benchmark on annotated plans** (`benchmark/run_plan_benchmark.py`,
  `dataset/plan_cases.json`). One floor plan photographed in three annotation
  states — circle only, dots only, fully marked — which makes the printed layout
  a constant and the marks the only variable, so a claim about an unmarked zone
  is *provably* false rather than merely unverified. Scored on recall of marked
  zones and on hallucinated zones; mark counting is deliberately **not** graded
  (counting dots on a phone photo is where vision models fail, and a wrong count
  becomes a wrong contract total nobody catches).
  Result — `gemini-3.5-flash-lite` and `gemini-flash-lite-latest`: **92% recall,
  0 hallucinations, 1.3 s**. `gemini-3.1-flash-lite` reaches 100% recall with
  **4 hallucinations** — it wins on recall by naming rooms that are not marked,
  which is exactly why recall alone must not pick the model. Groq's Llama 4
  Scout and Maverick **404 on this key**, so CLAUDE.md's "no vision model in the
  free Groq catalogue" still holds.
  Caveat kept deliberately: `gemini-3.6-flash` scored 0 hallucinations in a
  warm-up and 1 in the full run on identical input — three cases is a noisy
  sample and these numbers are directional, not precise.
- [x] **3. Image-generation reachability survey** (`benchmark/run_imagegen_survey.py`).
  **0 of 8 endpoints returned pixels.** Gemini's three image models answer
  `429 RESOURCE_EXHAUSTED`, Pollinations now `403`s anonymous callers, and the
  HF and Cloudflare paths have no credentials in `.env`. So the deterministic
  Pillow card is not a fallback in practice — it is the only image path that
  exists, exactly as `config.py` already claimed. The Gemini rows were probed
  right after 18 vision calls on the same key, so that verdict deserves one
  re-run on a cold quota before it is quoted in the report.
- [x] **4. Chantier from the voice + sticky fallback** — done 2026-08-15
  (`0d8eceb`). `chantier_mentionne` on the schema, `journal.resolve_site`
  replacing the hazard below, `_sticky_chantier` derived from the Rapports
  mirror, `chantiers.verifie`, and the `(repris du dernier rapport)` note on the
  summary. Precedence shipped as voice → sticky → org chart → `Non affecté`.
  16 tests in `test_chantier_routing.py`; suite 343 green at the time.

  **`journal.resolve_tab` is the hazard and must be fixed in the same pass.**
  Its first branch is `if chantier: return chantier, chantier, []` — a passed-in
  chantier is trusted verbatim *as a tab name*, with no check that it exists in
  the `chantiers` table. Nothing reaches that branch today because routing comes
  from the org chart, but the moment the voice supplies the name, whatever the
  model transcribes becomes a tab: "la DGH", "d.g.h" and "DGH" would be three
  papers, three split bordereaux, and the director's totals scattered across
  them. Tab creation is automatic and deliberately so — `file_report` calls
  `sheets.ensure_tab` before every read because `read_tab` on an unknown tab is
  a 400, not an empty list, so without it a new site's first message would 502
  and jam `failed_writes` forever.

  Owner's decision (2026-08-15), in two parts:
  - **Match first.** Normalize the spoken name (case, accents, articles,
    punctuation) against the existing `chantiers` rows, so the three spellings
    above all land on DGH. No new paper for a mis-transcription.
  - **Create on a genuine no-match**, rather than routing to `Non affecté`: an
    unmatched name creates the chantier and its tab, marked **unverified** and
    with `flag_review`, so a real new site works the first time a technician
    mentions it and the owner confirms it afterwards in the dashboard.

  Also settled the same day: the **per-site journal tabs stay**. They are the
  director's own `Tableau de Suivi projet` format, and three things live only
  there — accumulation (a second note the same day merges into one row per
  (date, technicien), or the JH totals line double-counts), the chef columns
  (EQUIPE / heures / JH / ordre du jour / taux de réalisation, written by the
  dashboard and never by a merge), and stock reconciliation with its
  `stock_ecart` warning. `GET /chantiers/{id}/bordereau` also reads
  `chantier["sheet_tab"]` directly, so deleting the tabs would empty the
  bordereau page. `Rapports` is the flat per-message mirror the dashboard
  reads, not a replacement for the journal.
- [~] **5. Rewrite `benchmark/dataset/text_cases.json`** — mostly done
  2026-08-15 (`dca386f`): 20 cases on the current schema, all 25 article fields
  covered, 52 null assertions against 3 zero assertions. **Still missing the
  chantier cases** (a spoken site, and a silent one so the sticky fallback is
  graded) — they were blocked on item 4, which has now landed. Original note: It still grades the
  pre-2026-08-05 schema (`goulottes_m`, `chantier`, `client`), so the text
  benchmark currently measures a contract that no longer exists. Port the 10
  cases, then add cases for the article columns, for a spoken chantier, and for
  a *silent* chantier so the sticky fallback is graded too. Keep the file's own
  rule: explicit negation is a stated 0, never-mentioned is `null`.
- [ ] **6. Port the .docx renderer to Python.** `Dashboard/src/lib/report-export.ts`
  builds it in the browser today, so the scheduled mail — sent by `jobs.py`
  inside the container — cannot attach it. Owner's decision: **the backend
  renders it**, so the document is produced and mailed even with no browser
  open; the dashboard button then downloads the same bytes instead of building
  its own. One renderer, or the two drift like the n8n mapping did.
  Image generation stays inline in the report job, conditional on the model's
  own `besoin_image` flag, with a per-report timeout — a hung image call must
  never cost every chef their report.

### Owner actions — blocking the items above

- [ ] **Confirm or correct the vision answer key** in `benchmark/dataset/plan_cases.json`.
  It is a *draft* written from reading the photos, not ground truth. Specifically
  `p03_complet_vert_bleu_rose` → "couloir sud (restaurant / salle de réunion)":
  **3 of 4 models miss it**, which is either a real shared blind spot or a wrong
  key penalising models for being right. Until this is settled the run is
  directional and must not be quoted in the PFE writeup.
- [ ] **More annotated plans, from other buildings.** One plan in three states
  cannot say whether a model generalises to different handwriting, a different
  layout or a worse photograph. The harness is reusable — a second round costs
  only the photos.
- [ ] **An `HF_TOKEN` or a Cloudflare account (`CF_ACCOUNT_ID` + `CF_API_TOKEN`)**,
  if generated images are wanted in the .docx at all. Without one of them the
  image survey has no candidate and the answer stays "Pillow card only".
- [ ] **Decide on the "illustration générée" caption.** Assumed on for every
  generated image so a reader cannot mistake one for a site photo; say if it
  should be off.
- [ ] **Restart the API** — `docker compose up -d --build api`. The extraction
  prompts changed and `prompt_loader` is `@lru_cache`d on purpose, so a running
  container still serves the old ones.
- [ ] **`benchmark/dataset/images/` and `benchmark/results/` are gitignored**, so
  the three plan photos and every result file live only on this machine. The
  benchmark is therefore not reproducible from a fresh clone — decide whether
  the plans are shareable (they are a client's floor plan) before changing that.

## Batch 2026-08-15 (3) — image generation removed, benchmarks widened

- [x] **AI image generation removed from the whole project** (`15a5fd0`).
  Image *understanding* untouched — it is the half that works (92% zone recall,
  0 hallucinations). Generation went because it never worked and could not:
  Google answers every image model with `429` and "check your plan and billing
  details" — a billing wall, not a rate that resets — reproduced twice on
  different days including once on a deliberately cold quota, and no other free
  endpoint returned pixels either (Pollinations now 403s anonymous callers; HF
  and Cloudflare need keys this project does not have). 0 of 8.
  Out: `app/imagegen.py`, `POST /generate-image`, `image_generation_chain`,
  `prompts/image-generation.md`, the survey script, and the whole dashboard
  surface (9 locale keys per file, now 446 x 3). `report_versions.image` is
  **kept** — dropping a column is irreversible and old signed-off versions still
  hold their picture.
- [x] **Benchmark results filed by date** (`b10fbf1`): `results/<YYYY-MM-DD>/`,
  with the STT history from 2026-07-27 to 08-08 filed retroactively. A ranking
  quoted without the day it was measured is not evidence — free catalogues
  change under you.
- [x] **Text candidates widened from 8 to 25** — every model the two keys
  actually serve (16 Gemini + 9 Groq), enumerated from the live catalogues
  rather than hand-picked. Includes `allam-2-7b`, Arabic-first, the one
  candidate with a claim to win on a Darija corpus specifically. Also fixed
  `engine_for`, which guessed the vendor from the model string and would have
  misrouted `allam-2-7b` and `gemma-4-31b-it` to the wrong API — returning a
  404 indistinguishable from "this model is dead".
- [ ] **Add the chantier cases to `text_cases.json`** — unblocked now that item
  4 has landed. One case stating a site, one silent so the sticky fallback is
  graded.
- [ ] **Deploy.** `docker compose up -d --build api`. The extraction prompts
  changed twice today (bordereau articles, then `chantier_mentionne`) and
  `prompt_loader` is `@lru_cache`d on purpose, so the running container still
  serves the old ones. **The features are committed, tested and not live.**

## Batch 2026-08-15 (4) — vérification bout en bout et ce qui reste

- [x] **Un vrai message a traversé le nouveau code** (2026-08-15, 23h). Une note
  vocale réelle du dataset (`WhatsApp Audio 2026-07-22 at 3.43.06 AM.ogg`)
  poussée dans le `/process` **en production**, pas dans un test : STT `gemini`
  en 6,3 s, aller-retour 12,9 s, aucun warning. Elle a rempli
  `cable_elec_3x2_5_m: 30` — un des 25 champs articles créés le jour même, à
  partir de « posina 30 m d'le câble 3*2.5 » en darija mélangé — plus
  `goulotte_m`, `prises_connectees`, `etages: [E4, E2, E1]`, et surtout
  `chantier_mentionne: "Novick"`. Toute la journée s'exécute en un appel.
  Note : « Novick » n'existe pas dans `chantiers`, donc le passage par
  `/journal` créera un site **non vérifié** et marquera la ligne — le chemin
  prévu, pas encore observé.

- [x] **Quatrième piège de déploiement trouvé en le commettant** (`ac2bb1c`).
  Le Dashboard est une image construite lui aussi (`build: ./Dashboard`) : rien
  dans `up -d --build api` ne le touche. Supprimer `POST /generate-image` côté
  API sans reconstruire `web` a laissé le bundle servi appeler un endpoint
  disparu — un bouton vivant en apparence qui renvoyait 404, en direct, pendant
  une heure. La règle est maintenant dans CLAUDE.md : **on retire une
  fonctionnalité `web` d'abord et `api` en dernier ; on en ajoute une dans
  l'autre sens.**

### Ce qui reste, par ordre de valeur

- [ ] **Confirmer le corrigé du benchmark vision** (`dataset/plan_cases.json`),
  en particulier `p03` → « couloir sud (restaurant / salle de réunion) » : 3
  modèles sur 4 la manquent. Soit c'est un angle mort réel, soit le corrigé est
  faux et les modèles sont punis d'avoir raison. **Tant que ce n'est pas tranché,
  ces chiffres ne peuvent pas être cités dans le rapport de PFE.**
- [ ] **Refaire la comparaison à 25 modèles un matin calme.** Celle du soir a été
  abandonnée à 2 modèles sur 25 : 13 appels sur 23 en 503 « high demand » et le
  reste en 429 sur le quota déjà consommé par les runs de la journée — le
  benchmark entrait en concurrence avec le pipeline en production pour le même
  quota gratuit. Ne pas relancer un jour où d'autres runs tournent.
- [x] **Porter le générateur .docx en Python** — fait 2026-08-16, **à vérifier
  par le propriétaire** (voir le batch 2026-08-16 (3) plus bas).
  Ancienne note : **toujours pas commencé.** Une tentative du 2026-08-16 s'est arrêtée sur la
  limite de session après n'avoir ajouté que la dépendance `python-docx`, qui a
  été annulée : une dépendance inutilisée dans l'image de production, c'est du
  poids et de la surface d'attaque pour rien, et `pip-compile` la régénère en
  une commande le jour où le rendu existe vraiment.
  C'est **le dernier endroit où le système contredit une décision prise à voix
  haute** : « keep it in the backend, so if no one has the browser opened, the
  docx will still be auto-generated and sent by email ». Aujourd'hui le
  document n'existe encore que si quelqu'un clique.
- [x] **Interface de confirmation des chantiers non vérifiés** — fait
  2026-08-16 (`76a5757`). `PATCH /chantiers/{id}` confirme, `DELETE` supprime
  une mauvaise transcription avec son bordereau ; les deux en
  `require_director` et tracés dans l'audit. La liste vit sur la page Vue
  d'ensemble — la seule qu'un directeur ouvre sans y être envoyé — et ne
  s'affiche pas du tout tant qu'il n'y a rien en attente. **La suppression
  laisse l'onglet du journal en place** : le bordereau est à nous et part avec
  la ligne, l'onglet est le registre du directeur, et un clic dans un dashboard
  ne doit jamais effacer des mois de rapports dans son fichier.

- [x] **Cas chantier dans `text_cases.json`** — fait 2026-08-16 (`4627044`).
  24 cas, dont 6 notent `chantier_mentionne` et 2 exigent qu'il vaille `null` :
  c'est cette absence qui déclenche la reprise du dernier chantier connu, donc
  un nom deviné n'y donne pas un champ un peu faux, il envoie une journée
  entière sur le mauvais onglet.
- [ ] **Plus de plans annotés, d'autres bâtiments.** Un seul plan en trois états
  ne dit rien sur une autre écriture, un autre bâtiment ou une photo plus
  mauvaise. Le harnais est réutilisable : un second tour ne coûte que les
  photos.

## Batch 2026-08-16 (2) — le repli local n'avait jamais répondu du premier coup

- [x] **`local` expirait systématiquement à son premier appel.** Le sidecar
  charge son modèle au **premier** `/transcribe` (pour ne pas immobiliser 4 Go
  d'une carte de 8 Go en permanence), et ce chargement se paie **dans la requête
  elle-même**. Mesuré le 2026-08-16 sur la 3070 : `load_seconds = 280,4`, puis
  ~32 s de transcription. Le budget client était de 300 s : il couvrait le
  chargement et ne laissait rien pour le travail. Donc **chaque premier appel
  après un redémarrage échouait — et en échouant il chauffait le modèle, si bien
  que le suivant réussissait.** Vu de l'extérieur cela ressemble à « c'est lent
  la première fois », et c'est exactement pour cela que personne ne l'a vu :
  ce moteur n'avait jamais répondu à sa première requête.
  Corrigé : `COLD_START_BUDGET_S = 420` (chargement + transcription + marge) et
  `proxy_read_timeout 460s` côté nginx, qui doit rester **au-dessus** du client
  sinon le proxy plafonne en silence un budget que l'API croit maîtriser.
  Le chiffre « ~235 s » de CLAUDE.md était faux et a été remplacé par la mesure.

- [x] **Le « 18 prises » n'était pas une hallucination.** Vérifié en
  re-transcrivant la même note avec le **moteur local** — autre fournisseur,
  autre architecture, autres modes d'échec. Les deux chaînes produisent `18`.
  Technique réutilisable : la chaîne existe pour la disponibilité, mais elle
  sert aussi de vérification croisée gratuite sur le GPU de la maison dès qu'un
  chiffre est contesté.

- [x] **Preuve sur modèle FROID** (2026-08-16, après le correctif) : 407 s au
  total, dont 394 s de STT, `engine=local`, et `prises_connectees: 18`. C'est
  la première fois que ce moteur répond à son premier appel. La marge est
  cependant **de 13 s seulement** sur le budget de 420 s — et 394 s, ce n'est
  pas les ~312 s attendus (280 de chargement + 32 de transcription) : le
  chargement n'est pas un coût fixe, il dépend de ce qui occupe la carte, et ici
  `stt-local` venait de redémarrer en même temps que l'API.

- [x] **Le chargement paresseux est la mauvaise forme pour un repli** — fait
  2026-08-16, **option 1**. `STT_LOCAL_PRELOAD` dans `stt_server.build_app` :
  un fil démon appelle le `_ensure_loaded` existant au démarrage, donc même
  verrou et même fonction — un `/transcribe` qui arrive pendant le chargement
  attend au lieu d'en lancer un second. `docker-compose.yml` met la variable à
  `1` pour le service `stt-local` ; la mettre à `0` rend le comportement
  paresseux. Le budget de 420 s reste en place : les deux moitiés ne dépendent
  plus l'une de l'autre. **À vérifier au prochain redémarrage** :
  `docker compose up -d stt-local` (pas `restart` — cf. piège n°4), puis
  `/health` doit passer `loading` → `ok` sans qu'aucune note n'ait été envoyée.
  Note d'origine : Ne pas
  « monter le timeout à 600 s » : poursuivre un nombre qui bouge, c'est finir
  avec un délai de dix minutes qui masque un vrai blocage. Le coût tombe sur le
  seul appelant qui le mérite le moins, au moment précis où les deux moteurs
  cloud ont déjà échoué. Deux vraies options :
  1. **Préchauffer au démarrage** derrière un drapeau (`STT_LOCAL_PRELOAD`) —
     on échange 4 Go de VRAM au repos contre un repli réellement présent quand
     il sert. C'est le compromis que le chargement paresseux avait justement
     refusé, mais il a été choisi avant qu'on sache que le premier appel
     échouait toujours.
  2. **Rendre le premier appel non bloquant** : `/transcribe` répond « en
     chargement, réessayez » et le déclenche, la chaîne passe au moteur suivant
     ou la file de reprise repasse plus tard. Le technicien n'attend jamais
     7 minutes.
  L'option 1 est la plus simple et la plus honnête tant que la carte n'est pas
  disputée.

- [ ] **Les deux moteurs ne sont PAS d'accord sur le reste de cette note.**
  Gemini : `cable_elec_3x2_5_m = 30`. Local : `cables_installes_m = 3`. Même
  audio, champ différent ET valeur différente — l'un des deux s'est trompé de
  matériau, ce qui n'est pas une nuance : l'un remplit une ligne du bordereau
  électricité, l'autre une ligne cuivre. C'est précisément ce que
  `benchmark/dataset/references.csv` (aujourd'hui vide, en-tête seul) doit
  trancher : une transcription de référence écrite par un humain qui parle
  darija, pour cette note au moins.

## Batch 2026-08-16 (3) — le .docx passe au backend, la transcription devient corrigeable

**Écrit, testé, pas encore vérifié en vrai par le propriétaire.** Rien n'est
déployé : `docker compose up -d --build api` puis `--build web` (dans cet ordre,
c'est un ajout de fonctionnalité — voir CLAUDE.md, piège n°3).

- [x] **Le rendu .docx vit maintenant dans l'API** (`api/app/docx_report.py`).
  C'était le dernier endroit où le système contredisait une décision prise à
  voix haute : le document n'existait que si quelqu'un cliquait, donc le
  courrier programmé — envoyé par un fil d'exécution dans le conteneur, sans
  navigateur — ne pouvait rien joindre. Désormais :
  - `jobs._report_mail` joint le document à **chaque** rapport envoyé, y
    compris celui de chaque chef. L'échec du rendu est **non fatal** et
    imprimé : un document qui ne se construit pas ne doit pas coûter le
    rapport lui-même, qui reste lisible dans le corps du mail.
  - `POST /reports/export` renvoie **les mêmes octets** ; le bouton du tableau
    de bord les télécharge au lieu de fabriquer sa copie. Un seul moteur de
    rendu, sinon les deux dérivent comme l'avait fait le mapping n8n.
  - **Les chiffres ne voyagent pas.** Le navigateur envoie le titre et le
    corps (l'opérateur a pu éditer le brouillon — ce texte *est* le rapport) ;
    l'API recalcule les huit totaux et le tableau par technicien depuis les
    lignes de la feuille que la période couvre. Un client ne peut donc pas
    poster ses propres chiffres dans un document signé de l'en-tête maison, et
    la page et le document ne peuvent pas se contredire. L'arithmétique
    reproduit `metrics.ts` (`num`, `isFlagged`) à l'identique — une virgule
    décimale est un nombre, `"abc"` vaut 0, un technicien vide n'est pas
    quelqu'un.
  - Dépendance `python-docx` ajoutée à `requirements.in` et recompilée ; la
    dépendance npm `docx` a été **retirée** du Dashboard, elle n'a plus
    d'appelant. 7 tests dans `api/tests/test_docx_report.py` (parité des
    chiffres, le .docx est un vrai ZIP OOXML avec en-tête, pied de page et
    champ `NUMPAGES` vivant, et un rapport sans lignes s'écrit quand même).
  - **Non vérifié :** personne n'a encore ouvert le fichier produit dans Word,
    ni reçu un mail avec la pièce jointe. C'est le contrôle à faire.

- [x] **La transcription d'une note vocale est affichée sous l'audio, et
  corrigeable** (inbox). Une sous-bulle « Transcription » sous le lecteur, avec
  un crayon ; l'édition écrit par `PATCH /reports/{row}` (champ
  `rapport_complet`) pour un message devenu ligne de la feuille, et par le
  nouveau `PATCH /exchanges/{id}` pour un message qui ne l'est jamais devenu.
  La règle précédente disait « jamais éditable — c'est la preuve, et une
  transcription corrigée rendrait l'extraction inauditables ». Elle avait raison
  sur le risque et tort sur le remède : laisser à la seule personne capable
  d'entendre l'erreur une transcription qu'elle peut lire sans la corriger ne
  préserve pas la preuve, cela préserve l'erreur. Les deux chemins d'écriture
  enregistrent la **valeur précédente** dans la piste d'audit
  (`transcript_edited` / `report_edited`), donc la sortie brute du moteur reste
  récupérable. **Ne jamais écrire cette correction autrement.**
  Un message **tapé** n'a pas de sous-bulle : son texte *est* ce que le
  technicien a écrit, et proposer de l'éditer inviterait à réécrire ses propos.

### À vérifier par le propriétaire (ce batch)

- [ ] Ouvrir un .docx produit par `POST /reports/export` dans Word : en-tête
  AZNET, pied de page avec `page / total`, grille de 8 chiffres, titres de
  niveau 2 réels (volet Navigation), tableau par technicien.
- [ ] Recevoir un rapport programmé et vérifier que la pièce jointe est là et
  qu'elle correspond au corps du mail.
- [ ] Corriger une transcription dans l'inbox, puis vérifier dans la page
  Historique que l'ancien texte figure bien en `before`.

- [ ] **Placer `docs/pipeline-voix-vers-sheets.png` dans le rapport — mais
  trancher d'abord le doublon.** Le schéma (1720×2436, dessiné avec Pillow, le
  script est dans le scratchpad) raconte le même trajet que la **Figure 3.3**
  déjà présente (`diagrams/02-lifecycle-voice.png`, « Cycle de vie complet
  d'une note vocale, de l'émission à la ligne du journal »). Deux figures pour
  un même parcours, c'est une de trop : un lecteur cherche la différence, n'en
  trouve pas, et doute des deux. Trois issues, au choix du propriétaire :
  1. **Remplacer** la 3.3 — le nouveau schéma porte le raisonnement dans la
     marge (ordre de la chaîne STT établi par mesure, null vs 0, pas de
     correspondance approximative), ce que le diagramme mermaid ne fait pas.
  2. **Le mettre ailleurs** — en ouverture du chapitre 4 (Réalisation) ou en
     synthèse du chapitre 1, là où il n'entre pas en concurrence avec la 3.3.
  3. **Le garder hors du rapport**, pour la soutenance et le README seulement.
  Quelle que soit l'issue : il faut un numéro et une légende au format EMSI
  (bloc `FigureImage` + `FigureCaption`, légende **au-dessus** pour les
  tableaux, en dessous pour les figures), une largeur en cm — il est en portrait
  très allongé, viser `width=12cm` maximum pour qu'il tienne sur une page — et
  la renumérotation de toutes les figures qui suivent, plus les renvois
  « **Figure X.Y** » dans le texte.

## Bilan des 15–16 août 2026 — 18 commits, suite à 355 vert

### Livré

| Livraison | Commit | État |
|---|---|---|
| 25 champs articles du bordereau (union DGH / Extralait / ACAPS) | `ac349cf` | Feuille Rapports à **62 colonnes**, en ligne |
| Benchmark vision sur plans annotés + relevé de joignabilité génération d'images | `7d9b75a` | Corrigé **confirmé par le propriétaire** le 16-08 → chiffres citables |
| Chantier dicté par le technicien + reprise du dernier connu | `0d8eceb` | Prouvé sur du darija réel (`chantier_mentionne: "Novick"`) |
| Jeu de cas du benchmark texte réécrit pour le schéma courant | `dca386f` | 20 cas, les 25 champs articles couverts |
| Génération d'images retirée du projet (compréhension conservée) | `15a5fd0` | 0/8 points d'accès joignables, mesuré deux fois |
| Résultats classés par date + 25 modèles candidats | `b10fbf1` | `results/<AAAA-MM-JJ>/`, historique STT reclassé |
| Les deux chaînes d'extraction reclassées sur les preuves | `70f0ab4` | `gpt-oss-120b` gardé en 2ᵉ pour le compteur indépendant |
| Cas chantier notés dans le benchmark | `4627044` | 24 cas, 2 exigent `null` |
| Chantiers non vérifiés : liste + confirmer/supprimer | `76a5757` | En ligne, la suppression épargne l'onglet du journal |
| Motif du flag + alerte `photo_zones_partielles` | `ec34be9` | Colonne en ligne, alerte issue d'une mesure |
| Repli STT local : budget de démarrage à froid | `4517469` | **407 s sur modèle froid — premier succès au premier appel** |

### Bugs trouvés en se servant du système, pas en le lisant

Chacun passait la suite de tests au moment où il a été trouvé.

| Bug | Comment il se présentait | Ce qu'il faisait vraiment |
|---|---|---|
| `engine_for` devinait le fournisseur d'après le nom du modèle | un 404 | `allam-2-7b` et `gemma-*` envoyés à la mauvaise API — indiscernable d'un modèle mort |
| Listes comparées avec `==` | rien du tout | `["E1","RDC"]` noté faux contre `["RDC","E1"]` : chaque cas multi-étages sous-noté |
| La chaîne `"null"` dans les champs liste | « Groq est mauvais » | validateur générique court-circuité → la moitié Groq de la chaîne échouait sur la plupart des rapports |
| Bundle du dashboard périmé | un bouton normal | appelait `POST /generate-image`, supprimé — 404 en direct pendant une heure |
| Limite de grille Sheets | un script qui plante | `_extend_headers` aurait bloqué la file de reprise au prochain champ ajouté |
| Repli STT local jamais joignable au 1ᵉʳ appel | « c'est lent la première fois » | **échouait toujours**, et l'échec chauffait le modèle donc la reprise passait |
| `ec34be9` poussé sans relancer la suite | vérifié en direct sur la vraie feuille | le faux service Sheets n'avait pas `.get()` — corrigé en `4517469` |

### Reste à faire, par valeur

| # | Tâche | Qui |
|---|---|---|
| 1 | **Un vrai message de technicien jusqu'au bout**, y compris `/journal` : création d'onglet, drapeau non vérifié, ligne à 62 colonnes, fusion d'un 2ᵉ message le même jour. **N'a jamais tourné.** | propriétaire |
| 2 | ~~Porter le générateur .docx en Python~~ — **écrit le 2026-08-16**, reste à ouvrir un fichier produit et à recevoir un mail avec la pièce jointe | propriétaire (vérification) |
| 3 | ~~Préchauffer le STT local~~ — **fait 2026-08-16** (`STT_LOCAL_PRELOAD=1`), reste à observer un démarrage réel | propriétaire (vérification) |
| 4 | Refaire la comparaison à 25 modèles un matin calme, hors production | assistant |
| 5 | Trancher le désaccord Gemini (`cable_elec_3x2_5_m: 30`) vs local (`cables_installes_m: 3`) sur la même note | propriétaire (darijophone) |
| 6 | Plus de plans annotés, d'autres bâtiments — l'encombrement attentionnel se reproduit-il ? | propriétaire |


- [] fix this in frontend "Generated by automatique"
