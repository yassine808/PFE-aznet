import { WhatsappLogoIcon, TelegramLogoIcon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import type { Identity, Technician } from '@/lib/api'

/**
 * "Open the chat with this person" — from the browser, on whichever device is
 * reading the dashboard.
 *
 * The two channels are not symmetric, and the asymmetry is the whole design.
 * WhatsApp identifies a person by their phone number, so `wa.me/<digits>` is a
 * real address that resolves in the desktop app, the mobile app and the web
 * client alike. Telegram identifies them by a numeric user id, which no
 * https://t.me/ URL can address — only the native `tg://user?id=` scheme can,
 * and only for a peer the reading account already knows.
 *
 * ponytail: so a Telegram row opens the app rather than promising a chat, and
 * the id is shown next to it — the thing a chef can paste into Telegram's own
 * search when the deep link does not resolve. Storing @usernames at reception
 * (n8n's `Sender` node has them) is the upgrade that would make both channels
 * a real link.
 */
export function chatUrl(identity: Identity): string | null {
  const id = identity.external_id.trim()
  if (!id) return null
  if (identity.channel === 'whatsapp') {
    // wa.me wants digits only: no +, no spaces, no dashes.
    const digits = id.replace(/\D/g, '')
    return digits ? `https://wa.me/${digits}` : null
  }
  return /^\d+$/.test(id) ? `tg://user?id=${id}` : null
}

function ChannelLink({ identity }: { readonly identity: Identity }) {
  const { t } = useI18n()
  const href = chatUrl(identity)
  const isWa = identity.channel === 'whatsapp'
  const Icon = isWa ? WhatsappLogoIcon : TelegramLogoIcon
  const label = t(isWa ? 'contact.openWhatsapp' : 'contact.openTelegram')

  if (!href) return null
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      title={`${label} · ${identity.external_id}`}
      aria-label={label}
      className="text-ink-faint hover:text-ink focus-visible:text-ink inline-flex items-center gap-1.5 text-xs transition-colors"
    >
      <Icon size={16} weight="regular" aria-hidden />
      <span className="tabular hidden sm:inline">{identity.external_id}</span>
    </a>
  )
}

export function ContactPanel({ people }: { readonly people: readonly Technician[] }) {
  const { t } = useI18n()
  // Someone with no reachable identity is not a contact row — an empty line
  // with a name and nothing to click reads as a broken link.
  const rows = people
    .filter((p) => p.active !== false)
    .map((p) => ({
      person: p,
      identities: (p.identities ?? []).filter((i) => i.active !== false && chatUrl(i)),
    }))
    .filter((r) => r.identities.length > 0)

  if (rows.length === 0) return <p className="text-ink-faint text-xs">{t('contact.none')}</p>

  return (
    <ul className="divide-line flex flex-col divide-y">
      {rows.map(({ person, identities }) => (
        <li key={person.id} className="flex items-center gap-4 py-2 first:pt-0 last:pb-0">
          <span className="text-ink min-w-0 flex-1 truncate text-sm">{person.name}</span>
          <span className="flex items-center gap-3">
            {identities.map((i) => (
              <ChannelLink key={`${i.channel}:${i.external_id}`} identity={i} />
            ))}
          </span>
        </li>
      ))}
    </ul>
  )
}
