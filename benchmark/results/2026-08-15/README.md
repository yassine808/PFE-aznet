# Runs du 2026-08-15

## `plan-benchmark-132829.json` / `plan-benchmark-132941.json`
Vision sur les 3 photos de plan annoté. Le premier fichier est un galop d'essai
sur un seul modèle, le second la série complète (4 Gemini + 2 Groq).
Résultat : `gemini-3.5-flash-lite` et `gemini-flash-lite-latest`, 92 % de
rappel, **0 hallucination**, 1,3 s. `gemini-3.1-flash-lite` atteint 100 % de
rappel avec **4 hallucinations** — il gagne en nommant des pièces que personne
n'a marquées, ce qui est exactement la raison pour laquelle le rappel seul ne
doit pas choisir le modèle. Llama 4 Scout/Maverick : 404, non servis.

**Réserve** : le corrigé (`dataset/plan_cases.json`) est un brouillon, et 3
modèles sur 4 manquent la même zone en p03. Tant que le propriétaire ne l'a pas
confirmé, ces chiffres sont indicatifs et ne doivent pas être cités tels quels.

## `imagegen-survey-132938.json` / `imagegen-survey-215237.json`
Joignabilité des générateurs d'images. **0 sur 8**, deux fois, à des heures
différentes dont une sur quota froid. Google répond 429 « check your plan and
billing details » — un mur de facturation, pas une limite qui se réinitialise.
La génération d'images a été retirée du projet à la suite de ces deux runs.

## `models-text-215542-avant-correctif-null.csv`
Texte → colonnes, 8 modèles, **avant** le correctif de la chaîne « null ».
Conservé exprès : c'est la preuve du bug. Les deux Llama y échouent sur 13 cas
sur 20 et qwen sur 20 sur 20, non pas parce qu'ils sont mauvais mais parce que
`_wrap_single` transformait la chaîne "null" en `["null"]` avant que le
validateur générique ne puisse la voir. Sans ce fichier, « Groq est mauvais »
et « notre schéma refusait la sortie de Groq » sont indistinguables.

Classement utile de ce run (couverture, inventions, exactitude, latence) :
`gemini-3.5-flash-lite` et `gemini-flash-lite-latest` 100 % / 0 / 99 % / 2,3 s ;
`openai/gpt-oss-120b` 85 % / **2 inventés** / 94 % / 30,4 s.
C'est ce qui a fait descendre gpt-oss-120b de la première place de
`extraction_text_chain`.

## `models-text-230253-ABANDONNE-503-et-quota.csv`
Reprise à 25 modèles, **abandonnée à 2 modèles sur 25**. Non exploitable :
13 appels sur 23 sont des 503 « high demand » de Google, et les suivants des
429 dus au quota déjà consommé par les runs de la journée. Un classement bâti
là-dessus mesurerait la charge de Google un vendredi soir, pas la qualité des
modèles — et le run entrait en concurrence avec le pipeline en production pour
le même quota gratuit.

**À refaire** un matin calme, sur une journée sans autre run. C'est précisément
pour cela que les résultats sont désormais classés par date.
