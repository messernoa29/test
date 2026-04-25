'use client'

import { useEffect, useState } from 'react'
import { scoreHexColor } from '@/lib/design'

interface ScoreHeroProps {
  score: number
  verdict: string
  animate?: boolean
}

export function ScoreHero({ score, verdict, animate = true }: ScoreHeroProps) {
  const [display, setDisplay] = useState(animate ? 0 : score)

  useEffect(() => {
    if (!animate) return
    const duration = 900
    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setDisplay(Math.round(score * eased))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [score, animate])

  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span
          className="text-5xl font-semibold tracking-tight leading-none tabular-nums"
          style={{ color: scoreHexColor(score) }}
        >
          {display}
        </span>
        <span className="text-lg font-normal text-text-tertiary">/100</span>
      </div>
      <p className="mt-2 text-sm text-text-secondary">{verdict}</p>
    </div>
  )
}
