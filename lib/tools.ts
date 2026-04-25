export type ToolStatus = 'live' | 'soon' | 'planned'

export interface Tool {
  id: string
  name: string
  description: string
  href: string
  status: ToolStatus
  icon: ToolIcon
}

export type ToolIcon =
  | 'audit'
  | 'tracker'
  | 'competitor'
  | 'content'
  | 'monitor'
  | 'settings'
  | 'dashboard'
  | 'llms'
  | 'bulk'
  | 'sitemap'

export const TOOLS: Tool[] = [
  {
    id: 'audit',
    name: 'Audit Web',
    description: "Rapport SEO, UX, sécurité, performance d'un site",
    href: '/audit',
    status: 'live',
    icon: 'audit',
  },
  {
    id: 'seo-tracker',
    name: 'SEO Tracker',
    description: 'Suivi positionnement mots-clés par campagne',
    href: '/seo-tracker',
    status: 'live',
    icon: 'tracker',
  },
  {
    id: 'competitor-watch',
    name: 'Competitor Watch',
    description: 'Audit comparatif client vs ses concurrents avec synthèse IA',
    href: '/competitor-watch',
    status: 'live',
    icon: 'competitor',
  },
  {
    id: 'content-brief',
    name: 'Content Brief',
    description: 'Brief éditorial SEO complet à partir d\'une requête cible',
    href: '/content-brief',
    status: 'live',
    icon: 'content',
  },
  {
    id: 'ai-visibility',
    name: 'AI Visibility',
    description: 'Vérifie si un site est cité par les moteurs AI sur ses requêtes',
    href: '/ai-visibility',
    status: 'live',
    icon: 'monitor',
  },
  {
    id: 'llms-txt',
    name: 'llms.txt Generator',
    description: 'Génère le fichier llms.txt recommandé pour les moteurs IA',
    href: '/llms-txt',
    status: 'live',
    icon: 'llms',
  },
  {
    id: 'bulk-audit',
    name: 'Bulk Audit CSV',
    description: 'Lance des audits en masse depuis un CSV d\'URLs',
    href: '/bulk-audit',
    status: 'live',
    icon: 'bulk',
  },
  {
    id: 'sitemap-watcher',
    name: 'Sitemap Watcher',
    description: 'Détecte pages ajoutées ou supprimées d\'un sitemap',
    href: '/sitemap-watcher',
    status: 'live',
    icon: 'sitemap',
  },
  {
    id: 'perf-monitor',
    name: 'Performance Monitor',
    description: 'Core Web Vitals en continu sur les pages clés',
    href: '/perf-monitor',
    status: 'live',
    icon: 'monitor',
  },
]

export function getTool(id: string): Tool | undefined {
  return TOOLS.find((t) => t.id === id)
}
