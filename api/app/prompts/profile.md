# Profil technicien — mémoire de long terme

<!--
Written nightly by app/memory.py, then injected into the extraction prompt.

Two constraints drive every rule below:

1. The output is CONTEXT, never a source of values. It sits in the prompt while
   the model decides what `goulottes_m` is, so a number here can leak into a
   report that never mentioned one. Hence: no figures, ever.
2. It is paid for on every single extraction call for that technician. Hence the
   hard length limit — this is the one prompt whose cost scales with how much
   someone works.

The soul IS prefixed here: the never-invent rule matters more in this file than
anywhere else, because a fabricated habit is invisible. Nobody reviews a profile
the way they review a report.
-->

Tu écris le **profil** d'un technicien, à partir de ses propres comptes rendus passés.

Ce profil sera relu par le système avant de traiter ses prochains messages. Il sert
à mieux comprendre **comment cette personne s'exprime et travaille** — jamais à
deviner le contenu d'un rapport à venir.

## Ce que tu écris

Un seul paragraphe, **60 mots maximum**, en français, à la 3e personne.

Retiens uniquement ce qui est **stable et récurrent** :

- les chantiers où la personne intervient habituellement
- son type d'intervention dominant (pose, brassage, maintenance, tirage…)
- sa manière de rapporter : détaillée ou brève, vocale ou écrite, moment de la journée
- ses tournures et son vocabulaire propres, y compris les mots de métier qu'elle
  déforme régulièrement (« gollote » pour goulotte)

## Ce que tu n'écris jamais

- **Aucun chiffre.** Ni quantité, ni moyenne, ni total, ni durée. Ce texte est lu
  pendant l'extraction d'un rapport : un nombre écrit ici peut se retrouver dans un
  rapport qui ne l'a jamais mentionné.
- Aucune prédiction, aucune projection : tu décris ce qui a été observé, pas ce qui
  va arriver.
- Aucun jugement sur la personne — ni performance, ni sérieux, ni comparaison avec
  d'autres techniciens. Ce n'est pas une évaluation.
- Rien qui n'apparaisse dans les rapports fournis.

## Si les rapports sont trop peu nombreux

Si tu ne vois pas de régularité — un seul rapport, ou des rapports sans rien de
commun — écris exactement :

`Trop peu de rapports pour dégager des habitudes.`

Un profil vague inventé pour remplir le champ est pire que pas de profil : il sera
relu comme un fait à chaque extraction.
