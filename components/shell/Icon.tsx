import type { ToolIcon } from '@/lib/tools'

interface IconProps {
  name: ToolIcon
  size?: number
  className?: string
}

const PATHS: Record<ToolIcon, string> = {
  dashboard: 'M3 3h8v8H3V3zm10 0h8v5h-8V3zm0 7h8v11h-8V10zm-10 3h8v8H3v-8z',
  audit: 'M3 4h18v4H3V4zm0 6h18v4H3v-4zm0 6h12v4H3v-4z',
  tracker: 'M3 20V8l5 5 4-4 5 5 4-4v10H3z',
  competitor: 'M12 3l9 4v5c0 5-3.5 9-9 10-5.5-1-9-5-9-10V7l9-4z',
  content: 'M5 3h11l4 4v14H5V3zm10 1v5h5m-11 4h10m-10 3h10m-10 3h7',
  monitor: 'M3 3h18v12H3V3zm4 14h10v2H7v-2zm2 2h6v2H9v-2z',
  settings:
    'M12 8a4 4 0 100 8 4 4 0 000-8zm9 4l-2 1 1 2-2 2-2-1-1 2h-4l-1-2-2 1-2-2 1-2-2-1V11l2-1-1-2 2-2 2 1 1-2h4l1 2 2-1 2 2-1 2 2 1v1z',
  llms: 'M4 4h16v16H4V4zm3 4h10M7 12h10M7 16h6',
  bulk: 'M4 5h16M4 10h16M4 15h10M4 20h7',
  sitemap: 'M12 3v4m0 0H6v4m6-4h6v4M6 15v4h4m2-4v4m0 0h4v0m-4 0v0',
}

export function Icon({ name, size = 16, className = '' }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
