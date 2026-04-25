# DESIGN.md — Système de Design · Outil d'Audit Web IA

> Ce document définit l'identité visuelle complète de l'application. Il est la référence absolue pour tout ce qui concerne le design — interface, PDF, composants, typographie, couleurs et animations. Claude doit le lire en entier avant de produire le moindre élément visuel.

---

## 1. Direction artistique

### Concept central : "The Intelligence Bureau"

L'outil se positionne comme un **cabinet d'expertise digitale haut de gamme** — pas un SaaS générique, pas un dashboard bleu pâle avec des icônes rondes. L'esthétique s'inspire des **salles de situation**, des **rapports d'intelligence stratégique** et des **publications financières premium** (Bloomberg, The Economist).

Le feeling doit être : **sérieux, précis, confidentiel, puissant.**

Un directeur marketing qui ouvre ce rapport doit immédiatement sentir qu'il tient quelque chose de professionnel — pas un export automatisé.

### Mots-clés du design

```
Autoritaire  ·  Précis  ·  Dense  ·  Lisible  ·  Monochrome avec éclats
Editorial    ·  Technique  ·  Premium  ·  Structuré  ·  Fonctionnel
```

### Ce que ce design N'EST PAS

- Pas de dégradés violets sur fond blanc (esthétique IA générique à éviter absolument)
- Pas de coins très arrondis partout (style SaaS 2020 dépassé)
- Pas de couleurs pastel douces
- Pas d'icônes emoji ou illustrations cartoon
- Pas de "dashboard bleu" avec des KPIs qui brillent
- Pas de police Inter ou Roboto

---

## 2. Typographie

### Hiérarchie typographique

```
Display / Titres principaux  →  DM Serif Display  (serif, élégant, autorité)
Sous-titres / Labels         →  DM Sans           (sans-serif propre, même famille)
Corps de texte               →  DM Sans Regular    (lisible, neutre)
Données / Code / URLs        →  JetBrains Mono     (monospace technique)
Chiffres / Scores            →  DM Serif Display   (impact visuel fort)
```

### Import Google Fonts

```css
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&family=JetBrains+Mono:wght@400;500&display=swap');
```

### Échelle typographique

| Rôle | Police | Taille | Poids | Line-height |
|------|--------|--------|-------|-------------|
| Hero / Score géant | DM Serif Display | 72px | 400 | 1.0 |
| Titre de section | DM Serif Display | 28px | 400 | 1.2 |
| Titre de carte | DM Sans | 16px | 500 | 1.3 |
| Corps principal | DM Sans | 14px | 400 | 1.6 |
| Label / Étiquette | DM Sans | 11px | 500 | 1.2 |
| Code / URL | JetBrains Mono | 12px | 400 | 1.5 |
| Micro / Caption | DM Sans | 11px | 300 | 1.4 |

### Règles typographiques strictes

- **Sentence case partout** — jamais de TOUT EN MAJUSCULES sauf pour les labels courts (ex: `CRITIQUE`, `URL`)
- Les labels courts de statut en majuscules → max 10 caractères, toujours dans un badge coloré
- Les chiffres de score s'affichent toujours en DM Serif Display
- Les URLs et données techniques s'affichent toujours en JetBrains Mono
- Interlignage minimum 1.5 pour le corps, pour une lisibilité maximale sur les rapports denses

---

## 3. Palette de couleurs

### Philosophie couleur

**Base monochrome + 5 couleurs sémantiques.**

L'interface est essentiellement noire, blanche et beige chaud. Les couleurs vives n'apparaissent que pour signaler un statut (critique, attention, bon, info). Cette retenue rend les alertes immédiatement visibles et crédibles.

### Couleurs de base

```css
:root {
  /* Arrière-plans */
  --bg-page:       #0F0F0D;   /* Noir chaud — fond de l'app */
  --bg-surface:    #1A1A17;   /* Surface principale (cards) */
  --bg-elevated:   #222220;   /* Éléments surélevés */
  --bg-overlay:    #2A2A27;   /* Hover, sélection */

  /* Textes */
  --text-primary:  #F0EDE6;   /* Blanc cassé chaud */
  --text-secondary:#9E9B94;   /* Gris chaud secondaire */
  --text-tertiary: #5C5A55;   /* Hints, placeholders */
  --text-inverse:  #0F0F0D;   /* Texte sur fond clair */

  /* Bordures */
  --border-subtle:  rgba(240, 237, 230, 0.06);  /* Très subtil */
  --border-default: rgba(240, 237, 230, 0.12);  /* Standard */
  --border-strong:  rgba(240, 237, 230, 0.24);  /* Emphase */

  /* Accent unique */
  --accent:        #D4A853;   /* Or chaud — l'unique couleur de marque */
  --accent-dim:    rgba(212, 168, 83, 0.15);
  --accent-border: rgba(212, 168, 83, 0.30);
}
```

### Couleurs sémantiques (statuts)

```css
:root {
  /* Critique — Rouge */
  --status-critical-bg:     #2A1515;
  --status-critical-border: #6B2020;
  --status-critical-text:   #F87171;
  --status-critical-accent: #EF4444;
  --status-critical-label:  #FCA5A5;

  /* Attention — Ambre */
  --status-warning-bg:      #261E0A;
  --status-warning-border:  #6B4E0A;
  --status-warning-text:    #FBB040;
  --status-warning-accent:  #F59E0B;
  --status-warning-label:   #FCD34D;

  /* OK / Positif — Vert sauge */
  --status-ok-bg:           #0D1F10;
  --status-ok-border:       #1A4D20;
  --status-ok-text:         #6EE7B7;
  --status-ok-accent:       #10B981;
  --status-ok-label:        #A7F3D0;

  /* Info — Bleu acier */
  --status-info-bg:         #0A1628;
  --status-info-border:     #1A3A6B;
  --status-info-text:       #93C5FD;
  --status-info-accent:     #3B82F6;
  --status-info-label:      #BFDBFE;

  /* Manquant — Violet ardoise */
  --status-missing-bg:      #160F2A;
  --status-missing-border:  #3D2575;
  --status-missing-text:    #C4B5FD;
  --status-missing-accent:  #8B5CF6;
  --status-missing-label:   #DDD6FE;
}
```

### Version claire (pour le PDF et les exports)

Le PDF utilise une version claire de la même palette pour l'impression :

```
Fond page PDF      : #F7F5F0   (beige chaud)
Fond surface PDF   : #EDEAE3   (beige légèrement plus foncé)
Texte principal    : #1A1A17   (noir chaud)
Texte secondaire   : #6B6860   (gris chaud)
Accent or          : #B8892D   (or légèrement plus foncé pour l'impression)
Critique           : #DC2626 (texte) / #FEF2F2 (fond)
Attention          : #D97706 (texte) / #FFFBEB (fond)
OK                 : #059669 (texte) / #F0FDF4 (fond)
Info               : #2563EB (texte) / #EFF6FF (fond)
```

---

## 4. Composants UI

### 4.1 Badges de statut

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.08em;
  padding: 3px 8px;
  border-radius: 3px;  /* Légèrement carré — pas de pill */
  text-transform: uppercase;
}

.badge-critical { background: var(--status-critical-bg); color: var(--status-critical-label); border: 0.5px solid var(--status-critical-border); }
.badge-warning  { background: var(--status-warning-bg);  color: var(--status-warning-label);  border: 0.5px solid var(--status-warning-border); }
.badge-ok       { background: var(--status-ok-bg);       color: var(--status-ok-label);       border: 0.5px solid var(--status-ok-border); }
.badge-info     { background: var(--status-info-bg);     color: var(--status-info-label);     border: 0.5px solid var(--status-info-border); }
.badge-missing  { background: var(--status-missing-bg);  color: var(--status-missing-label);  border: 0.5px solid var(--status-missing-border); }
```

Le point indicateur avant le texte :
```html
<span class="badge badge-critical">
  <span style="width:5px;height:5px;border-radius:50%;background:currentColor;flex-shrink:0"></span>
  Critique
</span>
```

### 4.2 Cartes (cards)

```css
.card {
  background: var(--bg-surface);
  border: 0.5px solid var(--border-default);
  border-radius: 6px;
  padding: 20px 24px;
  position: relative;
  overflow: hidden;
}

/* Accent latéral coloré selon statut */
.card::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--accent-color, var(--accent));
}
```

### 4.3 Inputs / Formulaires

```css
.input {
  width: 100%;
  height: 44px;
  padding: 0 16px;
  background: var(--bg-elevated);
  border: 0.5px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-primary);
  font-family: 'DM Sans', sans-serif;
  font-size: 14px;
  transition: border-color 0.15s;
  outline: none;
}

.input:focus {
  border-color: var(--accent-border);
  box-shadow: 0 0 0 3px var(--accent-dim);
}

.input::placeholder {
  color: var(--text-tertiary);
  font-style: italic;
}
```

### 4.4 Boutons

```css
/* Primaire — plein or */
.btn-primary {
  height: 44px;
  padding: 0 24px;
  background: var(--accent);
  color: var(--text-inverse);
  border: none;
  border-radius: 4px;
  font-family: 'DM Sans', sans-serif;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  letter-spacing: 0.01em;
  transition: opacity 0.15s, transform 0.1s;
}
.btn-primary:hover  { opacity: 0.9; }
.btn-primary:active { transform: scale(0.98); }

/* Secondaire — outline */
.btn-secondary {
  height: 44px;
  padding: 0 24px;
  background: transparent;
  color: var(--text-primary);
  border: 0.5px solid var(--border-strong);
  border-radius: 4px;
  font-family: 'DM Sans', sans-serif;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.btn-secondary:hover { background: var(--bg-elevated); border-color: var(--border-strong); }

/* Ghost — texte seul */
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: none;
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
}
.btn-ghost:hover { color: var(--text-primary); background: var(--bg-elevated); }
```

### 4.5 Barres de score

La barre de progression est un élément clé visuellement :

```css
.score-bar-track {
  width: 100%;
  height: 6px;
  background: var(--bg-elevated);
  border-radius: 1px;  /* Légèrement carré, pas pill */
  overflow: hidden;
}

.score-bar-fill {
  height: 100%;
  border-radius: 1px;
  transition: width 1.2s cubic-bezier(0.16, 1, 0.3, 1);
  /* La couleur est dynamique selon le score */
}
```

Logique de couleur selon le score :
- 0-39 → `var(--status-critical-accent)`
- 40-59 → `var(--status-warning-accent)`
- 60-79 → `var(--status-info-accent)`
- 80-100 → `var(--status-ok-accent)`

### 4.6 Score global (hero element)

L'élément le plus visible de tout le rapport — le score global doit avoir un impact immédiat :

```css
.score-hero {
  font-family: 'DM Serif Display', serif;
  font-size: 80px;
  font-weight: 400;
  line-height: 1;
  color: var(--accent);
  letter-spacing: -0.02em;
}

.score-hero-denom {
  font-family: 'DM Sans', sans-serif;
  font-size: 28px;
  font-weight: 300;
  color: var(--text-tertiary);
  vertical-align: super;
}

.score-verdict {
  font-family: 'DM Serif Display', serif;
  font-size: 18px;
  font-style: italic;
  color: var(--text-secondary);
  margin-top: 4px;
}
```

### 4.7 Séparateurs

```css
/* Séparateur horizontal standard */
.divider {
  width: 100%;
  height: 0.5px;
  background: var(--border-default);
  margin: 24px 0;
}

/* Séparateur avec label centré */
.divider-label {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-tertiary);
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.divider-label::before, .divider-label::after {
  content: '';
  flex: 1;
  height: 0.5px;
  background: var(--border-default);
}
```

### 4.8 Tableaux

```css
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  padding: 8px 12px;
  text-align: left;
  border-bottom: 0.5px solid var(--border-default);
}

.data-table td {
  padding: 10px 12px;
  color: var(--text-primary);
  border-bottom: 0.5px solid var(--border-subtle);
  vertical-align: top;
}

.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: var(--bg-elevated); }
```

---

## 5. Layout & Grilles

### Structure de l'application

```
┌─────────────────────────────────────────────────┐
│  SIDEBAR (220px fixe)  │  MAIN CONTENT (flex)   │
│                        │                         │
│  Logo                  │  Header de section      │
│  Navigation            │  ─────────────────────  │
│  ─────────────         │  Contenu principal      │
│  Derniers audits       │                         │
│  ─────────────         │                         │
│  Statut API            │                         │
└─────────────────────────────────────────────────┘
```

### Grilles de contenu

```css
/* Grille de métriques — 4 colonnes */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

/* Grille de sections — 2 colonnes */
.sections-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

/* Colonne unique — contenu dense */
.content-single {
  max-width: 760px;
  margin: 0 auto;
}
```

### Espacements (système 4px)

```
4px   — micro (entre éléments inline)
8px   — petit (gap interne d'une card)
12px  — défaut (gap entre éléments proches)
16px  — moyen (padding interne standard)
24px  — large (entre sections d'une page)
32px  — section (espacement entre blocs)
48px  — page (espacement majeur)
64px  — hero (marges de la zone principale)
```

---

## 6. Animations & Micro-interactions

### Principes

- Les animations doivent avoir un **sens fonctionnel** — elles communiquent un état ou guident l'attention
- Durées courtes : 150ms pour les hover, 300ms pour les transitions, max 1.2s pour les animations d'entrée
- Courbes : `cubic-bezier(0.16, 1, 0.3, 1)` pour les entrées (spring), `ease-out` pour les sorties
- Pas d'animation en boucle infinie sauf le spinner de chargement

### Animations clés

```css
/* Entrée des cards — stagger */
@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}

.card-enter {
  animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
}
.card-enter:nth-child(1) { animation-delay: 0ms; }
.card-enter:nth-child(2) { animation-delay: 60ms; }
.card-enter:nth-child(3) { animation-delay: 120ms; }
.card-enter:nth-child(4) { animation-delay: 180ms; }

/* Barre de progression — entrée */
@keyframes barFill {
  from { width: 0; }
}
.score-bar-fill {
  animation: barFill 1.2s cubic-bezier(0.16, 1, 0.3, 1) both;
  animation-delay: 0.3s;
}

/* Score — compteur */
/* Implémenter en JS : compter de 0 au score final en 1s */

/* Spinner de chargement */
@keyframes spin {
  to { transform: rotate(360deg); }
}
.spinner {
  width: 20px; height: 20px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

/* Pulse pour les statuts critiques */
@keyframes pulse-critical {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.5; }
}
.dot-critical {
  animation: pulse-critical 2s ease-in-out infinite;
}
```

---

## 7. Design du rapport PDF

Le PDF suit la même philosophie visuelle mais adapté à l'impression/lecture :

### Page de couverture PDF

```
┌─────────────────────────────────────┐
│                                     │
│  [BANDE ACCENT OR — 6px en haut]   │
│                                     │
│  AUDIT WEB                          │  ← JetBrains Mono, 10px, or, uppercase
│  Rapport d'analyse SEO & UX         │  ← DM Serif Display italic, 11px
│                                     │
│  ─────────────────────              │
│                                     │
│  lasource-foodschool.com            │  ← DM Serif Display, 32px
│  https://www.lasource-foodschool.com│  ← JetBrains Mono, 10px, gris
│                                     │
│  24 Avril 2026                      │  ← DM Sans, 12px, gris
│                                     │
│  ─────────────────────              │
│                                     │
│       58                            │  ← DM Serif Display, 72px, or
│       ──  Score global              │  ← DM Sans, 12px
│      100  À consolider              │  ← DM Serif Display italic, 14px
│                                     │
│  [■] 5 points critiques             │  ← Rouge
│  [■] 13 avertissements              │  ← Ambre
│                                     │
│  ─────────────────────              │
│                                     │
│  Produit par [Nom Agence]           │  ← DM Sans, 10px, gris
│                                     │
└─────────────────────────────────────┘
```

### En-tête PDF (toutes les pages)

```
[Nom du site]                    [Section courante]        [Page X / N]
JetBrains Mono 8px, gris        DM Sans 8px, gris         JetBrains Mono 8px
─────────────────────────────────────────────────────────────────────────────
```

### Fiche page (section 02 du rapport)

```
┌─ [BANDE COULEUR 4px] ────────────────────────────────────── [BADGE STATUT] ─┐
│                                                                               │
│  /formation-cuisine-alternance-paris...       [CRITIQUE]                      │
│  JetBrains Mono 9px                                                           │
│                                                                               │
├───────────────────────────────────────────────────────────────────────────────│
│  TITLE    │ Le Foodcamp l Formations certifiantes l TFP...    101 car. [▲]   │
│  H1       │ Commis de cuisine                                                 │
│  META     │ ABSENTE                                           0 car.  [✗]    │
├───────────────────────────────────────────────────────────────────────────────│
│  KW CIBLES   │ formation commis cuisine alternance paris, RNCP 37859          │
│  KW PRÉSENTS │ commis, alternance, TFP, RNCP, Paris                           │
│  KW ABSENTS  │ prix, durée, CPF, débouchés, salaire alternant                 │
├───────────────────────────────────────────────────────────────────────────────│
│  ● CRITIQUE   URL opaque «foodcamp» — aucun mot-clé métier dans l'URL        │
│  ● ATTENTION  Title trop long (101 car.) — tronqué dans Google               │
│  ● INFO       RNCP 37867 visible mais non exploité dans le title              │
├───────────────────────────────────────────────────────────────────────────────│
│  → Recommandation : /formation-commis-cuisine-alternance-paris                │
│    «Formation Commis Cuisine en Alternance Paris | RNCP 37859 — La Source»   │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. États de l'interface

### État vide (no data)

```
     [ Icône simple — loupe ou document ]

     Aucun audit lancé

     Entrez une URL ci-dessus pour démarrer
     votre première analyse.
```
Centré verticalement, icône 32px en `--text-tertiary`, texte en `--text-tertiary`.

### État de chargement

```
     ◌  Crawl du site en cours...

     → Lecture de la homepage
     → Navigation dans les sections
     → Analyse des balises SEO
     → Génération du rapport
```
Chaque étape s'active progressivement. Spinner doré en haut, étapes en JetBrains Mono 12px.

### État d'erreur

```
┌─────────────────────────────────────────┐
│  ✕  URL inaccessible                    │
│                                         │
│  Le site ne répond pas ou l'URL est     │
│  invalide. Vérifiez l'adresse et        │
│  réessayez.                             │
│                                         │
│  [Réessayer]                            │
└─────────────────────────────────────────┘
```

---

## 9. Règles absolues — Ne jamais enfreindre

```
1. JAMAIS de dégradé sur les arrière-plans principaux
2. JAMAIS d'ombres portées (box-shadow) sauf focus ring
3. JAMAIS de border-radius > 8px (sauf modal plein écran)
4. JAMAIS de couleurs vives hors palette sémantique
5. JAMAIS de texte blanc pur (#FFFFFF) — utiliser --text-primary (#F0EDE6)
6. JAMAIS de noir pur (#000000) — utiliser --bg-page (#0F0F0D)
7. JAMAIS d'animations > 1.5 secondes
8. JAMAIS d'icônes emoji dans l'UI principale — utiliser SVG ou caractères Unicode simples
9. JAMAIS de fonts > 3 familles par écran
10. TOUJOURS du Sentence case — sauf badges de statut (CRITIQUE, OK, etc.)
```

---

## 10. Checklist avant livraison de tout élément visuel

Avant de produire un composant, une page ou un PDF, Claude vérifie :

- [ ] Les fonts DM Serif Display + DM Sans + JetBrains Mono sont importées
- [ ] Les variables CSS de couleur sont définies et utilisées (pas de hex hardcodé)
- [ ] Les badges de statut utilisent les bonnes couleurs sémantiques
- [ ] Les scores s'affichent en DM Serif Display
- [ ] Les URLs et données techniques s'affichent en JetBrains Mono
- [ ] Les animations ont un délai de stagger sur les éléments en liste
- [ ] Les barres de score s'animent à l'entrée (pas statiques)
- [ ] Le border-radius ne dépasse pas 6px sur les éléments de données
- [ ] Aucune couleur pastel ni dégradé n'est utilisé
- [ ] Le contraste texte/fond est suffisant (minimum 4.5:1)
- [ ] L'état de chargement est prévu et designé
- [ ] La version PDF respecte la palette claire définie en section 3

---

*DESIGN.md — Version 1.0 — Projet Outil d'Audit Web IA*
*Ce document fait autorité sur toute décision de design.*
*À mettre à jour si la direction artistique évolue.*
