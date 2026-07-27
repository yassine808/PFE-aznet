import { DatabaseIcon, PlugsConnectedIcon, TableIcon, WaveformIcon } from '@phosphor-icons/react'

/**
 * Service and channel marks, monochrome by design.
 *
 * Brand colours (WhatsApp green, Telegram blue, n8n red) would enter the status
 * palette and compete with it: a green WhatsApp glyph beside a green
 * "operational" dot reads as a second status signal. Everything here inherits
 * `currentColor`, so shape identifies the service and colour stays free to mean
 * state.
 *
 * Brand marks are hand-inlined SVG; generic infrastructure uses Phosphor, which
 * is legible at 13px in a way a literal Postgres elephant is not.
 */

function BrandSvg({ size, className, d }: { size: number; className: string; d: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      className={`shrink-0 ${className}`}
    >
      <path d={d} />
    </svg>
  )
}

const WHATSAPP =
  'M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38a9.9 9.9 0 0 0 4.79 1.22h.01c5.46 0 9.9-4.45 9.9-9.91C21.95 6.45 17.5 2 12.04 2Zm0 18.15h-.01a8.2 8.2 0 0 1-4.19-1.15l-.3-.18-3.12.82.83-3.04-.2-.31a8.2 8.2 0 0 1-1.26-4.38c0-4.54 3.7-8.24 8.25-8.24 2.2 0 4.27.86 5.83 2.42a8.2 8.2 0 0 1 2.41 5.83c0 4.54-3.7 8.23-8.24 8.23Zm4.52-6.16c-.25-.13-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.13-.16.24-.64.8-.79.97-.14.16-.29.18-.54.06-.25-.13-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.01-.38.11-.5.11-.11.25-.29.37-.43.13-.15.17-.25.25-.41.08-.17.04-.31-.02-.43-.06-.13-.56-1.35-.77-1.84-.2-.48-.4-.42-.56-.43h-.47c-.16 0-.43.06-.65.31-.22.24-.86.84-.86 2.05 0 1.21.88 2.38 1 2.54.13.17 1.73 2.64 4.19 3.7.59.26 1.04.41 1.4.52.59.19 1.12.16 1.54.1.47-.07 1.47-.6 1.67-1.18.21-.58.21-1.07.15-1.18-.06-.1-.23-.16-.48-.29Z'

const TELEGRAM =
  'M21.94 4.63a1.2 1.2 0 0 0-1.24-.2L2.9 11.6c-.5.2-.83.68-.82 1.22.01.53.36 1 .87 1.17l4.13 1.4 1.6 5.02c.06.2.18.37.34.5.02.02.05.03.07.05.16.11.35.17.55.17h.03c.28 0 .54-.12.73-.32l2.46-2.62 4.2 3.27c.21.17.47.25.73.25.14 0 .27-.02.4-.07.38-.14.66-.46.75-.85l3.4-15.06c.09-.42-.05-.85-.4-1.1ZM9.3 14.35l-.02.02-.63 3.32-1.02-3.2 8.9-4.87-7.23 4.73Zm1.29 4.02.35-1.86.86.67-1.21 1.19Zm7.55 1.1-6.2-4.83 7.2-7.02-1 11.85Z'

/** n8n's node-graph mark: two endpoints feeding a hub, then one output. */
function N8nMark({ size, className }: { size: number; className: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      aria-hidden="true"
      className={`shrink-0 ${className}`}
    >
      <path d="M5.4 7.5h3.1M5.4 16.5h3.1M11.6 12h3.1" />
      <path d="M8.5 7.5c1.7 0 1.7 4.5 3.1 4.5M8.5 16.5c1.7 0 1.7-4.5 3.1-4.5" />
      <circle cx="3.6" cy="7.5" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="3.6" cy="16.5" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="10.2" cy="12" r="2.2" fill="currentColor" stroke="none" />
      <circle cx="16.6" cy="12" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="20.9" cy="12" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function ChannelIcon({
  channel,
  size = 14,
  className = '',
}: {
  channel: string
  size?: number
  className?: string
}) {
  switch (channel) {
    case 'whatsapp':
      return <BrandSvg size={size} className={className} d={WHATSAPP} />
    case 'telegram':
      return <BrandSvg size={size} className={className} d={TELEGRAM} />
    default:
      return null
  }
}

/** Resolves any service key used by the Services panel to a mark. */
export function ServiceIcon({
  service,
  size = 14,
  className = '',
}: {
  service: string
  size?: number
  className?: string
}) {
  const common = { size, className: `shrink-0 ${className}` }
  switch (service) {
    case 'whatsapp':
    case 'telegram':
      return <ChannelIcon channel={service} size={size} className={className} />
    case 'n8n':
      return <N8nMark size={size} className={className} />
    case 'postgres':
    case 'logstore':
      return <DatabaseIcon {...common} />
    case 'sheets':
      return <TableIcon {...common} />
    case 'ai':
      return <WaveformIcon {...common} />
    case 'api':
      return <PlugsConnectedIcon {...common} />
    default:
      return null
  }
}
