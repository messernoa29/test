# /errors

Affiche les erreurs passées documentées et les règles à ne jamais enfreindre.

## Usage
```
/errors              # Affiche le récapitulatif des 10 règles
/errors --full       # Affiche toutes les erreurs avec contexte complet
/errors --add        # Ajoute une nouvelle erreur au journal
```

## Ce que tu dois faire

Si appelé sans argument : afficher le récapitulatif rapide de `docs/SELF-IMPROVEMENT.md` :
les 10 règles numérotées, sans le détail complet.

Si appelé avec `--full` : afficher le contenu complet de `docs/SELF-IMPROVEMENT.md`
avec toutes les erreurs, causes racines et règles définitives.

Si appelé avec `--add` : demander à l'utilisateur de décrire la nouvelle erreur,
puis l'ajouter au fichier `docs/SELF-IMPROVEMENT.md` dans le bon format :
- Titre court
- Contexte
- Ce qui s'est passé
- Cause racine
- Règle définitive

Incrémenter le numéro d'erreur et mettre à jour la date de dernière modification.
Confirmer l'ajout à l'utilisateur.
