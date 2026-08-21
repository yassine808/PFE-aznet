import { WhatsappLogoIcon, TelegramLogoIcon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import type { BotLinks } from '@/lib/api'

/**
 * Open the conversation *with the bot* — the same thread the technicians write
 * into — from whichever device is reading the dashboard.
 *
 * Deliberately not a per-colleague contact list. A technician is stored under a
 * phone number or a numeric Telegram user id, and only the first of those is
 * addressable by URL; the bot has one public address per channel, which is the
 * one thing both channels agree on. `wa.me/<digits>` and `t.me/<username>` open
 * the native app on a phone and the desktop or web client on a PC.
 *
 * The brand colours are the exception DESIGN.md's Ten Percent Rule allows: they
 * are not decoration here, they are how the reader identifies the channel
 * without reading the label.
 */
const BRAND = {
  whatsapp: '#25D366',
  telegram: '#229ED9',
} as const

function BotLink({
  channel,
  href,
  handle,
}: {
  readonly channel: keyof typeof BRAND
  readonly href: string
  readonly handle: string
}) {
  const { t } = useI18n()
  const Icon = channel === 'whatsapp' ? WhatsappLogoIcon : TelegramLogoIcon
  const label = t(channel === 'whatsapp' ? 'contact.openWhatsapp' : 'contact.openTelegram')

  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      title={`${label} · ${handle}`}
      aria-label={label}
      className="border-line hover:border-ink-faint focus-visible:border-ink-faint flex min-w-0 flex-1 items-center gap-2.5 rounded-lg border px-3 py-2.5 transition-colors"
    >
      <Icon size={20} weight="fill" color={BRAND[channel]} aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="text-ink block truncate text-xs font-medium">{label}</span>
        <span className="text-ink-faint tabular block truncate text-[0.6875rem]">{handle}</span>
      </span>
    </a>
  )
}

export function ContactPanel({ bots }: { readonly bots: BotLinks }) {
  const { t } = useI18n()
  const any = bots.whatsapp || bots.telegram
  if (!any) return <p className="text-ink-faint text-xs">{t('contact.none')}</p>

  return (
    <div className="flex flex-wrap gap-3">
      {bots.whatsapp && (
        <BotLink channel="whatsapp" href={bots.whatsapp.url} handle={bots.whatsapp.number} />
      )}
      {bots.telegram && (
        <BotLink channel="telegram" href={bots.telegram.url} handle={bots.telegram.username} />
      )}
    </div>
  )
}
