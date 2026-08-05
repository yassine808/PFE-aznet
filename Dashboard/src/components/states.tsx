import { ArrowClockwiseIcon, TrayIcon, WarningIcon, type Icon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'

/** Skeletons match the shape of what is coming, so nothing jumps when data lands. */
export function Skeleton({ className }: { readonly className?: string }) {
  return <div className={cn('bg-line/70 animate-pulse rounded', className)} />
}

export function ErrorState({
  message,
  onRetry,
}: {
  readonly message: string
  readonly onRetry?: () => void
}) {
  const { t } = useI18n()
  return (
    <div className="border-status-fail/30 bg-status-fail/5 flex flex-col items-start gap-3 rounded-lg border p-5">
      <p className="text-status-fail flex items-center gap-2 text-sm font-medium">
        <WarningIcon size={16} weight="fill" />
        {t('state.error.title')}
      </p>
      <p className="text-ink-muted tabular max-w-[65ch] text-xs break-all">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="border-line text-ink hover:bg-surface-raised inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px"
        >
          <ArrowClockwiseIcon size={13} />
          {t('state.error.retry')}
        </button>
      )}
    </div>
  )
}

/**
 * Nothing here — and what to do about it.
 *
 * "Rien à afficher" is true and useless: it names the absence without naming
 * the period it is absent for, and leaves the one action that would fix it
 * somewhere else on the page. So this takes a mark, a title that says *when*,
 * a sentence about what would appear, and optionally the action itself.
 *
 * The mark is a Phosphor glyph in a tonal disc, not an emoji: DESIGN.md rules
 * out emoji icons outright, and an emoji renders as a different picture on
 * every platform — which is exactly the kind of thing an operator learns to
 * distrust. Same reason it is not an illustration.
 */
export function EmptyState({
  icon: Icon = TrayIcon,
  title,
  body,
  action,
}: {
  readonly icon?: Icon
  /** Say the period out loud — "Aucun rapport pour le 5 août" beats "Rien à afficher". */
  readonly title?: string
  readonly body?: string
  /** The way out, when the page has one. Rendered directly under the sentence. */
  readonly action?: React.ReactNode
}) {
  const { t } = useI18n()
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <span className="border-line bg-surface text-ink-faint flex size-11 items-center justify-center rounded-full border">
        <Icon size={19} />
      </span>
      <div className="flex flex-col gap-1">
        <p className="text-ink text-sm font-medium">{title ?? t('state.empty.title')}</p>
        <p className="text-ink-faint mx-auto max-w-[42ch] text-sm">
          {body ?? t('state.empty.body')}
        </p>
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}
