import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { GearSixIcon, XIcon } from '@phosphor-icons/react'
import { REFRESH_CHOICES, useSettings, type Density } from '@/lib/settings'
import { useI18n } from '@/lib/i18n'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { v: T; label: string }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">{label}</span>
      <div className="border-line flex rounded-md border p-0.5" role="group" aria-label={label}>
        {options.map((o) => (
          <button
            key={String(o.v)}
            type="button"
            onClick={() => onChange(o.v)}
            aria-pressed={o.v === value}
            className={cn(
              'flex-1 rounded px-2 py-1 text-xs transition-colors active:translate-y-px',
              o.v === value ? 'bg-slate-100 text-ink dark:bg-slate-850' : 'text-ink-faint hover:text-ink',
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export function SettingsPanel() {
  const { t } = useI18n()
  const { settings, update, reset } = useSettings()
  const { user } = useAuth()
  // Seuil de confiance: directeur seulement. Les chefs de chantier gardent le reste.
  const canTuneConfidence = user?.role === 'directeur'
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  // Close on outside click and on Escape: standard popover affordances, not reinvented.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={t('settings.title')}
        title={t('settings.title')}
        className="border-line text-ink-muted hover:text-ink rounded-md border p-1.5 transition-colors active:translate-y-px"
      >
        <GearSixIcon size={15} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 100, damping: 20 }}
            role="dialog"
            aria-label={t('settings.title')}
            className="border-line bg-surface-raised edge absolute bottom-full z-50 mb-2 w-72 origin-bottom rounded-xl border p-5 shadow-[0_16px_40px_-20px_oklch(0.146_0.008_245/0.45)] ltr:left-0 rtl:right-0"
          >
            <div className="mb-5 flex items-center justify-between">
              <p className="text-ink text-sm font-medium">{t('settings.title')}</p>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label={t('settings.close')}
                className="text-ink-faint hover:text-ink transition-colors"
              >
                <XIcon size={14} />
              </button>
            </div>

            <div className="flex flex-col gap-5">
              <Segmented
                label={t('settings.refresh')}
                value={settings.refreshMs}
                onChange={(v) => update({ refreshMs: v })}
                options={REFRESH_CHOICES.map((ms) => ({
                  v: ms,
                  label: ms === 0 ? t('settings.manual') : `${ms / 1000}s`,
                }))}
              />

              <Segmented<Density>
                label={t('settings.density')}
                value={settings.density}
                onChange={(v) => update({ density: v })}
                options={[
                  { v: 'comfortable', label: t('settings.comfortable') },
                  { v: 'compact', label: t('settings.compact') },
                ]}
              />

              {canTuneConfidence && (
              <div className="flex flex-col gap-2">
                <div className="flex items-baseline justify-between">
                  <label htmlFor="confidence" className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">
                    {t('settings.confidence')}
                  </label>
                  <span className="tabular text-ink text-xs">{settings.confidence.toFixed(2)}</span>
                </div>
                <input
                  id="confidence"
                  type="range"
                  min={0.3}
                  max={0.95}
                  step={0.05}
                  value={settings.confidence}
                  onChange={(e) => update({ confidence: Number(e.target.value) })}
                  className="accent-accent w-full"
                />
                <p className="text-ink-faint text-xs">{t('settings.confidenceHint')}</p>
              </div>
              )}

              <button
                type="button"
                onClick={reset}
                className="text-ink-faint hover:text-ink self-start text-xs underline underline-offset-4 transition-colors"
              >
                {t('settings.reset')}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
