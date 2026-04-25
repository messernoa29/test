interface Props {
  wins: string[]
}

export function QuickWinsList({ wins }: Props) {
  if (wins.length === 0) return null
  return (
    <div>
      <h3 className="font-sans font-medium text-text-primary mb-3">
        Quick wins prioritaires
      </h3>
      <ol className="space-y-2.5">
        {wins.map((w, i) => (
          <li key={i} className="flex gap-3 items-start">
            <span className="font-mono text-xs font-medium text-accent mt-[3px] flex-shrink-0">
              {String(i + 1).padStart(2, '0')}
            </span>
            <span className="text-sm text-text-primary leading-relaxed">{w}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
