'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  brandingLogoUrl,
  deleteBrandingLogo,
  getBranding,
  updateBranding,
  uploadBrandingLogo,
} from '@/lib/api'
import type { AgencyBranding } from '@/lib/types'

const DEFAULT_ACCENT = '#2563EB'
const ACCENT_SUGGESTIONS = [
  '#2563EB', '#D4A853', '#10B981', '#DC2626',
  '#7C3AED', '#F97316', '#0EA5E9', '#18181B',
]

export function BrandingSettings() {
  const [branding, setBranding] = useState<AgencyBranding | null>(null)
  const [form, setForm] = useState<AgencyBranding>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<
    { kind: 'ok' | 'error'; text: string } | null
  >(null)
  const [logoBust, setLogoBust] = useState<string>(() => Date.now().toString())
  const fileRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    let cancelled = false
    getBranding()
      .then((b) => {
        if (cancelled) return
        setBranding(b)
        setForm(b ?? {})
      })
      .catch((e) => {
        if (!cancelled) setMessage({ kind: 'error', text: (e as Error).message })
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const dirty = useMemo(() => {
    if (!branding) return Object.values(form).some((v) => v)
    return (
      (form.name ?? '') !== (branding.name ?? '') ||
      (form.tagline ?? '') !== (branding.tagline ?? '') ||
      (form.website ?? '') !== (branding.website ?? '') ||
      (form.accentColor ?? '') !== (branding.accentColor ?? '')
    )
  }, [branding, form])

  async function onSave(e: React.FormEvent) {
    e.preventDefault()
    if (saving) return
    setSaving(true)
    setMessage(null)
    try {
      const patch: AgencyBranding = {
        name: form.name?.trim() || undefined,
        tagline: form.tagline?.trim() || undefined,
        website: form.website?.trim() || undefined,
        accentColor: form.accentColor?.trim() || undefined,
      }
      const next = await updateBranding(patch)
      setBranding(next)
      setForm(next)
      setMessage({ kind: 'ok', text: 'Identité enregistrée.' })
    } catch (err) {
      setMessage({ kind: 'error', text: (err as Error).message })
    } finally {
      setSaving(false)
    }
  }

  async function onUploadLogo(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setSaving(true)
    setMessage(null)
    try {
      const next = await uploadBrandingLogo(file)
      setBranding(next)
      setForm((prev) => ({ ...prev, logoUrl: next.logoUrl }))
      setLogoBust(Date.now().toString())
      setMessage({ kind: 'ok', text: 'Logo mis à jour.' })
    } catch (err) {
      setMessage({ kind: 'error', text: (err as Error).message })
    } finally {
      setSaving(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function onRemoveLogo() {
    setSaving(true)
    setMessage(null)
    try {
      const next = await deleteBrandingLogo()
      setBranding(next)
      setForm((prev) => ({ ...prev, logoUrl: undefined }))
      setLogoBust(Date.now().toString())
      setMessage({ kind: 'ok', text: 'Logo supprimé.' })
    } catch (err) {
      setMessage({ kind: 'error', text: (err as Error).message })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-6 text-sm text-text-tertiary">
        Chargement…
      </div>
    )
  }

  const accent = form.accentColor || DEFAULT_ACCENT
  const hasLogo = Boolean(branding?.logoUrl)

  return (
    <section className="bg-bg-surface border border-[var(--border-subtle)] rounded-md">
      <header className="px-6 py-4 border-b border-[var(--border-subtle)]">
        <h2 className="text-base font-semibold text-text-primary">
          Identité de l&apos;agence
        </h2>
        <p className="text-xs text-text-tertiary mt-0.5">
          Utilisée sur la page de couverture des rapports PDF.
        </p>
      </header>

      <form onSubmit={onSave} className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 p-6">
        {/* Form */}
        <div className="space-y-4">
          <Field
            label="Nom de l'agence"
            value={form.name ?? ''}
            placeholder="Nom affiché en bas de la page de couverture"
            onChange={(v) => setForm((f) => ({ ...f, name: v }))}
          />
          <Field
            label="Tagline"
            value={form.tagline ?? ''}
            placeholder="Ex: Consulting SEO & UX"
            onChange={(v) => setForm((f) => ({ ...f, tagline: v }))}
          />
          <Field
            label="Site web"
            value={form.website ?? ''}
            placeholder="https://monagence.fr"
            type="url"
            onChange={(v) => setForm((f) => ({ ...f, website: v }))}
          />

          <div>
            <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2 block">
              Couleur d&apos;accent
            </label>
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={accent}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, accentColor: e.target.value.toUpperCase() }))
                  }
                  className="w-10 h-10 rounded-md border border-[var(--border-default)] bg-bg-surface cursor-pointer"
                  aria-label="Sélecteur de couleur d'accent"
                />
                <input
                  type="text"
                  value={form.accentColor ?? ''}
                  placeholder="#2563EB"
                  onChange={(e) =>
                    setForm((f) => ({ ...f, accentColor: e.target.value }))
                  }
                  className="h-10 px-3 w-32 bg-bg-surface border border-[var(--border-default)] rounded-md text-sm font-mono text-text-primary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)]"
                />
              </div>
              <div className="flex items-center gap-1.5">
                {ACCENT_SUGGESTIONS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, accentColor: c }))}
                    className="w-6 h-6 rounded-full border border-[var(--border-default)] transition-transform hover:scale-110"
                    style={{ background: c }}
                    aria-label={`Choisir ${c}`}
                    title={c}
                  />
                ))}
              </div>
            </div>
          </div>

          <div>
            <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2 block">
              Logo (PNG, JPEG, WebP, SVG — max 2 MB)
            </label>
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={saving}
                className="inline-flex h-9 px-3 items-center gap-2 bg-bg-surface text-text-primary border border-[var(--border-default)] rounded-md text-sm font-medium hover:bg-bg-elevated disabled:opacity-60"
              >
                {hasLogo ? 'Remplacer le logo' : 'Téléverser un logo'}
              </button>
              {hasLogo && (
                <button
                  type="button"
                  onClick={onRemoveLogo}
                  disabled={saving}
                  className="inline-flex h-9 px-3 items-center gap-2 bg-bg-surface text-[var(--status-critical-text)] border border-[var(--status-critical-border)] rounded-md text-sm font-medium hover:bg-[var(--status-critical-bg)] disabled:opacity-60"
                >
                  Supprimer
                </button>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                onChange={onUploadLogo}
                className="hidden"
              />
            </div>
            <p className="text-xs text-text-tertiary mt-2">
              Le SVG est accepté pour l&apos;UI. Le PDF préfère un PNG/JPEG car ReportLab
              ne rend pas le SVG nativement.
            </p>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={!dirty || saving}
              className="inline-flex h-10 px-4 items-center bg-primary text-white rounded-md font-medium text-sm hover:bg-primary-hover disabled:opacity-60 transition-colors"
            >
              {saving ? 'Enregistrement…' : 'Enregistrer'}
            </button>
            {message && (
              <span
                className={`text-xs ${
                  message.kind === 'ok'
                    ? 'text-[var(--status-ok-accent)]'
                    : 'text-[var(--status-critical-text)]'
                }`}
              >
                {message.text}
              </span>
            )}
          </div>
        </div>

        {/* Preview */}
        <CoverPreview
          name={form.name ?? branding?.name ?? undefined}
          tagline={form.tagline ?? branding?.tagline ?? undefined}
          website={form.website ?? branding?.website ?? undefined}
          accent={accent}
          logoUrl={hasLogo ? brandingLogoUrl(logoBust) : null}
        />
      </form>
    </section>
  )
}

function Field({
  label,
  value,
  placeholder,
  type = 'text',
  onChange,
}: {
  label: string
  value: string
  placeholder?: string
  type?: string
  onChange: (v: string) => void
}) {
  return (
    <div>
      <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2 block">
        {label}
      </label>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] transition"
      />
    </div>
  )
}

function CoverPreview({
  name,
  tagline,
  website,
  accent,
  logoUrl,
}: {
  name?: string
  tagline?: string
  website?: string
  accent: string
  logoUrl?: string | null
}) {
  return (
    <div className="lg:sticky lg:top-20 h-fit">
      <div className="text-[10px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
        Aperçu de la couverture
      </div>
      <div
        className="bg-white border border-[var(--border-default)] rounded-md p-6 text-[#1A1A17] shadow-sm"
        style={{ aspectRatio: '1 / 1.4' }}
      >
        <div
          className="h-1 rounded-full mb-6"
          style={{ background: accent, width: 80 }}
        />
        {logoUrl && (
          <img
            src={logoUrl}
            alt="Logo"
            className="h-8 mb-4 object-contain"
          />
        )}
        <div className="text-[10px] uppercase tracking-[0.18em] font-semibold mb-1" style={{ color: accent }}>
          Audit Web
        </div>
        <div className="text-xs text-[#6B6860] mb-6">Rapport d&apos;analyse SEO &amp; UX</div>

        <div className="border-t border-[#E4E4E7] my-4" />

        <div className="text-xl font-semibold mb-1">domain-client.com</div>
        <div className="font-mono text-[10px] text-[#6B6860] mb-1">
          https://domain-client.com/
        </div>
        <div className="text-[10px] text-[#6B6860] mb-6">24 Avril 2026</div>

        <div className="border-t border-[#E4E4E7] my-4" />

        <div className="flex items-baseline gap-1 mb-1">
          <span
            className="text-4xl font-semibold tracking-tight tabular-nums"
            style={{ color: accent }}
          >
            68
          </span>
          <span className="text-xs font-normal text-[#9E9B94]">/100</span>
        </div>
        <div className="italic text-xs text-[#6B6860] mb-6">Bon niveau — quelques quick wins</div>

        <div className="border-t border-[#E4E4E7] my-4" />

        <div className="text-[9px] text-[#6B6860] leading-relaxed">
          {[name && `Produit par ${name}`, tagline, website]
            .filter(Boolean)
            .join(' · ') || 'Rapport généré automatiquement'}
        </div>
      </div>
    </div>
  )
}
