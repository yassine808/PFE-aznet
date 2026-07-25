# À FAIRE — remise en service

État constaté le 2026-07-25 : **Telegram répond « ❌ Erreur… », WhatsApp ne répond pas du tout.**
Deux causes distinctes, aucune dans le code.

| Constat | Preuve |
|---|---|
| L'API ne tourne pas | `curl localhost:8000/health` → injoignable, rien n'écoute sur `:8000` |
| Postgres n'est pas démarré | `docker ps` → seul `pfe-n8n` tourne |
| Le tunnel est mort | `curl https://intervals-coding-owner-perceived.trycloudflare.com/` → HTTP 000 |
| `API_BASE_URL` absent du conteneur | `docker exec pfe-n8n printenv` → variable absente (conteneur démarré avant la mise à jour de `docker-compose.yml`) |

**Pourquoi Telegram et WhatsApp échouent différemment :** Telegram fonctionne en *polling* (`getUpdates`), une connexion sortante qui n'a besoin d'aucun tunnel. Le message arrive donc jusqu'à `POST /process`, qui échoue parce que l'API est éteinte → branche d'erreur → « ❌ Erreur… ». WhatsApp fonctionne en *webhook* : Meta doit joindre n8n depuis Internet via le tunnel. Le tunnel étant mort, Meta n'atteint jamais n8n, aucun nœud ne s'exécute, d'où le silence complet.

---

## Étape 1 — Tunnel permanent (ngrok, gratuit)

Le tunnel `trycloudflare` actuel change d'URL à **chaque redémarrage**, ce qui oblige à reconfigurer le webhook Meta à chaque fois. Un tunnel nommé Cloudflare nécessite un domaine (non disponible). La meilleure option gratuite : le **domaine statique offert par ngrok** (1 par compte gratuit), qui ne change jamais.

1. https://dashboard.ngrok.com → **Domains** → **Create Domain** → ex. `aznet-pfe.ngrok-free.app`
2. Installer et authentifier :
   ```bash
   choco install ngrok           # ou téléchargement sur ngrok.com/download
   ngrok config add-authtoken <TOKEN du dashboard>
   ```
3. Lancer (laisser tourner) :
   ```bash
   ngrok http --url=aznet-pfe.ngrok-free.app 5678
   ```
   Même commande à chaque démarrage — **l'URL ne change plus jamais**.

## Étape 2 — Variables d'environnement

Ajouter dans `.env` à la racine du dépôt :

```bash
WEBHOOK_URL=https://aznet-pfe.ngrok-free.app/
DATABASE_URL=postgresql://pfe:pfe@localhost:5432/pfe_logs
API_BASE_URL=http://host.docker.internal:8000
POSTGRES_USER=pfe
POSTGRES_PASSWORD=pfe
POSTGRES_DB=pfe_logs
```

⚠️ La barre oblique finale de `WEBHOOK_URL` est obligatoire : n8n y concatène les chemins.

## Étape 3 — Recréer les conteneurs

```bash
docker compose up -d
```

Recrée `pfe-n8n` avec `API_BASE_URL` + `extra_hosts`, et démarre `pfe-postgres`.
Vérifier : `docker exec pfe-n8n printenv | grep API_BASE_URL` doit renvoyer une valeur.

## Étape 4 — Démarrer l'API

```bash
cd api && .venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Attendu au démarrage : `[logs] postgres schema ready`.
Si le message est `[logs] DISABLED — …`, c'est que `DATABASE_URL` est absent ou que Postgres n'est pas joignable.

## Étape 5 — Importer le workflow

Importer **`n8n/aznet-complete.json`** (un seul fichier : réception + maintenance + rapport quotidien + erreurs).

Puis :
1. **Settings → Error Workflow → ce workflow lui-même** (le champ est vide car il attend l'ID attribué par n8n à l'import).
2. Rattacher les identifiants : compte de service Google, Telegram, WhatsApp, Gmail.
3. Activer.

## Étape 6 — Webhook Meta

Meta dashboard → **WhatsApp → Configuration → Webhook** :
- URL de rappel : `https://aznet-pfe.ngrok-free.app/webhook/<chemin du nœud WA Webhook verify (GET)>`
- Relancer la vérification, confirmer l'abonnement au champ `messages`.

À faire **une seule fois** grâce au domaine statique.

---

## Vérification finale

1. Note vocale Telegram → réponse avec le résumé (pas « ❌ Erreur »).
2. Même note en WhatsApp → même réponse.
3. Tableau de bord → panneau **Logs n8n** : les étapes `received → transcribed → extracted → replied → sheet_written` apparaissent, reliées par un même `correlation_id`.
4. Nouvelle ligne dans l'onglet `Rapports`.

## Non testé à ce jour

Le graphe réécrit (réponse-avant-Sheet, déduplication durable, file de reprise) est **validé structurellement mais jamais exécuté** : aucun message n'y est encore passé, et Postgres n'a jamais démarré, donc le schéma n'a jamais été créé sur un serveur réel.
