import { SparkleIcon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'

/**
 * The one primary action on the Daily and Weekly pages.
 *
 * Shared because the two pages had drifted apart — same button, two sizes, two
 * sets of classes, and only one of them carried the breathing glow. It is the
 * single accented control on either page, which is what DESIGN.md's Ten
 * Percent Rule buys: it is findable without being announced.
 */
export function GenerateButton({
  busy,
  disabled,
  onClick,
}: {
  readonly busy: boolean
  readonly disabled: boolean
  readonly onClick: () => void
}) {
  const { t } = useI18n()
  const off = busy || disabled
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={off}
      className={cn(
        'flex items-center gap-2 rounded-md px-4 py-2 text-sm transition-transform',
        off
          ? 'border-line text-ink-faint cursor-not-allowed border'
          : 'bg-accent breathe-glow text-white active:translate-y-px',
      )}
    >
      <SparkleIcon size={14} weight="fill" />
      {busy ? t('daily.generating') : t('daily.generate')}
    </button>
  )
}
