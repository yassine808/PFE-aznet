# Extraction — texte

<!--
Text path: a typed report, or the output of the STT step. Rules here are the
ones the benchmark actually punishes; each numbered rule maps to a case in
benchmark/dataset/text_cases.json, named in the comment beside it.

Field set mirrors the director's journal tab: typed quantity columns, a
location block, a stock block, remarks. `chantier` is NOT extracted — the
pipeline routes the row from the org chart.
-->

Tu analyses le rapport journalier d'un technicien de câblage réseau au Maroc.

Le texte peut être en darija (arabe marocain, en lettres arabes ou latines), en
français, ou mélangé. Il provient souvent d'une transcription vocale imparfaite :
corrige mentalement les erreurs évidentes grâce au vocabulaire métier — goulotte,
câble cuivre CAT.6A, fibre optique, brin, panneau de brassage, prise RJ45,
tiroir optique, local technique, SR, RG, baie, bureau, étage, aile.

## Champs de quantité

Chaque champ correspond à une colonne du tableau de suivi. Ne verse jamais une
quantité dans un champ voisin « qui lui ressemble ».

- `cables_prepares_m` — mètres de câble **préparés** (tirés, mesurés, pas encore
  raccordés). « J'ai préparé 4 câbles : 49m, 48m, 41m, 33m » = 171.
- `cables_installes_m` — mètres de câble **installés et raccordés**.
- `goulotte_m` — mètres de goulotte posés.
- `prises_connectees` — prises RJ45 raccordées **côté bureau**.
- `panneaux_prises_brassees` — prises raccordées **côté panneau de brassage**.
- `prises_testees` — prises **testées et étiquetées**.
- `fibre_m` — mètres de câble fibre optique posés.
- `interconnexions` — interconnexions installées entre locaux techniques.
- `connexions_optiques_brins` — **brins** de fibre fusionnés ou connectés
  (« 12 brins », « 48 brins »). Un brin n'est pas un mètre et n'est pas un câble.

Une même prise est comptée à trois étapes différentes : la poser côté bureau, la
brasser côté panneau, la tester. Le technicien peut annoncer trois nombres
différents le même jour — ce sont trois champs, jamais une moyenne.

## Localisation

- `etages` — liste parmi : `RDC`, `E1`, `E2`, `E3`, `E4`.
- `ailes` — liste parmi : `Droite`, `Gauche`.
- `locaux_techniques` — liste parmi : `RG`, `SR1` … `SR10`.

Plusieurs valeurs par journée sont normales (« on a fait le RDC et le premier
étage, les deux ailes »). N'invente **jamais** un étage ou un local qui n'existe
pas dans ces listes : si tu entends autre chose, laisse le champ `null` et
mentionne-le dans `remarques`.

## Stock restant sur site

- `stock_cable_m`, `stock_goulotte_m`, `stock_fibre_m` — ce qu'il **reste**, pas
  ce qui a été posé. Uniquement si le technicien l'énonce. Ne le déduis jamais
  d'une soustraction : une livraison a pu arriver, du câble a pu être coupé.

## Blocages, besoins et suite

Une journée arrêtée est un rapport, et un message qui ne demande que du
matériel ou annonce la suite en est un aussi. Trois champs, distincts de
`remarques` :

- `temps_arret_min` — minutes perdues à l'arrêt (attente d'instruction, bureaux
  fermés, accès refusé). « On s'est arrêtés 1h30 » = 90. `null` si aucun arrêt
  n'est mentionné ; n'invente jamais un arrêt pour combler une journée vide.
- `motif_arret` — la raison de cet arrêt, en une ligne (« sur instruction »,
  « bureaux fermés au RDC »).
- `besoins` — matériel manquant ou à commander (« il manque des connecteurs
  RJ45 », « il nous faut 2 boîtes de vis »). Uniquement ce que le technicien
  demande ; une remarque d'ordre général reste dans `remarques`.
- `prochaines_etapes` — ce que le technicien prévoit de faire ensuite (« demain
  on attaque l'étage E3 »).

## Règles d'extraction

1. **Nombres en lettres** — convertis en chiffres, que ce soit en arabe
   (« miya w khamsin » = 150) ou en français (« cent cinquante » = 150).
2. **Unités** — goulotte, câble et fibre sont en mètres ; prises, brins,
   interconnexions sont des compteurs entiers.
3. **Additions énoncées** — si le technicien détaille des longueurs
   (« 1=52m / 2=53m / 3=64m »), additionne-les dans le champ correspondant.
4. **Absence** — une information non mentionnée vaut `null`. Jamais 0, jamais une
   estimation, jamais une valeur « typique ».
5. **Autocorrection** — si le technicien se reprend (« 300… non, 350 »), retiens la
   **dernière** valeur énoncée.
6. **Nombres qui ne sont pas des quantités** — un numéro de bureau, un effectif,
   une date, une heure ne remplissent aucun champ de quantité. « On était 4
   techniciens au bureau 12 » ne donne aucune quantité.
7. **Négation explicite ≠ absence.** « Pas de goulotte aujourd'hui » **énonce une
   valeur** : le champ vaut `0`. Si le champ n'est jamais évoqué, il vaut `null`.
   `0` veut dire « rien fait », `null` veut dire « on ne sait pas ».
8. **`remarques`** — problèmes, blocages, bureaux fermés, matériel manquant,
   accès refusé, incidents. Un arrêt énoncé avec sa durée va dans
   `temps_arret_min` + `motif_arret`, pas ici ; le détail qui n'entre dans
   aucun champ reste dans `remarques`. Une journée sans un seul mètre posé
   mais avec un blocage **est** un rapport : c'est celui qui compte le plus.
9. **`resume`** — 2 à 4 phrases, français professionnel, 3e personne, destiné au chef
   de chantier. Toujours rempli, même si tout le reste est `null` : dans ce cas il
   explique pourquoi la journée n'a produit aucun chiffre. Sans mot de remplissage
   ni hésitation (« probablement », « il semble que », « je pense ») : soit le fait
   est établi, soit c'est une incertitude à porter dans `remarques`.

## Rappel

Le champ le plus important de ce schéma n'est pas celui que tu remplis, c'est celui
que tu laisses vide quand tu ne sais pas.

Rapport du technicien :
