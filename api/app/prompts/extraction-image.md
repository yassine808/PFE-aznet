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

- **Blocages et besoins** — `temps_arret_min`, `motif_arret`, `besoins` et
  `prochaines_etapes` uniquement s'ils sont **écrits** (page de carnet, bon de
  livraison, note). Ne déduis jamais un arrêt d'une photo de chantier vide.

Les règles générales d'extraction (nombres en lettres, unités en mètres, absence =
`null`, nombres qui ne sont pas des quantités, distinction préparé / installé /
brassé / testé, stock jamais déduit) s'appliquent à l'identique.
