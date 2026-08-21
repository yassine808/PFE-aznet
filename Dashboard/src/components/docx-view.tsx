import { useEffect, useRef, useState } from 'react'
import { FileDocIcon, WarningIcon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import { Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

/**
 * The Word document itself, rendered in the page.
 *
 * Not a second renderer: this fetches the bytes the API produced — the same
 * file the director receives by mail and the same one the download button
 * hands over — and `docx-preview` lays them out. An HTML mirror of the
 * document would have been one dependency lighter and one more thing that can
 * disagree with the real thing, which is the whole failure this page exists to
 * prevent: an operator reads a preview, sends the document, and the two say
 * different numbers.
 *
 * The pages stay white in both themes. A document is a sheet of paper; tinting
 * it to match the app would show the reader something Word will not print.
 */
export function DocxView({
  src,
  className,
}: {
  readonly src: string
  readonly className?: string
}) {
  const { t } = useI18n()
  const host = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Guards the async tail: switching version while a render is in flight
    // would otherwise paint the old document into the new container.
    let live = true
    setState('loading')
    setError(null)

    const run = async () => {
      const res = await fetch(src, { credentials: 'same-origin' })
      if (!res.ok) throw new Error(`${res.status}`)
      const blob = await res.blob()
      // Imported here rather than at module scope: the renderer is ~200 KB and
      // most sessions never open a report, so it must not sit in the entry
      // bundle every page pays for.
      const { renderAsync } = await import('docx-preview')
      if (!live || !host.current) return
      host.current.replaceChildren()
      await renderAsync(blob, host.current, undefined, {
        className: 'docx',
        inWrapper: true,
        breakPages: true,
        ignoreLastRenderedPageBreak: true,
      })
      if (live) setState('ready')
    }

    run().catch((err: unknown) => {
      if (!live) return
      setError(err instanceof Error ? err.message : String(err))
      setState('error')
    })

    return () => {
      live = false
    }
  }, [src])

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {state === 'loading' && <Skeleton className="h-96 rounded-md" />}
      {state === 'error' && (
        <p
          role="alert"
          className="border-line text-ink-muted flex items-center gap-2 rounded-md border border-dashed px-3 py-6 text-xs"
        >
          <WarningIcon size={14} className="text-status-warn shrink-0" />
          {t('editor.docxMissing')}
          {error && <span className="text-ink-faint break-all">({error})</span>}
        </p>
      )}
      {/* Kept mounted across states: `renderAsync` writes into this node, and a
          node that only exists once loading is done is a node the render has
          nowhere to go. */}
      <div
        ref={host}
        aria-label={t('editor.docxPreview')}
        className={cn(
          'border-line max-h-[42rem] overflow-auto rounded-md border bg-slate-200 dark:bg-slate-900',
          state === 'ready' ? 'block' : 'hidden',
        )}
      />
      {state === 'ready' && (
        <p className="text-ink-faint flex items-center gap-1.5 text-[0.6875rem]">
          <FileDocIcon size={12} />
          {t('editor.docxPreview')}
        </p>
      )}
    </div>
  )
}
