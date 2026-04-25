# Déploiement — Fly.io (backend) + Vercel (frontend)

Objectif : app publique à `https://audit-bureau.vercel.app` qui appelle un
backend FastAPI hébergé sur Fly.io.

Coût attendu : **0 € / mois** tant qu'on reste dans le free tier Fly (3
machines shared-cpu-1x + 3GB volume) et que Vercel reste en Hobby.

---

## 0. Prérequis (une seule fois)

### Outils à installer localement

```bash
# Fly CLI
brew install flyctl
fly auth login

# Vercel CLI
npm i -g vercel
vercel login
```

### Comptes

- Fly.io : https://fly.io/app/sign-up (CB requise mais rien facturé tant que tu restes gratuit)
- Vercel : https://vercel.com/signup (gratuit, OAuth GitHub recommandé)
- Gemini : clé déjà en place dans `api/.env` (tier Partner, pas de quota)

---

## 1. Première mise en ligne — backend Fly.io

Depuis la racine du repo :

```bash
# 1. Provisionner l'app Fly (ne déploie pas encore)
fly launch \
  --no-deploy \
  --copy-config \
  --name audit-bureau-api \
  --region cdg \
  --org personal

# 2. Créer le volume persistent pour SQLite + branding logo
fly volumes create audit_data --size 1 --region cdg --app audit-bureau-api

# 3. Injecter les secrets (variables d'env chiffrées Fly)
fly secrets set \
  LLM_PROVIDER=gemini \
  GEMINI_API_KEY=AIza... \
  GEMINI_MODEL=gemini-3-pro-preview \
  ALLOWED_ORIGINS=https://audit-bureau.vercel.app \
  ALLOWED_ORIGIN_REGEX='^https://audit-bureau-.*\.vercel\.app$' \
  PLAYWRIGHT_ENABLED=false \
  --app audit-bureau-api

# 4. Déployer
fly deploy --remote-only
```

Récupère l'URL : typiquement `https://audit-bureau-api.fly.dev`.

Tester :

```bash
curl https://audit-bureau-api.fly.dev/health
# {"status":"ok","provider":"gemini","model":"gemini-3-pro-preview"}
```

### Option — Postgres managé Fly (recommandé dès qu'il y a plusieurs audits/jour)

SQLite sur volume marche mais est lié à une seule machine. Pour scaler :

```bash
fly postgres create --name audit-bureau-db --region cdg --initial-cluster-size 1
fly postgres attach audit-bureau-db --app audit-bureau-api
# Ça injecte automatiquement DATABASE_URL dans les secrets de l'app
fly deploy --remote-only
```

---

## 2. Première mise en ligne — frontend Vercel

```bash
# À la racine du repo (Vercel détecte Next.js automatiquement)
vercel --prod
```

Réponses au prompt :
- **Set up and deploy?** → Y
- **Which scope?** → ton compte perso
- **Link to existing project?** → N
- **Project name?** → `audit-bureau`
- **In which directory?** → `.`
- **Want to override settings?** → N

Une fois déployé, va dans **Vercel dashboard → Settings → Environment Variables** et ajoute :

| Variable | Valeur | Environnements |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://audit-bureau-api.fly.dev` | Production, Preview, Development |

Puis redéployer :

```bash
vercel --prod
```

Teste sur `https://audit-bureau.vercel.app` ou le sous-domaine donné par Vercel.

---

## 3. Mises à jour suivantes

```bash
# Backend
make deploy-api
# ou : fly deploy --remote-only

# Frontend
make deploy-web
# ou : vercel --prod
```

Chaque `git push` sur `main` déclenche automatiquement un déploiement Vercel
(GitHub integration). Fly.io ne déploie que sur commande explicite.

---

## 4. Commandes utiles Fly

```bash
make logs          # logs live
make status        # état des machines
make secrets       # liste des secrets (masqués)
make console       # SSH dans une machine
fly scale count 1  # plus qu'une machine (assez pour MVP)
fly restart        # redémarrer sans redéployer
```

---

## 5. Dépannage courant

### Le container OOM-kill

512MB suffit sans Playwright. Si tu actives Playwright en prod plus tard :

```bash
fly scale memory 1024
```

### Les audits persistent pas

Vérifie que le volume est bien monté : `fly volumes list --app audit-bureau-api`.
Le `fly.toml` spécifie `destination = "/app/api/data"`, ce qui est le chemin
par défaut de notre SQLite.

### CORS bloque le front

Vérifier que `ALLOWED_ORIGINS` contient l'URL exacte Vercel :

```bash
fly secrets set ALLOWED_ORIGINS=https://audit-bureau.vercel.app --app audit-bureau-api
fly deploy --remote-only
```

Pour autoriser les previews Vercel (branches) :

```bash
fly secrets set \
  ALLOWED_ORIGIN_REGEX='^https://audit-bureau-.*\.vercel\.app$' \
  --app audit-bureau-api
```

### Le Dockerfile foire à cause de lxml

Déjà pris en charge par le `builder` stage multi-step. Si ça arrive malgré
tout, augmente temporairement la mémoire build :

```bash
fly deploy --remote-only --build-arg LXML_WITHOUT_STATIC=1
```

---

## 6. Architecture finale

```
┌──────────────────────┐          ┌───────────────────────┐
│ Vercel               │   HTTPS  │ Fly.io (Paris)        │
│ audit-bureau.        │──────────▶ audit-bureau-api.     │
│   vercel.app         │          │   fly.dev             │
│                      │          │                       │
│ Next.js 14 App Router│          │ FastAPI + uvicorn     │
│ React server comps   │          │ SQLAlchemy + SQLite   │
│ Build @ git push     │          │  ou Postgres managé   │
└──────────────────────┘          │                       │
                                  │ Crawler httpx + BS4   │
                                  │ LLM = Gemini 3 Pro    │
                                  │ PDF ReportLab         │
                                  │ XLSX openpyxl         │
                                  │                       │
                                  │ /app/api/data vol.    │
                                  └───────────────────────┘
```

Front et back sont strictement découplés. Un push code = deux déploiements
indépendants qui peuvent réussir séparément.
