# Extraction — image

<!--
Vision path. The photo goes straight to the schema: there is no transcription
step, so nothing downstream can catch a misread. That is why the confidence
rules here are stricter than the text ones and why every photo-derived row is
written with flag_review = true.
-->

L'image est une photo prise par un technicien de câblage : page de carnet, tableau
blanc, bon de livraison, écran, ou vue du chantier lui-même.

## Procédure

1. **Lis d'abord tout le texte visible**, quelle que soit la langue ou l'écriture :
   français, darija en lettres latines, arabe. Chiffres manuscrits compris.
2. **Puis observe ce que montre la photo** si elle documente un travail réalisé
   (goulottes posées, baie câblée, panneau raccordé).
3. **Enfin, remplis le schéma** à partir de ce que tu as lu et vu.

## Règles propres à l'image

- **Un chiffre illisible reste `null`.** Ne devine pas un « 3 » qui pourrait être un
  « 8 ». Sur une photo, une hésitation de lecture devient une donnée fausse
  définitive : personne en aval n'a la transcription pour la contredire.
- **Ne déduis pas une quantité d'un comptage visuel.** Compter des goulottes sur une
  photo pour en estimer les mètres est une invention, pas une mesure. Seul un nombre
  **écrit** est une quantité.
- **Ce que tu vois sans le lire va dans `remarques`**, pas dans les champs
  chiffrés. « Baie ouverte, câblage apparent non peigné » est une remarque utile ;
  ce n'est pas un `cables_installes_m`.
- **Photo inexploitable** — floue, hors sujet, sans information : tous les champs à
  `null`, et `resume` explique en une phrase ce que montre l'image et pourquoi elle
  ne permet pas d'établir un rapport.
- **Photo partielle** — lisible mais incomplète : tu extrais ce qui est lisible et tu
  laisses le reste à `null`. Tu ne commentes jamais la qualité du document (écriture,
  orientation, photo de travers) et tu ne demandes pas de meilleure photo.

- **Localisation** — `etages` (`RDC`, `E1`..`E4`), `ailes` (`Droite`, `Gauche`) et
  `locaux_techniques` (`RG`, `SR1`..`SR10`) uniquement si l'étiquette est **écrite**
  sur la photo. Reconnaître un couloir n'est pas lire un étage.

- **Chantier** — `chantier_mentionne` reprend le nom du site **mot pour mot**,
  et uniquement s'il est **écrit** sur la photo (en-tête de carnet, bon de
  livraison, panneau, étiquette de baie). Reconnaître un bâtiment n'est pas
  lire son nom : sans texte, le champ reste `null` et le pipeline reprend le
  dernier chantier connu du technicien.

- **Blocages et besoins** — `temps_arret_min`, `motif_arret`, `besoins` et
  `prochaines_etapes` uniquement s'ils sont **écrits** (page de carnet, bon de
  livraison, note). Ne déduis jamais un arrêt d'une photo de chantier vide.

- **Bon de livraison — c'est du matériel REÇU, pas posé.** Une photo de bon de
  livraison, de bon de réception ou de facture de matériel se traite ainsi :
  - `nature` = `"livraison"` ;
  - les quantités vont dans **`livraisons`**, un objet `{champ: quantité}` avec
    exactement les mêmes noms de champs que les quantités posées
    (`{"cables_installes_m": 500, "pigtail_sc_u": 24}`) ;
  - **aucun champ de quantité posée n'est rempli.** Une livraison n'est pas un
    travail effectué : l'écrire dans les colonnes posées ferait apparaître
    500 m livrés comme 500 m installés, et le chantier semblerait terminé alors
    que le câble est encore sur palette.
  - un article que tu ne peux rattacher à aucun champ connu ne s'invente pas :
    décris-le dans `besoins` (« reçu : 3 cartons de colliers »).
  - `resume` annonce la réception (« Réception de 500 m de câble sur DGH »), car
    c'est ce résumé que le technicien reçoit en réponse.

  Pour tout le reste — photo de chantier, page de carnet de pose — `nature`
  reste `null` et les quantités posées se remplissent normalement.

- **Articles du bordereau** — les champs matériel (`pigtail_sc_u`,
  `tiroir_optique_24_u`, `cordons_brassage_1m_u`, `disjoncteur_2x16a_u`, …) ne se
  remplissent que depuis un **nombre écrit** à côté du nom de l'article, sur une
  page de carnet de pose. Compter des objets sur une photo de
  baie est une invention. Et un article **livré** n'est pas un article **posé** :
  un bon de livraison énumère ce qui est arrivé, pas ce qui est installé — il ne
  remplit donc aucun de ces champs.

Les règles générales d'extraction (nombres en lettres, unités en mètres, absence =
`null`, nombres qui ne sont pas des quantités, distinction préparé / installé /
brassé / testé, stock jamais déduit) s'appliquent à l'identique.
