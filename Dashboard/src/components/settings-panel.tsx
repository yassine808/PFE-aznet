import { useState } from 'react'
import { GearSixIcon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import { SettingsOverlay } from '@/components/settings-overlay'

/**
 * The gear in the bottom-left rail.
 *
 * It used to *be* the settings: a 288px popover holding three local
 * preferences, while the schedule and the recipients lived on the Automation
 * page. They now live together in a tabbed overlay
 * (`components/settings-overlay.tsx`), so this file is what is left — the
 * trigger, in the corner people already reach for.
 */
export function SettingsPanel() {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t('settings.title')}
        title={t('settings.title')}
        className="border-line text-ink-muted hover:text-ink cursor-pointer rounded-md border p-1.5 transition-colors active:translate-y-px"
      >
        <GearSixIcon size={15} />
      </button>
      <SettingsOverlay open={open} onClose={() => setOpen(false)} />
    </>
  )
}
