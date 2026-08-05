import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  CheckCircleIcon,
  InfoIcon,
  WarningCircleIcon,
  WarningIcon,
  XIcon,
} from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'

export type ToastTone = 'success' | 'error' | 'warn' | 'info'

export interface Toast {
  id: number
  tone: ToastTone
  title: string
  body?: string
  /** Fired when the toast itself is clicked — used to jump to the source page. */
  onOpen?: () => void
}

/**
 * Tone → icon and colour, read from the same status ramp the rest of the app
 * uses. Deliberately not a free-form colour prop: four tones is the whole
 * vocabulary, and a fifth would be a design decision, not a call site's.
 */
const TONE: Record<ToastTone, { Icon: typeof InfoIcon; text: string; bar: string; ring: string }> = {
  success: {
    Icon: CheckCircleIcon,
    text: 'text-status-ok',
    bar: 'bg-status-ok',
    ring: 'ring-status-ok/25',
  },
  error: {
    Icon: WarningCircleIcon,
    text: 'text-status-fail',
    bar: 'bg-status-fail',
    ring: 'ring-status-fail/25',
  },
  warn: {
    Icon: WarningIcon,
    text: 'text-status-warn',
    bar: 'bg-status-warn',
    ring: 'ring-status-warn/25',
  },
  info: { Icon: InfoIcon, text: 'text-accent', bar: 'bg-accent', ring: 'ring-accent/25' },
}

/** An error stays longer: it is the one a reader has to act on. */
const LIFE_MS: Record<ToastTone, number> = {
  success: 4_000,
  info: 5_000,
  warn: 7_000,
  error: 9_000,
}

/** At most this many on screen; older ones drop off the bottom of the stack. */
const MAX = 4

type Push = (t: Omit<Toast, 'id'>) => void

const ToastContext = createContext<Push | null>(null)

export function ToastProvider({ children }: { readonly children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const seq = useRef(0)

  const dismiss = useCallback((id: number) => {
    setItems((list) => list.filter((t) => t.id !== id))
  }, [])

  const push = useCallback<Push>(
    (t) => {
      const id = ++seq.current
      setItems((list) => [...list, { ...t, id }].slice(-MAX))
      // The timer lives here rather than in the card so a toast that is
      // re-rendered (stack reflow, theme switch) does not restart its own life.
      window.setTimeout(() => dismiss(id), LIFE_MS[t.tone])
    },
    [dismiss],
  )

  return (
    <ToastContext.Provider value={push}>
      {children}
      <ToastStack items={items} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}

/**
 * Fire-and-forget toasts.
 *
 * Returns a no-op outside the provider rather than throwing: a toast is
 * feedback, and a component that renders in isolation (a test, a story) must
 * not crash because nobody set up the surface it would have drawn on.
 */
export function useToast(): Push {
  return useContext(ToastContext) ?? noop
}

const noop: Push = () => {}

function ToastStack({
  items,
  onDismiss,
}: {
  readonly items: Toast[]
  readonly onDismiss: (id: number) => void
}) {
  const { t } = useI18n()
  return (
    <div
      // `end-4` rather than `right-4`: top-right in French and English, top-left
      // in Arabic, which is the same corner to the reader.
      className="pointer-events-none fixed top-4 end-4 z-[70] flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2"
      role="region"
      aria-live="polite"
      aria-label={t('toast.region')}
    >
      <AnimatePresence initial={false}>
        {items.map((item) => (
          <ToastCard key={item.id} toast={item} onDismiss={onDismiss} />
        ))}
      </AnimatePresence>
    </div>
  )
}

function ToastCard({
  toast,
  onDismiss,
}: {
  readonly toast: Toast
  readonly onDismiss: (id: number) => void
}) {
  const { t } = useI18n()
  const { Icon, text, bar, ring } = TONE[toast.tone]

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -14, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96, y: -8, transition: { duration: 0.16 } }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className={cn(
        'border-line bg-surface edge pointer-events-auto relative overflow-hidden rounded-xl border shadow-xl shadow-black/10 ring-1',
        ring,
      )}
    >
      <div className="flex items-start gap-2.5 px-3.5 py-3">
        <Icon size={17} weight="fill" className={cn('mt-px shrink-0', text)} />

        <button
          type="button"
          onClick={() => {
            toast.onOpen?.()
            onDismiss(toast.id)
          }}
          className={cn(
            'min-w-0 flex-1 text-start',
            toast.onOpen ? 'cursor-pointer' : 'cursor-default',
          )}
        >
          <span className="text-ink block text-sm font-medium">{toast.title}</span>
          {toast.body && (
            <span className="text-ink-faint mt-0.5 line-clamp-2 block text-xs">{toast.body}</span>
          )}
        </button>

        <button
          type="button"
          onClick={() => onDismiss(toast.id)}
          aria-label={t('toast.dismiss')}
          className="text-ink-faint hover:text-ink -me-1 -mt-1 shrink-0 cursor-pointer rounded p-1 transition-colors"
        >
          <XIcon size={13} />
        </button>
      </div>

      {/* The remaining life, drawn. A CSS animation on purpose: React state
          ticking every frame would re-render the whole stack 60 times a second
          to move one bar. */}
      <motion.span
        aria-hidden="true"
        className={cn('absolute bottom-0 start-0 h-0.5 w-full origin-[left_center] rtl:origin-[right_center]', bar)}
        initial={{ scaleX: 1 }}
        animate={{ scaleX: 0 }}
        transition={{ duration: LIFE_MS[toast.tone] / 1000, ease: 'linear' }}
      />
    </motion.div>
  )
}
