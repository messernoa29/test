'use client'

import { useEffect, useState } from 'react'
import { scoreHexColor } from '@/lib/design'

interface ScoreBarProps {
  score: number
  animate?: boolean
  height?: number
}

export function ScoreBar({ score, animate = true, height = 6 }: ScoreBarProps) {
  const clamped = Math.max(0, Math.min(100, score))
  const [width, setWidth] = useState(animate ? 0 : clamped)

  useEffect(() => {
    if (!animate) return
    const raf = requestAnimationFrame(() => setWidth(clamped))
    return () => cancelAnimationFrame(raf)
  }, [clamped, animate])

  return (
    <div
      className="w-full overflow-hidden rounded-[1px]"
      style={{ height, background: 'var(--bg-elevated)' }}
    >
      <div
        className="h-full rounded-[1px]"
        style={{
          width: `${width}%`,
          background: scoreHexColor(clamped),
          transition: 'width 1.2s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      />
    </div>
  )
}
