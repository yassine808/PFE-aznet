import { ArrowClockwiseIcon, WarningIcon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'

/** Skeletons match the shape of what is coming, so nothing jumps when data lands. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('bg-line/70 animate-pulse rounded', className)} />
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
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

export function EmptyState({ body }: { body?: string }) {
  const { t } = useI18n()
  return (
    <div className="py-10">
      <p className="text-ink text-sm font-medium">{t('state.empty.title')}</p>
      <p className="text-ink-faint mt-1 max-w-[65ch] text-sm">{body ?? t('state.empty.body')}</p>
    </div>
  )
}
