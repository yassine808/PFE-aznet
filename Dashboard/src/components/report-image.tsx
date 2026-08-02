import { useState } from 'react'
import { DownloadSimpleIcon, SparkleIcon } from '@phosphor-icons/react'
import { generateImage, type GeneratedImage, type ReportRow } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { ErrorState } from '@/components/states'

/**
 * "Generate an image if needed from all the infos collected" — one button on
 * the daily and weekly pages. The card is the one output that invents
 * anything, so it is only ever fired by an explicit click, and the result is
 * shown here and downloaded from here: it never touches the Sheet, so a
 * generated picture can never be mistaken for a technician's own photo.
 */
export function ReportImageCard({
  rows,
  title,
  disabled,
}: {
  readonly rows: ReportRow[]
  readonly title: string
  readonly disabled: boolean
}) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [image, setImage] = useState<GeneratedImage | null>(null)

  const generate = async () => {
    setBusy(true)
    setError(null)
    setImage(null)
    try {
      setImage(await generateImage(rows, title))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="border-line rounded-xl border p-6">
      <div className="border-line flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div>
          <h2 className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">
            {t('image.title')}
          </h2>
          <p className="text-ink-faint mt-1 max-w-[60ch] text-xs">{t('image.intro')}</p>
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={busy || disabled}
          className={
            busy || disabled
              ? 'border-line text-ink-faint cursor-not-allowed rounded-md border px-4 py-2 text-sm'
              : 'bg-accent breathe-glow rounded-md px-4 py-2 text-sm text-white transition-transform active:translate-y-px'
          }
        >
          <span className="flex items-center gap-2">
            <SparkleIcon size={14} weight="fill" />
            {busy ? t('image.generating') : t('image.generate')}
          </span>
        </button>
      </div>

      {error && <ErrorState message={error} onRetry={generate} />}

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
    </section>
  )
}
