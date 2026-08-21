import { useEffect, useRef, useState } from 'react'
import { ArrowsOutSimpleIcon, CornersInIcon, WarningIcon } from '@phosphor-icons/react'
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
 *
 * And every page is rendered inline, with no scroller of its own. A document
 * inside a scrollbox is a document nobody reads past its first screen — the
 * reader has to guess how much is left, and the page's own scrollbar fights
 * the panel's. The panel is as tall as the report; the page scrolls, once.
 *
 * A Word page is 794 CSS px wide and the column often is not, so the pages are
 * *scaled* to fit rather than clipped or squeezed: `transform: scale()` keeps
 * the proportions the printer will use, and the wrapper's height is corrected
 * by the same factor so the layout below it does not sit on empty space. The
 * toggle offers true size for the one case fit-to-width is bad at — a dense
 * quantities table on a laptop.
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

  // Fit-to-width, measured rather than guessed: the column is a grid track that
  // changes with the window, the sidebar and the language direction, so the
  // factor cannot be a constant.
  const [fit, setFit] = useState(true)
  const [scale, setScale] = useState(1)
  // The scaled height, in px. A transform reserves the *unscaled* box, so the
  // host has to be told what the pages now actually occupy.
  const [height, setHeight] = useState<number | null>(null)

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

  // Re-measured on every resize *and* after the render lands, because the page
  // width only exists once `renderAsync` has written the pages.
  useEffect(() => {
    const node = host.current
    if (!node) return
    const measure = () => {
      const wrapper = node.querySelector('.docx-wrapper')
      const page = node.querySelector('section.docx')
      if (!(wrapper instanceof HTMLElement) || !(page instanceof HTMLElement)) return
      // `offsetWidth` ignores transforms, so this stays the page's true layout
      // width however far it is currently scaled — measuring the rendered box
      // instead would feed the scale back into itself and oscillate.
      const width = page.offsetWidth
      const room = node.clientWidth
      if (!width || !room) return
      // The 8 px is the scrollbar-and-shadow margin: fitting to the last pixel
      // makes a scrollbar appear, which takes the pixel away, which fits again.
      const next = fit ? Math.min(1, room / (width + 8)) : 1
      setScale(next)
      setHeight(wrapper.offsetHeight * next)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [fit, state])

  const ZoomIcon = fit ? ArrowsOutSimpleIcon : CornersInIcon

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {state === 'ready' && (
        <div className="flex items-center justify-end">
          <button
            type="button"
            onClick={() => setFit((v) => !v)}
            aria-pressed={!fit}
            className="border-line text-ink-faint hover:text-ink focus-visible:ring-accent flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1 text-[0.6875rem] transition-colors outline-none focus-visible:ring-2"
          >
            <ZoomIcon size={12} />
            {fit ? t('editor.docxFull') : t('editor.docxFit')}
          </button>
        </div>
      )}
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
        // `overflow-x` only, and only when the reader asked for true size: at
        // fit there is nothing to scroll, and a scrollbar that appears for one
        // pixel of rounding is worse than the pixel.
        style={{
          ['--docx-scale' as string]: scale,
          height: height ? `${height}px` : undefined,
        }}
        className={cn(
          'border-line docx-host rounded-md border bg-slate-200 dark:bg-slate-900',
          fit ? 'overflow-hidden' : 'overflow-x-auto',
          state === 'ready' ? 'block' : 'hidden',
        )}
      />
    </div>
  )
}
