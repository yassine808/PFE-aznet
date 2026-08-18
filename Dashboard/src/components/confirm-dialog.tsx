import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef } from 'react'

import { useI18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'

/**
 * The one way anything in this dashboard gets deleted.
 *
 * A delete that happens on a single click is a delete that happens by accident,
 * and nothing here is undoable from the interface: a removed technician takes
 * their channels with them, a removed site takes its bordereau. So every
 * destructive action stops here first, names what it is about to destroy, and
 * waits.
 *
 * Naming the target is the point of the copy — "Supprimer cet élément ?" tells
 * a hurried reader nothing they did not already assume, while "Supprimer
 * NAROUZE ?" is checkable against what they meant to click.
 *
 * The confirm button is the only red in the dashboard's palette that is not a
 * status: red here means "this cannot be undone", and it is spent nowhere else,
 * so it keeps meaning that.
 */
export function ConfirmDialog({
  open,
  target,
  body,
  confirmLabel,
  busy = false,
  onConfirm,
  onCancel,
}: {
  readonly open: boolean
  /** What is about to be destroyed, named. Goes into the question. */
  readonly target: string
  /** Optional second line: what else goes with it. */
  readonly body?: string
  readonly confirmLabel?: string
  readonly busy?: boolean
  readonly onConfirm: () => void
  readonly onCancel: () => void
}) {
  const { t } = useI18n()
  const cancelRef = useRef<HTMLButtonElement>(null)

  // Escape cancels, the page behind stops scrolling, and focus starts on
  // Cancel — a dialog that opens with the destructive button focused turns a
  // stray Enter into the very thing it exists to prevent.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    cancelRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [open, onCancel])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.14 }}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onCancel()
          }}
        >
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 140, damping: 18 }}
            role="alertdialog"
            aria-modal="true"
            aria-label={t('confirm.title')}
            className="border-line bg-surface edge w-[min(28rem,100%)] rounded-2xl border p-5 shadow-2xl shadow-black/20"
          >
            <h2 className="text-ink text-base font-semibold">
              {t('confirm.question').replace('{x}', target)}
            </h2>
            <p className="text-ink-faint mt-2 text-sm">{body || t('confirm.irreversible')}</p>

            <div className="mt-5 flex justify-end gap-2">
              <button
                ref={cancelRef}
                type="button"
                onClick={onCancel}
                className="border-line text-ink hover:bg-surface-2 focus-visible:ring-accent cursor-pointer rounded-md border px-3 py-1.5 text-sm outline-none focus-visible:ring-2"
              >
                {t('confirm.cancel')}
              </button>
              <button
                type="button"
                onClick={onConfirm}
                disabled={busy}
                className={cn(
                  'cursor-pointer rounded-md px-3 py-1.5 text-sm font-medium text-white outline-none',
                  'bg-status-fail hover:brightness-110 focus-visible:ring-2 focus-visible:ring-red-400',
                  busy && 'cursor-not-allowed opacity-60',
                )}
              >
                {busy ? t('confirm.deleting') : confirmLabel || t('confirm.delete')}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
