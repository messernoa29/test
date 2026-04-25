import { BrandingSettings } from '@/components/settings/BrandingSettings'

export const dynamic = 'force-dynamic'

export default function SettingsPage() {
  return (
    <div className="max-w-4xl mx-auto px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-text-primary mb-1">Réglages</h1>
        <p className="text-sm text-text-secondary">
          Personnalisez l&apos;identité de l&apos;agence affichée sur les rapports générés.
        </p>
      </div>

      <BrandingSettings />

      <div className="mt-10 space-y-3">
        <PlaceholderCard
          title="Clé API Anthropic / Gemini"
          description="Gérer les clés utilisées par les outils d'analyse IA. Rotation possible sans redéploiement."
          badge="À venir"
        />
        <PlaceholderCard
          title="Exports & partage"
          description="Liens publics temporaires, intégrations Slack, envoi email automatique."
          badge="Planifié"
        />
        <PlaceholderCard
          title="Utilisateurs & rôles"
          description="Gestion multi-utilisateurs avec rôles (admin, consultant, lecture seule)."
          badge="Planifié"
        />
      </div>
    </div>
  )
}

function PlaceholderCard({
  title,
  description,
  badge,
}: {
  title: string
  description: string
  badge: string
}) {
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-4 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h3 className="font-medium text-text-primary mb-1">{title}</h3>
        <p className="text-sm text-text-secondary leading-relaxed">{description}</p>
      </div>
      <span className="text-[10px] tracking-wider uppercase font-medium text-text-tertiary bg-bg-elevated px-2 py-0.5 rounded flex-shrink-0">
        {badge}
      </span>
    </div>
  )
}
