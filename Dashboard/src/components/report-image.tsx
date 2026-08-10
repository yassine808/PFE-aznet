import { DownloadSimpleIcon } from '@phosphor-icons/react'
import type { GeneratedImage } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { ErrorState } from '@/components/states'

/**
 * The illustrated summary card, shown and downloadable here — but never
 * generated here. The card is the one output that invents anything, so it is
 * only ever produced by an explicit gesture: the report's "Générer" click,
 * which now fires the image alongside the text (2026-08-10, replacing the old
 * second button). The page owns the call, the busy/error states and the
 * retry; this component renders the result and the failure, and the data URI
 * never touches the Sheet, so a generated picture can never be mistaken for a
 * technician's own photo.
 */
export function ReportImageCard({
  title,
  image,
  busy,
  error,
  onRetry,
}: {
  readonly title: string
  readonly image: GeneratedImage | null
  readonly busy: boolean
  readonly error: string | null
  /** Re-run the generation the page fired with the report. */
  readonly onRetry?: () => void
}) {
  const { t } = useI18n()

  return (
    <section className="border-line rounded-xl border p-6">
      <div className="border-line flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div>
          <h2 className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">
            {t('image.title')}
          </h2>
          <p className="text-ink-faint mt-1 max-w-[60ch] text-xs">{t('image.intro')}</p>
        </div>
        {busy && (
          <span className="text-ink-faint flex items-center gap-2 text-xs" role="status">
            <span className="bg-accent size-2 animate-pulse rounded-full" />
            {t('image.generating')}
          </span>
        )}
      </div>

      {error && <ErrorState message={error} onRetry={onRetry} />}

      {image && (
        <div className="mt-5 flex flex-col items-start gap-3">
          <img
            src={image.data_uri}
            alt={title}
            className="border-line max-h-[28rem] w-auto rounded-lg border"
          />
          <div className="flex items-center gap-3">
            <a
              href={image.data_uri}
              download="carte.png"
              className="border-line text-ink-muted hover:text-ink flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors"
            >
              <DownloadSimpleIcon size={13} />
              {t('image.download')}
            </a>
            <span className="text-ink-faint text-xs">{t('image.byModel', { model: image.model })}</span>
          </div>
        </div>
      )}

      {!busy && !error && !image && (
        <p className="text-ink-faint mt-4 text-xs">{t('image.autoHint')}</p>
      )}
    </section>
  )
}
