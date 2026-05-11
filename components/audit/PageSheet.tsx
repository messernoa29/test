import type { PageAnalysis, PageRecommendation, PageTechnical } from '@/lib/types'
import { Badge } from '@/components/ui/Badge'
import { PAGE_STATUS_LABEL } from '@/lib/design'
import { FindingRow } from './FindingRow'

interface PageSheetProps {
  page: PageAnalysis
}

export function PageSheet({ page }: PageSheetProps) {
  return (
    <article className="bg-bg-surface border border-[var(--border-subtle)] rounded-md overflow-hidden">
      <header
        className="flex items-center justify-between gap-3 px-5 py-3 border-l-[3px] bg-bg-elevated"
        style={{
          borderLeftColor: `var(--status-${page.status === 'improve' ? 'warning' : page.status}-accent)`,
        }}
      >
        <code className="font-mono text-xs text-text-secondary truncate">{page.url}</code>
        <Badge kind={page.status}>{PAGE_STATUS_LABEL[page.status]}</Badge>
      </header>

      {page.representsCount && page.representsCount > 0 ? (
        <div className="px-5 py-2.5 bg-[var(--status-info-bg)] border-b border-[var(--status-info-border)] text-xs text-[var(--status-info-text)]">
          <strong>Page type</strong> — cette analyse vaut pour {page.representsCount + 1}{' '}
          pages au même gabarit
          {page.representsPattern ? ` (${page.representsPattern})` : ''}
          {page.representsSampleUrls && page.representsSampleUrls.length > 1 ? (
            <span className="block mt-1 font-mono text-[10px] text-text-tertiary break-all">
              ex. : {page.representsSampleUrls.slice(0, 3).join(' · ')}
              {page.representsSampleUrls.length > 3 ? ' …' : ''}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="px-5 py-4 space-y-5">
        <MetaGrid page={page} />
        {page.technical && <TechnicalBlock t={page.technical} />}
        <KeywordsBlock page={page} />

        {page.findings.length > 0 && (
          <div>
            <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
              Points détectés
            </div>
            <div className="border border-[var(--border-subtle)] rounded-md overflow-hidden">
              <div className="grid grid-cols-[40px_140px_1fr_100px_100px_24px] gap-3 px-4 py-2 bg-bg-elevated border-b border-[var(--border-subtle)]">
                {['#', 'Sévérité', 'Titre', 'Impact', 'Effort', ''].map((h, i) => (
                  <div
                    key={i}
                    className="text-[10px] uppercase tracking-wider font-medium text-text-tertiary"
                  >
                    {h}
                  </div>
                ))}
              </div>
              {page.findings.map((f, i) => (
                <FindingRow key={i} finding={f} index={i} />
              ))}
            </div>
          </div>
        )}

        {page.recommendation && <RecoBlock reco={page.recommendation} />}
      </div>
    </article>
  )
}

function MetaGrid({ page }: { page: PageAnalysis }) {
  const rows = [
    { label: 'Title', value: page.title || 'absent', extra: `${page.titleLength} car.` },
    { label: 'H1', value: page.h1 || 'absent', extra: '' },
    {
      label: 'Meta',
      value: page.metaDescription || 'absente',
      extra: `${page.metaLength} car.`,
    },
  ]
  return (
    <div className="divide-y divide-[var(--border-subtle)] border border-[var(--border-subtle)] rounded-md">
      {rows.map((r) => (
        <div
          key={r.label}
          className="grid grid-cols-[70px_1fr_auto] gap-4 px-4 py-2.5 items-start"
        >
          <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary pt-0.5">
            {r.label}
          </div>
          <div className="text-sm text-text-primary leading-snug">{r.value}</div>
          <div className="font-mono text-[11px] text-text-tertiary pt-0.5">{r.extra}</div>
        </div>
      ))}
    </div>
  )
}

function TechnicalBlock({ t }: { t: PageTechnical }) {
  const fmtBytes = (n: number) =>
    n >= 1024 ? `${(n / 1024).toFixed(1)} Ko` : `${n} o`
  const canon =
    t.canonical == null
      ? 'absent'
      : t.canonicalIsSelf
        ? 'auto-référent ✓'
        : `→ ${t.canonical}`
  const cells: { label: string; value: string; warn?: boolean }[] = [
    {
      label: 'HTTP',
      value: String(t.statusCode ?? '—'),
      warn: t.statusCode != null && t.statusCode >= 400,
    },
    { label: 'Profondeur', value: t.depth != null ? `${t.depth} clics` : '—' },
    { label: 'Poids HTML', value: fmtBytes(t.htmlBytes) },
    { label: 'Mots', value: String(t.wordCount || '—') },
    {
      label: 'Ratio texte/HTML',
      value: t.htmlBytes ? `${Math.round(t.textRatio * 100)}%` : '—',
      warn: t.htmlBytes > 0 && t.textRatio < 0.1,
    },
    { label: 'Liens int/ext', value: `${t.internalLinksOut} / ${t.externalLinksOut}` },
    {
      label: 'Images (sans alt)',
      value: `${t.imagesCount}${t.imagesWithoutAlt ? ` (${t.imagesWithoutAlt})` : ''}`,
      warn: t.imagesWithoutAlt > 0,
    },
    { label: 'Canonical', value: canon, warn: t.canonicalIsSelf === false },
    {
      label: 'robots meta',
      value: t.robotsMeta || '—',
      warn: t.robotsMeta.includes('noindex'),
    },
    { label: 'lang', value: t.htmlLang || '—' },
    {
      label: 'hreflang',
      value: t.hreflangLangs.length ? t.hreflangLangs.join(', ') : '—',
    },
    {
      label: '<meta viewport>',
      value: t.hasViewportMeta ? 'présent ✓' : 'absent',
      warn: !t.hasViewportMeta,
    },
    {
      label: 'Mixed content',
      value: t.hasMixedContent ? 'OUI ⚠' : 'non',
      warn: t.hasMixedContent,
    },
    {
      label: 'Open Graph',
      value: t.ogTitle ? 'og:title ✓' : 'absent',
      warn: !t.ogTitle,
    },
    {
      label: 'Twitter card',
      value: t.twitterCard || '—',
    },
    {
      label: 'Schema.org',
      value: t.schemaTypes.length ? t.schemaTypes.join(', ') : '—',
    },
  ]
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
        Données techniques (crawl)
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5 border border-[var(--border-subtle)] rounded-md p-3">
        {cells.map((c) => (
          <div key={c.label} className="flex justify-between gap-2 text-xs">
            <span className="text-text-tertiary">{c.label}</span>
            <span
              className={`text-right ${c.warn ? 'text-[var(--status-critical-text)]' : 'text-text-primary'}`}
            >
              {c.value}
            </span>
          </div>
        ))}
      </div>
      {t.redirectChain.length > 0 && (
        <p className="mt-2 text-[11px] text-[var(--status-warning-text)]">
          Atteinte via {t.redirectChain.length} redirection(s) :{' '}
          {t.redirectChain.join(' → ')}
        </p>
      )}
      {t.issues.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[11px] text-text-secondary">
          {t.issues.map((i, idx) => (
            <li key={idx}>· {i}</li>
          ))}
        </ul>
      )}
      {t.suggestedSchema && (
        <div className="mt-3">
          <div className="text-[11px] uppercase tracking-wider font-medium text-primary mb-1">
            Schema.org suggéré ({t.suggestedSchemaType}
            {t.pageType ? ` · type de page : ${t.pageType}` : ''})
          </div>
          <p className="text-[11px] text-text-tertiary mb-1.5">
            Aucun schema {t.suggestedSchemaType} détecté. JSON-LD prêt à coller
            dans le &lt;head&gt; (remplacez les
            <code className="mx-1">[À COMPLÉTER : …]</code>) :
          </p>
          <pre className="text-[10px] leading-snug bg-bg-elevated border border-[var(--border-subtle)] rounded p-2 overflow-x-auto text-text-secondary">
            {`<script type="application/ld+json">\n${t.suggestedSchema}\n</script>`}
          </pre>
        </div>
      )}
    </div>
  )
}

function KeywordsBlock({ page }: { page: PageAnalysis }) {
  const rows = [
    {
      label: 'KW cibles',
      values: page.targetKeywords ?? [],
      color: 'var(--primary)',
    },
    {
      label: 'Présents',
      values: page.presentKeywords ?? [],
      color: 'var(--status-ok-accent)',
    },
    {
      label: 'Absents',
      values: page.missingKeywords ?? [],
      color: 'var(--status-critical-accent)',
    },
  ]
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[110px_1fr] gap-4 items-start">
          <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary pt-0.5">
            {r.label}
          </div>
          <div className="text-sm leading-snug" style={{ color: r.color }}>
            {r.values.length > 0 ? r.values.join(', ') : '—'}
          </div>
        </div>
      ))}
    </div>
  )
}

function RecoBlock({ reco }: { reco: PageRecommendation }) {
  const rows: { label: string; current?: string; proposed?: string; mono?: boolean }[] = []
  if (reco.urlCurrent || reco.url)
    rows.push({ label: 'URL', current: reco.urlCurrent, proposed: reco.url, mono: true })
  if (reco.titleCurrent || reco.title)
    rows.push({ label: 'Title', current: reco.titleCurrent, proposed: reco.title })
  if (reco.h1Current || reco.h1)
    rows.push({ label: 'H1', current: reco.h1Current, proposed: reco.h1 })
  if (reco.metaCurrent || reco.meta)
    rows.push({ label: 'Meta', current: reco.metaCurrent, proposed: reco.meta })

  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider font-medium text-primary mb-2">
        Recommandation détaillée
      </div>
      <div className="border border-[var(--border-subtle)] rounded-md overflow-hidden">
        <div className="grid grid-cols-[70px_1fr_1fr] bg-bg-elevated border-b border-[var(--border-subtle)]">
          <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-3 py-2">
            Champ
          </div>
          <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-3 py-2 border-l border-[var(--border-subtle)]">
            Actuel
          </div>
          <div className="text-[11px] uppercase tracking-wider font-medium text-primary px-3 py-2 border-l border-[var(--border-subtle)]">
            Recommandé
          </div>
        </div>
        {rows.map((r) => (
          <div
            key={r.label}
            className="grid grid-cols-[70px_1fr_1fr] border-b border-[var(--border-subtle)] last:border-0"
          >
            <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-3 py-2.5">
              {r.label}
            </div>
            <div
              className={`px-3 py-2.5 text-sm text-text-secondary border-l border-[var(--border-subtle)] ${r.mono ? 'font-mono text-xs' : ''}`}
            >
              {r.current || '—'}
            </div>
            <div
              className={`px-3 py-2.5 text-sm text-primary font-medium border-l border-[var(--border-subtle)] ${r.mono ? 'font-mono text-xs' : ''}`}
            >
              {r.proposed || '—'}
            </div>
          </div>
        ))}
      </div>

      {reco.actions && reco.actions.length > 0 && (
        <div className="mt-4">
          <div className="text-[11px] uppercase tracking-wider font-medium text-primary mb-2">
            Actions techniques
          </div>
          <ul className="space-y-1.5">
            {reco.actions.map((a, i) => (
              <li
                key={i}
                className="flex gap-2 text-sm text-text-primary leading-snug"
              >
                <span className="text-xs tabular-nums text-text-tertiary mt-[3px] flex-shrink-0 w-5">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {reco.estimatedMonthlyTraffic && (
        <p className="mt-3 text-xs text-text-tertiary">
          Trafic mensuel estimé :{' '}
          <span className="text-primary font-medium">
            ~{reco.estimatedMonthlyTraffic} visites/mois
          </span>
        </p>
      )}
    </div>
  )
}
