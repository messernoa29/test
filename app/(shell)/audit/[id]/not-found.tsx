import Link from 'next/link'

export default function AuditNotFound() {
  return (
    <div className="max-w-2xl mx-auto px-8 py-20 text-center">
      <p className="text-xs text-text-tertiary mb-2">404</p>
      <h1 className="text-2xl font-semibold text-text-primary mb-2">Audit introuvable</h1>
      <p className="text-text-secondary mb-6">
        Cet audit n&apos;existe pas ou a expiré. Les audits sont conservés en mémoire
        tant que le serveur tourne.
      </p>
      <Link
        href="/audit"
        className="inline-flex h-10 px-4 items-center bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors"
      >
        Lancer un nouvel audit
      </Link>
    </div>
  )
}
