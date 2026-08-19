import { motion } from 'motion/react'
import { GaugeIcon, WarningIcon } from '@phosphor-icons/react'
import { api, useApi, type ProviderUsage } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'

const rise = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 100, damping: 20 } },
}

const LABELS: Record<string, string> = {
  groq: 'Groq',
  gemini: 'Google Gemini',
  whatsapp: 'WhatsApp Cloud API',
}

/**
 * Share of a ceiling that is consumed, 0–1, or null when there is no ceiling.
 * Computed from remaining rather than from our own count: `remaining` is what
 * the vendor is actually enforcing, and our count cannot see calls made by
 * anything else on the same key.
 */
function consumed(limit?: number | null, remaining?: number | null): number | null {
  if (!limit || remaining == null) return null
  return Math.min(1, Math.max(0, (limit - remaining) / limit))
}

/**
 * The panel used to state the numbers and leave the conclusion to the reader.
 * A ceiling reached is exactly the case nobody notices from the outside — the
 * extraction chain falls through to the next vendor and the day looks normal —
 * so it is said in words here, not left to a bar that happens to be full.
 *
 * Exhaustion is read from `remaining`, the figure the vendor is enforcing, and
 * only when a ceiling exists: no ceiling means no verdict, never "fine".
 */
function verdict(p: ProviderUsage): 'exhausted' | 'near' | null {
  // The server's verdict first, when it has one. It sees what this function
  // cannot: whether a ceiling was confirmed by the vendor or merely documented,
  // and WhatsApp, where Meta gives the tier but not our consumption — so there
  // is nothing here to divide. The arithmetic below stays as the fallback for a
  // payload that predates the field, because a page that goes silent on an
  // older API is worse than one doing its own sums.
  if (p.state === 'epuise') return 'exhausted'
  if (p.state === 'bas') return 'near'
  if (p.state === 'ok') return null

  const pairs: [number | null | undefined, number | null | undefined][] = [
    [p.limit_requests, p.remaining_requests],
    [p.limit_tokens, p.remaining_tokens],
  ]
  let worst: 'exhausted' | 'near' | null = null
  for (const [limit, remaining] of pairs) {
    if (!limit || remaining == null) continue
    if (remaining <= 0) return 'exhausted'
    if ((limit - remaining) / limit >= 0.9) worst = 'near'
  }
  return worst
}

function Meter({ value }: { readonly value: number }) {
  // Colour by headroom, not by activity: a busy day is not a problem, a nearly
  // empty quota is. Amber at 75%, red at 90% — the point where the fallback
  // chain is about to start carrying traffic it was not meant to carry.
  const tone = value >= 0.9 ? 'bg-status-fail' : value >= 0.75 ? 'bg-status-warn' : 'bg-accent'
  return (
    <span className="bg-line block h-1 w-full overflow-hidden rounded-full">
      <span
        className={`block h-full rounded-full transition-[width] duration-500 ${tone}`}
        style={{ width: `${Math.round(value * 100)}%` }}
      />
    </span>
  )
}

function Row({
  label,
  value,
  hint,
}: {
  readonly label: string
  readonly value: string
  readonly hint?: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="text-ink-muted text-xs">{label}</span>
      <span className="flex items-baseline gap-2">
        {hint && <span className="text-ink-faint text-[0.6875rem]">{hint}</span>}
        <span className="tabular text-ink text-xs">{value}</span>
      </span>
    </div>
  )
}

function ProviderCard({ p }: { readonly p: ProviderUsage }) {
  const { t } = useI18n()
  const fmt = new Intl.NumberFormat()
  const req = consumed(p.limit_requests, p.remaining_requests)
  const tok = consumed(p.limit_tokens, p.remaining_tokens)
  const state = verdict(p)

  return (
    <motion.section
      variants={rise}
      className="border-line flex min-w-0 flex-col gap-3 rounded-lg border p-4"
    >
      <header className="flex items-baseline justify-between gap-3">
        <h3 className="text-ink text-sm font-medium">{LABELS[p.provider] ?? p.provider}</h3>
        {/* The one thing that must never be ambiguous: whether the ceiling was
            measured or looked up. Gemini publishes no quota header, so its
            limit is a documented constant and says so. */}
        <span
          className={`rounded-full px-2 py-0.5 text-[0.625rem] tracking-wide uppercase ${
            p.limit_source === 'live' ? 'bg-status-ok/10 text-status-ok' : 'bg-line text-ink-faint'
          }`}
        >
          {p.limit_source === 'live' ? t('usage.live') : t('usage.documented')}
        </span>
      </header>

      {/* Said before any figure: the sentence is the finding, the numbers under
          it are the evidence. Nothing is printed while the tier is healthy —
          "tout va bien" every day is how a warning stops being read. */}
      {state && (
        <p
          className={`flex items-start gap-2 text-xs ${
            state === 'exhausted' ? 'text-status-fail' : 'text-status-warn'
          }`}
        >
          <WarningIcon size={14} weight="fill" className="mt-0.5 shrink-0" />
          <span>{state === 'exhausted' ? t('usage.exhausted') : t('usage.nearLimit')}</span>
        </p>
      )}

      {p.error ? (
        <p className="text-status-warn flex items-start gap-2 text-xs">
          <WarningIcon size={14} className="mt-0.5 shrink-0" />
          <span className="break-all">{p.error}</span>
        </p>
      ) : null}

      {p.provider === 'whatsapp' ? (
        <div className="flex flex-col gap-1">
          <Row label={t('usage.tier')} value={p.tier ?? '—'} />
          <Row label={t('usage.quality')} value={p.quality ?? '—'} />
          <Row label={t('usage.throughput')} value={p.throughput ?? '—'} />
          {/* Meta gives the ceiling but not our consumption against it without
              a WABA id this token does not carry, so this count is ours. */}
          <Row
            label={t('usage.sent24h')}
            value={fmt.format(p.sent_24h ?? 0)}
            hint={t('usage.ourCount')}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Row
              label={t('usage.requests')}
              value={
                p.limit_requests
                  ? `${fmt.format(p.remaining_requests ?? 0)} / ${fmt.format(p.limit_requests)}`
                  : '—'
              }
              hint={t('usage.remaining')}
            />
            {req != null && <Meter value={req} />}
          </div>
          {p.limit_tokens ? (
            <div className="flex flex-col gap-1">
              <Row
                label={t('usage.tokens')}
                value={`${fmt.format(p.remaining_tokens ?? 0)} / ${fmt.format(p.limit_tokens)}`}
                hint={t('usage.remaining')}
              />
              {tok != null && <Meter value={tok} />}
            </div>
          ) : null}
          <div className="border-line border-t pt-2">
            <Row label={t('usage.calls24h')} value={fmt.format(p.calls_24h ?? 0)} />
            <Row label={t('usage.tokens24h')} value={fmt.format(p.tokens_24h ?? 0)} />
          </div>
          {p.by_model && p.by_model.length > 0 && (
            <ul className="flex flex-col gap-0.5">
              {p.by_model.map((m) => (
                <li
                  key={m.model ?? 'unknown'}
                  className="text-ink-faint flex items-baseline justify-between gap-2 text-[0.6875rem]"
                >
                  <span className="truncate">{m.model ?? '—'}</span>
                  <span className="tabular shrink-0">{fmt.format(m.calls)}</span>
                </li>
              ))}
            </ul>
          )}
          {p.reset_requests && (
            <p className="text-ink-faint text-[0.6875rem]">
              {t('usage.resets', { when: p.reset_requests })}
            </p>
          )}
        </div>
      )}
    </motion.section>
  )
}

/**
 * Every free tier this project depends on, and how much of it is left.
 *
 * It exists because a quota running out is invisible from the outside: the
 * extraction chain falls through to the next vendor and the day looks normal.
 * Instrumentation, so it sits in the system strip beside Logs and Queue rather
 * than in the working pages.
 */
export function UsagePage() {
  const { t } = useI18n()
  // 60s: the underlying data changes only when a message is processed, and the
  // Graph call costs a round trip to Meta.
  const usage = useApi('usage', api.usage, 60_000)

  if (usage.loading && !usage.data) return <Skeleton className="h-40" />
  if (usage.error) return <ErrorState message={usage.error} onRetry={usage.reload} />

  const providers = usage.data?.providers ?? []
  if (providers.length === 0) return <EmptyState icon={GaugeIcon} body={t('usage.none')} />

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.06 } } }}
      className="flex flex-col gap-4 pb-12"
    >
      <p className="text-ink-muted max-w-[70ch] text-xs leading-relaxed">{t('usage.intro')}</p>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {providers.map((p) => (
          <ProviderCard key={p.provider} p={p} />
        ))}
      </div>
    </motion.div>
  )
}
