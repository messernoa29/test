# SELF-IMPROVEMENT.md — Journal des erreurs & règles apprises

> Ce document liste chaque erreur commise sur ce projet, sa cause exacte, et la règle à appliquer pour ne plus jamais la reproduire. Claude doit le lire AVANT de produire quoi que ce soit. Ce n'est pas un document de bonnes pratiques générales — ce sont des erreurs RÉELLES qui se sont produites dans CE projet.

---

## FORMAT DE CHAQUE ENTRÉE

```
### ERREUR #N — [Titre court]
Contexte   : Ce qui était demandé
Ce qui s'est passé : L'erreur exacte commise
Cause racine : Pourquoi c'est arrivé
Règle définitive : Ce qu'il faut faire à la place — sans exception
```

---

## ERREURS TECHNIQUES

---

### ERREUR #1 — Appel API direct depuis un artifact Claude.ai

**Contexte** : Création de l'outil d'audit v1 — un artifact HTML qui devait appeler l'API Anthropic directement pour analyser un site.

**Ce qui s'est passé** : L'artifact appelait `https://api.anthropic.com/v1/messages` en JavaScript depuis le navigateur. Au clic sur "Analyser", l'erreur suivante apparaissait :

```
Erreur lors de l'analyse. Vérifiez l'URL et réessayez. (Load failed)
```

**Cause racine** : Le sandbox de Claude.ai bloque tous les appels réseau sortants depuis les artifacts via la Content Security Policy (CSP) du navigateur. L'appel à `api.anthropic.com` était bloqué silencieusement avant même d'atteindre le serveur.

**Règle définitive** :
> Dans un artifact Claude.ai, il est IMPOSSIBLE d'appeler une API externe directement depuis le JavaScript navigateur. La seule façon de faire appeler Claude depuis un artifact est d'utiliser `sendPrompt(texte)` — qui envoie un message dans la conversation, auquel Claude répond, et que l'artifact peut parser.

**Solution appliquée** : Utiliser `sendPrompt()` pour envoyer le prompt d'analyse à Claude, puis détecter la réponse avec `setInterval` + `querySelector` sur les messages du DOM, et parser le JSON balisé `<AUDIT_JSON>...</AUDIT_JSON>`.

---

### ERREUR #2 — Mécanisme de détection de réponse qui ne se déclenche pas

**Contexte** : Après correction de l'erreur #1 avec `sendPrompt()`, l'audit était lancé mais le rapport ne s'affichait jamais dans l'artifact — même quand Claude répondait correctement.

**Ce qui s'est passé** : L'artifact utilisait `setInterval` pour scanner le DOM à la recherche des balises `<AUDIT_JSON>` dans les messages Claude. Le sélecteur CSS utilisé ne ciblait pas les bons éléments du DOM de Claude.ai, donc le JSON était ignoré.

**Cause racine** : Les sélecteurs DOM de Claude.ai changent et ne sont pas documentés. S'appuyer sur des sélecteurs CSS précis de l'interface interne est fragile.

**Règle définitive** :
> Ne jamais concevoir un flux qui dépend du parsing automatique du DOM de Claude.ai pour récupérer une réponse. Si l'artifact a besoin de données de Claude, deux options fiables :
> 1. L'utilisateur copie-colle la réponse dans un champ de l'artifact
> 2. Claude affiche le résultat directement dans l'interface de conversation, et l'artifact sert uniquement à la saisie et à l'affichage final une fois les données reçues

**Solution appliquée** : Afficher le rapport directement dans un nouvel artifact hardcodé avec les données de l'audit, plutôt que de dépendre du parsing DOM automatique.

---

### ERREUR #3 — Prompt qui ne force pas assez le crawl réel

**Contexte** : Le premier prompt universel demandait à l'IA d'analyser le site sans suffisamment forcer la visite réelle des pages.

**Ce qui s'est passé** : Quand le prompt a été testé par l'utilisateur dans une autre interface IA (ChatGPT), l'IA a produit un audit qui semblait complet mais était basé sur des suppositions génériques — pas sur un crawl réel du site. Les données de title, H1 et meta n'étaient pas les vraies données du site.

**Cause racine** : Le prompt disait "analyse le site" sans forcer explicitement la visite page par page AVANT l'analyse. L'IA optimise pour la rapidité — si elle peut générer une réponse plausible sans crawler, elle le fait.

**Règle définitive** :
> Tout prompt d'audit SEO DOIT être structuré en 2 messages séparés et séquentiels :
> - **Message 1** : crawl uniquement — forcer l'IA à visiter et lister toutes les URLs avec leurs données exactes (title, H1, meta). Terminer par : "Ne génère aucune analyse tant que tu n'as pas visité toutes les pages."
> - **Message 2** : analyse + rapport — envoyé uniquement APRÈS confirmation du crawl
>
> Ne jamais fusionner crawl et analyse dans un seul message.

---

### ERREUR #4 — Titles et H1 non différenciés entre deux pages similaires (dans le prompt)

**Contexte** : Audit SEO de lasource-foodschool.com — analyse des pages `/formation-cuisine-alternance` et `/formation-cuisine-courte`.

**Ce qui s'est passé** : Les deux pages avaient exactement le même title et le même H1 ("Commis de cuisine"). Ce problème de cannibalisation n'avait pas été mentionné dans le premier audit général — il n'a été découvert que lors de l'audit SEO approfondi.

**Cause racine** : L'audit général (6 axes) ne vérifiait pas explicitement la cannibalisation entre pages. Il analysait chaque page isolément sans les comparer entre elles.

**Règle définitive** :
> Tout audit SEO doit inclure une étape de comparaison inter-pages. Les éléments à comparer systématiquement :
> - Titles identiques ou très proches entre plusieurs pages
> - H1 identiques entre plusieurs pages
> - Mots-clés principaux ciblés par plusieurs pages simultanément
> - URLs trop similaires qui peuvent se concurrencer
>
> Cette vérification doit être une section dédiée du rapport, pas une observation optionnelle.

---

### ERREUR #5 — Le PDF v1 n'avait pas de page de couverture structurée

**Contexte** : Génération du premier PDF d'audit (audit général 6 axes).

**Ce qui s'est passé** : Le PDF démarrait directement avec les sections d'analyse, sans page de couverture distincte et impactante. Le score global était affiché mais de manière trop modeste.

**Cause racine** : La page de couverture n'avait pas été explicitement spécifiée dans les instructions de génération PDF. ReportLab avait produit un document fonctionnel mais sans hierarchy visuelle forte.

**Règle définitive** :
> Tout PDF d'audit doit obligatoirement commencer par une page de couverture complète contenant :
> - Nom du domaine (grande taille, typographie forte)
> - URL complète
> - Date de l'audit
> - Score global en très grand (hero element)
> - Verdict en 2-3 mots
> - Compteurs critiques et avertissements avec couleurs
> - Nom de l'agence ou du produisant
>
> La couverture doit tenir sur une page entière — ne pas faire déborder le contenu dessus.

---

## ERREURS DE COMMUNICATION

---

### ERREUR #6 — Mauvaise orthographe "Streaming Frog" au lieu de "Screaming Frog"

**Contexte** : L'utilisateur a mentionné le logiciel "Streaming Frog" — une déformation phonétique du vrai nom.

**Ce qui s'est passé** : Dans un premier temps, le nom incorrect a été utilisé sans correction. Le vrai nom du logiciel est **Screaming Frog SEO Spider**.

**Cause racine** : Priorité donnée à la fluidité de la conversation plutôt qu'à la précision technique.

**Règle définitive** :
> Quand un nom de logiciel, d'outil ou de technologie est mal orthographié dans la question, le corriger discrètement dans la réponse sans faire de commentaire — utiliser le bon nom dans la réponse. Ne pas répéter l'erreur même si l'utilisateur la fait.
>
> Le logiciel SEO de crawl s'appelle : **Screaming Frog SEO Spider** (pas Streaming Frog, pas Screamingfrog).

---

### ERREUR #7 — Prompt trop générique pour être vraiment utile à une autre IA

**Contexte** : Création du "prompt universel" à donner à n'importe quelle IA.

**Ce qui s'est passé** : La première version du prompt était trop générique — elle fonctionnait bien dans Claude mais produisait des résultats beaucoup moins bons dans ChatGPT, qui n'avait pas réellement crawlé le site.

**Cause racine** : Le prompt avait été conçu et testé uniquement dans Claude. Il supposait implicitement des capacités (web search natif, exécution Python) que toutes les IAs n'ont pas.

**Règle définitive** :
> Tout prompt destiné à être "universel" doit :
> 1. Être testé mentalement dans au moins 2 IAs différentes (Claude, ChatGPT, Gemini)
> 2. Indiquer explicitement les prérequis : "Ce prompt nécessite que l'IA ait accès à la navigation web"
> 3. Indiquer ce qui est Claude-spécifique (exécution Python, génération PDF) vs ce qui marche partout
> 4. Prévoir une version dégradée sans PDF pour les IAs sans exécution de code

---

### ERREUR #8 — Ne pas avoir expliqué la limitation API vs claude.ai dès le départ

**Contexte** : L'utilisateur a demandé si l'outil pouvait être partagé, puis si une application était possible "sans API".

**Ce qui s'est passé** : Ces questions auraient dû être anticipées dès la création du premier artifact. La distinction entre :
- Ce qui fonctionne dans claude.ai (pour l'utilisateur connecté uniquement)
- Ce qui nécessite l'API (pour une vraie application partageable)

...n'avait pas été expliquée proactivement.

**Cause racine** : Focus sur la livraison rapide de l'outil sans anticiper les questions d'usage réel et de déploiement.

**Règle définitive** :
> Quand on crée un outil interactif dans Claude.ai, toujours préciser immédiatement :
> - Qui peut l'utiliser (compte Claude requis ou non)
> - Si c'est partageable tel quel
> - Ce qu'il faudrait pour en faire une vraie application
> - Le coût API estimé si l'utilisateur veut aller plus loin
>
> Ne pas attendre que l'utilisateur pose la question.

---

## ERREURS DE DESIGN

---

### ERREUR #9 — Design générique sur les premiers artifacts

**Contexte** : Les premiers artifacts (v1 et v2 de l'outil d'audit) utilisaient les variables CSS natives de Claude.ai.

**Ce qui s'est passé** : Le rendu était propre et fonctionnel mais sans personnalité propre — il ressemblait à n'importe quelle interface Claude.ai. Pas de typographie distinctive, pas de palette originale, pas d'identité visuelle.

**Cause racine** : Priorité donnée à la fonctionnalité plutôt qu'à l'identité visuelle. Les variables CSS de Claude.ai ont été utilisées par défaut sans réfléchir au design.

**Règle définitive** :
> Lire le fichier `DESIGN.md` AVANT de produire tout élément visuel. Ne jamais utiliser uniquement les variables CSS de Claude.ai par défaut pour un projet qui a sa propre identité.
>
> Si DESIGN.md n'est pas encore disponible dans la conversation, demander : "Faut-il que je suive le système de design du projet ou partir sur quelque chose de nouveau ?"

---

### ERREUR #10 — Scores affichés de manière trop modeste dans le premier PDF

**Contexte** : PDF d'audit général v1.

**Ce qui s'est passé** : Le score global (58/100) était affiché en taille normale, sans impact visuel particulier. Un client qui ouvre le rapport ne voyait pas immédiatement le score.

**Cause racine** : Pas de hiérarchie visuelle claire définie pour les éléments hero du rapport.

**Règle définitive** :
> Le score global est TOUJOURS le hero element du rapport. Il doit être :
> - Affiché en très grande taille (minimum 60px dans un PDF, 64px dans une interface)
> - Dans la typographie display (DM Serif Display selon DESIGN.md)
> - Coloré selon le niveau (rouge si critique, ambre si moyen, vert si bon)
> - Accompagné du verdict en italique juste en dessous
> - Visible immédiatement sans scrolling sur la page de couverture

---

## RÈGLES PROCESS

---

### RÈGLE PROCESS #1 — Ordre de lecture des fichiers de contexte

À chaque nouvelle conversation sur ce projet, lire dans cet ordre :

```
1. CONTEXTE-PROJET.md  →  comprendre où en est le projet
2. DESIGN.md           →  comprendre l'identité visuelle
3. SELF-IMPROVEMENT.md →  (ce fichier) ne pas répéter les erreurs
```

Ne jamais commencer à produire du code ou du design avant d'avoir lu ces 3 fichiers.

---

### RÈGLE PROCESS #2 — Tester mentalement avant de livrer

Avant de livrer tout artifact ou code, se poser ces questions :

```
□ Est-ce que ça marche dans le sandbox Claude.ai sans appel API externe ?
□ Est-ce que sendPrompt() est utilisé à la place des fetch() vers des APIs externes ?
□ Est-ce que le design correspond à DESIGN.md (palette, typo, composants) ?
□ Est-ce que le PDF a une page de couverture complète ?
□ Est-ce que le score est affiché en hero element ?
□ Est-ce que le crawl est séparé de l'analyse dans les prompts ?
□ Est-ce que j'ai vérifié la cannibalisation entre les pages ?
```

---

### RÈGLE PROCESS #3 — Nommer correctement les livrables

Convention de nommage établie sur ce projet :

```
CONTEXTE-PROJET.md              ← contexte général
DESIGN.md                       ← système de design
SELF-IMPROVEMENT.md             ← ce fichier
PROMPT-AUDIT-SEO-TECHNIQUE.txt  ← prompt universel

audit-[domaine].pdf             ← audit général 6 axes
audit-seo-[domaine].pdf         ← audit SEO technique Screaming Frog
audit-[domaine]-[date].txt      ← export texte brut
```

Ne pas inventer de nouveaux noms de fichiers hors de cette convention sans le signaler.

---

### RÈGLE PROCESS #4 — Mise à jour de ce fichier

Chaque fois qu'une nouvelle erreur est commise ou qu'une nouvelle règle est apprise :

1. L'ajouter immédiatement dans ce fichier sous le bon format
2. Incrémenter le numéro d'erreur
3. Mettre à jour la date de dernière modification en bas de fichier
4. Signaler à l'utilisateur : "J'ai ajouté cette erreur dans SELF-IMPROVEMENT.md"

---

## RÉCAPITULATIF RAPIDE — LES 10 RÈGLES À NE JAMAIS OUBLIER

```
1. JAMAIS d'appel fetch() vers une API depuis un artifact Claude.ai → utiliser sendPrompt()
2. TOUJOURS 2 messages séparés pour un audit : crawl d'abord, analyse ensuite
3. TOUJOURS vérifier la cannibalisation entre pages dans tout audit SEO
4. TOUJOURS une page de couverture complète dans tout PDF
5. TOUJOURS le score en hero element — grand, coloré, impactant
6. Le logiciel s'appelle Screaming Frog SEO Spider — pas "Streaming Frog"
7. Lire DESIGN.md avant tout élément visuel — jamais de design par défaut
8. Tout prompt "universel" doit préciser ses prérequis (web search, Python, etc.)
9. Expliquer proactivement les limites de partage et les options API
10. Lire CONTEXTE.md + DESIGN.md + SELF-IMPROVEMENT.md avant de commencer
```

---

*Dernière mise à jour : 24 avril 2026*
*Erreurs documentées : 10*
*Règles process : 4*
*À enrichir à chaque nouvelle erreur détectée*
