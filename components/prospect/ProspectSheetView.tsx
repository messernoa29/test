'use client'

import Link from 'next/link'
import type {
  DetectedTech,
  ProspectSheet,
  ProspectStackByCategory,
  TechConfidence,
} from '@/lib/types'

interface Props {
  sheet: ProspectSheet
}

export function ProspectSheetView({ sheet }: Props) {
  const { identity, stack, persona } = sheet
  const title = identity?.name?.trim() || sheet.domain

  return (
    <div>
      <div className="border-b border-[var(--border-subtle)] bg-bg-surface">
        <div className="max-w-5xl mx-auto px-8 py-5 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs text-text-tertiary mb-1">
              Fiche prospect · {sheet.createdAt.slice(0, 10)}
            </p>
            <h1 className="text-xl font-semibold text-text-primary truncate">
              {title}
            </h1>
            <a
              href={sheet.url}
              target="_blank"
              rel="noreferrer"
              className="text-xs font-mono text-primary hover:underline"
            >
              {sheet.domain}
            </a>
          </div>
          <Link
            href="/prospect"
            className="inline-flex h-9 px-3 items-center bg-bg-surface text-text-secondary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated hover:text-text-primary transition-colors"
          >
            ← Toutes les fiches
          </Link>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-8 py-8 space-y-8">
        {sheet.status === 'failed' && (
          <ErrorBox message={sheet.error ?? 'Erreur inconnue'} />
        )}

        {/* 1. Identité entreprise */}
        <Card label="1 · Identité entreprise">
          {identity ? (
            <div className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <KeyValue label="Nom" value={identity.name} />
                <KeyValue label="Localisation" value={identity.location} />
                <KeyValue label="Secteur d'activité" value={identity.sector} />
                <KeyValue
                  label="Création estimée"
                  value={
                    identity.estimatedFoundedYear
                      ? `~${identity.estimatedFoundedYear}`
                      : undefined
                  }
                />
                <KeyValue label="Taille estimée" value={identity.estimatedSize} />
              </div>
              {identity.valueProposition && (
                <Field
                  label="Positionnement / proposition de valeur"
                  value={identity.valueProposition}
                />
              )}
              {identity.onlinePresenceNotes && (
                <Field
                  label="Présence en ligne"
                  value={identity.onlinePresenceNotes}
                />
              )}
              {identity.socialProfiles.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
                    Réseaux sociaux trouvés
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {identity.socialProfiles.map((p, i) => (
                      <a
                        key={i}
                        href={p}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center px-2 py-0.5 rounded border border-[var(--border-default)] bg-bg-elevated text-xs text-primary hover:underline truncate max-w-[260px]"
                      >
                        {p}
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <Empty />
          )}
        </Card>

        {/* 2. Stack technique */}
        <Card label="2 · Stack technique détecté">
          {stack && hasAnyTech(stack) ? (
            <div className="space-y-4">
              <TechGroup label="CMS / plateforme" items={stack.cms} />
              <TechGroup label="Analytics" items={stack.analytics} />
              <TechGroup label="Tags publicitaires" items={stack.advertising} />
              <TechGroup label="Chat / CRM" items={stack.chatCrm} />
              <TechGroup label="Hébergeur / CDN" items={stack.hostingCdn} />
              <TechGroup label="Autre" items={stack.other} />
              <p className="text-[11px] text-text-tertiary pt-1">
                Confiance : <ConfidenceDot c="high" /> détection HTML directe ·{' '}
                <ConfidenceDot c="medium" /> signal indirect ·{' '}
                <ConfidenceDot c="low" /> déduction heuristique.
              </p>
            </div>
          ) : (
            <p className="text-sm text-text-tertiary">
              Aucune technologie identifiable détectée dans le HTML public.
            </p>
          )}
        </Card>

        {/* 3. Persona décideur + angle d'approche + contacts */}
        <Card label="3 · Persona décideur, contacts & angles d'approche" tone="primary">
          {persona &&
          (persona.likelyContactRoles.length > 0 ||
            persona.likelyPriorities.length > 0 ||
            persona.approachAngles.length > 0 ||
            (persona.contacts?.length ?? 0) > 0 ||
            (persona.companyEmails?.length ?? 0) > 0 ||
            (persona.companyPhones?.length ?? 0) > 0 ||
            !!persona.companyAddress?.trim()) ? (
            <div className="space-y-5">
              {(persona.contacts?.length ?? 0) > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
                    Personnes identifiées
                  </div>
                  <div className="space-y-2">
                    {persona.contacts!.map((c, i) => (
                      <div
                        key={i}
                        className="border border-[var(--border-subtle)] rounded-md p-3 bg-bg-elevated"
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-text-primary">
                            {[c.firstName, c.lastName].filter(Boolean).join(' ') || '(nom inconnu)'}
                          </span>
                          {c.role && (
                            <span className="text-xs text-text-secondary">— {c.role}</span>
                          )}
                          <ConfidenceDot c={c.confidence} />
                          {c.source && (
                            c.sourceUrl ? (
                              <a
                                href={c.sourceUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="text-[10px] text-text-tertiary hover:text-primary hover:underline"
                                title={c.sourceUrl}
                              >
                                source : {c.source} ↗
                              </a>
                            ) : (
                              <span className="text-[10px] text-text-tertiary">({c.source})</span>
                            )
                          )}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs">
                          {c.email && (
                            <a href={`mailto:${c.email}`} className="text-primary hover:underline">
                              ✉ {c.email}
                            </a>
                          )}
                          {c.phone && (
                            <a href={`tel:${c.phone.replace(/[^\d+]/g, '')}`} className="text-primary hover:underline">
                              ☎ {c.phone}
                            </a>
                          )}
                          {c.linkedin && (
                            <a href={c.linkedin} target="_blank" rel="noreferrer" className="text-primary hover:underline truncate max-w-[260px]">
                              in {c.linkedin.replace(/^https?:\/\/(www\.)?linkedin\.com\//, '')}
                            </a>
                          )}
                          {!c.email && !c.phone && !c.linkedin && (
                            <span className="text-text-tertiary">Pas de coordonnée directe trouvée</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {((persona.companyEmails?.length ?? 0) > 0 ||
                (persona.companyPhones?.length ?? 0) > 0 ||
                !!persona.companyAddress?.trim()) && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
                    Coordonnées générales de l'entreprise
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(persona.companyEmails ?? []).map((e, i) => (
                      <a key={`e${i}`} href={`mailto:${e}`} className="inline-flex items-center px-2 py-0.5 rounded border border-[var(--border-default)] bg-bg-elevated text-xs text-primary hover:underline">
                        ✉ {e}
                      </a>
                    ))}
                    {(persona.companyPhones ?? []).map((p, i) => (
                      <a key={`p${i}`} href={`tel:${p.replace(/[^\d+]/g, '')}`} className="inline-flex items-center px-2 py-0.5 rounded border border-[var(--border-default)] bg-bg-elevated text-xs text-primary hover:underline">
                        ☎ {p}
                      </a>
                    ))}
                  </div>
                  {persona.companyAddress?.trim() && (
                    <p className="mt-2 text-sm text-text-primary">{persona.companyAddress}</p>
                  )}
                </div>
              )}
              {persona.likelyContactRoles.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
                    Rôle·s probable·s à contacter
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {persona.likelyContactRoles.map((r, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center px-2 py-0.5 rounded border border-[var(--border-default)] bg-bg-elevated text-xs text-text-primary"
                      >
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {persona.likelyPriorities.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
                    Priorités / douleurs probables
                  </div>
                  <ul className="space-y-2">
                    {persona.likelyPriorities.map((p, i) => (
                      <li
                        key={i}
                        className="flex gap-3 text-sm text-text-primary"
                      >
                        <span className="text-text-tertiary">·</span>
                        <span>{p}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {persona.approachAngles.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider font-medium text-primary mb-2">
                    Accroches de prospection
                  </div>
                  <ul className="space-y-2">
                    {persona.approachAngles.map((a, i) => (
                      <li
                        key={i}
                        className="flex gap-3 text-sm text-text-primary"
                      >
                        <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary mt-[7px]" />
                        <span>{a}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <Empty />
          )}
        </Card>
      </div>
    </div>
  )
}

function hasAnyTech(stack: ProspectStackByCategory): boolean {
  return (
    stack.cms.length > 0 ||
    stack.analytics.length > 0 ||
    stack.advertising.length > 0 ||
    stack.chatCrm.length > 0 ||
    stack.hostingCdn.length > 0 ||
    stack.other.length > 0
  )
}

function TechGroup({ label, items }: { label: string; items: DetectedTech[] }) {
  if (items.length === 0) return null
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
        {label}
      </div>
      <div className="flex flex-wrap gap-2">
        {items.map((t, i) => (
          <span
            key={i}
            title={t.evidence || undefined}
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border border-[var(--border-default)] bg-bg-elevated text-xs text-text-primary"
          >
            <ConfidenceDot c={t.confidence} />
            {t.name}
          </span>
        ))}
      </div>
    </div>
  )
}

function ConfidenceDot({ c }: { c: TechConfidence }) {
  const color = {
    high: 'var(--status-ok-text)',
    medium: 'var(--status-warning-text)',
    low: 'var(--text-tertiary)',
  }[c]
  return (
    <span
      className="inline-block w-1.5 h-1.5 rounded-full"
      style={{ backgroundColor: color }}
      aria-label={`confiance ${c}`}
    />
  )
}

function Empty() {
  return (
    <p className="text-sm text-text-tertiary">
      Aucune donnée disponible pour cette section.
    </p>
  )
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] rounded-md p-4">
      <div className="text-[11px] uppercase tracking-wider font-medium text-[var(--status-critical-text)] mb-1">
        Échec
      </div>
      <p className="text-sm text-text-primary">{message}</p>
    </div>
  )
}

function Card({
  label,
  tone,
  children,
}: {
  label: string
  tone?: 'primary'
  children: React.ReactNode
}) {
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md">
      <div
        className={`px-5 pt-4 pb-2 text-[11px] uppercase tracking-wider font-medium ${
          tone === 'primary' ? 'text-primary' : 'text-text-tertiary'
        }`}
      >
        {label}
      </div>
      <div className="px-5 pb-4">{children}</div>
    </div>
  )
}

function KeyValue({ label, value }: { label: string; value?: string }) {
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-4">
      <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
        {label}
      </div>
      <div className="text-sm font-medium text-text-primary">
        {value?.trim() ? value : <span className="text-text-tertiary">—</span>}
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-1">
        {label}
      </div>
      <div className="text-sm text-text-primary leading-relaxed">
        {value?.trim() ? value : <span className="text-text-tertiary">—</span>}
      </div>
    </div>
  )
}
