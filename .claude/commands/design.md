# /design

Affiche les specs design du projet ou vérifie la conformité d'un composant.

## Usage
```
/design                          # Affiche les specs complètes
/design --check [fichier]        # Vérifie si le fichier respecte DESIGN.md
/design --component [nom]        # Génère le code d'un composant conforme
```

## Ce que tu dois faire

Si appelé sans argument : afficher un résumé structuré de `docs/DESIGN.md` avec :
- Direction artistique ("The Intelligence Bureau")
- Polices (DM Serif Display / DM Sans / JetBrains Mono)
- Palette de couleurs (variables CSS complètes)
- Composants clés (Badge, Card, Button, ScoreBar)
- Les 10 règles absolues à ne jamais enfreindre

Si appelé avec `--check [fichier]` : lire le fichier et vérifier :
- [ ] Les variables CSS sont utilisées (pas de hex hardcodé)
- [ ] Les bonnes polices sont utilisées selon le rôle
- [ ] Pas de gradients ni de box-shadow décoratifs
- [ ] border-radius ≤ 8px sur les éléments de données
- [ ] Les badges de statut utilisent les couleurs sémantiques correctes
- [ ] Sentence case partout (sauf badges de statut)

Si appelé avec `--component [nom]` : générer le code complet du composant
en respectant exactement les specs de `docs/DESIGN.md`.
