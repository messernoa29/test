# CLAUDE.md — Outil d'Audit Web IA

> Fichier lu automatiquement par Claude Code à chaque session. Concis, précis, actionnable.

---

## Projet

Application web d'audit de sites web propulsée par l'IA. Une agence digitale entre une URL, l'IA crawle le site, analyse 6 axes (sécurité, SEO, UX, contenu, performance, opportunités business) et génère un rapport PDF professionnel téléchargeable.

**Trois fichiers de référence à lire si besoin de contexte approfondi :**
- `docs/CONTEXTE-PROJET.md` — historique complet, décisions techniques, roadmap
- `docs/DESIGN.md` — système de design complet (typographie, couleurs, composants)
- `docs/SELF-IMPROVEMENT.md` — erreurs passées et règles à ne jamais enfreindre

---

## Stack technique

```
Frontend   : Next.js 14 (App Router) + TypeScript
Styling    : Tailwind CSS + variables CSS custom (voir DESIGN.md)
Backend    : FastAPI (Python 3.11)
IA         : Anthropic ou Gemini — switch via LLM_PROVIDER dans api/.env
             · Anthropic: claude-sonnet-4-6 (défaut)
             · Gemini:    gemini-2.5-flash (AI Studio free tier)
             Abstraction: api/services/llm/ (base.py + anthropic_provider.py + gemini_provider.py)
             Doc provider Gemini: docs/GEMINI-API.md
PDF        : ReportLab (Python) — déjà testé et validé
Hébergement: Vercel (frontend) + Railway (backend)
```

---

## Structure du projet

```
/
├── app/                    # Next.js App Router
│   ├── page.tsx            # Page d'accueil — formulaire URL
│   ├── audit/[id]/         # Page de résultats d'un audit
│   └── layout.tsx          # Layout global
├── components/             # Composants React réutilisables
│   ├── ui/                 # Composants de base (Badge, Card, Button...)
│   ├── audit/              # Composants spécifiques à l'audit
│   └── pdf/                # Prévisualisation du rapport
├── lib/                    # Utilitaires et helpers
│   ├── anthropic.ts        # Client Anthropic + logique d'appel
│   ├── pdf.py              # Génération PDF (ReportLab)
│   └── types.ts            # Types TypeScript partagés
├── api/                    # FastAPI backend
│   ├── main.py             # Point d'entrée FastAPI
│   ├── routes/audit.py     # Routes d'audit
│   └── services/           # Services métier
├── docs/                   # Documentation projet
│   ├── CONTEXTE-PROJET.md
│   ├── DESIGN.md
│   └── SELF-IMPROVEMENT.md
├── public/                 # Assets statiques
├── CLAUDE.md               # Ce fichier
└── .claude/
    ├── commands/           # Slash commands personnalisées
    └── settings.local.json # Config locale (gitignorée)
```

---

## Commandes essentielles

```bash
# Développement
npm run dev          # Lance le frontend Next.js (port 3000)
cd api && uvicorn main:app --reload  # Lance le backend FastAPI (port 8000)

# Tests
npm run test         # Tests Jest (frontend)
pytest api/          # Tests Python (backend)
npm run type-check   # Vérification TypeScript

# Build
npm run build        # Build production Next.js
npm run lint         # ESLint + Prettier check

# PDF (test local)
cd api && python services/pdf_generator.py  # Génère un PDF de test
```

---

## Variables d'environnement

```bash
# .env.local (frontend)
NEXT_PUBLIC_API_URL=http://localhost:8000

# api/.env (backend)
LLM_PROVIDER=anthropic          # or "gemini"
ANTHROPIC_API_KEY=sk-ant-...    # used when LLM_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-sonnet-4-6
GEMINI_API_KEY=                 # used when LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
ALLOWED_ORIGINS=http://localhost:3001,http://127.0.0.1:3001

# Persistance (dev = SQLite auto, prod = Postgres)
# DATABASE_URL=sqlite:///api/data/audit-bureau.db
# DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db
```

---

## Règles de code — non négociables

### TypeScript
- Typage strict — jamais de `any`
- Interfaces explicites pour toutes les réponses API
- Pas de `// @ts-ignore`

### Python
- Type hints sur toutes les fonctions
- Docstrings sur les fonctions publiques
- Gestion d'erreurs explicite — pas de `except: pass`

### CSS / Styling
- Utiliser les variables CSS définies dans `DESIGN.md` — jamais de hex hardcodé
- Polices : DM Serif Display (titres/scores) + DM Sans (corps) + JetBrains Mono (données)
- Palette sombre : `--bg-page: #0F0F0D`, accent or : `--accent: #D4A853`
- Jamais de border-radius > 8px sur les éléments de données
- Jamais de gradients ni de box-shadow décoratifs

### Composants React
- Un composant par fichier
- Props typées avec TypeScript interfaces
- `'use client'` uniquement si nécessaire (pas par défaut)

---

## Architecture de l'appel IA

Le flux d'audit se fait en **2 étapes séquentielles** — ne jamais les fusionner :

```
1. CRAWL    → Claude visite toutes les pages, retourne les données brutes
              (title exact, H1, meta, URLs, mots-clés)

2. ANALYSE  → Claude analyse les données du crawl et produit le JSON structuré
              Format : AuditResult (voir lib/types.ts)
```

```python
# Pattern d'appel provider-agnostique (dispatch via LLM_PROVIDER)
from api.services.llm import get_llm_client

response = get_llm_client().generate(
    system=SYSTEM_PROMPT,
    user_prompt=USER_PROMPT,
    max_tokens=8000,
    enable_web_search=True,  # web_search (Anthropic) ou google_search (Gemini)
)
# response.text, response.stop_reason ("end"|"max_tokens"|"safety"|"other"),
# response.raw_stop_reason, response.input_tokens, response.output_tokens
```

---

## Format de sortie IA attendu

Le modèle doit retourner un JSON structuré selon `AuditResult` dans `lib/types.ts`. Les sections clés :

```typescript
interface AuditResult {
  domain: string
  url: string
  globalScore: number        // 0-100
  globalVerdict: string      // "À consolider", "Bon niveau", etc.
  scores: Record<AuditSection, number>
  sections: SectionResult[]
  criticalCount: number
  warningCount: number
  quickWins: string[]
  pages?: PageAnalysis[]     // Pour l'audit SEO approfondi
  missingPages?: MissingPage[]
}
```

---

## Erreurs connues — à ne pas reproduire

Voir `docs/SELF-IMPROVEMENT.md` pour la liste complète. Les 3 plus importantes :

1. **Jamais de `fetch()` vers l'API Anthropic depuis le navigateur** — toujours passer par le backend FastAPI
2. **Toujours 2 appels séparés** : crawl d'abord, analyse ensuite — ne jamais fusionner
3. **Toujours vérifier la cannibalisation SEO** entre les pages dans tout audit

---

## Slash commands disponibles

```
/audit [url]    → Lance un audit complet sur l'URL donnée
/pdf            → Génère le PDF du dernier audit
/design         → Affiche les specs design (couleurs, typo, composants)
/errors         → Affiche les erreurs passées (SELF-IMPROVEMENT.md)
```

Définies dans `.claude/commands/` — voir les fichiers `.md` correspondants.

---

## Définition de "tâche terminée"

Une fonctionnalité est considérée terminée quand :
- [ ] Le TypeScript compile sans erreur (`npm run type-check`)
- [ ] Les tests passent (`npm run test` + `pytest`)
- [ ] Le lint passe (`npm run lint`)
- [ ] Le design correspond à `DESIGN.md` (palette, typo, composants)
- [ ] Le PDF généré a une page de couverture complète
- [ ] L'état de chargement et l'état d'erreur sont gérés dans l'UI
