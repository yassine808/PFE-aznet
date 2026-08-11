import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ChartBarIcon, MagnifyingGlassIcon, UserIcon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import { NAV, fold } from '@/lib/nav'
import { api, useApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Route } from '@/lib/router'

/** Ctrl/Cmd+K anywhere, or "/" outside a field. Ten pages is past the point where scanning a rail beats typing three letters. */
export function useCommandPalette(): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const typing =
        !!target &&
        (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName ?? ''))

      if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((o) => !o)
        return
      }
      if (e.key === '/' && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return [open, setOpen]
}

/**
 * Ordered-subsequence score: how tightly `q`'s letters sit inside `text`, in
 * order. 0 = contiguous, positive = gaps (missing or inserted letters), -1 =
 * a letter is absent. This is what tolerates "rappot" for "Rapports".
 */
function subsequenceScore(q: string, text: string): number {
  let at = 0
  let cost = 0
  for (const ch of q) {
    const found = text.indexOf(ch, at)
    if (found < 0) return -1
    cost += found - at
    at = found + 1
  }
  return cost
}

/** Classic Levenshtein, two rows of memory — small strings, called only as a fallback. */
function editDistance(a: string, b: string): number {
  const m = a.length
  const n = b.length
  if (!m) return n
  if (!n) return m
  let prev = Array.from({ length: n + 1 }, (_, j) => j)
  for (let i = 1; i <= m; i++) {
    const cur = [i] as number[]
    for (let j = 1; j <= n; j++) {
      const sub = prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, sub)
    }
    prev = cur
  }
  return prev[n]
}

interface Hit {
  route: Route
  /** Pages translate their label; people carry a raw name. */
  labelKey?: string
  label?: string
  /** Extra words the palette matches on, so "email" finds the daily report. */
  keywordsKey?: string
  section: string
  Icon: typeof ChartBarIcon
  /** Present on people hits, which all route to the same page. */
  personId?: number
}

export function CommandPalette({
  open,
  onClose,
  onNavigate,
  route,
}: {
  readonly open: boolean
  readonly onClose: () => void
  readonly onNavigate: (r: Route, params?: Record<string, string>) => void
  readonly route: Route
}) {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  // Whoever had focus before the palette opened gets it back on close, so
  // Escape does not dump a keyboard user at the top of the document.
  const restoreTo = useRef<HTMLElement | null>(null)

  const all: Hit[] = useMemo(
    () => NAV.flatMap((s) => s.items.map((i) => ({ ...i, section: s.section }))),
    [],
  )

  // Colleagues join the index: the palette searches people as well as pages.
  const techs = useApi('technicians', api.technicians)

  const people: Hit[] = useMemo(
    () =>
      (techs.data?.technicians ?? []).map((p) => ({
        route: 'equipe' as const,
        label: p.name,
        section: p.role ? `equipe.role.${p.role}` : 'nav.equipe',
        Icon: UserIcon,
        personId: p.id,
      })),
    [techs.data],
  )

  const pool = useMemo(() => [...all, ...people], [all, people])

  const { hits, fellBack } = useMemo(() => {
    const q = fold(query.trim())
    if (!q) return { hits: all, fellBack: false }
    const haystack = (h: Hit) =>
      fold(
        `${h.label ?? t(h.labelKey ?? '')} ${h.keywordsKey ? t(h.keywordsKey) : ''} ${t(
          h.section,
        )} ${h.route}`.trim(),
      )
    const scored = pool
      .map((h) => {
        const hay = haystack(h)
        if (hay.includes(q)) return { h, s: 0 }
        // One letter is not enough signal for fuzzy matching — substring only.
        if (q.length === 1) return { h, s: -1 }
        return { h, s: subsequenceScore(q, hay) }
      })
      .filter((x): x is { h: Hit; s: number } => x.s >= 0)
      .sort((a, b) => a.s - b.s)
    if (scored.length > 0) return { hits: scored.map((x) => x.h), fellBack: false }
    // Nothing fuzzy matched: offer the closest strings as suggestions.
    const near = pool
      .map((h) => {
        const hay = fold(
          `${h.label ?? t(h.labelKey ?? '')} ${h.keywordsKey ? t(h.keywordsKey) : ''}`,
        )
        return { h, d: editDistance(q, hay) }
      })
      .sort((a, b) => a.d - b.d)
      .slice(0, 2)
    return { hits: near.map((x) => x.h), fellBack: true }
  }, [all, pool, query, t])

  useEffect(() => {
    if (open) {
      restoreTo.current = document.activeElement as HTMLElement | null
      setQuery('')
      setCursor(0)
      // rAF: the input only exists after the enter animation mounts it.
      requestAnimationFrame(() => inputRef.current?.focus())
    } else {
      restoreTo.current?.focus?.()
    }
  }, [open])

  useEffect(() => setCursor(0), [query])

  // Keep the highlighted row on screen when arrowing past the fold.
  useEffect(() => {
    listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [cursor, hits.length])

  const go = (r: Route, params?: Record<string, string>) => {
    onNavigate(r, params)
    onClose()
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => (hits.length ? (c + 1) % hits.length : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => (hits.length ? (c - 1 + hits.length) % hits.length : 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const hit = hits[cursor]
      if (hit)
        go(hit.route, hit.personId !== undefined ? { person: String(hit.personId) } : undefined)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <div
            className="absolute inset-0 bg-slate-950/40 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={t('cmd.title')}
            onKeyDown={onKeyDown}
            initial={{ opacity: 0, y: -10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 140, damping: 18 }}
            className="border-line bg-surface relative w-full max-w-lg overflow-hidden rounded-xl border shadow-2xl"
          >
            <div className="border-line flex items-center gap-3 border-b px-4">
              <MagnifyingGlassIcon size={17} className="text-ink-faint shrink-0" />
              <label htmlFor="cmd-input" className="sr-only">
                {t('cmd.placeholder')}
              </label>
              <input
                id="cmd-input"
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('cmd.placeholder')}
                autoComplete="off"
                spellCheck={false}
                role="combobox"
                aria-expanded="true"
                aria-controls="cmd-list"
                aria-activedescendant={
                  hits[cursor]
                    ? `cmd-opt-${hits[cursor].personId ?? hits[cursor].route}`
                    : undefined
                }
                className="text-ink placeholder:text-ink-faint h-14 min-w-0 flex-1 bg-transparent text-sm outline-none"
              />
              <kbd className="border-line text-ink-faint hidden rounded border px-1.5 py-0.5 text-[0.6875rem] sm:block">
                esc
              </kbd>
            </div>

            <div // NOSONAR
              ref={listRef}
              id="cmd-list"
              // real ARIA combobox listbox — no native <select> fits icon+shortcut rows
              role="listbox"
              className="max-h-80 overflow-y-auto p-2"
            >
              {hits.length === 0 ? (
                <p className="text-ink-faint px-3 py-6 text-center text-sm">{t('cmd.noResults')}</p>
              ) : (
                <>
                  {fellBack && (
                    <p className="text-ink-faint px-3 pb-1 pt-2 text-xs">{t('cmd.didYouMean')}</p>
                  )}
                  {hits.map((hit, i) => {
                    const active = i === cursor
                    const id = `cmd-opt-${hit.personId ?? hit.route}`
                    return (
                      <button
                        key={hit.personId ?? hit.route}
                        id={id}
                        type="button"
                        role="option"
                        aria-selected={active}
                        data-active={active}
                        onMouseMove={() => setCursor(i)}
                        onClick={() =>
                          go(
                            hit.route,
                            hit.personId !== undefined
                              ? { person: String(hit.personId) }
                              : undefined,
                          )
                        }
                        className={cn(
                          'flex w-full cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 text-start text-sm transition-colors',
                          active ? 'bg-slate-100 text-ink dark:bg-slate-850' : 'text-ink-muted',
                        )}
                      >
                        <hit.Icon
                          size={17}
                          weight={active ? 'fill' : 'regular'}
                          className={active ? 'text-accent shrink-0' : 'shrink-0'}
                        />
                        <span className="min-w-0 flex-1 truncate">
                          {hit.label ?? t(hit.labelKey ?? '')}
                        </span>
                        <span className="text-ink-faint truncate text-xs">{t(hit.section)}</span>
                        {hit.route === route && (
                          <span className="text-ink-faint text-[0.6875rem]">
                            {t('cmd.current')}
                          </span>
                        )}
                      </button>
                    )
                  })}
                </>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
