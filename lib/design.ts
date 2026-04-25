import type { Severity, Impact, Effort } from './types'

export type StatusKind = Severity | 'improve'

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critique',
  warning: 'Attention',
  ok: 'OK',
  info: 'Info',
  missing: 'Manquant',
}

export const IMPACT_LABEL: Record<Impact, string> = {
  high: 'Impact fort',
  medium: 'Impact moyen',
  low: 'Impact faible',
}

export const EFFORT_LABEL: Record<Effort, string> = {
  quick: 'Quick win',
  medium: 'Effort moyen',
  heavy: 'Chantier',
}

export const PAGE_STATUS_LABEL: Record<'critical' | 'warning' | 'improve' | 'ok', string> = {
  critical: 'Critique',
  warning: 'Attention',
  improve: 'À améliorer',
  ok: 'OK',
}

export function scoreTone(score: number): 'critical' | 'warning' | 'info' | 'ok' {
  if (score < 40) return 'critical'
  if (score < 60) return 'warning'
  if (score < 80) return 'info'
  return 'ok'
}

export function scoreHexColor(score: number): string {
  const t = scoreTone(score)
  return {
    critical: '#EF4444',
    warning: '#F59E0B',
    info: '#3B82F6',
    ok: '#10B981',
  }[t]
}
