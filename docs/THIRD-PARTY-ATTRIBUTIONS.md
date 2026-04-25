# Third-party attributions

## claude-seo (Agrici Daniel) — MIT

Source : https://github.com/AgriciDaniel/claude-seo (v1.9.0, février 2026)
License : MIT

Nous avons adapté la **méthodologie** (pas le code) de ce projet, notamment :

- La **pondération des axes** pour le score global (22% technical, 23% content, 20% on-page, 10% schema, 10% performance, 10% AI search, 5% images).
- Les **règles SEO à jour 2025-2026** intégrées dans le system prompt de l'analyzer : INP remplaçant FID (mars 2024), mobile-first indexing 100% depuis juillet 2024, HowTo/SpecialAnnouncement dépréciés, FAQ restreint au gouvernement/santé, guidance Google JS rendering de décembre 2025.
- La **liste des crawlers AI** (GPTBot, Google-Extended, ClaudeBot, PerplexityBot, etc.) à monitorer dans robots.txt.
- Les **critères GEO / AI citation** : passage optimal 134-167 mots, réponse en 40-60 premiers mots, corrélation brand mentions > backlinks (étude Ahrefs déc 2025), llms.txt.
- La **discipline "INSUFFICIENT DATA"** : refuser de scorer un axe avec moins de 4/7 facteurs observables.
- Les **catégories de pages stratégiques manquantes** : locales, financement/prix, preuves sociales, comparatives, topic clusters, lead magnets.

Tout le code Python / TypeScript de notre application est écrit par nous. Aucune ligne n'est copiée du repo source.

### Texte de la licence MIT

```
MIT License

Copyright (c) AgriciDaniel

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```
