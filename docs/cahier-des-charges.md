# Cahier des charges – MVP Rapport Journalier des Techniciens Câblage

> Version texte extraite de `Documents/Cahier des charges generation de rapport journalier.docx` (source de vérité).

## 1. Objectif

Développer une solution simple permettant aux techniciens de câblage de transmettre leur rapport journalier en moins de deux minutes, sans rédaction complexe. Le rapport pourra être envoyé soit :
- par message vocal (prioritaire) ;
- par formulaire Web (alternative).

La solution devra transformer automatiquement les informations en données structurées et les enregistrer dans un tableau de suivi.

## 2. Cas d'utilisation

En fin de journée, le technicien envoie un message vocal en arabe marocain. Exemple :

> Installation de 150 m de goulotte, tirage et pose de 800 m de câble informatique, finition de 5 bureaux du 1er étage, connexion de 2 panneaux de brassage.

Ce rapport peut être introduit à partir d'un formulaire ou, mieux, dicté par message vocal en arabe marocain via WhatsApp ou Slack.

Le système devra automatiquement :
1. transcrire le message vocal en texte ;
2. comprendre les travaux réalisés ;
3. reformuler le rapport en français professionnel ;
4. enregistrer les données dans Google Sheets ;
5. envoyer un résumé au responsable.

## 3. Données à enregistrer

Chaque rapport devra contenir au minimum : Date · Heure · Nom du technicien · Chantier · Client · Type d'activité · Quantité de goulottes installées (m) · Quantité de câbles posés (m) · Nombre de bureaux terminés · Nombre de panneaux raccordés · Autres travaux · Observations · Texte complet du rapport · Lien vers le message vocal (option).

## 4. Mode de saisie

**Option 1 (prioritaire)** — Message vocal WhatsApp. Le technicien envoie simplement une note vocale. Aucune saisie supplémentaire n'est nécessaire.

**Option 2** — Petit formulaire Web comprenant : Nom · Chantier · Zone de texte libre ou champs standards (ex. nombre de prises installées, câbles installés…).

## 5. Traitement automatique

Le système devra : recevoir le message ; transcrire l'audio en texte (prise en charge de l'arabe marocain et du mélange arabe/français utilisé sur les chantiers) ; identifier automatiquement les quantités et les travaux réalisés ; reformuler le rapport dans un français professionnel ; enregistrer les informations dans Google Sheets ; notifier les responsables.

## 6. Format Google Sheets

Chaque ligne correspond à un rapport. Colonnes : Date · Technicien · Chantier · Client · Goulottes (m) · Câbles réseau (m) · Bureaux terminés · Panneaux raccordés · Autres travaux · Résumé · Rapport complet.

## 7. Notifications

À chaque nouveau rapport, envoi automatique d'un message contenant : Nom du technicien · Chantier · Résumé des travaux · Heure de réception.

Destinataires : Chef de chantier, Responsable technique. Le canal de notification (e-mail, WhatsApp ou Microsoft Teams) sera configurable.

## 8. Outils recommandés

- **Automatisation** : n8n
- **Canal de réception** : WhatsApp Business API (ou passerelle équivalente) ou Slack
- **IA** : modèle de transcription vocale compatible arabe marocain ; modèle de langage pour restructurer et résumer
- **Stockage** : Google Sheets (MVP), évolution possible vers PostgreSQL ou Supabase
- **Notifications** : e-mail, WhatsApp (si disponible), Microsoft Teams (option)

## 9. Workflow

Technicien → Message vocal WhatsApp → n8n → Transcription automatique → Analyse IA → Création d'un résumé professionnel → Enregistrement dans Google Sheets → Notification automatique aux responsables.

## 10. Livrables

- Workflow n8n entièrement documenté
- Configuration de la réception des messages
- Configuration de la transcription IA
- Google Sheets structuré
- Prompts IA pour l'analyse et la reformulation
- Documentation d'installation
- Guide utilisateur
