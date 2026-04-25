# /audit

Lance un audit web complet sur l'URL fournie en argument.

## Usage
```
/audit https://www.monsite.fr
/audit https://www.monsite.fr --seo-only
/audit https://www.monsite.fr --no-pdf
```

## Ce que tu dois faire

**Étape 1 — Crawl (obligatoire avant tout)**

Visite l'URL $ARGUMENTS et toutes les pages liées depuis la navigation principale. Pour chaque page, note :
- URL complète
- Contenu exact de la balise `<title>` + nombre de caractères
- Contenu exact du `<h1>`
- Présence/absence de meta description + contenu si présente
- Mots-clés visibles dans le contenu
- Liens internes

Ne génère aucune analyse tant que tu n'as pas visité toutes les pages.

**Étape 2 — Analyse**

Analyse les données crawlées selon les 6 axes définis dans `lib/types.ts` :
sécurité, SEO, UX, contenu, performance, opportunités business.

Produis un objet `AuditResult` conforme au type TypeScript.

**Étape 3 — Vérification cannibalisation**

Compare systématiquement les titles et H1 entre toutes les pages. Signale tout doublon.

**Étape 4 — PDF**

Appelle `api/services/pdf_generator.py` avec les données de l'audit pour générer le rapport PDF.
Le PDF doit avoir une page de couverture complète avec le score en grand (hero element).

## Règles
- Respecter la palette de couleurs de `docs/DESIGN.md`
- Polices : DM Serif Display (scores) + DM Sans (corps) + JetBrains Mono (URLs/données)
- Statuts : CRITIQUE (rouge #E24B4A) / ATTENTION (ambre #EF9F27) / OK (vert #3B6D11)
