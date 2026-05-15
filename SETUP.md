# Audit Bureau — Setup local

Guide pour lancer le projet en local. Pour le contexte fonctionnel, voir `CLAUDE.md` et `docs/CONTEXTE-PROJET.md`.

---

## Stack

- **Frontend** : Next.js 14 (App Router) + TypeScript + Tailwind — port `3000`
- **Backend** : FastAPI (Python 3.11) — port `8000`
- **Base de données** : SQLite local (fichier `api/data/audit-bureau.db`, auto-créé)
- **LLM** : Gemini (clé gratuite sur https://aistudio.google.com/apikey) ou Anthropic

---

## Prérequis

- **Node.js 20+** : https://nodejs.org/ (ou `brew install node` sur Mac)
- **Python 3.11+** : https://www.python.org/downloads/ (ou `brew install python@3.11` sur Mac)
- **Git** : https://git-scm.com/
- **Une clé API Gemini** (gratuit) : https://aistudio.google.com/apikey

Vérif :
```bash
node -v    # v20.x ou +
python3 -V # 3.11 ou +
git --version
```

---

## Installation (première fois)

### 1. Cloner le repo

```bash
git clone https://github.com/messernoa29/test.git audit-bureau
cd audit-bureau
```

### 2. Installer les dépendances frontend

```bash
npm install
```

### 3. Installer les dépendances backend (dans un virtualenv Python)

```bash
python3 -m venv .venv
source .venv/bin/activate         # Mac/Linux
# Windows PowerShell : .venv\Scripts\Activate.ps1
# Windows cmd       : .venv\Scripts\activate.bat

pip install -r api/requirements.txt
```

> À chaque nouvelle session terminal il faudra réactiver le venv avec `source .venv/bin/activate` avant de lancer le backend.

### 4. Configurer le backend (`api/.env`)

Crée le fichier `api/.env` à la racine du dossier `api/` avec ce contenu :

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=colle_ta_cle_ici
GEMINI_MODEL=gemini-3-flash-preview

APP_PASSWORD=choisis_un_mot_de_passe
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

CRAWL_CONCURRENCY=16
```

Optionnel :
- `PAGESPEED_API_KEY=...` si tu veux les vraies données Lighthouse (sinon l'audit perf fonctionne en mode dégradé)
- Pour utiliser Anthropic à la place de Gemini : `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=sk-ant-...` + `ANTHROPIC_MODEL=claude-sonnet-4-6`

### 5. Configurer le frontend (`.env.local`)

À la racine du projet :

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Lancer le projet

Il faut **deux terminaux** ouverts en parallèle (un pour le backend, un pour le frontend).

### Terminal 1 — Backend

```bash
cd audit-bureau
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

Tu dois voir :
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

Test rapide :
```bash
curl http://localhost:8000/health
# → {"status":"ok","provider":"gemini",...}
```

### Terminal 2 — Frontend

```bash
cd audit-bureau
npm run dev
```

Tu dois voir :
```
▲ Next.js 14.x
- Local: http://localhost:3000
✓ Ready in ...ms
```

### Utiliser l'application

Ouvre **http://localhost:3000** dans ton navigateur.

Login avec le `APP_PASSWORD` que tu as mis dans `api/.env`.

---

## Commandes utiles

```bash
# Type-check TypeScript (frontend)
npm run type-check

# Lint
npm run lint

# Build production frontend
npm run build

# Tests Python (backend)
source .venv/bin/activate
python3 -m pytest api/tests/ -q

# Régénérer l'OpenAPI après modif des routes
python3 -m api.scripts.export_openapi
```

---

## Problèmes courants

### `ModuleNotFoundError: No module named 'api'` au lancement uvicorn

Tu as lancé depuis le mauvais dossier. Lance toujours depuis la racine du projet avec :
```bash
uvicorn api.main:app --reload --port 8000
```
Pas `uvicorn main:app` depuis `api/`.

### `GEMINI_API_KEY missing for LLM_PROVIDER=gemini`

Le fichier `api/.env` n'est pas lu. Vérifie :
- qu'il existe bien à `api/.env` (pas `.env` à la racine)
- que la variable s'appelle exactement `GEMINI_API_KEY`
- que tu lances uvicorn **depuis la racine** du projet (pas depuis `api/`)

### `Backend injoignable` côté frontend

CORS : `ALLOWED_ORIGINS` dans `api/.env` doit contenir l'URL exacte du frontend (`http://localhost:3000`). Redémarre le backend après modification.

### Le frontend tourne mais reste sur l'écran de login

`NEXT_PUBLIC_API_URL` dans `.env.local` doit pointer vers le backend (`http://localhost:8000`). Si tu modifies `.env.local`, **redémarre `npm run dev`** — Next ne recharge pas les env vars à chaud.

### `port 8000 already in use`

Un uvicorn d'une session précédente tourne encore :
```bash
lsof -ti:8000 | xargs kill -9
```

### Audit qui reste bloqué en "pending"

Un job zombie d'un ancien process. Supprime-le depuis l'UI (bouton corbeille sur la liste des audits) ou redémarre le backend.

---

## Mise à jour du projet

```bash
git pull
npm install                       # si package.json a changé
source .venv/bin/activate
pip install -r api/requirements.txt  # si requirements.txt a changé
```

---

## Données

- Audits, fiches prospect, etc. sont stockés dans `api/data/audit-bureau.db` (SQLite).
- Pour repartir de zéro : `rm api/data/audit-bureau.db` puis relance le backend (recréé automatiquement).
- Pour exporter : le fichier `.db` est portable, copie-le.

---

## Auth & multi-utilisateurs

Un seul mot de passe partagé (`APP_PASSWORD`). Toute personne qui le connaît a accès à **tout l'historique** (pas de cloisonnement par utilisateur).
