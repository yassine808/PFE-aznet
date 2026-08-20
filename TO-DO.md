# TO-DO

Open items only. Everything marked done moves to `FIXED.md` — that file is the done log, this one is the queue.

## Batch 2026-08-16 (4) — la note vocale muette, et le lien audio qui pointe chez nous

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

- [ ] **Add the chantier cases to `text_cases.json`** — unblocked now that item
  4 has landed. One case stating a site, one silent so the sticky fallback is
  graded.
- [ ] **Deploy.** `docker compose up -d --build api`. The extraction prompts
  changed twice today (bordereau articles, then `chantier_mentionne`) and
  `prompt_loader` is `@lru_cache`d on purpose, so the running container still
  serves the old ones. **The features are committed, tested and not live.**

## Batch 2026-08-15 (4) — vérification bout en bout et ce qui reste

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

- [ ] **Plus de plans annotés, d'autres bâtiments.** Un seul plan en trois états
  ne dit rien sur une autre écriture, un autre bâtiment ou une photo plus
  mauvaise. Le harnais est réutilisable : un second tour ne coûte que les
  photos.

## Batch 2026-08-16 (2) — le repli local n'avait jamais répondu du premier coup

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

## Batch 2026-08-19 — file d'attente, quotas, ordre des messages (dictés par le propriétaire)

Notés ici tels qu'énoncés, avant toute analyse. Le grill qui suit les précise un
par un ; ce bloc reste la trace de la demande d'origine.

- [ ] Database mirror to google sheets, writes in two places (local as backup)

### Design verrouillé au grill du 2026-08-20 (avec le propriétaire, question par question)

Les trois items ci-dessus ne sont pas trois chantiers indépendants : le troisième
signale son état **par réaction**, donc il est illisible tant que le premier n'est
pas corrigé. Ordre imposé : 1 → 2 → 3.

**Constat 1 — la réaction ✅ manquante est un problème d'appariement d'items n8n.**
Tous les nœuds d'accusé visent le message par `$('Filtrer accès').item.json.message_id`.
`Filtrer accès` tourne en `runOnceForAllItems`, retourne un tableau neuf **sans
`pairedItem`**, et peut émettre *moins* d'items qu'il n'en reçoit (la branche
« étranger » en supprime). À un message l'appariement retombe correctement sur
l'unique item — vérifié sur l'exécution 54910, `WA ack done` a réussi. À N
messages il lève « can't determine which item to use » ou s'effondre sur l'indice 0.
Les deux nœuds d'accusé portent `onError=continueRegularOutput` : **l'échec est
donc muet**. Seul `Restore message` posait `pairedItem` ; `Process output` le *nomme en
commentaire* depuis le 2026-08-15 sans jamais le poser, donc la chaîne cassait là aussi.
Six nœuds corrigés, pas cinq.
→ **Correctif** : poser `pairedItem` dans `Extract TG msgs`, `Extract WA msgs`,
`Sender`, `Correlate` et `Filtrer accès`. On répare la chaîne une fois, pas les
seuls accusés : tous les `$('…').item` du workflow en dépendent.
*À ne pas confondre* avec « WhatsApp ne cite pas une note vocale » (tranché
2026-08-15) : là c'est le rendu de la bulle citée, ici l'appariement. On ne
retouche pas le routage `chat_id`/`message_id` des réponses.

**Constat 2 — l'ordre chronologique est déjà en place, sa cause racine non.**
Le workflow actif trie déjà du plus ancien au plus récent par heure d'envoi,
confirme l'offset Telegram **par update après traitement**, et dédoublonne dans
Postgres (`POST /logs/claim`). Mais `Offset + token` lit encore `lastUpdateId`
dans `$getWorkflowStaticData`, **que chaque push de workflow efface** : l'offset
retombe à 0, Telegram rejoue jusqu'à 24 h d'updates, et ils meurent sur `Fresh?`.
Le symptôme est masqué par le dédoublonnage, la cause est intacte.
→ **Correctif** : déplacer l'offset dans Postgres, à côté du dédoublonnage.

**Constat 3 — bloquant : un `/process` raté ne peut pas être rejoué.**
`_audio_input` transcrit **puis** archive (`main.py:513`). Si la transcription
échoue, `save_media` n'est jamais atteint : le blob n'existe nulle part, et les
URL média de Telegram (~1 h) comme de Meta (minutes) expirent. Une file qui ne
retient que « le message X a échoué » n'aurait rien à rejouer.
→ **Persist-first** : archiver le blob **avant** le travail qui peut échouer.

Décisions, telles qu'arrêtées :

| Question | Réponse retenue |
|---|---|
| Blocage | **Par technicien.** Le journal fusionne par (date, technicien) ; l'ordre inter-techniciens n'a pas de sens. Rayon d'action : une personne. |
| Périmètre de la file | **Échecs `/process` seulement.** Le chemin Sheet a déjà `failed_writes` + son drain et fonctionne. Deux files, une étape chacune. |
| Propriétaire | **API + Postgres.** n8n passe la main une fois ; `jobs.py` réessaie, comme `drain_sheet_queue`. La staticData n8n est disqualifiée : un push l'efface (cf. constat 2). |
| Abandon | Backoff 30 s → 2 min → 5 min → 10 min ×3 (~6 essais, ~40 min), puis ❌ « non traité », ligne marquée abandonnée, file du technicien libérée. Un refus de quota **ne consomme pas d'essai** (règle déjà posée dans `resolve_write(count_attempt=False)`). Un 422 — entrée malformée, jamais réparable — meurt au 1ᵉʳ essai. |
| Quota | **On suspend le traitement, pas la réception.** Sonder Telegram et accepter les webhooks Meta coûte peu et ne perd rien ; c'est l'appel au modèle qu'on arrête. Suspendre le sondage perdrait les updates au-delà des ~24 h de rétention Telegram, et Meta pousse de toute façon. |
| Déclencheur du quota | **Chaîne texte entièrement épuisée** (Groq *et* les deux Gemini). Groq seul épuisé ne bloque rien — la chaîne bascule, c'est pour cela qu'elle alterne les fournisseurs — mais c'est signalé au tableau de bord comme avertissement. |
| Message de quota | Une fois par panne et par technicien, sur son canal, **et** l'état suspendu au tableau de bord. |
| Signal de réessai | **Réaction seule, aucun message de chat** (choix du propriétaire contre ma recommandation) : ⏳ → 🔄 en file, ✅ ou ❌ à la fin. C'est ce qui rend le constat 1 bloquant. |
| Réponse tardive | **L'API répond.** `POST /reply` existe déjà et prend `identity_id`. Le job de réessai l'appelle et pose ✅. Aucune exécution n8n maintenue ouverte 40 minutes. |
| Portillon | **`/process` interroge la file lui-même** : si le technicien a un message non résolu, on met en file et on répond « queued ». Un seul portillon, à l'endroit par où tout passe déjà — Telegram, WhatsApp et le job de réessai compris. |
| Tableau de bord | Section « Messages en attente » **sur la page Queue existante**, au-dessus de `failed_writes`. Pas de route ni d'entrée de navigation en plus. |

Conséquence de périmètre repérée pendant le grill : `app/reply.py` sait envoyer du
**texte** sur les deux canaux, pas des **réactions**. Le signal par réaction
impose donc d'y ajouter `set_reaction()` — mêmes endpoints que ceux que n8n
appelle déjà, charges utiles connues.

## Batch 2026-08-19 (2) — ce que la journée a appris

- [ ] **Le prompt d'extraction coûte ~5 300 jetons par appel** (14,7 Ko + le soul), soit ~37 appels par jour de quota gratuit. Suffisant en usage réel, épuisé en une journée de tests. À réduire — mais chaque règle du fichier a été payée par un bug, donc pas sans vérifier ensuite.

- [ ] in the sites page, show the name of materials for each Site grouped,+ keep the ones i changed aswell, but in different section aswell, dont make them vanish
