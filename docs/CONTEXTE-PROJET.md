# CONTEXTE PROJET — Outil d'Audit Web IA pour Agence Digitale

> **À lire en premier.** Ce document est le contexte complet du projet. Il permet à Claude de comprendre ce qui a été fait, ce qui est en cours, et ce qui reste à construire — sans avoir à tout réexpliquer à chaque nouvelle conversation.

---

## 1. Vision du projet

L'objectif est de créer un **outil d'audit web complet propulsé par l'IA**, à destination d'une agence digitale qui souhaite :

1. **Analyser n'importe quel site web** de manière automatisée et approfondie
2. **Produire des rapports PDF professionnels** prêts à présenter à un client
3. **Proposer ce service** comme une offre différenciante à leurs clients
4. **Automatiser le travail** que font normalement les experts SEO manuellement avec des logiciels comme Screaming Frog SEO Spider

Le projet a démarré comme une exploration dans Claude.ai et évolue vers une vraie application web autonome.

---

## 2. Ce qui a déjà été construit (historique de la session)

### 2.1 Outil d'audit général (v1 — artifact interactif)

Un premier outil a été créé directement dans Claude.ai sous forme d'artifact HTML interactif. Il permettait d'entrer une URL et de lancer une analyse via l'API Anthropic.

**Problème rencontré :** l'appel direct à `api.anthropic.com` depuis l'artifact était bloqué par le sandbox navigateur (erreur `Load failed` / CSP).

**Solution adoptée :** utiliser `sendPrompt()` — l'artifact envoie la requête à Claude dans la conversation, Claude répond avec un JSON balisé `<AUDIT_JSON>...</AUDIT_JSON>`, et l'artifact parse et affiche le résultat.

### 2.2 Outil d'audit général (v2 — version fonctionnelle)

Version corrigée utilisant `sendPrompt()`. L'outil propose 6 axes d'analyse configurables :

| Axe | Contenu |
|-----|---------|
| Sécurité | HTTPS, headers, RGPD, cookies, vulnérabilités |
| SEO & règles web | Balises meta, structure H1-H6, accessibilité |
| UX / Design | Navigation, responsive, CTA, ergonomie |
| Contenu | Sections, copywriting, proposition de valeur |
| Performance | Core Web Vitals, images, scripts bloquants |
| Opportunités business | Conversion, quick wins, propositions agence |

L'audit produit : score global, scores par axe, findings catégorisés, recommandations, quick wins, export .txt.

### 2.3 Premier audit réel — lasource-foodschool.com

Le site `https://www.lasource-foodschool.com` a été analysé en profondeur. C'est une **école de cuisine engagée** (cuisine durable, responsable) avec des campus à Paris et Toulouse. Le site est construit sur **Webflow**.

**Résultats de l'audit général :**
- Score global : **58/100** — verdict "À consolider"
- 5 points critiques, 13 avertissements
- Quick wins identifiés : faute "diplomantes", absence de lead magnet, RGPD non conforme

**Rapport PDF généré** avec ReportLab (Python) — 6 sections, mise en page professionnelle, codes couleur par criticité, barres de scores animées.

### 2.4 Audit SEO technique approfondi — style Screaming Frog

Un second rapport a été produit, beaucoup plus technique, simulant le travail d'une agence avec Screaming Frog SEO Spider. Il a nécessité un **crawl réel page par page** du site.

**Pages crawlées et analysées :**

| URL | Statut |
|-----|--------|
| `/` Homepage | CRITIQUE |
| `/se-former` | CRITIQUE |
| `/formation-cuisine-alternance-paris-bordeaux-toulouse-foodcamp` | CRITIQUE |
| `/formation-cuisine-courte-paris-bordeaux-toulouse-foodcamp` | CRITIQUE |
| `/foodcamp-cycle2-alternance` | ATTENTION |
| `/rpms` | ATTENTION |
| `/cuisine-vegetale` | À AMÉLIORER |
| `/fermentation-cycle-1` | À AMÉLIORER |
| `/fermentation-cycle-2` | À AMÉLIORER |
| `/sinspirer` (blog) | ATTENTION |
| `/notre-communaute` | ATTENTION |
| `/nous-contacter` | ATTENTION |

**Problèmes critiques identifiés :**
- Faute orthographique dans le title ("diplomantes" → "diplômantes") visible dans Google
- 0/11 pages avec meta description rédigée
- Cannibalisation SEO : 2 pages avec title et H1 identiques
- URL `/sinspirer` non-SEO (devrait être `/blog`)
- Aucune page locale par ville (Paris, Toulouse, Bordeaux)
- Aucun schema.org sur les formations
- Aucun Google Business Profile mentionné

**6 pages manquantes stratégiques identifiées :**
- `/formation-cuisine-paris` (~1 900 rech/mois)
- `/formation-cuisine-toulouse` (~400 rech/mois)
- `/financement-formation-cpf` (~800 rech/mois)
- `/nos-diplomes-insertion` (~300 rech/mois)
- `/pourquoi-la-source` (~200 rech/mois)
- `/formation-patisserie-paris` (~900 rech/mois)

**Plan d'action en 3 phases** : Quick Wins semaine 1 / Fondations mois 1 / Contenu mois 2-3.

**PDF généré** : rapport multi-pages professionnel avec fiches page par page, tableau des mots-clés, plan d'action.

### 2.5 Prompt universel — Audit SEO Screaming Frog

Un prompt complet a été rédigé et exporté en `.txt`, utilisable dans n'importe quelle IA (Claude, ChatGPT, Gemini). Il est structuré en **2 messages séparés** :

- **Message 1** : force le crawl préliminaire de toutes les pages avant analyse
- **Message 2** : demande l'analyse complète + génération PDF avec ReportLab

### 2.6 Générateur de prompt no-code (artifact interactif)

Un outil visuel a été créé dans Claude.ai permettant de **générer automatiquement le prompt personnalisé** à partir de formulaires :
- URL du site, secteur, villes, cible, objectif, concurrents
- Sélection des sections à inclure (8 sections de base + 4 avancées)
- Génération de 2 prompts distincts (crawl + analyse) prêts à copier-coller

---

## 3. Architecture technique actuelle

### Ce qui fonctionne aujourd'hui (dans Claude.ai)

```
Utilisateur
    │
    ▼
Artifact HTML (interface)
    │  sendPrompt()
    ▼
Claude (dans la conversation)
    │  analyse + JSON balisé
    ▼
Artifact HTML (parse + affiche)
    │  Python + ReportLab
    ▼
Fichier PDF téléchargeable
```

**Limites de cette architecture :**
- Nécessite un compte Claude.ai actif (gratuit ou payant)
- Pas partageable à des tiers sans compte Claude
- Pas automatisable (nécessite une action humaine)
- L'appel API direct depuis l'artifact est bloqué par le CSP du sandbox

### Ce qui serait une vraie application

```
Utilisateur (n'importe qui, sans compte Claude)
    │
    ▼
Interface web (React / Next.js / no-code)
    │  Formulaire URL + options
    ▼
Backend (Node.js / Python / Make.com)
    │  Appel API Anthropic avec web_search
    ▼
Claude API (claude-sonnet-4-20250514)
    │  Crawl + analyse + JSON structuré
    ▼
Génération PDF (ReportLab Python)
    │
    ▼
Email au client + téléchargement direct
```

---

## 4. Modèle économique envisagé

### Coûts API (estimation)

| Volume | Coût API estimé |
|--------|----------------|
| 10 audits/mois | ~0,60 € |
| 50 audits/mois | ~3 € |
| 200 audits/mois | ~12 € |

*Basé sur Claude Sonnet : ~4 000 tokens entrée + ~6 000 tokens sortie par audit = ~0,06€/audit*

### Options de monétisation pour l'agence

1. **Outil interne** — utilisé par les consultants pour préparer les pitchs clients (gain de temps : 3-4h → 10 min)
2. **Service client payant** — audit proposé à 99-299€, généré automatiquement, livré en PDF
3. **Lead magnet** — audit "gratuit" pour capter des prospects, rapport PDF envoyé par email
4. **Abonnement** — audit mensuel automatique pour les clients en suivi SEO

---

## 5. Stack technique recommandée

### Option A — No-code (sans développeur)

| Outil | Rôle |
|-------|------|
| Make.com ou n8n | Orchestration des appels API |
| Anthropic API | Analyse IA (Claude Sonnet) |
| Airtable | Stockage des audits |
| Tally ou Typeform | Formulaire d'entrée client |
| Pdfmonkey ou WeasyPrint | Génération PDF |

### Option B — Code (avec développeur)

| Outil | Rôle |
|-------|------|
| Next.js (React) | Interface web |
| FastAPI (Python) | Backend API |
| Anthropic SDK Python | Appels Claude API |
| ReportLab | Génération PDF (déjà utilisé et testé) |
| Vercel + Railway | Hébergement |
| Resend | Envoi email avec PDF |

---

## 6. Ce qui reste à construire

### Priorité 1 — Court terme

- [ ] Transformer le prompt en workflow Make.com/n8n fonctionnel
- [ ] Créer un formulaire web simple (Tally) pour l'entrée des URLs
- [ ] Connecter Make.com → API Anthropic → PDF → Email
- [ ] Tester sur 5 sites différents pour valider la robustesse

### Priorité 2 — Moyen terme

- [ ] Interface web branded (logo agence, couleurs, domaine propre)
- [ ] Dashboard de gestion des audits passés
- [ ] Personnalisation du rapport (logo client, couleurs, intro personnalisée)
- [ ] Système de comparaison avant/après (audit initial vs audit de suivi)

### Priorité 3 — Long terme

- [ ] Automatisation des audits récurrents (mensuel/trimestriel)
- [ ] Intégration Google Search Console pour données réelles
- [ ] Alertes automatiques si le score chute
- [ ] API publique pour intégration dans d'autres outils agence

---

## 7. Fichiers produits lors du projet

| Fichier | Description |
|---------|-------------|
| `audit-lasource-foodschool.pdf` | Audit général 6 axes — lasource-foodschool.com |
| `audit-seo-lasource-foodschool.pdf` | Audit SEO technique style Screaming Frog — lasource-foodschool.com |
| `PROMPT-AUDIT-SEO-TECHNIQUE.txt` | Prompt universel complet (2 messages) utilisable dans toute IA |
| `CONTEXTE-PROJET.md` | Ce fichier — contexte complet du projet |

---

## 8. Comment utiliser ce fichier de contexte

### Au début de chaque nouvelle conversation avec Claude

Collez ce message en introduction :

```
Voici le contexte complet de notre projet. Lis-le attentivement avant de répondre.

[coller le contenu de ce fichier]

Contexte de ma demande aujourd'hui : [décris ce que tu veux faire]
```

### Ce que Claude doit savoir faire avec ce contexte

- Reprendre exactement là où le projet en est sans repartir de zéro
- Utiliser les mêmes palettes de couleurs, structures PDF et formats déjà établis
- Proposer des évolutions cohérentes avec l'architecture existante
- Ne pas réinventer ce qui a déjà été construit et validé

---

## 9. Décisions techniques déjà prises

| Décision | Raison |
|----------|--------|
| `sendPrompt()` au lieu d'appel API direct depuis l'artifact | CSP sandbox Claude.ai bloque les appels externes |
| ReportLab (Python) pour les PDF | Testé et validé — rendu professionnel, contrôle total |
| 2 messages séparés (crawl puis analyse) | Force l'IA à vraiment crawler avant d'analyser |
| JSON balisé `<AUDIT_JSON>` pour la communication artifact ↔ Claude | Parsing fiable et robuste |
| Claude Sonnet 4 (`claude-sonnet-4-20250514`) | Meilleur équilibre qualité/coût pour ce use case |

---

## 10. Principes de design du rapport PDF

Palette définie et utilisée dans tous les PDFs générés :

| Usage | Couleur | Hex |
|-------|---------|-----|
| Fond / arrière-plan | Beige clair | `#F5F4F0` |
| Texte principal | Noir profond | `#1C1C1C` |
| Critique | Rouge | `#E24B4A` |
| Attention | Orange | `#EF9F27` |
| OK / Positif | Vert | `#3B6D11` |
| Info | Bleu | `#378ADD` |
| Manquant | Violet | `#7F77DD` |
| Séparateurs | Gris clair | `#E2E0D8` |

Structure de chaque rapport :
1. Page de couverture (domaine, score, métriques clés, date)
2. Sections numérotées avec titres clairs
3. Tableaux avec alternance blanc / `#F5F4F0`
4. Fiches avec bande colorée gauche selon le statut
5. En-tête + pied de page sur chaque page (site + date + numéro)

---

*Document généré le 24 avril 2026 — Projet : Outil d'Audit Web IA*
*À mettre à jour à chaque avancée significative du projet*
