'use client'

import { useRouter } from 'next/navigation'
import { useState, useTransition } from 'react'
import { deleteAudit, runAudit, setArchived } from '@/lib/api'

interface Props {
  auditId: string
  archived: boolean
  /**
   * URL used to re-run an audit on the same site. If omitted, the rerun button is hidden.
   */
  rerunUrl?: string
  /**
   * Where to redirect after a destructive action (delete, or archive via redirect).
   * Defaults to the audit list.
   */
  redirectTo?: string
  variant?: 'inline' | 'compact'
}

export function AuditActions({
  auditId,
  archived,
  rerunUrl,
  redirectTo = '/audit',
  variant = 'inline',
}: Props) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [rerunning, setRerunning] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function toggleArchive() {
    setError(null)
    startTransition(async () => {
      try {
        await setArchived(auditId, !archived)
        router.refresh()
      } catch (e) {
        setError((e as Error).message || "Impossible de mettre à jour l'audit")
      }
    })
  }

  function doDelete() {
    setError(null)
    startTransition(async () => {
      try {
        await deleteAudit(auditId)
        router.push(redirectTo)
        router.refresh()
      } catch (e) {
        setError((e as Error).message || "Impossible de supprimer l'audit")
        setConfirmDelete(false)
      }
    })
  }

  async function doRerun() {
    if (!rerunUrl) return
    setError(null)
    setRerunning(true)
    try {
      const job = await runAudit(rerunUrl)
      router.push(`/audit/${job.id}`)
      router.refresh()
    } catch (e) {
      setError(
        (e as Error).message || "La nouvelle analyse n'a pas pu aboutir",
      )
    } finally {
      setRerunning(false)
    }
  }

  const anyPending = pending || rerunning

  if (variant === 'compact') {
    return (
      <div className="flex items-center gap-1">
        {rerunUrl && (
          <IconButton
            title="Relancer l'analyse"
            onClick={doRerun}
            disabled={anyPending}
          >
            <RefreshIcon spin={rerunning} />
          </IconButton>
        )}
        <IconButton
          title={archived ? 'Désarchiver' : 'Archiver'}
          onClick={toggleArchive}
          disabled={anyPending}
        >
          {archived ? <UnarchiveIcon /> : <ArchiveIcon />}
        </IconButton>
        <IconButton
          title="Supprimer"
          tone="danger"
          onClick={() => setConfirmDelete(true)}
          disabled={anyPending}
        >
          <TrashIcon />
        </IconButton>
        {confirmDelete && (
          <ConfirmDialog
            title="Supprimer cet audit ?"
            description="Cette action est définitive. Le rapport et son PDF ne seront plus accessibles."
            confirmLabel="Supprimer"
            pending={pending}
            onCancel={() => setConfirmDelete(false)}
            onConfirm={doDelete}
          />
        )}
        {error && (
          <span className="text-xs text-[var(--status-critical-text)]">{error}</span>
        )}
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {rerunUrl && (
        <button
          onClick={doRerun}
          disabled={anyPending}
          className="inline-flex h-9 px-3 items-center gap-2 bg-bg-surface text-text-primary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated transition-colors disabled:opacity-50"
        >
          <RefreshIcon spin={rerunning} />
          {rerunning ? 'Analyse en cours…' : "Relancer l'analyse"}
        </button>
      )}
      <button
        onClick={toggleArchive}
        disabled={anyPending}
        className="inline-flex h-9 px-3 items-center gap-2 bg-bg-surface text-text-secondary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated hover:text-text-primary transition-colors disabled:opacity-50"
      >
        {archived ? <UnarchiveIcon /> : <ArchiveIcon />}
        {archived ? 'Désarchiver' : 'Archiver'}
      </button>
      <button
        onClick={() => setConfirmDelete(true)}
        disabled={anyPending}
        className="inline-flex h-9 px-3 items-center gap-2 bg-bg-surface text-[var(--status-critical-text)] border border-[var(--status-critical-border)] rounded-md font-medium text-sm hover:bg-[var(--status-critical-bg)] transition-colors disabled:opacity-50"
      >
        <TrashIcon />
        Supprimer
      </button>
      {confirmDelete && (
        <ConfirmDialog
          title="Supprimer cet audit ?"
          description="Cette action est définitive. Le rapport et son PDF ne seront plus accessibles."
          confirmLabel="Supprimer"
          pending={pending}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={doDelete}
        />
      )}
      {error && (
        <span className="text-xs text-[var(--status-critical-text)] w-full">{error}</span>
      )}
    </div>
  )
}

function IconButton({
  title,
  onClick,
  disabled,
  tone,
  children,
}: {
  title: string
  onClick: () => void
  disabled?: boolean
  tone?: 'danger'
  children: React.ReactNode
}) {
  const base =
    'w-8 h-8 flex items-center justify-center rounded-md border transition-colors disabled:opacity-50'
  const toneCls =
    tone === 'danger'
      ? 'border-[var(--border-subtle)] text-text-tertiary hover:text-[var(--status-critical-text)] hover:border-[var(--status-critical-border)] hover:bg-[var(--status-critical-bg)]'
      : 'border-[var(--border-subtle)] text-text-tertiary hover:text-text-primary hover:bg-bg-elevated'
  return (
    <button
      title={title}
      aria-label={title}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        onClick()
      }}
      disabled={disabled}
      className={`${base} ${toneCls}`}
    >
      {children}
    </button>
  )
}

function ConfirmDialog({
  title,
  description,
  confirmLabel,
  pending,
  onCancel,
  onConfirm,
}: {
  title: string
  description: string
  confirmLabel: string
  pending: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onCancel}
    >
      <div
        className="bg-bg-surface border border-[var(--border-default)] rounded-md p-5 max-w-sm w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-semibold text-text-primary mb-1">{title}</h3>
        <p className="text-sm text-text-secondary mb-5">{description}</p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={pending}
            className="h-9 px-3 bg-bg-surface text-text-secondary border border-[var(--border-default)] rounded-md text-sm hover:bg-bg-elevated disabled:opacity-50"
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            disabled={pending}
            className="h-9 px-3 bg-[var(--status-critical-accent)] text-white rounded-md font-medium text-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? '...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

function ArchiveIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={14}
      height={14}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="4" width="18" height="4" rx="1" />
      <path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4" />
    </svg>
  )
}

function UnarchiveIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={14}
      height={14}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="4" width="18" height="4" rx="1" />
      <path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M9 14l3-3 3 3M12 11v8" />
    </svg>
  )
}

function RefreshIcon({ spin }: { spin?: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={14}
      height={14}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={spin ? 'animate-spin' : undefined}
      style={spin ? { animationDuration: '1s' } : undefined}
    >
      <path d="M21 12a9 9 0 0 1-15.5 6.3M3 12a9 9 0 0 1 15.5-6.3" />
      <path d="M21 4v5h-5M3 20v-5h5" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={14}
      height={14}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M6 6l1 14a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-14M10 11v6M14 11v6" />
    </svg>
  )
}
