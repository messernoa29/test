"""Generate a sample PDF from a dense, realistic AuditResult fixture — no API call.

Usage:
    cd "ANALYSE AUDIT" && python -m api.scripts.test_pdf
Output:
    out/sample-audit.pdf
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from api.models import (
    AuditResult,
    Finding,
    MissingPage,
    PageAnalysis,
    PageRecommendation,
    SectionResult,
)
from api.services.pdf_generator import write_pdf


# ---------------------------------------------------------------------------
# Security (6 findings)

_SECURITY = [
    Finding(
        severity="critical",
        title="En-têtes de sécurité HTTP manquants",
        description=(
            "Le site ne renvoie ni Content-Security-Policy, ni Strict-Transport-Security, "
            "ni X-Frame-Options, ni X-Content-Type-Options. Exposition aux attaques XSS, clickjacking et MIME-sniffing."
        ),
        evidence="GET / → headers: Server: Webflow (aucun header sécurité dans la réponse).",
        recommendation="Ajouter les 4 headers de sécurité critiques via Cloudflare Transform Rules ou Webflow custom headers.",
        actions=[
            "Cloudflare → Rules → Transform Rules → Modify Response Header",
            'Ajouter: Strict-Transport-Security: max-age=63072000; includeSubDomains; preload',
            'Ajouter: Content-Security-Policy: default-src \'self\' https:; script-src \'self\' https://assets.website-files.com \'unsafe-inline\'',
            'Ajouter: X-Frame-Options: SAMEORIGIN',
            'Ajouter: X-Content-Type-Options: nosniff',
            "Tester sur securityheaders.com — objectif note A minimum",
        ],
        impact="high",
        effort="quick",
        reference="https://web.dev/security-headers/",
    ),
    Finding(
        severity="critical",
        title="Bandeau cookies non conforme RGPD",
        description=(
            "Google Analytics, Meta Pixel et HotJar se déclenchent avant tout consentement utilisateur. "
            "Risque de sanction CNIL (amende jusqu'à 20M€ ou 4% du CA) et perte de confiance."
        ),
        evidence="Observed: _ga, _gid, _fbp, _hjSessionUser cookies set on first page load before any user interaction.",
        recommendation="Implémenter un CMP (Consent Management Platform) qui bloque les scripts tiers tant que le consentement n'est pas explicite.",
        actions=[
            "Installer Axeptio ou Didomi (tarif ~30€/mois pour ce volume)",
            "Catégoriser les trackers: nécessaires (toujours actifs), analytics, marketing, préférences",
            "Intégrer le mode Consent Mode v2 de Google pour continuer à recevoir des données agrégées même sans consentement",
            "Journaliser les consentements (preuve CNIL en cas d'audit)",
            "Ajouter un lien 'Gérer mes cookies' dans le footer de toutes les pages",
        ],
        impact="high",
        effort="medium",
        reference="https://www.cnil.fr/fr/cookies-et-autres-traceurs/regles/cookies-solutions-pour-les-outils-de-mesure-daudience",
    ),
    Finding(
        severity="warning",
        title="Absence de politique de confidentialité détaillée",
        description="La page /mentions-legales existe mais ne détaille pas les finalités de traitement des données, les sous-traitants (Webflow US, Google, Meta) ni la durée de conservation.",
        recommendation="Rédiger une politique de confidentialité exhaustive conforme au RGPD (articles 13 & 14).",
        actions=[
            "Lister toutes les données collectées (formulaires, cookies, logs serveur)",
            "Indiquer les sous-traitants et transferts hors UE (Webflow = États-Unis)",
            "Mentionner les DPIA (Data Protection Impact Assessments) effectuées",
            "Publier les durées de conservation par type de donnée",
        ],
        impact="medium",
        effort="medium",
    ),
    Finding(
        severity="warning",
        title="Formulaire de contact sans CAPTCHA",
        description="Le formulaire /nous-contacter est vulnérable au spam automatisé. À terme, risque de dégradation de la délivrabilité email si les bots saturent.",
        recommendation="Ajouter reCAPTCHA v3 (invisible) ou hCaptcha pour bloquer les bots sans frictionner les utilisateurs.",
        actions=[
            "Créer une clé reCAPTCHA v3 sur google.com/recaptcha",
            "Intégrer le script dans Webflow → Page Settings → Before </body>",
            "Vérifier côté serveur le token retourné (score > 0.5)",
        ],
        impact="low",
        effort="quick",
    ),
    Finding(
        severity="info",
        title="Aucun honeypot anti-bot sur les formulaires",
        description="Complément au CAPTCHA : un champ 'honeypot' invisible pour les humains mais rempli par les bots permet de les filtrer sans UX cost.",
        recommendation="Ajouter un champ input type=text name='website' caché en CSS, et rejeter toute soumission où ce champ est rempli.",
        impact="low",
        effort="quick",
    ),
    Finding(
        severity="ok",
        title="HTTPS correctement appliqué",
        description="Le certificat TLS est valide jusqu'à 2026-09, délivré par Let's Encrypt via Webflow. Redirection 301 du HTTP vers HTTPS en place.",
        evidence="curl -I http://lasource-foodschool.com → 301 → https://www.lasource-foodschool.com",
    ),
]

# ---------------------------------------------------------------------------
# SEO (10 findings)

_SEO = [
    Finding(
        severity="critical",
        title="Faute d'orthographe dans un title indexé Google",
        description=(
            "La page /se-former affiche « Formations diplomantes » au lieu de « diplômantes » "
            "dans sa balise title. Ce title est visible directement dans les résultats Google, "
            "ce qui dégrade la crédibilité perçue et le taux de clic."
        ),
        evidence='<title>La Source — Formations diplomantes en cuisine</title>  (page /se-former)',
        recommendation="Corriger immédiatement le title dans Webflow (Settings → SEO).",
        actions=[
            "Webflow Designer → Pages → /se-former → Page Settings → SEO Title",
            "Remplacer « diplomantes » par « diplômantes »",
            "Republier le site",
            "Demander une réindexation dans Google Search Console → URL Inspection",
        ],
        impact="high",
        effort="quick",
    ),
    Finding(
        severity="critical",
        title="0 des 11 pages principales n'a de meta description rédigée",
        description=(
            "Toutes les pages laissent Google générer automatiquement un snippet à partir du "
            "premier paragraphe. Résultat : snippets peu vendeurs, CTR sous-optimal estimé à -30%."
        ),
        recommendation="Rédiger 11 meta descriptions de 150-160 caractères, orientées bénéfice + CTA.",
        actions=[
            "Lister les 11 pages dans un tableau (URL, mot-clé cible, angle)",
            "Rédiger chaque meta avec structure : [Bénéfice] + [Preuve/Chiffre] + [CTA]",
            "Exemple pour /se-former : « Devenez cuisinier(ère) en 12 mois avec nos formations RNCP à Paris & Toulouse. Alternance possible. Financement CPF. »",
            "Intégrer chaque meta dans Webflow → Page Settings → Meta Description",
            "Vérifier la longueur avec l'outil SERP Simulator (yoast.com ou mangools.com)",
        ],
        impact="high",
        effort="medium",
        reference="https://developers.google.com/search/docs/appearance/snippet",
    ),
    Finding(
        severity="critical",
        title="Cannibalisation SEO entre deux pages formations",
        description=(
            "/formation-cuisine-alternance et /formation-cuisine-courte partagent exactement "
            "le même title, le même H1 (« Commis de cuisine ») et ciblent les mêmes requêtes. "
            "Google ne sait pas laquelle ranker et pénalise les deux."
        ),
        evidence='Both pages: <title>Le Foodcamp | Formations certifiantes | TFP Commis de cuisine</title>',
        recommendation="Différencier radicalement les deux pages par cible, durée et format.",
        actions=[
            "/formation-cuisine-alternance → cibler « formation cuisine alternance paris » (mot-clé commercial, volume 480/mois)",
            "/formation-cuisine-courte → cibler « formation courte cuisine adulte » (volume 320/mois)",
            "Réécrire H1 de chaque page pour refléter la cible",
            "Ajouter des sections uniques : durée, rythme, coût, public visé",
            "Croiser les liens internes entre les deux pages avec des ancres différenciées",
        ],
        impact="high",
        effort="medium",
    ),
    Finding(
        severity="critical",
        title="URL opaque /foodcamp-cycle2-alternance",
        description=(
            "Cette URL utilise un jargon interne (« foodcamp », « cycle2 ») incompréhensible "
            "pour Google et les utilisateurs. Aucun mot-clé métier dans l'URL."
        ),
        recommendation="Renommer l'URL en une version SEO-friendly avec mots-clés métier.",
        actions=[
            "Cible : /formation-cuisine-alternance-cycle-avance",
            "Dans Webflow : Page Settings → Slug → renommer",
            "Créer une redirection 301 depuis l'ancienne URL (Webflow → Project Settings → Hosting → 301 Redirects)",
            "Mettre à jour tous les liens internes pointant vers l'ancienne URL",
            "Soumettre la nouvelle URL à Google Search Console",
        ],
        impact="high",
        effort="medium",
    ),
    Finding(
        severity="warning",
        title="Structure Hn incohérente sur la home",
        description=(
            "La homepage comporte 3 balises H1 (une dans le hero, deux dans les sections) et "
            "saute le H2 pour passer directement du H1 au H3. Google perd le fil sémantique."
        ),
        evidence="Home DOM: h1 (x3), h3 (x5), h4 (x2) — aucun h2 détecté.",
        recommendation="Structure Hn stricte : 1 seul H1 par page, puis H2 pour chaque section majeure, H3 pour les sous-sections.",
        actions=[
            "Auditer chaque page avec l'extension Chrome « Headings Map »",
            "Rétrograder les H1 supplémentaires en H2",
            "Insérer des H2 pour les sections actuellement en H3",
            "Vérifier la hiérarchie avec screamingfrog.co.uk (crawler)",
        ],
        impact="medium",
        effort="medium",
    ),
    Finding(
        severity="warning",
        title="Aucune donnée structurée Schema.org sur les formations",
        description=(
            "Les pages de formation ne déclarent ni `Course`, ni `EducationalOccupationalProgram`. "
            "Google ne peut pas générer de rich snippets formations dans les SERP."
        ),
        recommendation="Implémenter le schéma `Course` et `EducationalOccupationalProgram` sur chaque page formation.",
        actions=[
            "Utiliser schema.org/Course (provider, hasCourseInstance, educationalCredentialAwarded)",
            "Ajouter RNCP 37859 en tant que `educationalCredentialAwarded` de type `EducationalOccupationalCredential`",
            "Injecter le JSON-LD via Webflow → Page Settings → Custom Code → Inside <head>",
            "Valider sur search.google.com/test/rich-results",
        ],
        impact="medium",
        effort="medium",
        reference="https://schema.org/Course",
    ),
    Finding(
        severity="warning",
        title="URL blog /sinspirer non-SEO",
        description="Le blog est sous /sinspirer (néologisme), illisible par Google, aucun volume sur cette requête.",
        recommendation="Migrer le blog sous /blog, standard de facto.",
        actions=[
            "Renommer la page parent blog en /blog dans Webflow",
            "Mettre en place 301 de /sinspirer/* → /blog/* en conservant les slugs enfants",
            "Mettre à jour la navigation principale et le footer",
        ],
        impact="medium",
        effort="quick",
    ),
    Finding(
        severity="warning",
        title="Sitemap XML non soumis à Google Search Console",
        description="Webflow génère bien /sitemap.xml mais il n'est pas déclaré dans GSC. Le crawl Google est donc réactif et non proactif.",
        recommendation="Soumettre le sitemap dans Google Search Console pour forcer un crawl régulier.",
        actions=[
            "Google Search Console → Sitemaps → Ajouter sitemap.xml",
            "Vérifier le nombre d'URLs détectées vs soumises (écart = problème de crawlabilité)",
            "Planifier un audit mensuel des URLs non indexées dans GSC > Pages",
        ],
        impact="medium",
        effort="quick",
    ),
    Finding(
        severity="info",
        title="Robots.txt minimaliste",
        description="Le robots.txt actuel ne contient que les directives par défaut Webflow. Aucune directive explicite de blocage des pages admin/parcours de paiement.",
        recommendation="Enrichir le robots.txt avec les directives Allow/Disallow utiles et l'URL du sitemap.",
        impact="low",
        effort="quick",
    ),
    Finding(
        severity="missing",
        title="Aucune page locale par ville",
        description=(
            "Le site revendique 3 campus (Paris, Toulouse, Bordeaux) mais ne dispose d'aucune "
            "page dédiée « formation cuisine [ville] », alors que ces requêtes cumulent 3000+ recherches/mois."
        ),
        recommendation="Créer 3 landing pages locales, une par ville, optimisées pour la requête locale.",
        actions=[
            "/formation-cuisine-paris — cible « formation cuisine paris » (1 900/mois)",
            "/formation-cuisine-toulouse — cible « formation cuisine toulouse » (400/mois)",
            "/formation-cuisine-bordeaux — cible « formation cuisine bordeaux » (700/mois)",
            "Chaque page : H1 avec ville, mentions campus + adresse, carte Google Maps, témoignages locaux",
            "Créer un Google Business Profile pour chaque campus et lier vers la landing locale",
        ],
        impact="high",
        effort="heavy",
    ),
]

# ---------------------------------------------------------------------------
# UX (5 findings)

_UX = [
    Finding(
        severity="warning",
        title="CTA principal peu contrasté en dark mode",
        description="Le bouton « Candidater » utilise du jaune sur fond noir mais son ratio de contraste est de 3.8:1 (norme WCAG AA = 4.5:1 minimum).",
        evidence="Button bg=#D4A853, text=#0F0F0D — contrast ratio 3.8:1 measured via axe DevTools.",
        recommendation="Ajuster la couleur du bouton pour atteindre au moins 4.5:1.",
        actions=[
            "Solution A : foncer le fond or à #B8892D (ratio 4.7:1)",
            "Solution B : garder l'or actuel mais passer le texte en #FFFFFF (ratio 5.2:1)",
            "Tester avec contrastchecker.com sur les deux options",
        ],
        impact="medium",
        effort="quick",
        reference="https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html",
    ),
    Finding(
        severity="warning",
        title="Navigation mobile sans indicateur de section active",
        description="Sur mobile, le menu burger ouvre un drawer mais ne met pas en avant la page courante. L'utilisateur perd la notion de navigation.",
        recommendation="Ajouter un état `aria-current=\"page\"` + style visuel (soulignement or) sur le lien actif.",
        actions=[
            "Webflow → Navigator → sélectionner le lien du menu mobile",
            "Ajouter la classe CSS active (border-bottom or, opacity pleine)",
            "Injecter un snippet JS qui compare window.location.pathname à chaque link.href",
        ],
        impact="medium",
        effort="quick",
    ),
    Finding(
        severity="warning",
        title="Formulaire de contact en 12 champs",
        description=(
            "Trop de champs obligatoires (prénom, nom, email, téléphone, ville, formation souhaitée, "
            "date de naissance, niveau actuel, objectif, disponibilités, budget, source). "
            "Taux de complétion estimé : < 15%."
        ),
        recommendation="Réduire à 4 champs obligatoires, reporter le reste en étape 2 ou dans un call de qualification.",
        actions=[
            "Étape 1 (formulaire court) : prénom, email, téléphone, formation souhaitée",
            "Étape 2 (après 1er contact) : qualification par un conseiller — les 8 autres champs",
            "Mesurer le taux de conversion formulaire avant/après (GA4 event 'form_submit')",
        ],
        impact="high",
        effort="quick",
    ),
    Finding(
        severity="info",
        title="Temps de lecture non indiqué sur les articles blog",
        description="Les articles ne mentionnent pas leur durée de lecture estimée, ce qui limite l'engagement (information clé sur mobile).",
        recommendation="Afficher un petit label « X min de lecture » en début d'article.",
        impact="low",
        effort="quick",
    ),
    Finding(
        severity="ok",
        title="Design global cohérent et identitaire",
        description="Charte graphique claire, photos de haute qualité, rythme visuel agréable. Le site ne fait pas générique.",
    ),
]

# ---------------------------------------------------------------------------
# Content (5 findings)

_CONTENT = [
    Finding(
        severity="critical",
        title="Absence totale de preuve sociale chiffrée",
        description=(
            "Aucun chiffre de performance : taux d'insertion, nombre de diplômés, partenaires employeurs, "
            "avis Google. Sur un marché concurrentiel (Ferrandi, Le Cordon Bleu), c'est un frein majeur à la conversion."
        ),
        recommendation="Intégrer un bandeau chiffres-clés en haut de home et page /se-former.",
        actions=[
            "Collecter : nb diplômés depuis 2020, taux d'insertion à 6 mois, nb partenaires restaurants",
            "Demander au réseau alumni 20-30 témoignages vidéo courts (30s)",
            "Ajouter un widget Avis Google sur la home + bas de page contact",
            "Publier le taux de réussite RNCP (obligatoire Qualiopi)",
        ],
        impact="high",
        effort="medium",
    ),
    Finding(
        severity="critical",
        title="Pas de proposition de valeur différenciante visible en 5 secondes",
        description=(
            "La home parle de « cuisiner le monde de demain » sans expliquer : pour qui, avec quoi, avec quels résultats. "
            "Un visiteur ne sait pas immédiatement ce qui distingue La Source de Ferrandi ou Le Cordon Bleu."
        ),
        recommendation="Réécrire le hero en respectant la structure : [Pour qui] + [Quoi] + [Différenciation concrète].",
        actions=[
            "Exemple : « Formations RNCP cuisine durable à Paris & Toulouse — la seule école 100% bio, zéro déchet, avec 94% d'insertion »",
            "Remplacer la vidéo hero par une formule verbale forte + 3 chiffres-clés en dessous",
            "A/B tester 2 variantes pendant 2 semaines (GA4 + Hotjar)",
        ],
        impact="high",
        effort="medium",
    ),
    Finding(
        severity="warning",
        title="Ton éditorial inégal entre les pages",
        description=(
            "La home est poétique (« Cuisinez le monde de demain »), la page /se-former est très technique (RNCP, TFP, cycles), "
            "la page blog est décontractée. Dissonance pour le lecteur."
        ),
        recommendation="Établir une charte éditoriale avec 3 règles de ton et l'appliquer à toutes les pages.",
        actions=[
            "Rédiger un document 'Voix La Source' : vocabulaire autorisé, vocabulaire interdit, niveau de formalité",
            "Relire et harmoniser toutes les pages de 1er niveau (8 pages)",
            "Former les rédacteurs blog à cette charte",
        ],
        impact="medium",
        effort="heavy",
    ),
    Finding(
        severity="missing",
        title="Absence de lead magnet",
        description="Aucun téléchargement (brochure, guide, quiz d'orientation) en échange d'un email. Le site ne capte pas les visiteurs non encore prêts à candidater.",
        recommendation="Créer un lead magnet principal : « Guide : choisir sa formation cuisine en 2026 » (PDF 15 pages).",
        actions=[
            "Rédaction du PDF par le responsable pédagogique (2 semaines)",
            "Landing page /guide-formation-cuisine avec formulaire email",
            "Automation : séquence email de 5 messages sur 2 semaines (bienvenue → témoignage → comparatif → call-to-action)",
            "Outil : Brevo (ex-Sendinblue) ou Mailchimp, gratuit jusqu'à 500 contacts",
        ],
        impact="high",
        effort="heavy",
    ),
    Finding(
        severity="info",
        title="Blog actif mais peu d'articles evergreen",
        description="Les 12 derniers articles sont des actualités (événements, portraits). Peu de contenus de type « comment/pourquoi » qui attirent un trafic SEO durable.",
        recommendation="Publier 1 article evergreen par mois pour bâtir un socle SEO long terme.",
        impact="medium",
        effort="medium",
    ),
]

# ---------------------------------------------------------------------------
# Performance (5 findings)

_PERF = [
    Finding(
        severity="critical",
        title="LCP mobile à 4.2 s — au-delà du seuil « poor »",
        description=(
            "Le Largest Contentful Paint sur mobile est mesuré à 4.2 s (seuil « good » = 2.5 s, seuil « poor » = 4 s). "
            "Google pénalise activement les sites au-delà de 4 s dans le classement mobile."
        ),
        evidence="PageSpeed Insights (2026-04-23, 4G emulated) — LCP: 4.2s / FID: 120ms / CLS: 0.18.",
        recommendation="Optimiser les images du hero et réduire le JavaScript bloquant.",
        actions=[
            "Convertir toutes les images hero en WebP (gain ~40% de poids)",
            "Ajouter rel=\"preload\" sur l'image LCP du hero",
            "Activer lazy-loading sur les images below-the-fold (Webflow → Image Settings → Lazy Load: on)",
            "Différer les scripts non critiques (HotJar, Meta Pixel) avec async/defer",
            "Cible : LCP < 2.5 s dans les 30 jours",
        ],
        impact="high",
        effort="medium",
        reference="https://web.dev/lcp/",
    ),
    Finding(
        severity="warning",
        title="CLS à 0.18 — décalages visuels gênants",
        description="Le Cumulative Layout Shift de 0.18 (seuil « good » = 0.1) provient principalement des images sans dimensions et des fonts qui chargent tardivement.",
        recommendation="Fixer width/height sur toutes les images et préloader les fonts web.",
        actions=[
            "Ajouter width/height HTML sur toutes les <img> (Webflow le fait automatiquement si on utilise l'upload Webflow, pas les URLs externes)",
            "Ajouter <link rel=\"preload\" as=\"font\" type=\"font/woff2\" crossorigin> pour DM Serif et DM Sans",
            "Tester CLS avec Lighthouse en mode mobile",
        ],
        impact="medium",
        effort="quick",
    ),
    Finding(
        severity="warning",
        title="12 scripts tiers chargés sur toutes les pages",
        description=(
            "GA4, Meta Pixel, HotJar, LinkedIn Insight Tag, Google Maps, Tally, Axeptio... chaque script ajoute "
            "50-200 KB et un round-trip réseau. Total : ~1.4 MB de JS tiers avant interaction."
        ),
        recommendation="Auditer chaque script et ne charger que ceux strictement nécessaires, avec chargement différé.",
        actions=[
            "Lister tous les scripts tiers et justifier leur présence",
            "Supprimer ceux qui ne servent plus (audit : LinkedIn Insight Tag reste-t-il utile ?)",
            "Charger les restants avec defer/async",
            "Utiliser Google Tag Manager pour centraliser et optimiser",
        ],
        impact="medium",
        effort="medium",
    ),
    Finding(
        severity="info",
        title="Pas de CDN devant Webflow",
        description="Webflow hébergé sur AWS CloudFront par défaut, mais aucune couche de cache personnalisée. Sur un site plutôt statique, un CDN Cloudflare en amont accélérerait encore le TTFB.",
        recommendation="Passer le DNS par Cloudflare (plan gratuit suffit) et activer le cache edge.",
        impact="low",
        effort="quick",
    ),
    Finding(
        severity="ok",
        title="Compression Brotli active",
        description="Les assets statiques sont servis avec Content-Encoding: br. Gain ~20% vs gzip.",
    ),
]

# ---------------------------------------------------------------------------
# Business (6 findings)

_BUSINESS = [
    Finding(
        severity="critical",
        title="Aucun tracking de conversion paramétré",
        description=(
            "Aucun événement GA4 n'est configuré sur les soumissions de formulaires, clics CTA ou téléchargements. "
            "Impossible de calculer un coût par lead ou un taux de conversion par source de trafic."
        ),
        recommendation="Paramétrer 8 événements GA4 critiques + GTM pour orchestrer.",
        actions=[
            "Événements à créer : form_submit_contact, form_submit_candidature, cta_click_hero, cta_click_sticky, download_brochure, video_play, scroll_75, phone_click",
            "Outil : Google Tag Manager (gratuit)",
            "Lier GA4 à Google Ads pour remonter les conversions dans les campagnes",
            "Créer un rapport hebdo dans Looker Studio : sessions → leads → clients",
        ],
        impact="high",
        effort="medium",
    ),
    Finding(
        severity="critical",
        title="Aucun call-to-action sticky sur mobile",
        description="Sur mobile, après le scroll, aucun CTA n'est visible. L'utilisateur doit remonter pour trouver le bouton « Candidater ».",
        recommendation="Ajouter un CTA sticky en bas d'écran mobile sur toutes les pages formations.",
        actions=[
            "Webflow → Symbol → Créer un bloc sticky bottom (position fixed, bottom: 0, z-index: 100)",
            "CTA : « Candidater » ou « Être rappelé »",
            "Masquer sur desktop (media query)",
            "Mesurer l'uplift sur les conversions formulaires",
        ],
        impact="high",
        effort="quick",
    ),
    Finding(
        severity="warning",
        title="Pas de page /prix ou /financement",
        description=(
            "Aucune page ne parle du coût des formations ni des financements possibles (CPF, OPCO, Pôle Emploi, alternance). "
            "Ce sont pourtant les 2 premières questions d'un prospect."
        ),
        recommendation="Créer une page /financement-formation-cuisine exhaustive.",
        actions=[
            "Sections : Prix par formation, Financement CPF (avec simulateur), Alternance (coût = 0€), OPCO, Pôle Emploi",
            "Intégrer un lien Mon Compte Formation pour chaque formation éligible",
            "CTA : « Simuler mon financement » → formulaire de mise en relation",
        ],
        impact="high",
        effort="medium",
    ),
    Finding(
        severity="warning",
        title="Aucun suivi retargeting installé",
        description="Le Meta Pixel est présent mais aucune audience custom n'est paramétrée. Les visiteurs qui ne convertissent pas ne sont jamais retargetés.",
        recommendation="Créer 3 audiences Meta et 3 audiences Google Ads pour les campagnes de remarketing.",
        actions=[
            "Audience Meta 1 : visiteurs home 7 derniers jours",
            "Audience Meta 2 : visiteurs /se-former 14 derniers jours (plus qualifiés)",
            "Audience Meta 3 : soumissions formulaire sans follow-up",
            "Déployer 3 campagnes remarketing avec budgets 15€/jour",
        ],
        impact="medium",
        effort="medium",
    ),
    Finding(
        severity="info",
        title="Avis Google non remontés sur le site",
        description="L'école a 47 avis Google (note 4.8). Aucun affichage sur le site.",
        recommendation="Intégrer un widget Google Reviews sur la home et la page candidature.",
        impact="medium",
        effort="quick",
    ),
    Finding(
        severity="missing",
        title="Pas de page /pourquoi-la-source",
        description="Aucune page ne raconte l'histoire, la mission, les valeurs et l'équipe. C'est pourtant un élément clé de décision pour une école.",
        recommendation="Créer une page narrative avec l'histoire, les fondateurs, la mission écologique, les engagements Qualiopi.",
        impact="medium",
        effort="heavy",
    ),
]


# ---------------------------------------------------------------------------
# Pages (detailed)


_PAGES = [
    PageAnalysis(
        url="https://www.lasource-foodschool.com/",
        status="critical",
        title="Le Foodcamp — École de cuisine engagée à Paris et Toulouse",
        titleLength=66,
        h1="Cuisinez le monde de demain.",
        metaDescription=None,
        metaLength=0,
        targetKeywords=["école cuisine durable", "formation cuisine paris", "école cuisine engagée"],
        presentKeywords=["cuisine", "école", "foodcamp", "engagée"],
        missingKeywords=["RNCP", "alternance", "diplôme", "insertion", "Paris", "Toulouse", "CPF"],
        findings=[
            Finding(
                severity="critical",
                title="Meta description absente — Google génère un snippet suboptimal",
                description="Google prend le premier paragraphe (« Bienvenue chez Le Foodcamp... ») — snippet peu vendeur.",
                impact="high",
                effort="quick",
            ),
            Finding(
                severity="warning",
                title="H1 poétique sans mot-clé métier",
                description="« Cuisinez le monde de demain » ne contient ni « formation » ni « cuisine » ni « école ».",
                impact="medium",
                effort="quick",
            ),
            Finding(
                severity="warning",
                title="Absence de chiffres-clés above-the-fold",
                description="Aucune preuve sociale (nb diplômés, taux insertion) visible sans scroll.",
                impact="medium",
                effort="medium",
            ),
        ],
        recommendation=PageRecommendation(
            urlCurrent="/",
            titleCurrent="Le Foodcamp — École de cuisine engagée à Paris et Toulouse",
            h1Current="Cuisinez le monde de demain.",
            metaCurrent=None,
            title="École de cuisine engagée — Formations RNCP Paris & Toulouse | La Source",
            h1="École de cuisine durable — Formations RNCP à Paris et Toulouse",
            meta="La Source forme les cuisiniers de demain : formations RNCP en alternance, cuisine durable et zéro déchet. Campus à Paris & Toulouse. 94% d'insertion.",
            actions=[
                "Webflow → Pages → Home → Page Settings",
                "Remplacer le Title par la version recommandée (maximum 70 caractères)",
                "Rédiger la meta description (155 caractères)",
                "Modifier le H1 du hero depuis le Designer",
                "Ajouter un bandeau chiffres-clés juste sous le hero (4 chiffres)",
                "Republier et demander la réindexation",
            ],
        ),
    ),
    PageAnalysis(
        url="https://www.lasource-foodschool.com/formation-cuisine-alternance-paris-bordeaux-toulouse-foodcamp",
        status="critical",
        title="Le Foodcamp | Formations certifiantes | TFP Commis de cuisine",
        titleLength=63,
        h1="Commis de cuisine",
        metaDescription=None,
        metaLength=0,
        targetKeywords=["formation commis cuisine alternance", "RNCP 37859", "alternance cuisine paris"],
        presentKeywords=["commis", "alternance", "TFP", "Paris", "cuisine"],
        missingKeywords=["prix", "durée", "CPF", "salaire alternant", "débouchés", "entreprises partenaires"],
        findings=[
            Finding(
                severity="critical",
                title="URL opaque « foodcamp » — illisible par Google et utilisateur",
                description="Aucun mot-clé métier dans l'URL.",
                impact="high",
                effort="medium",
            ),
            Finding(
                severity="critical",
                title="URL contient 3 villes — cannibalise les pages locales futures",
                description="« paris-bordeaux-toulouse » dans l'URL dilue la pertinence par ville.",
                impact="high",
                effort="medium",
            ),
            Finding(
                severity="warning",
                title="H1 trop court (« Commis de cuisine ») — aucune contextualisation",
                description="Manque la mention de l'alternance, du diplôme et de la durée.",
                impact="medium",
                effort="quick",
            ),
            Finding(
                severity="warning",
                title="Cannibalisation avec /formation-cuisine-courte (même title, même H1)",
                description="Google ne sait pas laquelle ranker.",
                impact="high",
                effort="medium",
            ),
        ],
        recommendation=PageRecommendation(
            urlCurrent="/formation-cuisine-alternance-paris-bordeaux-toulouse-foodcamp",
            titleCurrent="Le Foodcamp | Formations certifiantes | TFP Commis de cuisine",
            h1Current="Commis de cuisine",
            metaCurrent=None,
            url="/formation-commis-cuisine-alternance-paris",
            title="Formation Commis Cuisine en Alternance Paris | RNCP 37859 — La Source",
            h1="Formation Commis de Cuisine en Alternance — 12 mois, Paris, RNCP 37859",
            meta="Devenez commis de cuisine en 12 mois d'alternance à Paris. Formation RNCP 37859, rémunérée, dans une école engagée en cuisine durable. Candidatures ouvertes.",
            actions=[
                "Renommer le slug Webflow : /formation-commis-cuisine-alternance-paris",
                "Créer une redirection 301 depuis l'ancienne URL (Webflow → Hosting → 301 Redirects)",
                "Réécrire Title, H1 et Meta selon les valeurs recommandées",
                "Ajouter 4 sections manquantes : Prix & financement, Rythme de l'alternance, Salaire alternant, Entreprises partenaires",
                "Injecter le Schema.org Course (JSON-LD) dans <head>",
                "Mettre à jour le menu principal pour pointer vers la nouvelle URL",
                "Demander une réindexation Google dans GSC",
            ],
            estimatedMonthlyTraffic=480,
        ),
    ),
    PageAnalysis(
        url="https://www.lasource-foodschool.com/se-former",
        status="critical",
        title="La Source — Formations diplomantes en cuisine",
        titleLength=46,
        h1="Se former à La Source",
        metaDescription=None,
        metaLength=0,
        targetKeywords=["formation cuisine", "école cuisine diplômante", "se former cuisine"],
        presentKeywords=["formation", "cuisine", "diplômante"],
        missingKeywords=["RNCP", "alternance", "prix", "Paris", "Toulouse"],
        findings=[
            Finding(
                severity="critical",
                title="Faute d'orthographe dans le title — « diplomantes »",
                description="Apparaît tel quel dans les SERP Google, dégrade la crédibilité.",
                evidence="<title>La Source — Formations diplomantes en cuisine</title>",
                impact="high",
                effort="quick",
            ),
            Finding(
                severity="warning",
                title="Page hub sans structure claire",
                description="Liste des formations sans hiérarchie visuelle, aucun filtre par durée ou niveau.",
                impact="medium",
                effort="medium",
            ),
        ],
        recommendation=PageRecommendation(
            urlCurrent="/se-former",
            titleCurrent="La Source — Formations diplomantes en cuisine",
            h1Current="Se former à La Source",
            title="Toutes les formations cuisine diplômantes — La Source Paris & Toulouse",
            h1="Toutes nos formations cuisine — Diplômantes, en alternance ou courtes",
            meta="Découvrez toutes les formations cuisine diplômantes de La Source : alternance, formations courtes, Paris & Toulouse. 100% RNCP, financement CPF possible.",
            actions=[
                "Corriger immédiatement « diplomantes » → « diplômantes » dans le title",
                "Restructurer en 3 blocs : Alternance / Formations courtes / Masterclasses",
                "Ajouter filtres (durée, ville, niveau d'entrée)",
                "Demander réindexation Google sur cette page",
            ],
        ),
    ),
]


# ---------------------------------------------------------------------------
# Missing pages (enriched)

_MISSING = [
    MissingPage(
        url="/formation-cuisine-paris",
        reason="Capter la requête locale principale — aucune page dédiée, 1 900 recherches/mois.",
        estimatedSearchVolume=1900,
        priority="high",
    ),
    MissingPage(
        url="/formation-cuisine-toulouse",
        reason="Deuxième campus sans page locale. Concurrents directs (Ferrandi Toulouse) occupent la SERP.",
        estimatedSearchVolume=400,
        priority="high",
    ),
    MissingPage(
        url="/financement-formation-cpf",
        reason="Frein principal à la conversion (question #1 des prospects). Aucune page ne traite du sujet.",
        estimatedSearchVolume=800,
        priority="high",
    ),
    MissingPage(
        url="/formation-patisserie-paris",
        reason="Extension naturelle de l'offre — requête connexe à fort volume non couverte.",
        estimatedSearchVolume=900,
        priority="medium",
    ),
    MissingPage(
        url="/nos-diplomes-insertion",
        reason="Preuve sociale et storytelling — requête informationnelle de qualification.",
        estimatedSearchVolume=300,
        priority="medium",
    ),
    MissingPage(
        url="/pourquoi-la-source",
        reason="Page « à propos » narrative absente — étape de décision clé pour une école.",
        estimatedSearchVolume=200,
        priority="low",
    ),
]


# ---------------------------------------------------------------------------


def build_fixture() -> AuditResult:
    sections = [
        SectionResult(
            section="security",
            title="Sécurité",
            score=48,
            verdict="À consolider — plusieurs fondamentaux manquants",
            findings=_SECURITY,
        ),
        SectionResult(
            section="seo",
            title="SEO",
            score=38,
            verdict="Bloquant — gains rapides à fort impact disponibles",
            findings=_SEO,
        ),
        SectionResult(
            section="ux",
            title="UX / Design",
            score=64,
            verdict="Bon niveau visuel, quelques frictions persistantes",
            findings=_UX,
        ),
        SectionResult(
            section="content",
            title="Contenu",
            score=52,
            verdict="Proposition forte, preuves sociales à renforcer",
            findings=_CONTENT,
        ),
        SectionResult(
            section="performance",
            title="Performance",
            score=55,
            verdict="Acceptable, images et scripts tiers à optimiser",
            findings=_PERF,
        ),
        SectionResult(
            section="business",
            title="Opportunités business",
            score=42,
            verdict="Leviers de conversion massivement sous-exploités",
            findings=_BUSINESS,
        ),
    ]

    return AuditResult(
        id="fixture-0001",
        domain="lasource-foodschool.com",
        url="https://www.lasource-foodschool.com",
        createdAt=datetime.now(timezone.utc).isoformat(),
        globalScore=50,
        globalVerdict="À consolider — 37 points d'action identifiés",
        scores={
            "security": 48,
            "seo": 38,
            "ux": 64,
            "content": 52,
            "performance": 55,
            "business": 42,
        },
        sections=sections,
        criticalCount=11,
        warningCount=16,
        quickWins=[
            "Corriger la faute « diplomantes » → « diplômantes » dans le title de /se-former (10 min, impact fort).",
            "Rédiger les 11 meta descriptions manquantes (2 h, +30% CTR estimé).",
            "Ajouter les 4 headers de sécurité HTTP via Cloudflare (30 min).",
            "Ajouter un CTA sticky en bas d'écran mobile sur les pages formations (1 h).",
            "Activer le lazy-loading sur toutes les images below-the-fold (15 min, -1 s LCP).",
            "Paramétrer les 8 événements GA4 de conversion via GTM (2 h).",
            "Différencier les pages /formation-cuisine-alternance et /formation-cuisine-courte (cannibalisation).",
            "Créer /formation-cuisine-paris pour capter 1 900 recherches mensuelles.",
        ],
        pages=_PAGES,
        missingPages=_MISSING,
    )


def main() -> int:
    out_dir = Path(os.getenv("PDF_OUT_DIR", "out"))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sample-audit.pdf"
    write_pdf(build_fixture(), str(path), agency_name="Agence Démo")
    print(f"PDF written to {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
