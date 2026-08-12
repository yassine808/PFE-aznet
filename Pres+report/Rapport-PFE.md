::: {custom-style="CoverLogos"}
![](assets/logo-emsi.png){ width=9cm } ![](assets/logo-aznet.png){ width=1.9cm }
:::

::: {custom-style="CoverSchool"}
ÉCOLE MAROCAINE DES SCIENCES DE L'INGÉNIEUR
:::

::: {custom-style="CoverSub"}
Membre de Honoris United Universities — Rabat
:::

::: {custom-style="CoverKind"}
Rapport de Projet de Fin d'Études
:::

::: {custom-style="CoverKindSub"}
présenté pour l'obtention du diplôme d'Ingénieur d'État
:::

::: {custom-style="CoverTitle"}
AUTOMATISATION DES RAPPORTS JOURNALIERS DE CHANTIER PAR INTELLIGENCE ARTIFICIELLE
:::

::: {custom-style="CoverSubtitle"}
Transcription de notes vocales en darija et extraction structurée
:::

::: {custom-style="CoverMeta"}
**Filière :** [À COMPLÉTER — ex. Ingénierie Informatique et Réseaux]
:::

::: {custom-style="CoverMeta"}
**Réalisé par :** Yassine [À COMPLÉTER — NOM]
:::

::: {custom-style="CoverMeta"}
**Encadrant académique :** [À COMPLÉTER]  ·  **Encadrant industriel :** [À COMPLÉTER]
:::

::: {custom-style="CoverMeta"}
**Entreprise d'accueil :** AZNET — Casablanca
:::

::: {custom-style="CoverFoot"}
Soutenu le [À COMPLÉTER] devant le jury : [À COMPLÉTER]
:::

::: {custom-style="CoverFoot"}
Année universitaire 2025 / 2026
:::

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Remerciements

Je tiens tout d'abord à exprimer ma gratitude à mon encadrant académique, [À COMPLÉTER — NOM ENCADRANT ACADÉMIQUE], pour son accompagnement, sa disponibilité et ses conseils méthodologiques tout au long de ce projet de fin d'études.

Je remercie également mon encadrant industriel, [À COMPLÉTER — NOM ENCADRANT INDUSTRIEL], ainsi que l'ensemble de l'équipe d'AZNET, pour leur accueil, leur confiance et le partage de leur expérience du terrain, qui ont permis d'ancrer ce projet dans les besoins réels des équipes de câblage.

Mes remerciements vont aussi au corps professoral de l'EMSI, dont les enseignements ont constitué le socle technique et scientifique de ce travail.

Enfin, je remercie ma famille et mes proches pour leur soutien constant durant l'ensemble de mon cursus.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Résumé

Dans le secteur du câblage réseau, le suivi de l'activité des techniciens repose encore largement sur des comptes rendus oraux ou manuscrits, hétérogènes et difficiles à exploiter. Ce projet de fin d'études, réalisé au sein de l'entreprise AZNET, automatise la production des rapports journaliers de chantier. Le technicien envoie, en fin de journée, une simple note vocale en arabe marocain (darija) — ou une photo de relevé — via Telegram ou WhatsApp ; le système transcrit l'audio, en extrait les données métier typées (mètres de goulotte, de câble préparé et installé, prises bureau, prises panneau, prises testées, mètres de fibre, interconnexions, brins optiques, étages et ailes concernés, stock, remarques), reformule le tout en un résumé professionnel en français, écrit la ligne dans le journal de chantier Google Sheets correspondant et notifie l'encadrement.

L'architecture retenue est hybride : une plateforme d'orchestration low-code (n8n, 65 nœuds) assure la réception multicanale et les intégrations, tandis qu'un microservice développé en Python/FastAPI (66 routes, 8 489 lignes) prend en charge la transcription, l'extraction structurée par grands modèles de langage, la reformulation, la tenue du journal, l'ordonnancement des tâches périodiques et le service du tableau de bord. Un tableau de bord React (11 590 lignes) trilingue français/anglais/arabe complète l'ensemble. La méthodologie suivie est une démarche agile de type Scrum allégé.

Un banc d'essai comparatif de **treize** moteurs de transcription du darija — trois par API et douze en local sur GPU — a été conduit et a renversé l'hypothèse initiale : le moteur retenu n'est pas le service commercial de référence, mais un modèle open-source affiné sur le darija, `BounharAbdelaziz/Morocco-Darija-STT-large`, seul à préserver simultanément les quantités numériques et les emprunts techniques français dont dépend l'intégralité du schéma métier. La chaîne complète, de la note vocale à la réponse de confirmation, est opérationnelle depuis la première semaine du projet. [À COMPLÉTER : résultats chiffrés du pilote en conditions réelles]

**Mots-clés :** reconnaissance vocale, darija, grands modèles de langage, extraction d'information, automatisation de workflows, langue peu dotée.

# Abstract

In the network cabling industry, tracking technicians' daily activity still relies heavily on oral or handwritten reports, which are inconsistent and hard to exploit. This graduation project, carried out at AZNET, automates the production of daily site reports. At the end of the day a technician sends a plain voice note in Moroccan Arabic (Darija) — or a photo of a hand-written tally — through Telegram or WhatsApp; the system transcribes the audio, extracts typed business data (metres of cable tray, of prepared and installed cable, office sockets, patch-panel sockets, tested sockets, metres of fibre, interconnections, optical strands, floors and wings involved, stock, remarks), rewrites everything into a professional French summary, writes the row into the matching Google Sheets site journal, and notifies management.

The chosen architecture is hybrid: a low-code orchestration platform (n8n, 65 nodes) handles multi-channel reception and integrations, while a custom Python/FastAPI microservice (66 routes, 8,489 lines) performs transcription, LLM-based structured extraction, rewriting, journal bookkeeping, job scheduling and dashboard serving. A trilingual French/English/Arabic React dashboard (11,590 lines) completes the system. The project follows a lightweight Scrum methodology.

A comparative benchmark of **thirteen** Darija speech-to-text engines — three via API and twelve locally on GPU — was carried out and overturned the initial hypothesis: the engine finally selected is not the reference commercial service but an open-source Darija fine-tune, `BounharAbdelaziz/Morocco-Darija-STT-large`, the only one preserving both numeric quantities and the French technical loanwords on which the entire business schema depends. The full chain, from voice note to confirmation reply, has been operational since the first week of the project. [TO BE COMPLETED: field-pilot figures]

**Keywords:** speech recognition, Darija, large language models, information extraction, workflow automation, low-resource language.

# ملخص

في قطاع التمديدات الشبكية، لا يزال تتبع النشاط اليومي للتقنيين يعتمد إلى حد كبير على تقارير شفوية أو مكتوبة بخط اليد، غير متجانسة ويصعب استغلالها. يقوم مشروع نهاية الدراسة هذا، المنجز داخل شركة AZNET، بأتمتة إعداد التقارير اليومية للأوراش. يرسل التقني في نهاية اليوم رسالة صوتية بسيطة بالدارجة المغربية — أو صورة لكشف مكتوب بخط اليد — عبر تيليغرام أو واتساب؛ فيقوم النظام بتحويل الصوت إلى نص، واستخراج المعطيات المهنية المصنّفة (أمتار القنوات، الكابلات المحضّرة والمركّبة، مآخذ المكاتب، مآخذ اللوحات، المآخذ المختبرة، أمتار الألياف، الوصلات البينية، الشعيرات البصرية، الطوابق والأجنحة المعنية، المخزون، الملاحظات)، ثم إعادة صياغتها في ملخص مهني بالفرنسية، وتسجيل السطر في دفتر الورش المناسب على Google Sheets وإشعار المسؤولين.

تعتمد البنية المختارة على مقاربة هجينة: منصة أتمتة منخفضة البرمجة (n8n، 65 عقدة) تتكفل بالاستقبال عبر قناتين وبالتكاملات، بينما تتولى خدمة مصغرة مطوّرة بلغة Python/FastAPI (66 مسارًا، 8489 سطرًا) تحويل الصوت إلى نص، والاستخراج المهيكل بواسطة النماذج اللغوية الكبيرة، وإعادة الصياغة، ومسك الدفتر، وجدولة المهام الدورية، وخدمة لوحة القيادة. وتكتمل المنظومة بلوحة قيادة React (11590 سطرًا) بثلاث لغات: الفرنسية والإنجليزية والعربية.

وقد أُجري اختبار مقارن لـ**ثلاثة عشر** محركًا للتعرف على الكلام بالدارجة، ثلاثة عبر واجهات برمجية واثنا عشر محليًا على بطاقة رسومية، فقلب الفرضية الأولية: المحرك المعتمد ليس الخدمة التجارية المرجعية، بل نموذج مفتوح المصدر مُدرَّب على الدارجة، `BounharAbdelaziz/Morocco-Darija-STT-large`، وهو الوحيد الذي يحافظ في آن واحد على الكميات الرقمية وعلى المصطلحات التقنية الفرنسية المقترضة التي يقوم عليها المخطط المهني بأكمله. والسلسلة الكاملة، من الرسالة الصوتية إلى رد التأكيد، تشتغل منذ الأسبوع الأول للمشروع. [يُستكمل: النتائج الرقمية للتجربة الميدانية]

**الكلمات المفاتيح:** التعرف على الكلام، الدارجة، النماذج اللغوية الكبيرة، استخراج المعلومات، أتمتة سير العمل، لغة قليلة الموارد.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

```{=openxml}
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Table des matières</w:t></w:r></w:p>
<w:p>
  <w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>
  <w:r><w:instrText xml:space="preserve"> TOC \o "1-3" \h \z \u </w:instrText></w:r>
  <w:r><w:fldChar w:fldCharType="separate"/></w:r>
  <w:r><w:t>Table des matières — appuyer sur F9 pour la générer.</w:t></w:r>
  <w:r><w:fldChar w:fldCharType="end"/></w:r>
</w:p>
```

```{=openxml}
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Liste des figures</w:t></w:r></w:p>
<w:p>
  <w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>
  <w:r><w:instrText xml:space="preserve"> TOC \h \z \t "FigureCaption,1" </w:instrText></w:r>
  <w:r><w:fldChar w:fldCharType="separate"/></w:r>
  <w:r><w:t>Liste des figures — appuyer sur F9 pour la générer.</w:t></w:r>
  <w:r><w:fldChar w:fldCharType="end"/></w:r>
</w:p>
```


```{=openxml}
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Liste des tableaux</w:t></w:r></w:p>
<w:p>
  <w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>
  <w:r><w:instrText xml:space="preserve"> TOC \h \z \t "TableCaption,1" </w:instrText></w:r>
  <w:r><w:fldChar w:fldCharType="separate"/></w:r>
  <w:r><w:t>Liste des tableaux — appuyer sur F9 pour la générer.</w:t></w:r>
  <w:r><w:fldChar w:fldCharType="end"/></w:r>
</w:p>
```

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Liste des abréviations et acronymes

| Acronyme | Signification |
|---|---|
| API | Application Programming Interface |
| ASR | Automatic Speech Recognition (reconnaissance automatique de la parole) |
| CER | Character Error Rate (taux d'erreur caractère) |
| CSV | Comma-Separated Values |
| CTC | Connectionist Temporal Classification |
| E2E | End-to-End (de bout en bout) |
| FK | Foreign Key (clé étrangère) |
| HTTP | HyperText Transfer Protocol |
| IA | Intelligence Artificielle |
| JSON | JavaScript Object Notation |
| LLM | Large Language Model (grand modèle de langage) |
| LoRA | Low-Rank Adaptation (affinage à faible rang) |
| MSA | Modern Standard Arabic (arabe standard moderne) |
| MVP | Minimum Viable Product (produit minimum viable) |
| ORM | Object-Relational Mapping |
| PFE | Projet de Fin d'Études |
| REST | Representational State Transfer |
| RTL | Right-To-Left (écriture de droite à gauche) |
| SMTP | Simple Mail Transfer Protocol |
| SPA | Single Page Application |
| STT | Speech-To-Text (transcription de la parole en texte) |
| TTL | Time To Live (durée de validité) |
| UML | Unified Modeling Language |
| VRAM | Video Random Access Memory (mémoire de la carte graphique) |
| WABA | WhatsApp Business Account |
| WER | Word Error Rate (taux d'erreur mot) |

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Introduction générale

**Contexte.** La transformation numérique des métiers de terrain constitue aujourd'hui un enjeu majeur pour les entreprises de services techniques. Dans le domaine du câblage réseau et des infrastructures informatiques, les équipes passent leurs journées sur les chantiers, loin des outils bureautiques, et la remontée d'information vers l'encadrement reste un maillon faible : les comptes rendus d'activité sont transmis oralement, par messages dispersés ou sur papier, quand ils ne sont pas simplement omis. L'entreprise AZNET, spécialisée dans les infrastructures réseau, souhaite fiabiliser ce processus sans alourdir la charge administrative de ses techniciens, dont la langue de travail naturelle est l'arabe marocain (darija), souvent mêlé de vocabulaire technique français.

**Problématique.** Comment permettre à un technicien de chantier de produire, en moins de deux minutes et sans aucune saisie complexe, un rapport journalier structuré, exploitable par l'encadrement et archivé de manière centralisée ? La difficulté est triple : (1) le canal d'entrée doit être un outil que le technicien utilise déjà — la messagerie instantanée et la note vocale ; (2) la parole spontanée en darija, dialecte peu doté en ressources de reconnaissance vocale, doit être transcrite avec une fiabilité suffisante ; (3) le texte libre obtenu doit être transformé en données structurées normalisées sans invention d'informations.

**Objectifs.** Ce projet vise à concevoir et réaliser une chaîne de traitement complète : réception d'une note vocale ou d'une photo via une messagerie instantanée, transcription automatique du darija, extraction des données métier par grands modèles de langage, reformulation en français professionnel, tenue automatique du journal de chantier dans Google Sheets et notification de l'encadrement. Les choix de moteurs d'intelligence artificielle doivent être justifiés par un banc d'essai comparatif, et l'ensemble doit être réalisé sous une contrainte forte : un budget nul, en s'appuyant exclusivement sur les offres gratuites des fournisseurs.

**Méthodologie.** Le projet est conduit selon une démarche agile de type Scrum allégé : des sprints de deux semaines, précédés d'une phase de cadrage et de neutralisation des risques d'intégration, avec démonstration à l'encadrant à chaque itération. L'architecture retenue est hybride : une plateforme d'orchestration low-code (n8n) pour les intégrations, et un microservice développé sur mesure (Python/FastAPI) pour le cœur algorithmique.

**Organisation du rapport.** Ce rapport s'articule en quatre chapitres. Le chapitre 1 présente l'organisme d'accueil, l'étude de l'existant, la problématique, l'analyse des besoins et la démarche de conduite du projet. Le chapitre 2 dresse un état de l'art de la reconnaissance vocale de l'arabe dialectal et de l'extraction structurée par grands modèles de langage, puis justifie les choix technologiques. Le chapitre 3 détaille la conception de la solution : architecture générale, modèle de données, conception du service d'intelligence artificielle, du workflow d'orchestration et du tableau de bord. Le chapitre 4 décrit la réalisation, le banc d'essai, les tests et les résultats obtenus. Une conclusion générale synthétise les contributions et ouvre les perspectives d'évolution.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Chapitre 1 : Contexte général du projet

## 1.1 Introduction du chapitre

Ce premier chapitre situe le projet dans son environnement. Il présente l'entreprise d'accueil, analyse le processus existant de remontée d'information et ses limites, formule la problématique, délimite le périmètre fonctionnel à partir du cahier des charges, puis décrit la méthodologie de conduite du projet et la gestion des risques.

## 1.2 Présentation de l'organisme d'accueil

AZNET est une entreprise marocaine spécialisée dans les infrastructures réseau et le câblage informatique : pose de goulottes, tirage et raccordement de câbles cuivre et fibre optique, équipement de bureaux, de panneaux de brassage et de locaux techniques pour des clients professionnels. [À COMPLÉTER : fiche d'identité de l'entreprise — date de création, effectif, organigramme, références clients — à valider avec l'encadrant industriel.]

Les équipes de techniciens interviennent quotidiennement sur plusieurs chantiers simultanés. Le suivi de l'avancement — quantités posées, zones terminées, incidents, besoins en matériel — conditionne directement la facturation, la planification et l'approvisionnement.

## 1.3 Étude de l'existant

### 1.3.1 Processus actuel

En fin de journée, chaque technicien rend compte de son activité de manière informelle : appel téléphonique au chef de chantier, message vocal ou textuel sur une messagerie personnelle, ou note manuscrite. Ces informations sont ensuite ressaisies — partiellement — par l'encadrement dans un fichier de suivi Excel, le *Tableau de Suivi projet*, organisé en un onglet par chantier.

### 1.3.2 Limites identifiées

Ce processus présente plusieurs faiblesses structurelles :

- **Hétérogénéité** : chaque technicien rapporte à sa manière ; les quantités sont parfois absentes ou approximatives.
- **Perte d'information** : les messages vocaux dispersés ne sont ni archivés ni centralisés ; l'historique d'un chantier est difficile à reconstituer.
- **Double saisie** : l'encadrement retranscrit manuellement les informations, tâche chronophage et source d'erreurs.
- **Latence** : les responsables ne disposent pas d'une vue consolidée le jour même.
- **Barrière linguistique de l'écrit** : la rédaction d'un rapport écrit en français représente un effort important pour des techniciens dont la langue de travail orale est la darija ; l'oral est le canal naturel.

### 1.3.3 Contrainte clé : l'expression orale en darija

Le point central de l'étude de l'existant est que la note vocale en arabe marocain — mêlée de termes techniques français (« goulotte », « panneau de brassage », « câble », « fibre ») — est déjà le mode de communication spontané des équipes. Toute solution imposant une saisie structurée à la source serait rejetée par l'usage. La solution doit donc s'adapter au technicien, et non l'inverse.

## 1.4 Problématique

La problématique se formule ainsi : comment transformer automatiquement une note vocale spontanée en darija en un rapport journalier structuré, fiable et exploitable, en moins de deux minutes d'effort pour le technicien et sans budget logiciel ?

Elle se décompose en trois verrous techniques :

1. **Transcription** : les moteurs de reconnaissance vocale sont majoritairement entraînés sur l'arabe standard moderne ; le darija est une langue peu dotée, au code-switching arabe/français fréquent.
2. **Structuration** : le texte transcrit est du langage libre ; il faut en extraire des champs normalisés — quantités numériques, localisations, observations — sans inventer de données absentes.
3. **Intégration** : la chaîne complète (messagerie, téléchargement du média, traitement IA, journal de chantier, notifications) doit fonctionner de bout en bout de manière fiable et gratuite.

## 1.5 Analyse des besoins

### 1.5.1 Besoins fonctionnels

Le cahier des charges fourni par l'entreprise (Annexe A) définit les exigences suivantes :

- **BF1 — Saisie vocale (prioritaire)** : le technicien envoie une note vocale en darija via une messagerie instantanée ; aucune autre action ne lui est demandée.
- **BF2 — Saisie alternative** : un second canal alimente le même traitement.
- **BF3 — Transcription automatique** de l'audio en texte, avec prise en charge du darija et du mélange arabe/français.
- **BF4 — Extraction automatique** des travaux réalisés et des quantités.
- **BF5 — Reformulation** du rapport en français professionnel.
- **BF6 — Enregistrement** de chaque rapport dans un tableau de suivi Google Sheets structuré.
- **BF7 — Notification automatique** du chef de chantier et du responsable technique.
- **BF8 — Confirmation** au technicien que son rapport a bien été traité.

### 1.5.2 Besoins non fonctionnels

- **BNF1 — Simplicité d'usage** : temps de soumission inférieur à deux minutes.
- **BNF2 — Coût nul** : uniquement des offres gratuites ; volumétrie faible (5 à 10 rapports/jour) compatible avec les quotas gratuits.
- **BNF3 — Fiabilité** : aucune donnée inventée — tout champ absent de l'audio doit rester vide ; les transcriptions douteuses doivent être signalées plutôt que silencieusement acceptées.
- **BNF4 — Latence** : traitement de bout en bout visé sous 60 secondes.
- **BNF5 — Évolutivité** : moteurs d'IA interchangeables ; migration possible vers une base de données.
- **BNF6 — Sécurité** : secrets hors du code source ; validation stricte des entrées.

### 1.5.3 Priorisation MoSCoW

::: {custom-style="TableCaption"}
**Tableau 1.1 :** Priorisation MoSCoW du périmètre fonctionnel.
:::

| Priorité | Périmètre |
|---|---|
| **Must** | Chaîne vocale complète (réception → transcription → extraction → résumé français → Sheets → notification) ; documentation d'installation ; guide utilisateur |
| **Should** | Tableau de bord de consultation ; chapitre de benchmark STT ; réponse de confirmation au technicien ; signalement des transcriptions douteuses |
| **Could** | Second canal de réception ; deuxième vague de benchmark sur enregistrements réels ; document de migration base de données |
| **Won't (ce PFE)** | Application de bureau ; multi-entreprises |


Le périmètre effectivement livré dépasse cette priorisation sur trois points, documentés au chapitre 4 : le second canal de réception (WhatsApp Cloud API) est en service et non resté en « Could » ; la base de données PostgreSQL a été introduite en complément de Google Sheets et non reportée ; et le tableau de bord a dépassé la consultation pour devenir l'outil d'administration du système (organigramme, comptes, ordonnanceur, journaux).

## 1.6 Conduite du projet

### 1.6.1 Méthodologie : Scrum allégé

Le projet étant mené par un développeur unique avec un encadrant industriel jouant le rôle de *product owner*, une méthode Scrum complète serait artificielle. Une déclinaison allégée est adoptée : backlog priorisé, sprints de deux semaines, démonstration à l'encadrant en fin de sprint, rétrospective individuelle. Cette approche conserve les bénéfices essentiels — itérations courtes, feedback régulier, priorisation explicite — sans le cérémonial d'équipe.

Le dépôt Git compte **220 commits** entre le 15 juillet 2026 (`feat: week 0 scaffold`) et la date de rédaction, en convention *Conventional Commits*, ce qui fournit une trace fine et vérifiable de l'avancement.

### 1.6.2 Planification

::: {custom-style="TableCaption"}
**Tableau 1.2 :** Planning prévisionnel du projet.
:::

| Phase | Période | Objectifs principaux |
|---|---|---|
| Semaine 0 — Cadrage et neutralisation des risques | 15 – 19 juillet | Création des comptes, squelette du dépôt, test de bout en bout du maillon le plus risqué, constitution du jeu de test |
| Sprint 1 — Cœur IA et benchmark | 20 juillet – 1er août | Service FastAPI, interface d'adaptateurs STT, banc d'essai comparatif, extraction structurée et tests unitaires |
| Sprint 2 — Chaîne complète et application Web | 3 – 14 août | Workflow n8n complet, observabilité PostgreSQL, tableau de bord, gestion des cas d'échec |
| Sprint 3 — Pilote, documentation, rapport | 17 – 28 août | Déploiement pilote, livrables documentaires, rédaction finale, présentation |
| Tampon | 28 – 31 août | Finitions, répétition de la soutenance |


### 1.6.3 Gestion des risques

::: {custom-style="TableCaption"}
**Tableau 1.3 :** Registre des risques principaux.
:::

| Risque | Impact | Mitigation |
|---|---|---|
| Taux d'erreur de transcription du darija trop élevé sur tous les moteurs | Fort | Banc d'essai sur 13 moteurs ; le modèle de langage corrige le bruit grâce au vocabulaire métier ; confirmation du résumé au technicien |
| Friction d'accès au canal de réception (politique de la plateforme) | Fort | Conception indépendante du canal ; Telegram d'abord, WhatsApp ensuite une fois les contraintes Meta levées |
| Quotas des offres gratuites | Moyen | Volumétrie très faible ; chaîne de repli alternant les fournisseurs, qui mesurent leurs quotas séparément ; moteur local sur GPU en dernier recours |
| Panne d'un service externe (Google Sheets, fournisseur LLM) | Moyen | File de reprise persistante en base ; journal d'événements en PostgreSQL, délibérément hors du Sheet |
| Glissement de planning (développeur seul) | Moyen | Ordre de coupe explicite ; le cœur du périmètre *Must* est protégé |


## 1.7 Conclusion du chapitre

Ce chapitre a établi le cadre du projet : un besoin métier réel — fiabiliser la remontée d'information des chantiers — contraint par l'usage (l'oral en darija), par le budget (offres gratuites uniquement) et par le calendrier. Le chapitre suivant examine l'état de l'art des deux verrous scientifiques du projet, la transcription du darija et l'extraction structurée par grands modèles de langage, et en déduit les choix technologiques.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Chapitre 2 : État de l'art et étude technique

## 2.1 Introduction du chapitre

Ce chapitre passe en revue les fondements techniques du projet. Il examine d'abord la reconnaissance vocale de l'arabe dialectal marocain, puis l'extraction d'information structurée par grands modèles de langage. Il compare ensuite les plateformes d'orchestration et les canaux de messagerie envisageables, avant de synthétiser et de justifier les choix technologiques retenus.

## 2.2 Reconnaissance vocale de l'arabe dialectal

### 2.2.1 Le darija, une langue peu dotée

L'arabe marocain (darija) est la langue vernaculaire du Maroc. Il diffère sensiblement de l'arabe standard moderne (MSA) sur les plans phonologique, lexical et syntaxique, et se caractérise sur les chantiers par un code-switching permanent avec le français : les termes techniques — « goulotte », « câble », « panneau de brassage », « fibre », « vérifier » — sont empruntés tels quels. Or les corpus d'entraînement des systèmes de reconnaissance vocale arabes sont dominés par le MSA ; le darija appartient à la catégorie des langues dites *low-resource*, pour lesquelles les données annotées sont rares [1].

Une conséquence pratique, centrale pour ce projet, mérite d'être posée dès maintenant : l'écriture du darija n'est pas normalisée. Un même énoncé peut être transcrit en caractères arabes ou en caractères latins (*arabizi*), et les chiffres peuvent apparaître en chiffres arabes, en chiffres indo-arabes ou en toutes lettres (`ربعين` pour 40). Cette variabilité rend le WER, qui compare des chaînes de mots, particulièrement peu représentatif de la valeur métier réelle — point sur lequel le chapitre 4 revient longuement.

### 2.2.2 Les modèles de bout en bout : Whisper

L'approche dominante actuelle est le modèle de bout en bout entraîné par supervision massive et faiblement supervisée. Whisper, publié par OpenAI, est entraîné sur 680 000 heures d'audio multilingue et constitue la référence ouverte en robustesse multilingue [1]. Sa déclinaison `large-v3` prend en charge l'arabe ; ses performances sur les dialectes restent toutefois inférieures à celles obtenues sur le MSA, avec une tendance documentée à « normaliser » le dialecte vers l'arabe standard. Point favorable au cas d'usage : les emprunts français du vocabulaire du câblage sont souvent bien reconnus, précisément parce qu'ils appartiennent à une langue richement dotée.

Whisper est accessible gratuitement à travers plusieurs fournisseurs d'inférence ; Groq propose une API à très faible latence exposant `whisper-large-v3` avec une offre gratuite adaptée à une volumétrie de prototype [2].

### 2.2.3 L'architecture concurrente : wav2vec2 et la classification temporelle connexionniste

Une seconde famille d'architectures a été retenue pour le banc d'essai : wav2vec2, modèle auto-supervisé suivi d'une tête CTC (*Connectionist Temporal Classification*). Contrairement à Whisper, qui est un modèle génératif encodeur-décodeur, wav2vec2-CTC émet une distribution par trame acoustique sans modèle de langage interne. Deux conséquences pour ce projet :

- **Il ne peut pas boucler.** Les répétitions dégénérées observées sur les modèles génératifs (§4) sont structurellement impossibles en CTC.
- **Sa mesure de confiance n'est pas comparable à celle de Whisper.** La confiance CTC est une moyenne de *softmax* sur les trames émises ; celle de Whisper est `exp(mean token logprob)`. Les deux vivent dans l'intervalle [0, 1] et mesurent des quantités différentes. Ce piège s'est matérialisé lors du benchmark et est analysé au chapitre 4.

### 2.2.4 Modèles affinés sur le darija

La communauté Hugging Face publie des affinages (*fine-tunes*) de Whisper et de wav2vec2 sur des corpus marocains. Leur qualité est variable et leur documentation souvent minimale. Le projet en a recensé et téléchargé onze, auxquels s'ajoutent deux contrôles non affinés — les modèles OpenAI d'origine —, sans lesquels aucune conclusion sur l'apport de l'affinage ne serait possible. Ce point de méthode s'est révélé décisif : sans les contrôles, un affinage de qualité moyenne aurait été couronné vainqueur.

### 2.2.5 Métriques d'évaluation

La qualité de transcription se mesure classiquement par le **WER** (*Word Error Rate*), proportion de mots insérés, supprimés ou substitués par rapport à une transcription de référence, et par le **CER** (*Character Error Rate*), plus tolérant aux variations orthographiques.

Ce projet a délibérément retenu une **métrique applicative** à la place : la préservation des champs métier — quantités numériques et emprunts techniques français. La justification est développée en §4.5.3, mais son principe tient en une phrase : le tableau de suivi ne consomme ni des mots ni des caractères, il consomme des nombres et des noms de lieux ; un moteur qui écrit `ربعين` là où la référence dit « 40 » est pénalisé par le WER alors qu'il fournit exactement l'information dont le système a besoin, et un moteur qui écrit une phrase fluide en perdant la quantité est récompensé par le WER alors qu'il produit une ligne vide dans le journal.

## 2.3 Extraction d'information structurée par grands modèles de langage

### 2.3.1 De l'extraction classique aux LLM

L'extraction d'information — entités, quantités, relations — reposait classiquement sur des règles ou des modèles supervisés spécifiques. Les grands modèles de langage ont déplacé ce paradigme : un modèle génératif correctement instruit extrait des champs arbitraires d'un texte libre sans entraînement dédié, y compris depuis un texte bruité — capacité déterminante ici, puisque la transcription du darija est imparfaite par nature. Le LLM joue alors un double rôle : extracteur de données et correcteur implicite du bruit de transcription, guidé par le vocabulaire métier fourni dans l'instruction.

### 2.3.2 Sorties structurées et fiabilité

Le risque principal des LLM est l'hallucination : produire une donnée plausible mais absente de la source. Deux mécanismes le contiennent :

- **La sortie structurée contrainte** : les API récentes permettent d'imposer un schéma JSON au modèle (*structured output* de Gemini [3], mode JSON de Groq [2]), garantissant la forme de la réponse.
- **La validation applicative** : côté service, chaque réponse est validée par un schéma Pydantic strict (types, bornes, énumérations) ; l'instruction impose la valeur nulle pour tout champ non mentionné, et la politique du projet interdit toute valeur inventée par défaut.

Ce projet ajoute un troisième mécanisme, propre à son domaine et décrit au chapitre 3 : une valeur de localisation non reconnue **lève une erreur** au lieu d'être ignorée, afin que la chaîne de repli réessaie plutôt que d'écrire un étage inventé.

### 2.3.3 Modèles candidats

Sous contrainte d'offre gratuite, deux fournisseurs se distinguent : **Gemini** (Google AI Studio), doté d'une sortie structurée native et d'une forte qualité rédactionnelle en français pour la reformulation, et **Groq**, qui sert des modèles ouverts en mode JSON avec une latence très faible. Plutôt que d'en choisir un seul, le projet les organise en **chaîne de repli** alternant délibérément les fournisseurs — Gemini et Groq mesurant leurs quotas gratuits séparément, l'alternance double la capacité effective — la défaillance de tous étant remontée comme une erreur explicite plutôt que masquée.

## 2.4 Plateformes d'orchestration

Le cahier des charges recommande n8n comme outil d'automatisation. L'étude comparative confirme ce choix :

::: {custom-style="TableCaption"}
**Tableau 2.1 :** Comparaison des solutions d'orchestration.
:::

| Critère | n8n | Zapier / Make | Code sur mesure |
|---|---|---|---|
| Coût | Gratuit (auto-hébergé, licence fair-code) | Quotas gratuits restrictifs | Gratuit |
| Hébergement | Docker local ou serveur | SaaS uniquement | Au choix |
| Intégrations (messageries, Sheets, e-mail) | Natives | Natives | À développer |
| Logique personnalisée | Nœuds de code JavaScript | Limitée | Totale |
| Valeur pédagogique / maintenance | Workflows visuels documentables | Boîte noire | Coût de maintenance élevé |


n8n auto-hébergé en Docker combine gratuité, intégrations prêtes à l'emploi et possibilité d'insérer du code JavaScript. Le choix architectural du projet — détaillé au chapitre 3 — est toutefois **hybride** : n8n orchestre les intégrations, mais le cœur métier est un microservice codé sur mesure, testable et versionné.

Le chapitre 4 documente la limite pratique qui a fixé la frontière entre les deux : une logique qui exige un *read-modify-write* — lire la ligne du jour, y fusionner de nouvelles quantités, réconcilier un stock — n'est pas exprimable dans un nœud conditionnel. C'est cette contrainte, et non une préférence esthétique, qui a fait migrer l'écriture du journal de n8n vers le service Python.

## 2.5 Canal de réception : étude comparative

Le cahier des charges cite WhatsApp Business API « ou passerelle équivalente ». L'étude pratique des deux principaux candidats a structuré le calendrier du projet :

::: {custom-style="TableCaption"}
**Tableau 2.2 :** Comparaison des canaux de réception.
:::

| Critère | WhatsApp Cloud API (Meta) | Telegram Bot API |
|---|---|---|
| Processus d'accès | Compte développeur Meta, application publiée, validation d'entreprise | Création d'un bot en une minute (BotFather) |
| Jeton d'accès | Expire toutes les 24 h en mode test ; permanent via un *System User* | Permanent |
| Destinataires (mode test) | Liste blanche limitée à 5 numéros | Illimité |
| Réception des messages | Webhook obligatoire (URL publique HTTPS + poignée de main de vérification) | Webhook **ou** interrogation périodique (long polling) |
| Coût | Gratuit en test, conversations facturées en production | Gratuit |
| Adoption par le public cible | Très forte au Maroc | Moyenne |


**Décision et évolution.** Telegram a été retenu en premier pour le développement, précisément parce qu'il n'impose aucune approbation et autorise le *polling* — donc aucune exposition publique du poste de développement. WhatsApp, indispensable à terme du fait de son adoption au Maroc, a été mis en service dans un second temps une fois les obstacles Meta levés (jeton *System User* sans expiration, application publiée, souscription `subscribed_apps` du WABA). **Les deux canaux sont aujourd'hui en production simultanément**, servis par un seul workflow et un seul service.

Cette asymétrie a une conséquence de diagnostic qu'il faut garder à l'esprit : Telegram *interroge* (connexions sortantes, aucun tunnel nécessaire) tandis que WhatsApp est *poussé* par webhook et exige une URL publique HTTPS. Par conséquent, « Telegram répond une erreur mais WhatsApp reste muet » ne décrit pas une panne mais deux : une réponse d'erreur prouve que le message a atteint la chaîne ; le silence prouve qu'il n'y est jamais arrivé.


## 2.6 Étude comparative des solutions existantes

Avant de concevoir un système, il faut justifier de ne pas en acheter un. Trois familles de produits couvrent partiellement ce besoin.

**Les applications de suivi de chantier** — Procore, Fieldwire, Kizeo Forms — proposent des formulaires mobiles, des photos géolocalisées et des tableaux de bord. Elles échouent sur deux points décisifs ici. D'une part, le prix : toutes sont facturées par utilisateur et par mois, ce qui est incompatible avec la contrainte de budget nul. D'autre part, et c'est plus fondamental, **elles imposent une saisie structurée à la source** : le technicien doit ouvrir une application, choisir un chantier dans une liste et remplir des champs. L'étude de l'existant (§1.3.3) a montré que c'est précisément ce qui serait rejeté par l'usage. Aucune n'accepte une note vocale en darija comme entrée principale.

**Les plateformes d'automatisation avec IA managée** — Microsoft Power Automate couplé à Azure Speech, ou Zapier couplé à OpenAI. Techniquement viables et rapides à assembler, elles sont écartées pour trois raisons : le coût à l'usage dès la sortie des quotas d'essai ; l'absence de prise en charge sérieuse du darija dans les services de transcription généralistes, qui est le cœur du problème ; et une logique métier enfermée dans une interface propriétaire, non versionnée et non testable — inacceptable pour un travail d'ingénierie qui doit être défendu et repris.

**Les assistants de transcription généralistes** — Otter, Notta, ou l'envoi manuel à un modèle de langage. Ils transcrivent, mais ne structurent pas, n'écrivent pas dans le tableau de suivi, ne notifient personne et ne connaissent pas le vocabulaire du câblage. Ils résolvent un cinquième du problème.

::: {custom-style="TableCaption"}
**Tableau 2.3 :** Positionnement face aux solutions existantes.
:::

| Critère | Applications de chantier | Automatisation + IA managée | Assistants de transcription | **Ce projet** |
|---|---|---|---|---|
| Coût | Par utilisateur / mois | À l'usage | Abonnement | **Nul** |
| Entrée en darija | Non | Faible | Partielle | **Oui, moteur dédié** |
| Effort du technicien | Formulaire à remplir | Formulaire à remplir | Envoi manuel | **Une note vocale** |
| Extraction structurée métier | Oui, par formulaire | À construire | Non | **Oui, par LLM** |
| Écriture dans le fichier du client | Export | Oui | Non | **Oui, fusion par chantier** |
| Logique versionnée et testée | Non | Non | — | **Oui, 272 tests** |


La conclusion n'est pas que ces produits sont mauvais, mais que le besoin d'AZNET a une contrainte que le marché ne traite pas : **l'entrée doit être de la parole spontanée en langue peu dotée**, et tout le reste en découle.

## 2.7 Technologies et langages retenus

### 2.7.1 Vue d'ensemble

::: {custom-style="TableCaption"}
**Tableau 2.4 :** Technologies retenues et alternatives écartées.
:::

| Technologie | Rôle dans le projet | Principales alternatives | Raison du choix |
|---|---|---|---|
| **Python 3.11** | Service applicatif, banc d'essai | Node.js, Go, Java | Écosystème IA/ML sans équivalent ; toutes les bibliothèques de modèles sont d'abord publiées en Python |
| **FastAPI** | Framework HTTP | Django, Flask | Validation et documentation dérivées des types ; asynchrone natif |
| **Pydantic** | Contrat de données | dataclasses, marshmallow | La validation *est* le garde-fou anti-hallucination du projet |
| **TypeScript** | Tableau de bord | JavaScript | Le contrat d'API change souvent ; le typage transforme une rupture en erreur de compilation |
| **React 19** | Interface | Vue, Svelte, Angular | Standard industriel, écosystème et employabilité |
| **Vite** | Outil de construction | webpack, Next.js | Démarrage quasi instantané ; aucun besoin de rendu serveur |
| **Tailwind CSS v4** | Style | CSS modules, styled-components, shadcn/ui | Couche de jetons entièrement en CSS, sans fichier de configuration JavaScript |
| **PostgreSQL 16** | Stockage technique | SQLite, MongoDB | Accès concurrents réels (API, ordonnanceur, n8n) ; JSON natif |
| **Google Sheets** | Registre métier | Base de données seule | **Imposé par l'usage** : c'est le fichier que le directeur ouvre déjà |
| **n8n** | Orchestration | Zapier, Make, code | Auto-hébergeable et gratuit ; intégrations natives (voir §2.4) |
| **Docker Compose** | Déploiement | Installation manuelle, Kubernetes | Cinq services reproductibles ; Kubernetes serait disproportionné pour une machine |
| **PyTorch + Transformers** | Banc d'essai local | ONNX Runtime, llama.cpp | Seul écosystème où les treize points de contrôle évalués sont publiés |
| **Playwright** | Contrôle visuel | Selenium, Cypress | Capture multi-navigateur scriptable ; sert aussi à produire les captures de ce rapport |
| **pytest** | Tests | unittest | Fixtures et paramétrage ; 272 tests sans aucune clé d'API |
| **GitHub Actions** | Intégration continue | GitLab CI, Jenkins | Gratuit sur dépôt privé ; au plus près du dépôt |
| **Mermaid** | Diagrammes | draw.io, Visio | Diagrammes en texte, donc versionnés et révisables comme du code |


### 2.7.2 Les choix qui méritaient un débat

Quatre décisions n'allaient pas de soi et ont été tranchées sur des critères vérifiables.

**FastAPI plutôt que Django ou Flask.** Django apporte un ORM, une administration et une authentification — l'essentiel de ce qu'il offre est inutile ici, puisque le registre métier est un classeur Google et non une base relationnelle. Flask est minimal mais n'a ni validation ni documentation automatique. FastAPI dérive la validation, la documentation OpenAPI et le contrat d'erreurs **des annotations de type déjà écrites**, ce qui compte doublement dans un système dont la règle principale est « aucune donnée inventée » : le schéma qui documente est le schéma qui valide.

**PostgreSQL plutôt que SQLite.** SQLite aurait suffi au volume — quelques dizaines de lignes par jour. Il a été écarté sur la concurrence, non sur la taille : trois processus écrivent simultanément — l'API sur le chemin de réponse, l'ordonnanceur en arrière-plan, n8n à chaque étape — et le verrouillage de fichier de SQLite transforme cela en attentes sur le chemin où un technicien attend une réponse.

**Tailwind v4 sans bibliothèque de composants.** shadcn/ui aurait fait gagner des semaines. Il a été écarté parce que ce tableau de bord a une identité visuelle propre, décrite dans un document de conception, et qu'adopter une bibliothèque revient à hériter de ses décisions esthétiques puis à lutter contre elles. Les graphiques sont en SVG et CSS écrits à la main, pour la même raison — et cela évite une dépendance de plus de 400 Ko pour quatre visualisations.

**Le darija en local plutôt qu'une API.** C'est le choix le plus coûteux du projet : 7,7 s de latence contre 1,53 s, environ 4 Go de mémoire graphique, et une machine à maintenir. Il est justifié au chapitre 4 par la seule chose qui compte ici — la préservation des quantités et des emprunts techniques français — et il a été confirmé à l'oreille par un locuteur natif avant d'être adopté.


## 2.8 Synthèse des choix technologiques

::: {custom-style="TableCaption"}
**Tableau 2.5 :** Récapitulatif des choix technologiques.
:::

| Besoin | Choix | Justification résumée |
|---|---|---|
| Canal de réception | Telegram Bot API **et** WhatsApp Cloud API | Gratuit et sans approbation pour le premier ; adoption réelle du public cible pour le second |
| Orchestration | n8n (Docker, auto-hébergé) | Recommandé par le cahier des charges, gratuit, intégrations natives |
| Transcription | Chaîne `gemini → local → groq` | Ordre fixé par accuracy mesurée (chapitre 4), non par latence |
| Extraction / reformulation | Chaîne de repli alternant Gemini et Groq | Sortie structurée native ; quotas gratuits mesurés séparément par fournisseur |
| Service métier | Python / FastAPI | Écosystème IA, validation Pydantic, tests, documentation OpenAPI automatique |
| Interface Web | React 19 + TypeScript + Vite + Tailwind v4 | Standard industriel ; rendu statique servi par la même origine que l'API |
| Stockage métier | Google Sheets | Imposé par le cahier des charges ; c'est le fichier que le directeur lit déjà |
| Stockage technique | PostgreSQL | Journal d'événements, idempotence, sessions, file de reprise — délibérément hors du Sheet |


## 2.9 Conclusion du chapitre

L'état de l'art confirme la faisabilité du projet sous ses contraintes : Whisper fournit une base de transcription multilingue robuste dont les limites sur le darija sont compensées en aval par l'extraction LLM ; les sorties structurées contraintes et la validation stricte contiennent le risque d'hallucination ; et l'écosystème gratuit couvre l'intégralité de la chaîne. Il a également posé deux points de méthode que le chapitre 4 exploitera : la nécessité de contrôles non affinés dans tout banc d'essai de *fine-tunes*, et l'inadéquation du WER à un système dont la valeur tient aux nombres. Le chapitre suivant traduit ces choix en une conception détaillée.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Chapitre 3 : Conception de la solution

## 3.1 Introduction du chapitre

Ce chapitre présente la conception de la solution : l'architecture générale hybride, le modèle de données qui constitue le contrat entre les composants, la conception détaillée du service applicatif (patrons de conception, chaînes de repli, contrat d'erreurs, tenue du journal), celle du workflow d'orchestration, du tableau de bord, et les dispositions de sécurité.

## 3.2 Architecture générale

### 3.2.1 Le choix d'une architecture hybride

Deux approches extrêmes étaient possibles : tout construire dans n8n — fidèle à la lettre du cahier des charges, mais logique métier enfouie dans des nœuds difficiles à tester — ou tout coder sur mesure, ce qui imposait de réécrire des intégrations que n8n fournit nativement. L'architecture retenue est **hybride** et répartit les responsabilités selon la valeur ajoutée de chaque outil :

- **n8n (orchestration)** : réception des messages Telegram et WhatsApp, vérification du webhook Meta, déduplication, téléchargement des médias, appel du service, réponses au technicien, journalisation d'étape.
- **Service applicatif (FastAPI, sur mesure)** : transcription, extraction structurée, reformulation, tenue du journal de chantier, ordonnancement des tâches périodiques, authentification, service du tableau de bord — le cœur, versionné, testé et documenté.
- **Tableau de bord (React)** : consultation, correction, administration de l'organigramme et des comptes, supervision de l'ordonnanceur et des journaux.
- **PostgreSQL** : journal d'événements, idempotence, sessions, file de reprise, organigramme, chantiers.
- **Google Sheets** : le registre métier permanent — le fichier que le directeur lit déjà.

::: {custom-style="FigureImage"}
![](diagrams/01-architecture.png){ width=14.7cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.1 :** Architecture générale : les cinq responsabilités et leurs échanges. Les deux arêtes numérotées vers le technicien et vers le journal matérialisent l'invariant réponse-d'abord (§3.5.2).
:::



### 3.2.2 Frontière entre orchestration et code

La frontière n'est pas esthétique, elle est fonctionnelle, et l'expérience du projet l'a déplacée une fois. À l'origine, l'écriture dans Google Sheets était un nœud n8n. Elle a migré dans le service Python le 5 août 2026 pour une raison précise : tenir le journal exige un *read-modify-write* — lire la ligne existante du jour, y fusionner les nouvelles quantités, réconcilier le stock — qu'un nœud conditionnel ne sait pas exprimer. La correspondance entre les champs extraits et les colonnes du Sheet, jusque-là écrite en expressions n8n non testables, est devenue du code Python couvert par des tests.

**Règle retenue :** ce qui est *intégration* reste dans n8n ; ce qui est *décision* passe dans le service.

### 3.2.3 Flux nominal

1. Le technicien envoie une note vocale, une photo ou un texte au bot, sur Telegram ou WhatsApp.
2. Le workflow n8n détecte le message, **réclame** son identifiant auprès du service (déduplication : WhatsApp re-livre un webhook non acquitté), identifie l'expéditeur dans l'organigramme et vérifie son autorisation.
3. Le média est téléchargé et transmis au service (`POST /process`, multipart).
4. Le service transcrit, extrait les champs, produit le résumé français et renvoie un JSON structuré assorti d'avertissements de qualité.
5. **n8n répond au technicien** avec son résumé.
6. **Ensuite seulement**, n8n appelle `POST /journal`, qui fusionne la ligne dans l'onglet du chantier et met à jour le miroir plat.
7. Les responsables sont notifiés.

L'ordre des étapes 5 et 6 est un invariant de conception, développé en §3.5.2.

### 3.2.4 Diagrammes UML

::: {custom-style="FigureImage"}
![](diagrams/07-usecase.png){ width=9.4cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.2 :** Diagramme de cas d'utilisation. Le système figure comme acteur à part entière : quatre cas d'usage n'ont aucun déclencheur humain.
:::



::: {custom-style="FigureImage"}
![](diagrams/02-lifecycle-voice.png){ width=16.0cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.3 :** Cycle de vie complet d'une note vocale, de l'émission à la ligne du journal, y compris la déduplication en amont et la mise en file de reprise en aval. Le cadre vert isole l'étape que rien ne doit précéder.
:::



## 3.3 Modèle de données

### 3.3.1 Le rapport structuré, contrat central

Le schéma `ExtractedReport` est le contrat entre le service, n8n et le journal. Il a été **reconstruit le 5 août 2026 à partir du fichier de suivi réel du directeur**, en remplacement d'un schéma générique initial :

::: {custom-style="TableCaption"}
**Tableau 3.1 :** Schéma du rapport extrait (`ExtractedReport`).
:::

| Champ | Type | Description |
|---|---|---|
| `cables_prepares_m` | décimal ≥ 0, optionnel | Mètres de câble cuivre préparés (tirés et mesurés) |
| `cables_installes_m` | décimal ≥ 0, optionnel | Mètres de câble cuivre installés et raccordés |
| `goulotte_m` | décimal ≥ 0, optionnel | Mètres de goulotte posés |
| `prises_connectees` | entier ≥ 0, optionnel | Prises RJ45 raccordées côté bureau |
| `panneaux_prises_brassees` | entier ≥ 0, optionnel | Prises raccordées côté panneau de brassage |
| `prises_testees` | entier ≥ 0, optionnel | Prises testées et étiquetées |
| `fibre_m` | décimal ≥ 0, optionnel | Mètres de câble fibre optique posés |
| `interconnexions` | entier ≥ 0, optionnel | Interconnexions installées entre locaux |
| `connexions_optiques_brins` | entier ≥ 0, optionnel | Brins de fibre fusionnés ou connectés |
| `etages` | liste énumérée, optionnel | RDC, E1 à E4 |
| `ailes` | liste énumérée, optionnel | Droite, Gauche |
| `locaux_techniques` | liste énumérée, optionnel | RG, SR1 à SR10 |
| `stock_cable_m` | décimal ≥ 0, optionnel | Câble restant en stock sur site |
| `stock_goulotte_m` | décimal ≥ 0, optionnel | Goulotte restante en stock |
| `stock_fibre_m` | décimal ≥ 0, optionnel | Fibre restante en stock |
| `remarques` | texte, optionnel | Problèmes, blocages, matériel manquant |
| `resume` | texte, **obligatoire** | Résumé professionnel en français (2 à 4 phrases) |


Trois décisions de modélisation méritent d'être justifiées.

**Trois compteurs de prises, pas un.** La même prise physique est comptée trois fois dans le fichier du directeur, à trois stades différents ; une seule journée peut légitimement rapporter « 14 côté bureaux, 17 côté panneau, 15 testées ». Fusionner ces compteurs perdrait l'information d'avancement qui les rend utiles.

**`chantier` n'est délibérément pas un champ du modèle.** Le routage vient de l'organigramme — un chef porte un chantier, ses techniciens en héritent — et non de ce que le modèle a cru entendre. Le chantier est estampillé sur la ligne par le service, puis figé, de sorte qu'une réaffectation ultérieure ne réécrit jamais l'histoire.

**Les colonnes de pilotage sont exclues.** Équipe, heures, jours-homme, ordre du jour et taux de réalisation sont planifiés avant la journée ou jugés après elle. Un technicien ne les dicte pas ; le chef les saisit dans le tableau de bord, et une fusion ne les touche jamais.


::: {custom-style="FigureImage"}
![](diagrams/11-report-states.png){ width=16.0cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.4 :** Cycle de vie d'un rapport, vu comme une machine à états. Les états terminaux sont volontairement nombreux : un doublon, un expéditeur non autorisé et un message sans contenu exploitable sont trois issues normales, pas trois pannes.
:::


### 3.3.2 Politique « aucune donnée inventée »

Tous les champs métier sont optionnels et valent nul par défaut. L'instruction impose explicitement la valeur nulle pour toute information absente ; la validation Pydantic rejette les valeurs hors bornes. Trois mécanismes complètent cette politique :

- **Normalisation avant typage** : les modèles en mode JSON émettent parfois la *chaîne* `"null"` ; un validateur la ramène à la valeur nulle avant le typage strict.
- **Normalisation des formes, pas des faits** : `rdc`, `1er étage`, `SR 4` sont des erreurs de forme, pas de contenu ; une table d'alias les normalise. Mais une localisation **non reconnue lève une erreur** au lieu d'être ignorée : la chaîne de repli réessaie, plutôt que d'écrire un étage inventé.
- **`has_data()`** : « salam » s'extrait parfaitement — tous les champs nuls et un `resume` poli — et un code 200 devient alors indiscernable d'un vrai rapport. `has_data()` ignore délibérément `resume`, le seul champ que le modèle remplit toujours et qui ne peut donc pas distinguer les deux cas. Il compte en revanche les remarques, la localisation et le stock : une journée sans mètres mais avec un blocage (« arrêtés 1h30 sur instruction ») **est** le rapport dont le directeur a le plus besoin.

### 3.3.3 Le modèle relationnel : une personne, plusieurs canaux

Le stockage technique repose sur PostgreSQL. Sa décision structurante date du 1er août 2026 : la table `users` a été **fusionnée dans `persons` puis supprimée**.

L'argument initial du découpage était le cycle de vie (« un technicien ne se connecte jamais »), qui est un argument sur les *identifiants de connexion*, non sur l'*identité*. Deux tables pour un même humain faisaient d'un chef qui envoie aussi des notes vocales deux lignes sans relation — donc deux cases sur l'organigramme. Le modèle retenu est :

- **`persons`** : l'humain (nom, rôle, `manager_id`, chantier, profil **et identifiants de connexion**).
- **`technicians`** : ses identités de canal (`channel`, `external_id`, `active`), plusieurs par personne.

Conséquence directe : **`password_hash IS NOT NULL` constitue à lui seul la définition d'« un compte »**. La suppression d'un compte efface les identifiants sans supprimer la ligne — un `DELETE` emporterait en cascade la personne, ses canaux et son profil.

Les autres tables sont `pipeline_logs` (journal d'étapes), `processed_messages` (idempotence), `failed_writes` (file de reprise), `sessions`, `user_actions`, `page_visits`, `service_samples` (historique de disponibilité), `app_settings`, `chantiers` et `articles`.

::: {custom-style="FigureImage"}
![](diagrams/06-er-identity.png){ width=16.0cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.5 :** Modèle relationnel. `persons` est au centre et se référence elle-même par `manager_id` : c'est l'organigramme. `password_hash IS NOT NULL` y tient lieu, à lui seul, de définition d'un compte.
:::


::: {custom-style="FigureImage"}
![](diagrams/06-er-operations.png){ width=16.0cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.6 :** Tables d'audit. Les quatre tables restantes — `pipeline_logs`, `processed_messages`, `failed_writes`, `service_samples` et `app_settings` — n'ont délibérément aucune clé étrangère : ce sont des journaux et des files, décrits en §3.3.4.
:::




### 3.3.4 Les onze tables en détail

Quatre tables portent le métier et l'organigramme ; trois tracent l'usage humain ; quatre servent la mécanique du pipeline et n'ont **délibérément aucune clé étrangère** — ce sont des journaux et des files, pas des entités liées.

**`persons` — l'humain.** Une ligne par personne, quel que soit son rôle. `role` vaut `directeur`, `chef` ou `tech` et pilote l'affichage de l'organigramme ; `manager_id` pointe un technicien vers son chef ; `chantier_id` porte l'affectation, qui n'est renseignée que sur les chefs, les techniciens en héritant. `profile` reçoit le paragraphe réécrit chaque nuit. `password_hash` est la seule chose qui distingue un compte d'une simple fiche : sa non-nullité **est** la définition d'un compte, ce qui explique que `login()` la teste explicitement, que la liste des comptes filtre dessus, et que la suppression d'un compte efface l'empreinte sans supprimer la ligne.

**`technicians` — les identités de canal.** Une ligne par couple (personne, canal). `channel` vaut `telegram` ou `whatsapp`, `external_id` est l'identifiant que la plateforme attribue, `active` permet de révoquer un accès sans effacer l'historique — la recherche d'expéditeur filtre dessus, sans quoi l'interrupteur du tableau de bord ne révoquerait rien.

**`chantiers` — les sites.** `nom` et `onglet`, ce dernier désignant l'onglet du classeur où le journal de ce site est tenu.

**`articles` — le bordereau.** Les quantités contractuelles d'un chantier. `champ` fait le lien avec un champ du schéma d'extraction ; il vaut `null` pour un article que le journal ne suit pas — un onduleur, un commutateur — et cette valeur nulle signifie « non suivi ici », jamais « rien d'installé ».

**`sessions` — les connexions.** Jetons **opaques** stockés en base, et non des jetons auto-portants : supprimer la ligne déconnecte ce navigateur à sa requête suivante, ce qu'un jeton signé ne permettrait pas sans liste de révocation.

**`user_actions` et `page_visits` — la piste d'audit.** Qui a fait quoi, et quel temps a été passé sur quelle page. Le minuteur de page vit au-dessus du routeur et transmet ses mesures à la fermeture de l'onglet.

**`pipeline_logs` — le journal d'étapes.** La colonne décisive est `correlation_id` : n8n publie une ligne par étape et le service journalise ses propres erreurs avec le même identifiant, de sorte que deux processus distincts se recomposent en une seule chronologie dans le panneau **Journaux**. Ce journal est en PostgreSQL et non dans le Sheet pour une raison précise : l'événement le plus important à consigner est « l'écriture dans le Sheet a échoué », et un journal adossé au Sheet devient aveugle pendant exactement cette panne.

**`processed_messages` — l'idempotence.** WhatsApp relivre un webhook non acquitté ; sans cette table, un message relivré produirait une seconde réponse et une seconde ligne. Le workflow « réclame » l'identifiant avant tout traitement.

**`failed_writes` — la file de reprise.** Charge utile complète et statut. Rejouée toutes les cinq minutes par le même chemin que le flux vivant, et résolue seulement lorsque Google a accepté la ligne. Une charge utile que le schéma ne sait plus lire est résolue en échec plutôt que de bloquer indéfiniment la file derrière elle.

**`service_samples` — l'historique de disponibilité.** Un échantillon par service et par intervalle, alimenté par l'échantillonneur du tableau de bord.

**`app_settings` — les réglages vivants.** Horaires des tâches, ordre des chaînes. Relus **à chaque battement** de l'ordonnanceur, de sorte qu'une heure modifiée depuis le tableau de bord prend effet sans redémarrage.

Toutes les migrations sont idempotentes et rejouées à chaque démarrage. Celle qui a fusionné les comptes est encapsulée dans un bloc conditionnel dynamique : elle lit une colonne qu'elle supprime elle-même, et PostgreSQL planifie une instruction entière avant de l'exécuter.


## 3.4 Conception du service applicatif

### 3.4.1 Interface unique

Le service expose `POST /process`, acceptant **exactement une** de trois entrées : `audio`, `image` ou `text` — toute autre combinaison est un 422. L'aiguillage par type d'entrée est fait par n8n, jamais à l'intérieur du service. Les trois modes convergent vers le même pipeline d'extraction, ce qui rend la solution indépendante du canal.

Le service compte **66 routes** et **8 489 lignes** de Python, organisées en modules : `main.py` (routes), `extraction.py`, `journal.py`, `sheets.py`, `logs.py`, `auth.py`, `jobs.py`, `memory.py`, `mailer.py`, `reply.py`, `daily_report.py`, `imagegen.py`, `prompt_loader.py`, `schemas.py`, `config.py`.

### 3.4.2 Patron Stratégie pour la transcription

Le choix du moteur étant arbitré par un banc d'essai, la conception rend les moteurs interchangeables. Le patron **Stratégie** est appliqué : une classe abstraite `TranscriptionProvider` définit le contrat, et chaque moteur est un adaptateur concret enregistré dans un registre par un décorateur `@register("nom")`. Les adaptateurs sont importés en bas de `providers/__init__.py` pour déclencher leur enregistrement.

Trois moteurs sont implémentés : `groq` (Whisper large-v3 par API), `gemini` (modèle multimodal natif) et `local` (client HTTP vers un service GPU dédié).

::: {custom-style="FigureImage"}
![](diagrams/03-stt-chain.png){ width=11.0cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.7 :** Chaîne de transcription. L'ordre est celui de l'exactitude mesurée, non de la latence : `groq` occupe la dernière place en tant que socle rapide et toujours disponible. Aucune branche ne mène à un repli silencieux.
:::



### 3.4.3 Chaînes de repli

Le service exploite **quatre** chaînes ordonnées `fournisseur:modèle`, une par forme d'entrée : `extraction_text_chain`, `extraction_image_chain`, `image_generation_chain` et `profile_chain`, auxquelles s'ajoute la chaîne STT. Chaque chaîne est essayée de gauche à droite, retourne quel modèle a répondu, et l'échec de toutes lève une `ExtractionError` combinée détaillant chaque cause — **jamais de repli silencieux**.

La chaîne texte **alterne délibérément les fournisseurs**, Gemini et Groq mesurant leurs quotas gratuits séparément ; la chaîne image est exclusivement Google, le catalogue gratuit de Groq ne comportant aucun modèle de vision.


::: {custom-style="FigureImage"}
![](diagrams/04-extraction-chains.png){ width=10.1cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.8 :** Les quatre chaînes de repli d'extraction. Une localisation non reconnue ne provoque pas un abandon mais une nouvelle tentative : c'est la traduction en flux de contrôle de la politique « aucune donnée inventée ».
:::


### 3.4.4 Contrat d'erreurs

::: {custom-style="TableCaption"}
**Tableau 3.2 :** Contrat d'erreurs du service.
:::

| Situation | Code HTTP | Comportement attendu de n8n |
|---|---|---|
| Entrée invalide (ni audio, ni image, ni texte ; fournisseur inconnu) | 422 | Erreur de configuration à corriger |
| Défaillance d'un moteur (`TranscriptionError`, `ExtractionError`) | 502 | Marquage de la ligne en anomalie, notification |
| Échec de transport de la réponse au technicien | 502 | Distinguer une panne externe d'un défaut du service |
| Transcription anormalement courte (moins de 10 caractères) | 200 + `short_transcription` | Ligne enregistrée mais signalée |
| Message sans contenu exploitable | 200 + `no_report_content` | Réponse au technicien, **pas** d'écriture dans le journal |


La distinction 422/502 sépare les erreurs de l'appelant des défaillances des moteurs externes ; l'avertissement plutôt que l'erreur illustre le principe : un signal de qualité douteuse est un avertissement structuré, ni une erreur bloquante ni un silence.

### 3.4.5 Les instructions comme contenu versionné

Les instructions destinées aux modèles vivent dans `api/app/prompts/` en **Markdown versionné**, non en littéraux Python : un changement d'instruction est un changement de contenu et doit être visible en revue. Six fichiers : `00-soul.md`, `extraction-text.md`, `extraction-image.md`, `image-generation.md`, `profile.md`, `stt-vocabulary.md`.

`00-soul.md` est préfixé à toute instruction adressée à un modèle : identité, interdiction d'inventer, « absence n'est pas zéro ». Les fichiers sont lus une fois et mis en cache, ce qui impose de redémarrer le service après une modification — propriété voulue : une instruction qui pourrait changer entre deux requêtes rendrait une mauvaise extraction impossible à reproduire.

`stt-vocabulary.md` est la seule exception et ne reçoit **pas** l'âme : Whisper interprète son paramètre `prompt` comme la transcription *précédant* le clip, et non comme des consignes ; l'âme serait recopiée dans la transcription. Le chapitre 4 montre que cette subtilité a des conséquences bien plus graves encore en local.

### 3.4.6 Le profil du technicien : un cinquième modèle

Un paragraphe en français par technicien est rédigé chaque nuit à 03:00 à partir de ses propres rapports passés, stocké dans `persons.profile` et injecté comme contexte étiqueté dans l'instruction d'extraction.

Trois décisions le rendent sûr. Il n'existe **aucune table de faits mémorisés** : le Sheet est déjà le registre permanent, et un second magasin qui en dériverait serait un cache sans chemin critique pour le justifier. Il ne s'exécute **jamais sur le chemin de réponse** : un technicien qui attend son résumé ne doit pas en plus attendre qu'on range son profil. Enfin, l'instruction **interdit les nombres** et le bloc d'injection présente le texte comme informatif et prohibé comme source de valeurs — sans quoi « intervient surtout sur Sidi Maarouf » est à un pas de remplir `chantier` sur un message qui n'a jamais nommé de site.

### 3.4.7 Le journal de chantier

`journal.py` tient **une ligne par (date, technicien)** dans l'onglet du chantier concerné, à l'image du fichier du directeur. Deux règles en assurent la justesse.

**Accumulation.** Un second message le même jour est **fusionné** dans la ligne existante : les nombres s'additionnent, les localisations s'unissent, la prose s'ajoute, le stock est remplacé. Une seconde ligne doublerait les jours-homme et fausserait la ligne de totaux — le seul chiffre que le directeur lit vraiment. Les colonnes de pilotage ne sont jamais touchées par une fusion.

**Réconciliation de stock.** La valeur de référence est *dernier stock connu moins quantité installée* ; un chiffre rapporté par le technicien l'emporte toujours et devient la nouvelle référence ; un écart émet un avertissement `stock_ecart` chiffré **au lieu de choisir silencieusement** — car une livraison et une perte sont arithmétiquement identiques, et seul un humain peut les distinguer.

Les dates sont normalisées, le même jour arrivant tantôt au format ISO, tantôt en `05/08/2026`, tantôt sous forme de numéro de série `46174` ; une date illisible provoque un **ajout** (visible) plutôt qu'une fusion dans la mauvaise ligne (invisible).


::: {custom-style="FigureImage"}
![](diagrams/05-journal-merge.png){ width=13.3cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.9 :** Tenue du journal : accumulation intra-journalière et réconciliation de stock. Les deux encadrés orangés sont les cas où le système préfère un signal visible à une décision silencieuse.
:::


### 3.4.8 Les tâches planifiées

`jobs.py` implémente un ordonnanceur : un fil d'exécution, un battement de 30 s, **six tâches** — vidange de la file de reprise (5 min), purge des journaux (03:00), reconstruction des profils (03:00), rappels, rapport quotidien par e-mail (lundi-samedi) et rapport hebdomadaire. Chacune dispose d'un budget de temps propre, dimensionné sur son coût réel : 600 s pour les rapports, qui enchaînent une lecture du Sheet, un envoi SMTP et un appel de modèle **par chef de chantier**.

Ces tâches étaient des nœuds *cron* n8n ; elles ont migré dans le service parce qu'un nœud cron ne peut ni montrer à un opérateur ce qu'il a produit, ni lui permettre de forcer une réexécution — ce que la page **Automatisation** du tableau de bord fait.

Un invariant : **une tâche ne remonte jamais d'exception dans la boucle**. Les échecs sont enregistrés comme résultats, car un fil qui meurt à 03:00 emporte les quatre autres et personne ne s'en aperçoit avant de trouver le Sheet vide.


::: {custom-style="FigureImage"}
![](diagrams/09-scheduler.png){ width=16.0cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.10 :** Ordonnanceur : six tâches, un fil unique, et une réclamation atomique du droit d'enregistrer le résultat — sans laquelle une tâche terminée juste au seuil du délai inscrivait deux issues contradictoires pour une même exécution.
:::


## 3.5 Conception du workflow d'orchestration

### 3.5.1 Structure

Le workflow unique compte **65 nœuds** couvrant : le déclencheur périodique Telegram et son *offset* persistant ; le webhook WhatsApp et sa poignée de main de vérification ; la corrélation et la déduplication ; l'identification de l'expéditeur et le contrôle d'autorisation ; l'accusé de réception ; l'aiguillage média/texte puis audio/image ; les appels `/process` ; les réponses de résumé, d'erreur et de refus ; les commandes `/rapport`, `/modifier` et `/supprimer` ; l'appel `/journal` ; la journalisation de chaque étape ; et un déclencheur d'erreur.

::: {custom-style="FigureImage"}
![](diagrams/08-n8n-reception.png){ width=10.5cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.11 :** Workflow d'orchestration : les 65 nœuds regroupés par fonction. Les deux déclencheurs de gauche correspondent aux deux modes de réception opposés — interrogation sortante pour Telegram, webhook entrant pour WhatsApp.
:::


::: {custom-style="FigureImage"}
![](diagrams/08-n8n-traitement.png){ width=11.5cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.12 :** Workflow, seconde moitié : aiguillage, traitement, réponse au technicien puis journal. Le nœud encadré en vert est celui que rien ne doit précéder.
:::



Le gestionnaire d'erreurs est resté dans n8n alors que les tâches planifiées en sont sorties, pour une raison précise : il intercepte les défaillances **du workflow lui-même**, que le service ne peut pas observer.

### 3.5.2 L'ordre réponse-d'abord

Dans le workflow, la réponse au technicien précède l'appel `/journal`. Ce n'est pas un détail d'agencement mais un invariant : une écriture Sheets en échec se gare dans la file de reprise, est rejouée toutes les 5 minutes par le même chemin que le flux vivant, et n'est résolue que lorsque Google a effectivement accepté la ligne. **Elle ne coûte jamais au technicien son résumé.**

Le nœud qui vérifie qu'un message est exploitable est placé **après** le nœud de réponse, pour la même raison : un « salam » mérite une réponse, mais pas une ligne de blancs dans le journal.


### 3.5.3 Les 65 nœuds, groupe par groupe

Le workflow se lit en sept bandes. Le détail ci-dessous explique ce que chacune fait et, lorsque c'est le cas, pourquoi elle existe sous cette forme plutôt qu'une autre.

**Bande 1 — Réception (9 nœuds).** `Every 15s` déclenche la boucle Telegram ; `Offset + token` lit le dernier identifiant traité dans les données statiques du workflow et le transmet à `getUpdates`, ce qui garantit qu'un message n'est jamais retraité. Côté WhatsApp, `WA Webhook verify (GET)` et `WA Echo challenge` répondent à la poignée de main de Meta — un nœud manuel, parce que le déclencheur WhatsApp natif de n8n échoue à cette vérification — et `WA Webhook messages (POST)` reçoit les messages. `Extract TG msgs` et `Extract WA msgs` normalisent deux formats d'enveloppe très différents vers une seule forme interne, ce qui est précisément ce qui rend la suite indépendante du canal.

**Bande 2 — Déduplication (4 nœuds).** `Correlate` attribue un identifiant de corrélation qui suivra le message dans tous les journaux. `Claim message (dedup)` appelle le service, qui tente d'insérer l'identifiant dans `processed_messages` ; `Fresh ?` bifurque sur le résultat et `Log duplicate` termine silencieusement les relivraisons. C'est le seul endroit où le silence est la bonne réponse : le technicien a déjà reçu son résumé.

**Bande 3 — Identité et autorisation (4 nœuds).** `Sender` extrait l'expéditeur, `Lookup technicien` interroge l'organigramme et récupère la personne **et son chantier**, `Filtrer accès` et `Authorized ?` décident. Un expéditeur inconnu reçoit un refus explicite et `Log denied` en garde trace : un message ignoré sans réponse serait indiscernable d'une panne.

**Bande 4 — Accusé de réception (6 nœuds).** `TG ack` / `WA ack` puis leurs variantes `done` et `fail` accusent réception avant tout traitement long. Sans cela, le technicien attend jusqu'à une minute sans aucun signe que son message est arrivé.

**Bande 5 — Aiguillage et traitement (10 nœuds).** `Is /rapport?`, `Is /modify?` interceptent d'abord les commandes. Sinon `Media or text?` puis `Audio or image?` orientent vers l'un des trois appels `POST /process`. L'aiguillage est ici et non dans le service : c'est n8n qui connaît la forme du message reçu, le service se contentant d'exiger exactement une entrée sur les trois. Le téléchargement du média emprunte un nœud HTTP simple côté WhatsApp, l'opération native renvoyant une requête invalide.

**Bande 6 — Réponse, puis journal (12 nœuds).** `Process output` met en forme le résultat. Les nœuds `TG reply summary` / `WA reply summary` renvoient le résumé **au technicien**. Ce n'est qu'ensuite que `Rapport exploitable ?` décide d'appeler `POST /journal`. Cet ordre est un invariant : une écriture qui échoue se gare dans la file de reprise, sans jamais coûter au technicien sa réponse. L'appel au journal est configuré **sans réessai**, le service se garant lui-même — un réessai créerait un doublon dans la file.

**Bande 7 — Journalisation et erreurs (17 nœuds).** `Log received`, `Log replied`, `Log denied`, `Log duplicate`, `Log process failed`, `Log journal failed` publient une ligne par étape avec l'identifiant de corrélation. `Error Trigger`, `Format error row` et `POST /logs` forment le gestionnaire d'erreurs : il capture les défaillances **de n8n lui-même**, que le service ne peut pas observer. C'est la raison pour laquelle cette bande est restée dans n8n quand les tâches planifiées en sont sorties. Elle exige une manipulation manuelle après import — désigner ce workflow comme son propre *Error Workflow* — faute de quoi le déclencheur ne se déclenche jamais.


## 3.6 Conception du tableau de bord

Le tableau de bord (11 590 lignes de TypeScript) est une application React 19 servie en statique.

**Toutes les chaînes d'interface vivent dans `locales/{fr,en,ar}.json`**, le français faisant référence. L'arabe impose le sens droite-à-gauche, ce qui interdit les marges directionnelles au profit des propriétés logiques.

**L'organigramme** dessine trois bandes fixes indexées sur le rôle — directeur, chefs, techniciens — et non une récursion : c'est pourquoi aucun garde-fou anti-cycle n'est nécessaire. La réaffectation utilise le glisser-déposer natif HTML5 ; comme celui-ci ne fonctionne ni au toucher ni au clavier, la liste déroulante du panneau de détail est le chemin **réel** pour ces deux modes, non un pis-aller.

**La lecture des données** passe par un cache au niveau du module, afin qu'une navigation aller-retour se repeigne instantanément puis se revalide en arrière-plan. Le sondage d'état et l'échantillonneur de disponibilité vivent **au-dessus** du routeur : les placer dans une page les arrêterait à la navigation et creuserait de faux trous dans l'historique de disponibilité.

Les captures du tableau de bord en fonctionnement sont rassemblées au §4.7, afin d'être lues à côté des résultats plutôt qu'au milieu de la conception.


## 3.7 Sécurité

**Tout est protégé.** Deux voies d'accès coexistent : un cookie de session pour les humains, un en-tête `X-API-Key` pour n8n, qui appelle le service à chaque message et n'a pas de navigateur. Trois niveaux de dépendance les distinguent : `require_user` accepte les deux, `require_human` rejette la machine (réglages, corrections, comptes), `require_director` restreint davantage.

Le contrôle est placé sur le service et non sur le formulaire de connexion : le tableau de bord étant un paquet statique, un écran de connexion seul serait contournable depuis les outils de développement.

Décisions complémentaires :

- **Sessions opaques en base**, non des jetons auto-portants : supprimer la ligne déconnecte ce navigateur dès sa requête suivante.
- **Clé machine non définie signifie accès machine *désactivé***, jamais « tout le monde est une machine ».
- **Origines croisées restreintes**, jamais un joker — un joker et l'envoi de cookies d'authentification sont de toute façon incompatibles.
- **Limitation de débit sur la connexion** : 8 échecs par 5 minutes et par adresse cliente, l'adresse étant résolue à travers un nombre configuré de relais de confiance. Une valeur erronée laisse soit un script faire tourner l'en-tête, soit enferme tous les visiteurs derrière une même clé.
- **Secrets hors du dépôt** ; le mot de passe PostgreSQL n'a délibérément **aucune valeur par défaut**, afin qu'un clone sans configuration échoue bruyamment plutôt que de démarrer avec un mot de passe connu.
- **Moindre privilège** : le compte de service Google n'accède qu'au classeur concerné ; les empreintes de mots de passe ne quittent jamais la base, les requêtes de lecture nommant leurs colonnes plutôt que de tout sélectionner.


::: {custom-style="FigureImage"}
![](diagrams/10-auth.png){ width=16.0cm }
:::


::: {custom-style="FigureCaption"}
**Figure 3.13 :** Contrôle d'accès. Les deux voies — cookie humain et clé machine — convergent vers trois niveaux d'exigence. Une clé machine non configurée **désactive** l'accès machine ; elle ne l'ouvre jamais.
:::



## 3.8 Protection des données personnelles

Le système enregistre la voix de salariés identifiés, la rattache à leur nom et la conserve. Il s'agit de **données à caractère personnel** au sens de la loi marocaine **09-08** relative à la protection des personnes physiques à l'égard du traitement des données à caractère personnel, dont l'autorité de contrôle est la **CNDP**. Un enregistrement vocal est en outre une donnée biométrique par nature, ce qui appelle une prudence particulière.

### 3.8.1 Ce qui est collecté, et où

::: {custom-style="TableCaption"}
**Tableau 3.3 :** Données personnelles traitées par le système.
:::

| Donnée | Emplacement | Durée de conservation |
|---|---|---|
| Enregistrement audio | PostgreSQL, table des médias | Purgée par la tâche de rétention |
| Transcription et rapport structuré | Google Sheets, journal du chantier | Permanente — c'est le registre métier |
| Nom, rôle, rattachement hiérarchique | PostgreSQL, `persons` | Durée de la relation de travail |
| Identifiants de messagerie | PostgreSQL, `technicians` | Désactivables sans suppression |
| Profil rédigé automatiquement | PostgreSQL, `persons.profile` | Réécrit chaque nuit |
| Journal d'étapes, sessions, visites | PostgreSQL | Purgés à 03:00 par la tâche de rétention |


### 3.8.2 Les principes appliqués

**Finalité déterminée.** Le traitement a un objet unique et explicite : produire le rapport journalier de chantier. Aucune donnée n'est exploitée à une autre fin, et notamment pas pour évaluer individuellement un salarié.

**Minimisation.** Le schéma d'extraction ne comporte que des quantités, des localisations et des remarques de chantier. Le profil technicien, qui est la donnée dérivée la plus sensible, **interdit explicitement les nombres** dans son instruction de rédaction et est cantonné à un rôle de contexte, sans jamais pouvoir alimenter une valeur du rapport.

**Limitation de la conservation.** Une tâche de rétention supprime chaque nuit les journaux et les échantillons au-delà de leur fenêtre. Le registre métier, lui, est conservé : c'est un document d'entreprise, au même titre que le fichier de suivi qu'il remplace.

**Accès restreint.** Les trois niveaux d'autorisation décrits au §3.7 s'appliquent : un technicien n'a aucun accès à l'interface, un chef accède à son périmètre, seul le directeur administre. Les sessions sont révocables individuellement.

**Sécurité.** Empreintes de mots de passe jamais exposées, secrets hors du dépôt, une seule origine publiée, limitation de débit sur la connexion.

### 3.8.3 Ce qui reste à faire avant une mise en production

Ces points relèvent de l'entreprise et non de la technique, et sont énoncés ici parce qu'ils conditionnent un déploiement réel :

1. **Déclaration du traitement auprès de la CNDP** avant toute exploitation en production.
2. **Information des personnes concernées** : les techniciens doivent être informés de la finalité, des destinataires, de la durée de conservation et de leurs droits d'accès, de rectification et d'opposition.
3. **Formalisation d'une durée de conservation** des enregistrements audio, actuellement fixée par un paramètre technique et non par une politique écrite.
4. **Encadrement du transfert hors du Maroc** : la transcription et l'extraction utilisent des services hébergés à l'étranger. C'est le point le plus sensible du dossier — et l'argument le plus fort en faveur du moteur local, qui traite l'audio **sans qu'il quitte la machine de l'entreprise**.

Ce dernier point mérite d'être souligné : le moteur de transcription local, retenu au chapitre 4 pour son exactitude, se trouve également être le seul qui n'expose aucune donnée à un tiers. Un choix technique fait pour la qualité s'avère aussi le meilleur choix pour la conformité.


## 3.9 Conclusion du chapitre

La conception traduit les contraintes du projet en structures : une architecture hybride dont la frontière est fonctionnelle et a été déplacée par l'expérience, un contrat de données reconstruit sur le fichier réel du client, un patron Stratégie qui a permis au banc d'essai de décider, quatre chaînes de repli explicites, un contrat d'erreurs qui refuse les échecs silencieux, un journal dont les règles d'accumulation et de réconciliation protègent le seul chiffre qui compte, et un modèle relationnel qui fait d'un humain une seule ligne. Le chapitre suivant décrit la mise en œuvre, le banc d'essai et les résultats.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Chapitre 4 : Réalisation, banc d'essai, tests et résultats

## 4.1 Introduction du chapitre

Ce chapitre décrit la mise en œuvre de la conception : l'environnement de développement, la réalisation du service et du workflow, le banc d'essai comparatif des moteurs de transcription du darija — cœur scientifique du projet — les difficultés techniques rencontrées et leur résolution, la stratégie de test, puis les résultats obtenus.

## 4.2 Environnement et outils de développement

::: {custom-style="TableCaption"}
**Tableau 4.1 :** Environnement de développement.
:::

| Outil | Rôle |
|---|---|
| Python 3.11 / FastAPI / Pydantic | Service applicatif |
| pytest | Tests automatisés (272 tests) |
| PostgreSQL 16 | Journal d'événements, idempotence, sessions, organigramme |
| React 19 / TypeScript / Vite / Tailwind v4 | Tableau de bord |
| Docker / Docker Compose | Exécution de la pile complète (5 services) |
| n8n | Orchestration des workflows |
| Git / GitHub Actions | Versionnage (220 commits), intégration continue (17 contrôles) |
| PyTorch 2.5 / CUDA / transformers | Banc d'essai local sur GPU |
| Groq API, Google AI Studio, Hugging Face | Inférence (offres gratuites) |


Le dépôt est organisé en modules : `api/` (service), `Dashboard/` (tableau de bord), `n8n/` (workflow exporté et documentation), `benchmark/` (banc d'essai), `docs/` (cahier des charges, guides).

### 4.2.1 Déploiement : une seule origine

La pile complète est décrite par un fichier Docker Compose de cinq services : `postgres`, `n8n`, `api`, `stt-local` et `web`. **Un seul service publie un port** : le proxy `web`, qui sert le tableau de bord, l'API sous `/api/` et les webhooks sous `/webhook/`. C'est cette origine unique qui permet au cookie de session de rester en `SameSite=Lax` et qui rend les problématiques d'origines croisées sans objet — et la forme est identique en local, derrière le tunnel et sur le serveur de l'entreprise ; seul le nom d'hôte change.

Deux pièges de déploiement, rencontrés le 30 juillet 2026, méritent d'être documentés car ils font qu'**un changement peut sembler appliqué sans être exécuté** :

1. Le service est une **image construite**, code source inclus. Un simple redémarrage réexécute l'*ancien* code ; il faut reconstruire.
2. n8n conserve **sa propre copie** du workflow dans son volume. Modifier le fichier JSON versionné ne change rien tant qu'il n'est pas réimporté ou poussé par l'API de n8n.


::: {custom-style="FigureImage"}
![](diagrams/12-deployment.png){ width=16.0cm }
:::


::: {custom-style="FigureCaption"}
**Figure 4.1 :** Topologie de déploiement. Un seul service publie un port ; tout le reste n'existe que sur le réseau interne de la pile. C'est cette forme unique — identique en local, derrière le tunnel et sur le serveur — qui rend les questions d'origines croisées sans objet.
:::


## 4.3 Le banc d'essai des moteurs de transcription

C'est le volet scientifique du projet. Il a été mené sur **treize moteurs** — trois par API et douze exécutés localement sur une carte NVIDIA RTX 3070 (8 Go) — et il a **renversé l'hypothèse initiale** du cahier des charges.

### 4.3.1 Protocole

Onze notes vocales réelles, issues des échanges des techniciens, ont servi de corpus. Trois campagnes ont été menées :

1. **Comparaison par API** (3 moteurs), le 7 août 2026.
2. **Première campagne locale** (9 moteurs), le même jour.
3. **Campagne locale complète** (12 moteurs), après déblocage de deux dépôts sous licence.

### 4.3.2 Une décision de méthode : ni WER, ni CER

**La vérité terrain a été délibérément écartée**, et il faut le dire explicitement plutôt que de le dissimuler : le fichier de références est resté vide, et le calcul du WER et du CER n'a donc **pas** été effectué. Ce n'est pas un oubli mais un arbitrage, fondé sur trois constats :

- **L'écriture du darija n'est pas normalisée.** Le WER compare des chaînes de mots ; sur une langue sans orthographe fixée, il mesure autant la convention d'écriture du transcripteur de référence que la qualité du moteur.
- **Le système ne consomme pas des mots, il consomme des nombres et des lieux.** Un moteur qui écrit `ربعين` là où la référence dit « 40 » est lourdement pénalisé par le WER, alors qu'il fournit exactement l'information dont la chaîne d'extraction a besoin — celle-ci lit le darija.
- **Le critère retenu est donc applicatif** : *quel moteur préserve les chiffres et les emprunts techniques français* — « 6 mètres », « 3ème étage », « panneau de brassage », « la fibre », « vérifier ». C'est tout ce que le journal consomme.

Ce critère a été appliqué par lecture des transcriptions clip par clip, puis **confirmé à l'oreille par un locuteur natif du darija le 8 août 2026**. Cette confirmation humaine est ce qui a fixé l'ordre définitif de la chaîne.


::: {custom-style="FigureImage"}
![](diagrams/13-benchmark.png){ width=16.0cm }
:::


::: {custom-style="FigureCaption"}
**Figure 4.2 :** Démarche du banc d'essai, y compris ses détours. Les deux encadrés rouges signalent le bogue silencieux : il flattait un modèle au lieu de le pénaliser, ce qui est le mode de défaillance le plus dangereux pour une comparaison.
:::


### 4.3.3 Résultats — moteurs par API

::: {custom-style="TableCaption"}
**Tableau 4.2 :** Comparaison des moteurs accessibles par API (7 août 2026).
:::

| Moteur | Clips | Erreurs | Latence moyenne | Confiance moyenne | Caractères moyens |
|---|---|---|---|---|---|
| Groq (Whisper large-v3) | 11 | 0 | **1,53 s** | 0,483 | 613 |
| Gemini | 11 | 0 | 16,94 s | non exposée | 20 651 (faussé, voir §4.4.1) |
| Hugging Face (affinage darija) | 11 | **11** | — | — | jeton non configuré |


**Constat majeur : Groq déforme les quantités.** Sur un même clip, Gemini produit `40 كابل`, `8 ديال les panneaux`, `12 پانُو`, `3ème étage` ; Groq produit `mniya dyal panno`, `Pouzina ssimetro`, `3O mietage`, `ondélique`. Le schéma métier étant intégralement composé de quantités et de localisations, un moteur qui fusionne un chiffre dans le mot suivant ne donne rien à extraire — et `has_data()` renvoie alors « faux » sur un rapport qui *contenait* pourtant des données.

### 4.3.4 Résultats — moteurs locaux sur GPU

Douze moteurs ont été exécutés localement en demi-précision sur la RTX 3070.

::: {custom-style="TableCaption"}
**Tableau 4.3 :** Campagne locale complète, 12 moteurs, 11 clips, RTX 3070 (7 août 2026). Trié par confiance décroissante.
:::

| Modèle | Latence | Confiance | Caractères | Chiffres |
|---|---|---|---|---|
| `boumehdi/wav2vec2-moroccan-darija` | 0,7 s | 0,916 | 501 | 0 |
| `amineouaki/xlsr-53-darija-combined` | 6,3 s | 0,884 | 493 | 7 |
| `amineouaki/wav2vec2-darija-combined` | 4,0 s | 0,853 | 439 | 22 |
| `ychafiqui/whisper-medium-darija` | 3,7 s | 0,843 | 184 | 0 |
| **`BounharAbdelaziz/Morocco-Darija-STT-large`** | **7,7 s** | **0,791** | **249** | **45** |
| `TaloCreations/whisper-darija-finetuned` | 2,3 s | 0,735 | 198 | 0 |
| `ychafiqui/whisper-small-darija` | 2,3 s | 0,716 | 199 | 0 |
| `openai/whisper-large-v3-turbo` (contrôle) | 1,0 s | 0,597 | 174 | 30 |
| `openai/whisper-large-v3` (contrôle) | 5,7 s | 0,582 | 214 | 55 |
| `C-Ilyas/whisper-base-darija` | 5,0 s | 0,548 | **0** | 0 |


**Ce tableau est trié par confiance précisément pour démontrer qu'il ne faut pas s'y fier.** `boumehdi` domine la colonne à 0,916 et perd purement et simplement le « 40 » ; le meilleur moteur n'arrive qu'en cinquième position. C'est la troisième confirmation indépendante que `exp(mean logprob)` mesure la certitude du décodeur, non son exactitude.

Deux précautions de lecture s'imposent :

- **Les confiances ne sont pas comparables d'une famille à l'autre.** Le 0,85–0,92 de wav2vec2 est une moyenne de *softmax* CTC ; celle de Whisper est `exp(mean token logprob)`. Même échelle, grandeurs différentes.
- **La colonne « chiffres » est un leurre.** Les affinages capturent bien les nombres, mais sous forme de **mots arabes** : `تمنية` (8), `طناشر` (12), `ربعين` (40). La chaîne d'extraction lit le darija ; ces formes sont donc parfaitement récupérables. La colonne mesure une commodité de format, non une perte d'information.

### 4.3.5 Le moteur retenu et sa justification

`BounharAbdelaziz/Morocco-Darija-STT-large` (environ 2 milliards de paramètres, licence Apache 2.0) a été retenu. Sur un clip de référence dont le contenu est *« hier 20/07/2026, arrivés à Essaouira à 1 h, vérifié le chemin de 27 câbles, pris le métrage, coupés, vérifié le chemin de la fibre, sortis à 7 h »* :

::: {custom-style="TableCaption"}
**Tableau 4.4 :** Comportement comparé sur les champs métier d'un clip de référence.
:::

| Modèle | Effet sur les champs de données |
|---|---|
| **Morocco-Darija-STT-large** | `20 سبعة 2026`, `27 كابل`, `فيريفينا` (vérifier), `لافيبر` (la fibre), `السبع` (7 h) — **tous les champs extractibles survivent** |
| `whisper-large-v3` | Date et `27 كابل` corrects, mais *vérifier* devient **`فرحنا`** (« nous nous sommes réjouis ») — un verbe technique français transformé en mot arabe sans rapport |
| `ychafiqui/medium-darija` | **`27 câbles` devient `السبعة وعشر وعشر الين كابل`** — la quantité est détruite ; la ligne atteint le journal sans compte de câbles |


Le moteur retenu conserve également les noms propres du domaine — Novec, Essaouira, Kenitra — à travers l'ensemble des clips.

**Le coût de ce choix est assumé : 7,7 s de latence moyenne**, le plus lent des douze, et environ 4 Go de mémoire graphique, contre 1,53 s pour l'API de Groq. Ce compromis — la meilleure exactitude contre cinq fois l'attente — est la décision centrale du banc d'essai, et c'est la validation par un locuteur natif qui l'a tranchée.

### 4.3.6 Une hypothèse renversée, puis rétablie

L'histoire de cette conclusion mérite d'être racontée, car elle illustre la valeur des contrôles.

À l'issue de la première campagne locale, la conclusion était **négative** : les deux contrôles OpenAI non affinés égalaient ou surpassaient *tous* les affinages darija disponibles. Ce résultat contre-intuitif — l'affinage sur la langue cible ne servirait à rien — n'a pu être formulé que parce que les contrôles avaient été téléchargés ; sans eux, `ychafiqui/medium-darija` aurait été couronné vainqueur.

Or les deux modèles les plus prometteurs étaient **sous licence restreinte** et n'avaient pas pu être téléchargés lors de cette première campagne. Une fois l'accès obtenu et la campagne rejouée, la conclusion s'est inversée : **l'affinage sur le darija fonctionne bel et bien, à condition que le modèle affiné soit assez grand.** L'énoncé négatif reste vrai des cinq *petits* affinages ; la généralisation qu'on en avait tirée était fausse.

Une ambiguïté a été close au passage : l'adaptateur historique pointait vers un identifiant de dépôt inexistant. Il retournait une erreur 401 tant que le jeton d'authentification manquait — donc « non authentifié » — et une erreur 404 une fois le jeton fourni — donc « n'existe pas ». **Deux défauts empilés, le moins grave masquant le fatal** : cet adaptateur n'avait jamais pu fonctionner une seule fois depuis sa création.

### 4.3.7 Trois bogues de harnais, dont un silencieux

La mise au point du banc d'essai local a révélé trois défauts, dont l'ordre de gravité est instructif :

| # | Défaut | Mode de défaillance |
|---|---|---|
| 1 | Tenseur d'invite vide, indexé sans garde | Exception à chaque clip — **bruyant** |
| 2 | Budget de génération incompatible avec la fenêtre du décodeur | Exception à chaque clip — **bruyant** |
| 3 | Les jetons d'invite relus **comme s'ils étaient la transcription** | **Silencieux** |

Le troisième est le seul qui compte vraiment. Il produisait `Kmmalna khamsa dyal bureaux` — exactement ce qu'un technicien dirait — et aurait couronné `whisper-large-v3` vainqueur sur une transcription **qu'il n'avait jamais générée**. Deux signaux l'ont trahi : une sortie *identique* sur des audios différents, et un effondrement de la confiance à 0,085–0,34 contre 0,48 pour Groq. La confiance ne mesure pas l'exactitude, mais son effondrement soudain signale que le harnais ment.

### 4.3.8 L'invite de vocabulaire : survivable par API, fatale en local

Une même instruction produit deux comportements opposés selon la voie d'exécution.

::: {custom-style="TableCaption"}
**Tableau 4.5 :** Effet de l'invite de vocabulaire en exécution locale.
:::

| Condition | Sortie observée (`whisper-large-v3` local) |
|---|---|
| Invite activée | `The work, the work, the work…` — boucle dégénérée, sur **tous** les clips |
| Invite désactivée | `السلام عليكم بالنسبة لخدمة اليوم في نوفيك…` — darija propre |


Les deux explications concurrentes ont été **éliminées avant** de conclure, et non écartées par hypothèse : le décodage audio a été validé par corrélation de 1,0000 entre deux décodeurs indépendants, et la précision de calcul a produit un texte identique octet pour octet.

**Cause réelle.** L'API de Groq et la bibliothèque `transformers` ne traitent pas l'invite de la même manière : la première conditionne segment par segment avec sa propre troncature ; la seconde préfixe les jetons bruts au décodeur et le laisse les *continuer*. Recevant 180 jetons de darija en caractères latins présentés comme « transcription précédente », le modèle poursuit en caractères latins et s'effondre.

Par contraste, une comparaison A/B menée sur l'API a montré que la même invite y est non seulement inoffensive mais **bénéfique** : elle contrôle décisivement le système d'écriture (6 caractères arabes avec l'invite, 3 702 sans) sans coûter de chiffres (93 contre 89), et sa suppression fait perdre un tiers du contenu transcrit. **L'invite est donc conservée pour la voie API et désactivée pour la voie locale** — deux réglages opposés pour un même fichier, parce que deux implémentations en font deux choses différentes.

## 4.4 Difficultés techniques rencontrées et résolues

Au-delà du banc d'essai, la confrontation au réel a révélé plusieurs défauts indétectables hors ligne.

### 4.4.1 La boucle de répétition de Gemini

**Symptôme mesuré :** un clip de 84 Ko a produit **222 797 caractères en 129,2 secondes**, la fin répétant sans terme une même locution. Groq renvoyait 381 caractères en 1,0 seconde sur le même audio. Gemini traduisait de surcroît en français malgré une consigne explicite de ne pas traduire.

**Résolution**, en trois volets : un plafond de génération fixé à environ quatre fois le pire cas légitime observé ; une température nulle, la transcription n'étant pas une tâche créative et l'échantillonnage étant ce qui autorise le décodeur à quitter l'audio ; et surtout un **détecteur de dégénérescence qui lève une erreur** au lieu de tronquer. Ce dernier point est un choix de conception : une boucle tronquée reste plusieurs milliers de caractères de bruit que la chaîne d'extraction résumerait en une fiction confiante, et que `has_data()` ne rattraperait pas, un texte répété n'étant pas un texte vide.

### 4.4.2 Validation de format par Groq

L'API Whisper de Groq valide l'extension du nom de fichier **avant** de décoder les octets ; or les notes vocales arrivent en `audio/ogg`, parfois présentées comme un flux binaire générique. **Résolution :** normalisation du type MIME vers une table d'extensions acceptées, avec alias, et repli sur le format des notes vocales.

### 4.4.3 Rotation des modèles chez le fournisseur

Un modèle épinglé a été retiré par Google en cours de projet (404), et l'alias du modèle phare répondait 503 aux heures de pointe sur l'offre gratuite. **Résolution :** sondage systématique des modèles candidats, puis bascule vers un alias vérifié opérationnel. Cet épisode valide *a posteriori* le patron d'adaptateurs et la configuration externalisée — et impose une leçon durable : **figurer dans le catalogue d'un fournisseur ne signifie pas être appelable.**

### 4.4.4 Chaînes « null » des modèles

En mode JSON, certains modèles émettent la *chaîne* `"null"` au lieu de la valeur nulle, provoquant un rejet de validation sur les champs numériques. **Résolution :** un validateur de pré-traitement normalise `null`, `none` et la chaîne vide vers la valeur nulle avant le typage strict.

### 4.4.5 Une identité scindée en deux

Sur données réelles, un même humain est apparu **deux fois** dans l'organigramme : sa ligne WhatsApp le déclarait `directeur`, sa ligne Telegram `tech`. La cause était une correspondance établie sur le couple (nom, rôle). **Résolution :** la correspondance se fait désormais **sur le nom seul**. C'est cette correction qui permet à un profil de suivre le collègue plutôt que le numéro de téléphone.

### 4.4.6 Une migration qui se planifie avant de s'exécuter

La migration de fusion des comptes lit une colonne qu'elle supprime elle-même. PostgreSQL planifiant l'intégralité d'une instruction avant de l'exécuter, elle échouait. **Résolution :** encapsulation dans un bloc conditionnel dynamique, la rendant réexécutable à chaque démarrage.

## 4.5 Stratégie de test et intégration continue

La suite compte **272 tests** répartis en 22 fichiers (3 782 lignes), **exécutables sans aucune clé d'API et sans base de données**. Cette propriété est une règle du projet, obtenue par deux moyens : les bibliothèques externes sont importées paresseusement *à l'intérieur* des fonctions, et les appels externes sont simulés aux frontières.

Elle a un corollaire honnête, qu'il faut énoncer : **aucun test ne parcourt le chemin réseau réel**. Les défauts décrits en §4.4 sont précisément ceux qu'une suite hors ligne ne peut pas voir, et c'est pourquoi la vérification en conditions réelles reste une étape distincte et nécessaire.

L'intégration continue (GitHub Actions) exécute la suite, l'analyse statique, et un contrôle de parité des trois fichiers de traduction.

## 4.6 Résultats

### 4.6.1 Chaîne de bout en bout opérationnelle

**Dès la semaine 0** — alors que le planning la prévoyait au Sprint 2 — la chaîne complète a été validée en conditions réelles : note vocale → détection → téléchargement → transcription → extraction → résumé français → réponse de confirmation. Le risque d'intégration majeur du projet a ainsi été neutralisé très tôt, ce qui est précisément l'objet d'une semaine de neutralisation des risques.

Lors de ces essais, **le repli d'extraction s'est déclenché en conditions réelles** (indisponibilité du fournisseur principal en soirée) : la chaîne a produit son rapport via le moteur secondaire sans intervention, validant la conception.

### 4.6.2 Périmètre livré

::: {custom-style="TableCaption"}
**Tableau 4.6 :** État du périmètre livré.
:::

| Composant | État |
|---|---|
| Réception Telegram | En production |
| Réception WhatsApp Cloud API | En production |
| Transcription (3 moteurs, chaîne de repli) | En production |
| Extraction structurée (4 chaînes de repli) | En production |
| Entrée par photo (modèle de vision) | En production |
| Journal de chantier par site (fusion, stock) | En production |
| Miroir plat pour le tableau de bord | En production |
| Observabilité PostgreSQL | En production |
| Tableau de bord trilingue (FR/EN/AR) | En production |
| Organigramme, comptes, chantiers, bordereau | En production |
| Ordonnanceur (6 tâches) et page Automatisation | En production |
| Rapports quotidien et hebdomadaire par e-mail | En production |
| Commandes `/rapport`, `/modifier`, `/supprimer` | En production |
| Moteur local sur GPU, conteneurisé | En production |
| Pilote en conditions réelles avec les techniciens | *[À COMPLÉTER]* |


### 4.6.3 Métriques du projet

::: {custom-style="TableCaption"}
**Tableau 4.7 :** Métriques du projet à la date de rédaction.
:::

| Indicateur | Valeur |
|---|---|
| Commits | 220 |
| Lignes de Python (service) | 8 489 |
| Lignes de tests | 3 782 (22 fichiers, 272 tests) |
| Lignes de TypeScript (tableau de bord) | 11 590 |
| Routes d'API | 66 |
| Nœuds n8n | 65 |
| Instructions de modèles versionnées | 6 |
| Moteurs STT évalués | 13 |
| Tables PostgreSQL | 11 |
| Services Docker | 5 |


### 4.6.4 Latence de bout en bout

*[À COMPLÉTER — mesure de la latence note vocale → ligne dans le journal, à relever sur le pilote. Les latences unitaires mesurées sont disponibles : transcription 1,53 s (Groq) à 7,7 s (moteur local), extraction non chronométrée séparément.]*

### 4.6.5 Pilote

*[À COMPLÉTER — déploiement pilote, nombre de rapports traités, retours des techniciens et de l'encadrement, incidents observés.]*



## 4.8 Analyse des coûts et des quotas

La contrainte de budget nul n'est tenable que si elle est chiffrée. Un rapport consomme, au plus, **un appel de transcription** et **un appel d'extraction**, plus les écritures dans le classeur.

::: {custom-style="TableCaption"}
**Tableau 4.8 :** Consommation des offres gratuites.
:::

| Service | Offre gratuite | Consommation par rapport | Marge à 10 rapports/jour |
|---|---|---|---|
| Groq (transcription et extraction) | Quotas par minute et par jour | 1 appel | Très large |
| Google AI Studio (Gemini) | Quotas par minute et par jour | 1 à 2 appels | Très large |
| Moteur local (GPU) | Aucun quota | Illimité | Sans objet |
| Telegram Bot API | Gratuit | 2 à 3 appels | Sans objet |
| WhatsApp Cloud API | Conversations de service gratuites | 2 appels | Large |
| Google Sheets API | Quota par minute et par utilisateur | 3 à 5 appels | Large |
| Gmail SMTP | Envois quotidiens | 1 à 2 par jour | Large |
| PostgreSQL, n8n, Docker | Auto-hébergés | — | Sans objet |


Trois décisions d'architecture entretiennent directement cette marge. La **chaîne d'extraction alterne les fournisseurs**, Gemini et Groq mesurant leurs quotas séparément — l'alternance double la capacité effective. Le **moteur local n'a aucun quota**, ce qui en fait le filet de sécurité en cas d'épuisement simultané. Et la **file de reprise** absorbe un dépassement de quota du côté Google sans perdre une ligne : la reprise a lieu cinq minutes plus tard, quand la fenêtre s'est rouverte.

Le facteur limitant n'est donc pas le nombre de rapports mais leur **simultanéité**. À la volumétrie visée — 5 à 10 rapports par jour, envoyés en fin de journée —, aucun quota gratuit n'est approché.

## 4.9 Statistiques et qualité du projet

### 4.9.1 Répartition du code

Hors fichiers générés — verrous de dépendances, exports d'outils — le dépôt représente **33 274 lignes** réparties comme suit :

::: {custom-style="TableCaption"}
**Tableau 4.9 :** Répartition du code par langage.
:::

| Langage | Fichiers | Lignes | Part |
|---|---|---|---|
| Python | 59 | 15 040 | 45,2 % |
| TypeScript | 54 | 11 642 | 35,0 % |
| Markdown | 27 | 5 101 | 15,3 % |
| YAML | 4 | 545 | 1,6 % |
| JavaScript | 3 | 432 | 1,3 % |
| CSS | 1 | 399 | 1,2 % |
| HTML | 2 | 83 | 0,2 % |
| PowerShell | 1 | 32 | 0,1 % |


Deux lectures méritent d'être faites. La part de **Markdown à 15 %** n'est pas de la documentation d'accompagnement : elle contient les instructions versionnées des modèles (§3.4.5), qui sont du contenu exécutable au même titre que du code. Et l'équilibre Python/TypeScript reflète fidèlement l'architecture — un service métier substantiel et une interface d'administration complète, plutôt qu'une simple façade.

### 4.9.2 Indicateurs de qualité mesurés

::: {custom-style="TableCaption"}
**Tableau 4.10 :** Indicateurs de qualité mesurés.
:::

| Indicateur | Valeur |
|---|---|
| Tests automatisés | 272, répartis en 22 fichiers |
| Lignes de test | 3 782 |
| Ratio test / code applicatif | ≈ 1 ligne de test pour 4 lignes de service |
| Dépendances d'exécution requises pour les tests | **Aucune** — ni clé d'API, ni base de données |
| Durée de la suite complète | ≈ 8 minutes |
| Contrôles d'intégration continue | **17** par *push* (détail au §4.9.3) |
| Commits | **220**, en convention *Conventional Commits* |
| Période de développement | 15 juillet – 12 août 2026, soit 29 jours |


### 4.9.3 La chaîne d'intégration continue

Chaque *push* sur la branche principale déclenche **dix-sept contrôles automatiques**, définis dans un unique fichier `.github/workflows/ci.yml`. Ils se répartissent en quatre familles, et cette répartition n'est pas décorative : elle correspond à quatre natures de défaut distinctes, qu'aucun outil unique ne détecte toutes.

::: {custom-style="TableCaption"}
**Tableau 4.11 :** Les dix-sept contrôles d'intégration continue, par famille.
:::

| Famille | Contrôles | Ce qu'ils attrapent |
|---|---|---|
| Correction | `API — lint, types & tests` (ruff, 272 tests), `Dashboard — types, lint & build` (tsc, oxlint), `n8n workflow`, `Docker compose config`, `Locale key parity` | Régressions de logique, dérive de types, workflow invalide, clé de traduction manquante dans l'une des trois langues |
| Sécurité du code | `CodeQL (python)`, `CodeQL (javascript-typescript)`, `Semgrep (OWASP Top 10)`, `Bandit SAST` | Injections, chemins de données non assainis, primitives cryptographiques faibles |
| Dépendances et secrets | `Trivy filesystem scan`, `Trivy config scan`, `pip-audit`, `npm audit`, `Secret scan` (gitleaks + `scripts/check_secrets.py`) | Vulnérabilités connues des bibliothèques tierces, mauvaise configuration d'infrastructure, jeton commité |
| Conformité des fichiers | `Hadolint (api/Dockerfile)`, `Hadolint (Dashboard/Dockerfile)`, `actionlint` | Images Docker non conformes aux bonnes pratiques, workflow GitHub Actions syntaxiquement fragile |


Deux points méritent d'être soulignés. Le contrôle de secrets s'exécute sur **l'historique complet** (`fetch-depth: 0`) et non sur le seul dernier état : un jeton retiré dans le dernier commit reste public dans l'historique, et ne le vérifier qu'au sommet donnerait une fausse assurance. Et la **parité des clés de traduction** est un contrôle propre à ce projet : l'interface étant trilingue, une clé ajoutée en français mais oubliée en arabe ne casse aucun test et ne se voit qu'à l'usage, en production, par un utilisateur arabophone.

**Dependabot** complète le dispositif : configuré sur **cinq écosystèmes** — `npm` pour le tableau de bord, `pip` pour le service, les deux images Docker et les actions GitHub elles-mêmes — il ouvre **quotidiennement** des demandes de mise à jour, groupées par niveau de version pour éviter une avalanche de demandes unitaires. **Trente-cinq** ont été ouvertes sur la durée du projet. Chacune franchit les dix-sept contrôles avant d'être fusionnée : la mise à jour automatique n'a d'intérêt que si elle est automatiquement vérifiée, sans quoi elle ne fait que déplacer le risque.

::: {custom-style="FigureImage"}
![](diagrams/14-devops.png){ width=14.7cm }
:::


::: {custom-style="FigureCaption"}
**Figure 4.3 :** La chaîne d'intégration continue : les deux sources de changement, les dix-sept contrôles et l'analyse statique externe avant fusion.
:::


### 4.9.4 Analyse statique externe

Au-delà des contrôles exécutés dans le dépôt, le projet est analysé par **SonarCloud**, qui fournit une lecture indépendante de la qualité du code : notes de fiabilité, de sécurité et de maintenabilité, dette technique estimée, taux de duplication et couverture de tests.

[ESPACE RÉSERVÉ — insérer ici le tableau des indicateurs SonarCloud et la capture du tableau de bord.]

*[FIGURE À INSÉRER — capture SonarCloud.]*

### 4.9.5 Chronologie réelle du développement

L'historique Git fournit une mesure d'activité que le planning prévisionnel ne peut pas donner, puisqu'elle est constatée et non annoncée :

::: {custom-style="TableCaption"}
**Tableau 4.12 :** Activité de développement par semaine.
:::

| Semaine | Commits | Étape |
|---|---|---|
| S29 (15–19 juillet) | 11 | Cadrage, neutralisation du risque d'intégration |
| S30 (20–26 juillet) | 42 | Service FastAPI, adaptateurs STT, extraction |
| S31 (27 juillet – 2 août) | 92 | Chaîne complète, observabilité, tableau de bord |
| S32 (3–9 août) | 49 | Journal par chantier, banc d'essai, organigramme |
| S33 (10–16 août) | 23 | Conteneurisation du moteur local, corrections, rapport |


Le pic de la semaine 31 correspond à la construction simultanée du tableau de bord et de la couche d'observabilité ; la décroissance ensuite traduit le passage de la construction à la consolidation — corrections, tests et documentation — ce qui est le profil attendu d'un projet qui converge.



## 4.10 Le tableau de bord en fonctionnement

Les captures ci-dessous proviennent de l'application réelle, connectée à la pile complète, en thème sombre et en anglais — l'interface étant trilingue, la langue d'affichage est un choix de l'utilisateur. Elles ont été produites par un script Playwright versionné dans le dépôt, qui ouvre une session, attend la disparition des squelettes de chargement avant chaque capture, et cadre chaque écran en 16:9.

### 4.10.1 Écrans principaux
::: {custom-style="FigureImage"}
![](screens/en-login.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.4 :** L'écran de connexion. Le contrôle d'accès est appliqué par le service, non par ce formulaire : le tableau de bord étant un paquet statique, un écran de connexion seul serait contournable.
:::

::: {custom-style="FigureImage"}
![](screens/en-overview.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.5 :** Vue d'ensemble. Les repères du jour, le rythme horaire des messages, l'état des sept services et l'activité de l'année. La disponibilité provient d'échantillons enregistrés, non d'une sonde instantanée.
:::

::: {custom-style="FigureImage"}
![](screens/en-overview-2.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.6 :** Vue d'ensemble, partie basse : qualité des extractions, répartition par chantier et derniers rapports reçus.
:::

::: {custom-style="FigureImage"}
![](screens/en-inbox.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.7 :** Réception. Le flux des messages entrants, canal par canal, avec le média d'origine et le texte transcrit — l'écran qui permet de remonter d'une ligne douteuse à l'audio qui l'a produite.
:::

::: {custom-style="FigureImage"}
![](screens/en-reports.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.8 :** Rapports. Le miroir plat du journal, filtrable et corrigeable ; une correction faite ici est écrite dans le classeur, pas seulement affichée.
:::

::: {custom-style="FigureImage"}
![](screens/en-daily.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.9 :** Rapport du jour, tel qu'il part par courriel, avec régénération et téléchargement.
:::

::: {custom-style="FigureImage"}
![](screens/en-weekly.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.10 :** Rapport hebdomadaire : le même moteur que le rapport quotidien, appelé sur une plage de dates.
:::

::: {custom-style="FigureImage"}
![](screens/en-automation.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.11 :** Automatisation. Les six tâches planifiées, leur dernier résultat et leur horaire. Le bouton de réexécution est la raison d'être de la migration depuis les nœuds cron.
:::

::: {custom-style="FigureImage"}
![](screens/en-tasks.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.12 :** Tâches et rappels, avec leur périodicité.
:::

::: {custom-style="FigureImage"}
![](screens/en-logs.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.13 :** Journaux. La chronologie du pipeline reconstituée par identifiant de corrélation : les étapes publiées par n8n et les erreurs journalisées par le service apparaissent dans une seule suite.
:::

::: {custom-style="FigureImage"}
![](screens/en-queue.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.14 :** File de reprise : les écritures en échec en attente de rejeu, avec leur nombre de tentatives.
:::

::: {custom-style="FigureImage"}
![](screens/en-equipe.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.15 :** Organigramme. Trois bandes fixes — directeur, chefs, techniciens — et non une récursion, ce qui est la raison pour laquelle aucun garde-fou anti-cycle n'est nécessaire.
:::

::: {custom-style="FigureImage"}
![](screens/en-equipe-2.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.16 :** Organigramme, panneau de détail : canaux, profil et accès d'un technicien. Le panneau change de contenu selon le rôle, un technicien n'ayant pas de compte.
:::

::: {custom-style="FigureImage"}
![](screens/en-palette.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.17 :** La palette de commandes (Ctrl+K) : navigation, collègues et actions, sans quitter le clavier.
:::

::: {custom-style="FigureImage"}
![](screens/en-palette-fuzzy.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.18 :** Recherche approximative : « rapprt » est mal orthographié et trouve malgré tout les entrées pertinentes.
:::

::: {custom-style="FigureImage"}
![](screens/en-palette-noresult.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.19 :** Aucune correspondance : plutôt qu'une liste vide, la palette propose les entrées les plus proches. Un cul-de-sac est une impasse ; une suggestion est une issue.
:::

::: {custom-style="FigureImage"}
![](screens/en-notfound.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.20 :** Une adresse qui ne correspond à aucune route. L'application le dit explicitement au lieu de rediriger silencieusement vers l'accueil, où l'utilisateur croirait que son lien a fonctionné.
:::

::: {custom-style="FigureImage"}
![](screens/en-overview-light.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.21 :** Le même écran en thème clair : le thème est un choix persistant de l'utilisateur, pas une préférence système imposée.
:::

::: {custom-style="FigureImage"}
![](screens/ar-overview.jpg){ width=15.5cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.22 :** La même page en arabe. L'arabe impose l'écriture de droite à gauche, ce qui a dicté l'emploi de propriétés CSS logiques dans toute l'interface plutôt que de marges directionnelles.
:::


### 4.10.2 Usage mobile

L'interface est utilisable depuis un téléphone, ce qui compte pour un chef de chantier qui consulte l'avancement sans revenir au bureau.

::: {custom-style="FigureImage"}
![](screens/mobile-overview.jpg){ width=11.2cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.23 :** Vue d'ensemble sur téléphone : la barre latérale se replie et les indicateurs passent sur une colonne.
:::

::: {custom-style="FigureImage"}
![](screens/mobile-reports.jpg){ width=11.2cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.24 :** Rapports sur téléphone : le tableau défile horizontalement dans son propre conteneur, la page elle-même ne défilant jamais latéralement.
:::

::: {custom-style="FigureImage"}
![](screens/mobile-equipe.jpg){ width=11.2cm }
:::

::: {custom-style="FigureCaption"}
**Figure 4.25 :** Organigramme sur téléphone. Le glisser-déposer natif ne fonctionnant ni au toucher ni au clavier, la liste déroulante du panneau de détail est ici le chemin réel de réaffectation.
:::


## 4.11 Conclusion du chapitre

La réalisation a concrétisé la conception et l'a confrontée au réel. Le banc d'essai, mené sur treize moteurs, a produit un résultat qu'aucune revue de littérature n'aurait donné : le moteur le plus exact pour ce cas d'usage n'est pas le service commercial de référence mais un affinage open-source du darija, et ce constat n'a pu émerger que parce que des contrôles non affinés avaient été inclus et parce que trois bogues de harnais — dont un silencieux et flatteur — ont été débusqués. Six défauts d'intégration invisibles hors ligne ont par ailleurs été diagnostiqués et corrigés. La chaîne complète fonctionne de bout en bout depuis la semaine 0, repli compris.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```


# Bilan et compétences acquises

**Compétences techniques.** Ce projet a imposé d'aller au bout de plusieurs domaines plutôt que d'en effleurer beaucoup : la conception d'une API en Python avec un contrat de données strict ; l'intégration de grands modèles de langage avec sortie contrainte et chaînes de repli ; l'évaluation empirique de treize modèles de reconnaissance vocale, avec la mise au point du harnais que cela suppose ; la conception d'un schéma relationnel et la migration de données réelles ; le développement d'une interface React trilingue avec prise en charge de l'écriture de droite à gauche ; et la mise en production conteneurisée d'une pile de cinq services, dont un service GPU.

**Compétences méthodologiques.** Trois habitudes ont plus compté que n'importe quelle bibliothèque.

*Neutraliser le risque le plus élevé en premier.* La chaîne complète a été validée de bout en bout dès la semaine 0, alors que le planning la prévoyait au sprint 2. C'est ce qui a permis de découvrir tôt les défauts d'intégration qu'aucun test hors ligne ne pouvait révéler.

*Se méfier de ses propres mesures.* Le banc d'essai comportait un bogue silencieux qui aurait couronné un modèle sur une transcription qu'il n'avait jamais produite. Il n'a été détecté que parce que deux indicateurs secondaires étaient incohérents. La leçon retenue est qu'un résultat flatteur mérite plus de vérification qu'un résultat décevant.

*Écrire pourquoi, pas seulement quoi.* Les décisions non évidentes de ce système sont documentées à l'endroit du code qu'elles concernent. Plusieurs fois au cours du projet, une correction a été évitée parce qu'un commentaire expliquait qu'un comportement surprenant était voulu.

**Ce que je referais autrement.** Trois choses. D'abord, **constituer la vérité terrain dès le premier jour** : son absence est la principale limite du banc d'essai, et enregistrer quelques transcriptions de référence en semaine 0 aurait coûté une heure. Ensuite, **écrire les tests d'intégration réels plus tôt** : la suite hors ligne est excellente contre les régressions de logique, mais tous les défauts sérieux rencontrés venaient de contrats externes qu'elle ne touche pas. Enfin, **traiter la documentation comme du code dès le départ** : plusieurs affirmations du fichier d'architecture étaient devenues fausses sans que rien ne le signale, et elles n'ont été corrigées que lorsqu'un travail ultérieur les a confrontées à la réalité.

**Compétences humaines.** Le dialogue avec l'encadrant industriel a été déterminant sur un point précis : le schéma de données a été reconstruit à partir de son fichier de suivi réel, et non de ce qu'un développeur imaginait utile. Les trois compteurs de prises distincts, incompréhensibles hors contexte, sont la trace directe de cette conversation. C'est probablement l'enseignement le plus transférable de ce projet : la qualité d'un modèle de données dépend moins de la technique que de la précision avec laquelle on a écouté celui qui s'en servira.


# Conclusion générale et perspectives

**Rappel des objectifs.** Ce projet de fin d'études visait à automatiser la production des rapports journaliers des techniciens de câblage d'AZNET : permettre à un technicien de transmettre son compte rendu par une simple note vocale en darija, et obtenir automatiquement un rapport structuré en français professionnel, centralisé dans le fichier de suivi et notifié aux responsables — le tout sans budget logiciel.

**Contributions.** Le travail réalisé apporte :

1. **Une architecture hybride** combinant orchestration low-code et service métier sur mesure, dont la frontière a été fixée par une contrainte fonctionnelle identifiée en cours de projet — une logique de lecture-modification-écriture n'est pas exprimable dans un nœud conditionnel — et non par préférence.
2. **Un banc d'essai comparatif de treize moteurs de transcription du darija**, langue peu dotée, assorti d'une critique argumentée du WER pour ce cas d'usage et d'une métrique applicative de substitution ; il a renversé l'hypothèse technologique initiale du cahier des charges.
3. **Un service d'extraction** fondé sur les grands modèles de langage avec sortie structurée contrainte, quatre chaînes de repli explicites alternant les fournisseurs, et une politique stricte d'absence de données inventées, poussée jusqu'à faire échouer une localisation non reconnue plutôt que de l'ignorer.
4. **Un modèle métier reconstruit sur le fichier réel du client**, tenant un journal par chantier avec accumulation intra-journalière et réconciliation de stock — deux règles sans lesquelles le seul chiffre que lit le directeur, la ligne de totaux, serait faux.
5. **Une conception indépendante du canal**, démontrée en pratique par la mise en service successive de deux messageries aux contraintes opposées, sans modification du cœur du système.

**Résultats.** La chaîne complète est opérationnelle depuis la première semaine du projet, avec un mécanisme de repli validé en conditions réelles. Le système compte 66 routes, 65 nœuds d'orchestration, 11 tables et 272 tests automatisés exécutables sans aucune clé d'API. *[À COMPLÉTER : latence de bout en bout mesurée et bilan du pilote.]*

**Limites.** Trois limites doivent être énoncées sans détour. D'abord, **le WER et le CER n'ont pas été calculés** : le choix d'une métrique applicative est argumenté au §4.3.2, mais il prive la comparaison d'un chiffre unique et universellement reconnu, et le classement final repose sur un jugement humain — rigoureux, mais non reproductible par un tiers sans le même locuteur. Ensuite, **la suite de tests ne parcourt jamais le réseau réel** ; elle sécurise les régressions de logique, non les ruptures de contrat des fournisseurs, qui ont été la source de la majorité des défauts rencontrés. Enfin, *[À COMPLÉTER : bilan du pilote en conditions réelles]*.

**Perspectives.** Plusieurs évolutions prolongent naturellement ce travail : constituer la vérité terrain qui manque, en s'appuyant sur les rapports réels accumulés, afin de publier un WER et un CER et de rendre le classement reproductible ; affiner un modèle de transcription sur ce corpus darija propre au câblage, l'apport de l'affinage étant désormais démontré pour un modèle assez grand ; remplacer Google Sheets par une base de données lorsque la volumétrie le justifiera, l'infrastructure PostgreSQL étant déjà en place ; étendre le tableau de bord vers l'analytique de chantier — avancement par site, consommation de matériel, alertes de stock, le bordereau en fournissant déjà la base ; et généraliser la plateforme à plusieurs équipes ou entreprises.

Au-delà du système livré, ce projet illustre une conviction d'ingénierie : dans les applications des grands modèles de langage, la valeur ne réside pas dans le choix des modèles, mais dans l'architecture qui les entoure — contrats de données stricts, chaînes de repli explicites, refus des échecs silencieux, et bancs d'essai assez sceptiques pour se surprendre eux-mêmes. Le banc d'essai de ce projet a renversé son hypothèse de départ deux fois, et démasqué un bogue qui lui faisait couronner un vainqueur sur une transcription jamais générée. C'est cette discipline, plus que le modèle finalement retenu, qui constitue le résultat le plus transférable de ce travail.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Références bibliographiques

[1] A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey et I. Sutskever, « Robust Speech Recognition via Large-Scale Weak Supervision », *Proceedings of the 40th International Conference on Machine Learning (ICML)*, PMLR vol. 202, pp. 28492–28518, 2023.

[2] Groq, « GroqCloud Documentation — Speech to Text & Chat Completions ». Disponible sur : https://console.groq.com/docs

[3] Google, « Gemini API Documentation — Structured Output & Audio Understanding ». Disponible sur : https://ai.google.dev/gemini-api/docs

[4] Telegram, « Telegram Bot API ». Disponible sur : https://core.telegram.org/bots/api

[5] Meta, « WhatsApp Business Platform — Cloud API Documentation ». Disponible sur : https://developers.facebook.com/docs/whatsapp

[6] n8n, « n8n Documentation — Workflow Automation ». Disponible sur : https://docs.n8n.io

[7] S. Ramírez, « FastAPI Documentation ». Disponible sur : https://fastapi.tiangolo.com

[8] Pydantic, « Pydantic Documentation — Data Validation ». Disponible sur : https://docs.pydantic.dev

[9] K. Schwaber et J. Sutherland, *The Scrum Guide*, 2020. Disponible sur : https://scrumguides.org

[10] E. Gamma, R. Helm, R. Johnson et J. Vlissides, *Design Patterns: Elements of Reusable Object-Oriented Software*, Addison-Wesley, 1994.

[11] A. Baevski, Y. Zhou, A. Mohamed et M. Auli, « wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Representations », *Advances in Neural Information Processing Systems (NeurIPS)*, vol. 33, pp. 12449–12460, 2020.

[12] A. Graves, S. Fernández, F. Gomez et J. Schmidhuber, « Connectionist Temporal Classification: Labelling Unsegmented Sequence Data with Recurrent Neural Networks », *Proceedings of the 23rd International Conference on Machine Learning (ICML)*, pp. 369–376, 2006.

[13] A. Bounhar, « Morocco-Darija-STT-large ». Hugging Face, licence Apache 2.0. Disponible sur : https://huggingface.co/BounharAbdelaziz/Morocco-Darija-STT-large

[14] E. J. Hu, Y. Shen, P. Wallis, Z. Allen-Zhu, Y. Li, S. Wang, L. Wang et W. Chen, « LoRA: Low-Rank Adaptation of Large Language Models », *International Conference on Learning Representations (ICLR)*, 2022.

*[À COMPLÉTER : références académiques additionnelles sur l'ASR de l'arabe dialectal, à ajouter selon les exigences de la filière.]*

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Annexes

## Annexe A : Cahier des charges

*[À INSÉRER — cahier des charges fourni par l'entreprise, reproduit intégralement. Source : `docs/cahier-des-charges.md`.]*

## Annexe B : Schéma de données et contrat d'API

Ce schéma n'est pas recopié : il est extrait du document OpenAPI que le service
publie lui-même, et il est donc par construction identique à ce que le code
valide à l'exécution.

### B.1 `ExtractedReport` — le rapport extrait

```json
{
  "properties": {
    "cables_prepares_m": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Cables Prepares M",
      "description": "Mètres de câble cuivre préparés (tirés et mesurés)"
    },
    "cables_installes_m": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Cables Installes M",
      "description": "Mètres de câble cuivre installés et raccordés"
    },
    "goulotte_m": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Goulotte M",
      "description": "Mètres de goulotte posés"
    },
    "prises_connectees": {
      "anyOf": [
        {
          "type": "integer",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Prises Connectees",
      "description": "Prises RJ45 raccordées côté bureau"
    },
    "panneaux_prises_brassees": {
      "anyOf": [
        {
          "type": "integer",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Panneaux Prises Brassees",
      "description": "Prises raccordées côté panneau de brassage"
    },
    "prises_testees": {
      "anyOf": [
        {
          "type": "integer",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Prises Testees",
      "description": "Prises testées et étiquetées"
    },
    "fibre_m": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Fibre M",
      "description": "Mètres de câble fibre optique posés"
    },
    "interconnexions": {
      "anyOf": [
        {
          "type": "integer",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Interconnexions",
      "description": "Nombre d'interconnexions installées entre locaux"
    },
    "connexions_optiques_brins": {
      "anyOf": [
        {
          "type": "integer",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Connexions Optiques Brins",
      "description": "Brins de fibre optique fusionnés/connectés"
    },
    "etages": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Etages",
      "description": "Étages travaillés (RDC, E1..E4)"
    },
    "ailes": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Ailes",
      "description": "Ailes (Droite, Gauche)"
    },
    "locaux_techniques": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Locaux Techniques",
      "description": "Locaux techniques (RG, SR1..SR10)"
    },
    "stock_cable_m": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Stock Cable M",
      "description": "Mètres de câble restants en stock sur site"
    },
    "stock_goulotte_m": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Stock Goulotte M",
      "description": "Mètres de goulotte restants en stock"
    },
    "stock_fibre_m": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Stock Fibre M",
      "description": "Mètres de fibre optique restants en stock"
    },
    "remarques": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Remarques",
      "description": "Problèmes, blocages, matériel manquant, remarques"
    },
    "resume": {
      "type": "string",
      "title": "Resume",
      "description": "Résumé professionnel en français (2-4 phrases)"
    }
  },
  "type": "object",
  "required": [
    "resume"
  ],
  "title": "ExtractedReport",
  "description": "Structured facts extracted from one daily report."
}
```

### B.2 `ProcessResponse` — la réponse de `POST /process`

```json
{
  "properties": {
    "rapport_complet": {
      "type": "string",
      "title": "Rapport Complet",
      "description": "Texte intégral (transcription brute ou texte du formulaire)"
    },
    "report": {
      "$ref": "#/components/schemas/ExtractedReport"
    },
    "transcription": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/TranscriptionInfo"
        },
        {
          "type": "null"
        }
      ],
      "description": "Absent en mode texte (formulaire)"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Warnings",
      "description": "Signaux qualité (ex: transcription douteuse) pour le flagging n8n"
    },
    "lien_audio": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Lien Audio",
      "description": "Lien durable (Google Drive) vers l'audio, quand l'upload a réussi. n8n le préfère au file_id de la chaîne, qui expire."
    }
  },
  "type": "object",
  "required": [
    "rapport_complet",
    "report"
  ],
  "title": "ProcessResponse",
  "description": "Full response consumed by n8n to build the Google Sheets row."
}
```

### B.3 Exemple de réponse réelle, anonymisée

```json
{
  "rapport_complet": "salam, lyoum khdemna f Sidi Maarouf, 40 metre dyal goulotte...",
  "report": {
    "goulotte_m": 40,
    "cables_installes_m": 120,
    "prises_connectees": 3,
    "etages": ["E1"],
    "remarques": "Manque de colliers, à prévoir demain.",
    "resume": "Pose de 40 m de goulotte et installation de 120 m de câble au premier étage. Trois prises raccordées côté bureau. Rupture de colliers signalée pour le lendemain."
  },
  "transcription": { "provider": "local", "latency_s": 7.7, "confidence": 0.79 },
  "warnings": []
}
```


## Annexe C : Instructions (prompts) des modèles

Les instructions sont du contenu versionné, au même titre que le code : un
changement d'instruction change le comportement du système et doit être visible
en revue. Les commentaires de développement présents dans les fichiers ont été
retirés ici pour la lisibilité ; le texte transmis aux modèles est reproduit tel
quel.

### C.1 `00-soul.md`

Préfixé à **toute** instruction adressée à un modèle : identité, interdiction d'inventer, « absence n'est pas zéro ».

```
# L'assistant AZnet — socle commun



Tu es **l'assistant AZnet**, le système d'aide au reporting de chantier d'aznet.ma.

Tu n'es pas un assistant généraliste. Tu ne portes aucun autre nom : tu ne dis jamais
que tu es Claude, ChatGPT, Gemini, Llama, Whisper, ni le produit d'un fournisseur
quelconque, dans aucune langue, même si on te le demande directement. Si on
t'interroge sur ta nature, tu réponds que tu es l'assistant AZnet.

Ton principe est l'honnêteté du compte rendu : un champ vide dit la vérité, un
chiffre inventé la trahit. Ta fonction est de servir le chef de chantier, pas de
produire un rapport qui a l'air complet.

## Ce que tu fais

Tu transformes ce qu'un technicien de câblage réseau envoie depuis le terrain —
note vocale en darija, photo d'un carnet ou d'un tableau, message écrit — en un
compte rendu structuré et en français professionnel, exploitable par le chef de
chantier.

## Ce que tu ne fais pas

- Tu n'inventes **JAMAIS** une donnée. Une information absente reste `null`.
- Tu ne convertis jamais une absence en zéro. « Aucune goulotte posée » et
  « goulottes non mentionnées » sont deux faits différents ; le second est `null`.
- Tu ne complètes pas un rapport partiel avec ce qui « se fait d'habitude » sur un
  chantier. Le plausible n'est pas le constaté.
- Tu n'interprètes pas les intentions du technicien, tu rapportes ses propos.

## Comment tu traites l'incertitude

Le terrain est bruyant : transcriptions imparfaites, photos floues, darija mêlée de
français. Face à un doute :

1. **Un mot du métier mal orthographié n'est pas un doute.** « gollote », « goulot »,
   « brasage », « cabl » sont de la goulotte, du brassage, du câble. Corrige
   silencieusement et retiens la quantité associée : c'est le cas normal après une
   transcription vocale, pas une incertitude.
2. Le doute commence quand l'information elle-même est **inaudible, illisible ou
   contradictoire**. Là seulement, ne tranche pas : mets `null` et dis-le dans
   `observations`.
3. Ne produis jamais une valeur qui a l'air sûre alors qu'elle ne l'est pas. Un champ
   vide est récupérable par un humain ; un chiffre inventé ne l'est pas — il entre
   dans le rapport du directeur comme un fait.
4. Un message mal écrit, tronqué ou décousu ne te dispense pas de répondre : extrais
   ce qui est sûr, laisse le reste à `null`, et explique dans `observations` ce qui
   manque. Tu ne demandes jamais de clarification — le technicien n'attend pas de
   réponse.

## Ton et forme

Français professionnel, 3e personne, style compte rendu. Pas de formules de
politesse, pas d'emoji, pas de mise en forme décorative. Tu écris pour un chef de
chantier qui lit vingt rapports d'affilée.

Ni mots de remplissage (« bien sûr », « certainement », « bien entendu », « veuillez »),
ni formules d'ouverture ou de clôture, ni commentaire sur la forme du message
d'origine (orthographe, accent, qualité audio ou photo) : tu rapportes le contenu,
jamais le contenant.
```

### C.2 `extraction-text.md`

L'instruction principale : elle porte le vocabulaire du câblage et la règle du champ nul.

```
# Extraction — texte



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
   accès refusé, arrêt de chantier, incidents. Une journée sans un seul mètre
   posé mais avec un blocage **est** un rapport : c'est celui qui compte le plus.
9. **`resume`** — 2 à 4 phrases, français professionnel, 3e personne, destiné au chef
   de chantier. Toujours rempli, même si tout le reste est `null` : dans ce cas il
   explique pourquoi la journée n'a produit aucun chiffre. Sans mot de remplissage
   ni hésitation (« probablement », « il semble que », « je pense ») : soit le fait
   est établi, soit c'est une incertitude à porter dans `remarques`.

## Rappel

Le champ le plus important de ce schéma n'est pas celui que tu remplis, c'est celui
que tu laisses vide quand tu ne sais pas.

Rapport du technicien :
```

### C.3 `extraction-image.md`

Variante pour la voie photo : le modèle de vision lit le relevé et remplit le même schéma en un seul appel.

```
# Extraction — image



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

Les règles générales d'extraction (nombres en lettres, unités en mètres, absence =
`null`, nombres qui ne sont pas des quantités, distinction préparé / installé /
brassé / testé, stock jamais déduit) s'appliquent à l'identique.
```

### C.4 `profile.md`

Rédaction du profil nocturne. Les nombres y sont explicitement interdits.

```
# Profil technicien — mémoire de long terme



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
```

### C.5 `stt-vocabulary.md`

**Seul fichier sans le socle commun** : Whisper lit son paramètre `prompt` comme la transcription précédant le clip, et non comme des consignes — le socle y serait recopié dans la transcription.

```
# STT — amorce de vocabulaire



Rapport de chantier, aznet, câblage réseau. Salam, lyoum f chantier Marina Center,
client OCP. Rakebna miya w khamsin metre dyal goulotte f couloir, w jerrina tmn miya
metre dyal câble réseau. Kmmalna khamsa dyal bureaux f l'étage l'lewel, w raccordina
juj panneaux de brassage. Prise RJ45, baie de brassage, chemin de câbles, goulotte,
gaine, fibre optique, tableau électrique, faux plafond. Kayn chi problème f
l'ascenseur, ma qdrnach ntl3o l'étage tmnya. Khass matériel ghedda : goulottes w
colliers. Chantier Anfa Place, Technopark, Casa Finance City, Zenith Millenium,
Bouskoura, Sidi Maarouf. Client Attijari, Maroc Telecom, CNSS, Renault.
```

### C.6 `image-generation.md`

Génération de la carte illustrée de synthèse.

```
# Génération d'image — carte de synthèse



Tu produis une **carte de synthèse illustrée** résumant l'activité d'une journée ou
d'une semaine de chantier, à partir des chiffres qui te sont fournis.

## Contraintes absolues

- **Style illustration, jamais photographie.** Rendu graphique plat, vectoriel,
  éditorial. Aucune image photoréaliste de chantier, de personne ou de matériel :
  elle serait indiscernable d'une vraie photo de terrain une fois insérée dans un
  rapport.
- **Aucun chiffre inventé.** Seuls les nombres fournis dans le contexte peuvent
  apparaître. Si un chiffre manque, il n'apparaît pas — tu ne le remplaces ni par une
  estimation ni par un exemple.
- **Aucun visage identifiable**, aucun nom de technicien, aucun logo de client réel.
- **Texte lisible et minimal** : les libellés en français, courts, sans faute.

## Composition

Palette sobre et professionnelle — gris ardoise, blanc cassé, un seul bleu d'accent.
Mise en page claire : un titre, les quantités mises en avant comme des chiffres clés,
des pictogrammes simples pour les catégories (goulotte, câble, bureaux, panneaux).
Format paysage, marges généreuses, pas de dégradé chargé ni de décor superflu.

## Contexte fourni

Les données réelles de la période suivent. Utilise-les telles quelles.
```


## Annexe D : Workflow n8n documenté

*[À INSÉRER — export JSON du workflow (65 nœuds) et captures d'écran annotées du canvas.]*

## Annexe E : Documentation d'installation

### E.1 Prérequis

Docker et Docker Compose ; Python 3.11 et Node.js pour le développement hors
conteneur ; une carte NVIDIA avec pilote à jour **uniquement** si le moteur de
transcription local est utilisé ; un compte de service Google disposant d'un
accès en écriture au seul classeur de suivi.

### E.2 Configuration

Toute la configuration est portée par un fichier `.env` non versionné, dont un
modèle documenté (`.env.example`) accompagne le dépôt. Les clés d'API sont
optionnelles au démarrage et vérifiées à l'appel : le service démarre sans
secret — ce qui est nécessaire aux tests automatisés — mais échoue avec un
message explicite si un appel en requiert un. Le mot de passe de la base n'a
délibérément aucune valeur par défaut, afin qu'un déploiement mal configuré
échoue bruyamment plutôt que de démarrer avec un mot de passe connu.

### E.3 Démarrage de la pile

```bash
docker compose up -d
```

Cinq services démarrent : `postgres`, `n8n`, `api`, `stt-local` et `web`. Un
seul port est publié, celui du proxy, qui sert le tableau de bord, l'API sous
`/api/` et les webhooks sous `/webhook/`. Les trois services centraux sont en
redémarrage automatique, de sorte que la chaîne se rétablit seule après un
redémarrage de la machine.

### E.4 Développement du service

```bash
cd api
.venv/Scripts/python.exe -m pytest              # 272 tests, sans aucune clé d'API
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

### E.5 Deux pièges de déploiement

Ces deux points ont réellement coûté du temps et méritent d'être connus, car
dans les deux cas **une modification peut sembler appliquée sans être exécutée** :

1. Le service est une **image construite**, code source inclus. Un simple
   redémarrage du conteneur réexécute l'ancien code ; il faut reconstruire
   l'image.
2. n8n conserve **sa propre copie** du workflow dans son volume. Modifier le
   fichier JSON versionné ne change rien tant qu'il n'a pas été réimporté ou
   poussé par l'API de n8n.

### E.6 Étape manuelle après l'import du workflow

Le gestionnaire d'erreurs n'est actif que si le workflow est désigné comme son
propre *Error Workflow* dans ses paramètres. Sans cette manipulation, le
déclencheur d'erreur ne se déclenche jamais.


## Annexe F : Guide utilisateur

*[À INSÉRER — guide d'une page : comment envoyer son rapport vocal, les commandes disponibles, que faire en cas d'erreur.]*

## Annexe G : Protocole et données du banc d'essai

### G.1 Protocole

**Corpus.** Onze notes vocales réelles issues des échanges des techniciens,
en darija spontanée avec code-switching français, de durées et de conditions
d'enregistrement variées.

**Campagnes.** Trois passes successives : trois moteurs accessibles par API ;
neuf moteurs exécutés localement ; puis douze moteurs, une fois obtenus les
accès aux deux dépôts sous licence.

**Matériel.** NVIDIA RTX 3070 (8 Go), demi-précision, PyTorch avec CUDA.

**Mesures relevées.** Transcription intégrale, latence, mesure de confiance
propre au moteur, longueur du texte, et nombre de chiffres émis.

**Critère de décision.** Ni WER ni CER — voir §4.3.2 pour la justification —
mais la préservation des quantités et des emprunts techniques français,
vérifiée clip par clip, puis **confirmée à l'oreille par un locuteur natif du
darija**.

### G.2 Catalogue des moteurs évalués

| Moteur | Famille | Voie |
|---|---|---|
| `whisper-large-v3` via Groq | Whisper | API |
| Gemini (audio natif) | Multimodal | API |
| Affinage darija via Hugging Face | Whisper | API (jamais fonctionnel, voir §4.3.6) |
| `BounharAbdelaziz/Morocco-Darija-STT-large` | Whisper affiné | Local |
| `openai/whisper-large-v3` | Whisper (contrôle) | Local |
| `openai/whisper-large-v3-turbo` | Whisper (contrôle) | Local |
| `ychafiqui/whisper-medium-darija` | Whisper affiné | Local |
| `ychafiqui/whisper-small-darija` | Whisper affiné | Local |
| `KandirResearch/Whisper-Small-Darija` | Whisper affiné | Local (échec de chargement) |
| `TaloCreations/whisper-darija-finetuned` | Whisper affiné | Local |
| `C-Ilyas/whisper-base-darija` | Whisper affiné | Local |
| `boumehdi/wav2vec2-large-xlsr-moroccan-darija` | wav2vec2 | Local |
| `amineouaki/wav2vec2-darija-combined` | wav2vec2 | Local |
| `amineouaki/wav2vec2-large-xlsr-53-darija-combined` | wav2vec2 | Local |
| `anaszil/whisper-large-v3-turbo-darija` | Adaptateur LoRA | Local (non fusionné) |
| `Qwen/Qwen3-ASR-1.7B` | Autre | Local (sans exécuteur) |

**Tableau G.1 :** Catalogue des moteurs téléchargés et évalués.

### G.3 Reproductibilité

Le catalogue des points de contrôle et le harnais d'exécution sont versionnés
dans le dépôt ; les poids eux-mêmes ne le sont pas — 5,8 Go, dont un fragment de
4,7 Go, ce qui dépasse la limite par fichier de Git LFS. Le script de
téléchargement les reconstitue à l'identique, deux d'entre eux exigeant
l'acceptation préalable d'une licence sur la plateforme.

### G.4 Limite assumée

Le fichier de transcriptions de référence est resté vide : le WER et le CER
n'ont donc **pas** été calculés. Le classement final repose sur une lecture
experte et une validation par un locuteur natif, ce qui est rigoureux mais non
reproductible par un tiers sans ce même locuteur. Constituer cette vérité
terrain à partir des rapports réels accumulés est la première des perspectives
énoncées en conclusion.

