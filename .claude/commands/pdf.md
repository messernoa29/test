# /pdf

Génère ou regénère le rapport PDF du dernier audit.

## Usage
```
/pdf
/pdf --open
/pdf --client "Nom du Client"
```

## Ce que tu dois faire

1. Récupérer les données du dernier `AuditResult` disponible (en mémoire ou depuis le fichier `output/last-audit.json`)
2. Appeler `python api/services/pdf_generator.py` avec ces données
3. Le PDF doit contenir dans l'ordre :
   - Page de couverture (domaine, URL, date, score en grand, métriques critiques)
   - Section 01 : Synthèse technique (tableau 15 indicateurs)
   - Section 02 : Analyse page par page (fiche par URL)
   - Section 03 : Pages manquantes stratégiques
   - Section 04 : Mots-clés (tableau volume + intention + priorité)
   - Section 05 : Plan d'action 3 phases
4. Placer le PDF généré dans `output/audit-[domaine]-[date].pdf`
5. Confirmer le chemin du fichier généré

## Palette PDF (version claire pour impression)
- Fond page : #F7F5F0
- Fond surface : #EDEAE3
- Texte : #1A1A17
- Accent : #B8892D
- Critique : #DC2626 (texte) / #FEF2F2 (fond)
- Attention : #D97706 (texte) / #FFFBEB (fond)
- OK : #059669 (texte) / #F0FDF4 (fond)

## Score — hero element obligatoire
Le score global doit être affiché en très grand (72px) en DM Serif Display sur la couverture.
Couleur selon le score : <40 rouge, 40-69 ambre, 70+ vert.
