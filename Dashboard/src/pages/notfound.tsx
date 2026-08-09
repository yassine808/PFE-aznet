import { motion } from 'motion/react'
import { CompassIcon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import { useRoute } from '@/lib/router'

/**
 * Adresse inconnue.
 *
 * Rendered inside the app shell, not as a bare page: the sidebar stays, so the
 * way out is already on screen and this reads as "that address is wrong" rather
 * than "the app broke".
 *
 * It exists because the router used to send any unrecognised hash to Overview.
 * A retired bookmark then looked like it worked — the same reasoning that kept
 * `team` and `access` as explicit aliases instead of letting them fall through.
 * The offending path is echoed back so a typo is visible without opening the
 * address bar.
 */
export function NotFoundPage() {
  const { t } = useI18n()
  const [, go] = useRoute()
  const path = window.location.hash.replace(/^#\/?/, '').split('?')[0]

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: [0.2, 0, 0, 1] }}
      className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center"
    >
      <CompassIcon
        weight="thin"
        className="text-ink-faint size-14 opacity-60"
        aria-hidden
      />

      {/* The number is decorative; the sentence carries the meaning, so the
          heading is the sentence and 404 is a caption. */}
      <p className="text-ink-faint text-xs font-medium tracking-[0.2em] uppercase">404</p>
      <h1 className="text-ink text-xl font-medium text-balance">{t('notfound.title')}</h1>
      <p className="text-ink-faint max-w-sm text-sm text-pretty">{t('notfound.body')}</p>

      {path && (
        <code className="border-line text-ink-faint rounded-md border px-2 py-1 text-xs break-all">
          #/{path}
        </code>
      )}

      <button
        type="button"
        onClick={() => go('overview')}
        className="border-line text-ink hover:bg-slate-100 dark:hover:bg-slate-850 mt-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px"
      >
        {t('notfound.back')}
      </button>
    </motion.section>
  )
}
