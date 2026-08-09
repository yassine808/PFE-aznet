import { useCallback, useEffect, useState } from 'react'
import { ArrowDownIcon, ArrowUpIcon, CircleIcon } from '@phosphor-icons/react'
import { api, putSettings, type SttStatus } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

/**
 * Ordre des moteurs STT — directeur uniquement.
 *
 * Reordering is buttons, not drag-and-drop: there are three items, and native
 * HTML5 drag fires on neither touch nor keyboard (see equipe.tsx, where the
 * <select> is the real path for both). Up/down arrows work everywhere and need
 * no fallback.
 *
 * The API enforces the director rule; this gate is presentation. A chef sees
 * the order and the usage — knowing which engine transcribed is operational
 * information — but gets no controls.
 */
export function SttOrder() {
  const { t } = useI18n()
  const { user } = useAuth()
  const isDirector = user?.role === 'directeur'
  const [status, setStatus] = useState<SttStatus | null>(null)
  const [chain, setChain] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const s = (await api.sttStatus()) as SttStatus
      setStatus(s)
      setChain(s.chain)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /** Persist an order, optimistically. Shared by reorder and reset so both
   *  behave identically on failure: snap back to the server's truth. */
  const persist = async (next: string[]) => {
    setChain(next)
    setSaving(true)
    setError(null)
    try {
      // put_settings upserts per key, so sending stt_chain alone leaves every
      // other setting untouched.
      await putSettings({ stt_chain: next.join(',') })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      await load()
    } finally {
      setSaving(false)
    }
  }

  const move = async (from: number, to: number) => {
    if (to < 0 || to >= chain.length) return
    const next = [...chain]
    const [item] = next.splice(from, 1)
    next.splice(to, 0, item)
    // Optimistic: the list reorders instantly, and a rejected save snaps back
    // to the server's truth rather than leaving the UI lying about the order.
    await persist(next)
  }

  if (error && !status) {
    return <p className="text-status-fail text-xs">{error}</p>
  }
  if (!status) {
    return <p className="text-ink-faint text-xs">{t('common.loading')}</p>
  }

  const usageOf = (engine: string) =>
    status.usage.engines.find((u) => u.engine === engine)

  return (
    <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
      <legend className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">
        {t('settings.sttOrder')}
      </legend>
      <p className="text-ink-faint text-xs">{t('settings.sttOrderHint')}</p>

      <ol className="m-0 flex list-none flex-col gap-1 p-0">
        {chain.map((engine, i) => {
          const u = usageOf(engine)
          const isLocal = engine === 'local'
          const localDown = isLocal && status.local.status !== 'ok'
          return (
            <li
              key={engine}
              className="border-line flex items-center gap-2 rounded-md border px-2 py-1.5"
            >
              <span className="text-ink-faint w-4 text-xs tabular-nums">{i + 1}</span>
              <CircleIcon
                weight="fill"
                className={cn(
                  'size-2 shrink-0',
                  localDown ? 'text-status-fail' : 'text-status-ok',
                )}
                aria-hidden
              />
              <span className="text-ink flex-1 text-xs">{engine}</span>

              {/* Usage is OUR call count, never a quota: Gemini exposes no
                  remaining-quota signal, so showing these side by side in a
                  slot labelled "quota" would invent a limit that does not exist. */}
              <span className="text-ink-faint text-[0.6875rem] tabular-nums">
                {u ? t('settings.sttUsage', { today: u.today, period: u.period }) : '—'}
              </span>

              {isDirector && (
                <span className="flex gap-0.5">
                  <button
                    type="button"
                    disabled={i === 0 || saving}
                    onClick={() => void move(i, i - 1)}
                    aria-label={t('settings.sttMoveUp', { engine })}
                    className="text-ink-faint hover:text-ink rounded p-0.5 disabled:opacity-30"
                  >
                    <ArrowUpIcon className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    disabled={i === chain.length - 1 || saving}
                    onClick={() => void move(i, i + 1)}
                    aria-label={t('settings.sttMoveDown', { engine })}
                    className="text-ink-faint hover:text-ink rounded p-0.5 disabled:opacity-30"
                  >
                    <ArrowDownIcon className="size-3.5" />
                  </button>
                </span>
              )}
            </li>
          )
        })}
      </ol>

      {/* Reset restores the benchmarked default from the API, not a list
          hardcoded here that would drift from config.py. */}
      {isDirector && status.default_chain.join(',') !== chain.join(',') && (
        <button
          type="button"
          disabled={saving}
          onClick={() => void persist(status.default_chain)}
          className="text-ink-faint hover:text-ink self-start text-xs underline underline-offset-2 disabled:opacity-40"
        >
          {t('settings.sttReset', { order: status.default_chain.join(' → ') })}
        </button>
      )}

      {status.local.url_set && status.local.status !== 'ok' && (
        <p className="text-ink-faint text-[0.6875rem]">{t('settings.sttLocalDown')}</p>
      )}
      {!status.local.url_set && (
        <p className="text-ink-faint text-[0.6875rem]">{t('settings.sttLocalUnset')}</p>
      )}
      {error && <p className="text-status-fail text-xs">{error}</p>}
    </fieldset>
  )
}
