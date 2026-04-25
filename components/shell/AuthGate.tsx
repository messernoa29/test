'use client'

import { useEffect, useState } from 'react'
import {
  fetchAuthStatus,
  getStoredPassword,
  setStoredPassword,
  verifyPassword,
} from '@/lib/api'

type State =
  | { kind: 'checking' }
  | { kind: 'open' }            // backend has no password set
  | { kind: 'login' }           // need creds
  | { kind: 'authenticated' }
  | { kind: 'error'; message: string }

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>({ kind: 'checking' })

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      try {
        const status = await fetchAuthStatus()
        if (cancelled) return
        if (!status.required) {
          setState({ kind: 'open' })
          return
        }
        const stored = getStoredPassword()
        if (!stored) {
          setState({ kind: 'login' })
          return
        }
        const ok = await verifyPassword(stored)
        if (cancelled) return
        if (ok) setState({ kind: 'authenticated' })
        else {
          setStoredPassword(null)
          setState({ kind: 'login' })
        }
      } catch (err) {
        if (cancelled) return
        setState({
          kind: 'error',
          message: (err as Error).message || 'Backend injoignable.',
        })
      }
    }

    function handleAuthRequired() {
      setState({ kind: 'login' })
    }

    bootstrap()
    window.addEventListener('audit-bureau:auth-required', handleAuthRequired)
    return () => {
      cancelled = true
      window.removeEventListener(
        'audit-bureau:auth-required', handleAuthRequired,
      )
    }
  }, [])

  if (state.kind === 'checking') {
    return <CenteredMessage title="Connexion au serveur…" subtitle="Le backend Render peut mettre 30–60 s à se réveiller." />
  }
  if (state.kind === 'error') {
    return (
      <CenteredMessage
        title="Backend injoignable"
        subtitle={state.message}
      />
    )
  }
  if (state.kind === 'login') {
    return <LoginScreen onSuccess={() => setState({ kind: 'authenticated' })} />
  }
  return <>{children}</>
}

function LoginScreen({ onSuccess }: { onSuccess: () => void }) {
  const [pw, setPw] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!pw || submitting) return
    setError(null)
    setSubmitting(true)
    const ok = await verifyPassword(pw)
    setSubmitting(false)
    if (!ok) {
      setError('Mot de passe incorrect.')
      return
    }
    setStoredPassword(pw)
    onSuccess()
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-6 bg-bg-page">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm flex flex-col gap-4 p-6 rounded-lg border border-[var(--border-subtle)] bg-bg-surface"
      >
        <header>
          <h1 className="text-lg font-semibold text-text-primary mb-1">
            Audit Bureau
          </h1>
          <p className="text-xs text-text-secondary">
            Application privée. Saisis le mot de passe partagé pour accéder
            aux outils.
          </p>
        </header>
        <input
          type="password"
          required
          autoFocus
          autoComplete="current-password"
          disabled={submitting}
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          placeholder="Mot de passe"
          className="h-10 px-3 bg-bg-page border border-[var(--border-default)] rounded-md text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] transition text-sm disabled:opacity-60"
        />
        {error && (
          <p className="text-xs text-[var(--status-critical-text)]">{error}</p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors disabled:opacity-60"
        >
          {submitting ? 'Vérification…' : 'Entrer'}
        </button>
      </form>
    </div>
  )
}

function CenteredMessage({
  title,
  subtitle,
}: {
  title: string
  subtitle?: string
}) {
  return (
    <div className="min-h-screen flex items-center justify-center px-6 bg-bg-page">
      <div className="text-center">
        <p className="text-sm font-medium text-text-primary">{title}</p>
        {subtitle && (
          <p className="text-xs text-text-secondary mt-1">{subtitle}</p>
        )}
      </div>
    </div>
  )
}
