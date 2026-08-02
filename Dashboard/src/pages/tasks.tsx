import { useState, type FormEvent } from 'react'
import { motion } from 'motion/react'
import {
  CheckCircleIcon,
  CircleIcon,
  PlusIcon,
  TrashIcon,
} from '@phosphor-icons/react'
import { api, createTask, deleteTask, updateTask, useApi, type TaskItem } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

const REPEATS: TaskItem['repeat'][] = ['none', 'daily', 'weekly', 'monthly']

/**
 * The shared to-do panel (TO-DO #33). One list, every account can edit it.
 * The API's reminders job rings every bell when a task falls due, repeats the
 * ring on the chosen cadence, and emails the accounts at the same moment.
 */
export function TasksPage() {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const list = useApi('tasks', api.tasks, settings.refreshMs)

  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const [due, setDue] = useState('')
  const [repeat, setRepeat] = useState<TaskItem['repeat']>('none')
  const [busy, setBusy] = useState<'new' | number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const tasks = list.data?.tasks ?? []
  const open = tasks.filter((task) => !task.done_at)
  const done = tasks.filter((task) => task.done_at)

  const add = async (e: FormEvent) => {
    e.preventDefault()
    const trimmed = title.trim()
    if (!trimmed || busy !== null) return
    setBusy('new')
    setError(null)
    try {
      await createTask({
        title: trimmed,
        notes: notes.trim() || null,
        due_at: due ? new Date(due).toISOString() : null,
        repeat,
      })
      setTitle('')
      setNotes('')
      setDue('')
      setRepeat('none')
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  const toggle = async (task: TaskItem) => {
    if (busy !== null) return
    setBusy(task.id)
    setError(null)
    try {
      await updateTask(task.id, { done: !task.done_at })
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  const remove = async (task: TaskItem) => {
    if (busy !== null) return
    setBusy(task.id)
    setError(null)
    try {
      await deleteTask(task.id)
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  const renderItem = (task: TaskItem) => {
    const overdue = !task.done_at && task.due_at && new Date(task.due_at).getTime() < Date.now()
    return (
      <li
        key={task.id}
        className="border-line bg-surface edge flex flex-col gap-1.5 rounded-xl border p-4"
      >
        <div className="flex items-start gap-3">
          <button
            type="button"
            onClick={() => void toggle(task)}
            disabled={busy !== null}
            aria-label={t(task.done_at ? 'tasks.reopen' : 'tasks.done')}
            className={cn(
              'focus-visible:ring-accent mt-0.5 cursor-pointer rounded-full outline-none focus-visible:ring-2 disabled:opacity-50',
              task.done_at ? 'text-status-ok' : 'text-ink-faint hover:text-accent',
            )}
          >
            {task.done_at ? <CheckCircleIcon size={19} weight="fill" /> : <CircleIcon size={19} />}
          </button>

          <div className="min-w-0 flex-1">
            <p
              className={cn(
                'text-ink break-words text-sm font-medium',
                task.done_at && 'line-through opacity-60',
              )}
            >
              {task.title}
            </p>
            {task.notes && (
              <p className="text-ink-muted mt-0.5 text-xs break-words">{task.notes}</p>
            )}
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {task.due_at && (
                <span
                  className={cn(
                    'rounded-full px-2 py-0.5 text-[0.625rem] tabular',
                    overdue ? 'bg-status-fail/10 text-status-fail' : 'border-line text-ink-faint border',
                  )}
                >
                  {new Date(task.due_at).toLocaleString(locale, {
                    dateStyle: 'short',
                    timeStyle: 'short',
                    hour12: settings.timeFormat === '12h',
                  })}
                </span>
              )}
              {task.repeat !== 'none' && (
                <span className="border-line text-ink-faint rounded-full border px-2 py-0.5 text-[0.625rem]">
                  {t(`tasks.repeat.${task.repeat}`)}
                </span>
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={() => void remove(task)}
            disabled={busy !== null}
            aria-label={t('tasks.delete')}
            className="text-ink-faint hover:text-status-fail focus-visible:ring-accent cursor-pointer rounded p-1 transition-colors outline-none focus-visible:ring-2 disabled:opacity-50"
          >
            <TrashIcon size={15} />
          </button>
        </div>
      </li>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-8"
    >
      <p className="text-ink-faint max-w-[65ch] text-sm">{t('tasks.intro')}</p>

      {error && <p className="text-status-fail text-xs break-all">{error}</p>}

      <form
        onSubmit={add}
        className="border-line bg-surface edge flex flex-col gap-3 rounded-xl border p-4 md:flex-row md:items-end"
      >
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <label htmlFor="task-title" className="text-ink-faint text-[0.6875rem] font-medium uppercase tracking-wide">
            {t('tasks.label')}
          </label>
          <input
            id="task-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('tasks.placeholder')}
            className="border-line text-ink bg-canvas w-full rounded-md border px-3 py-2 text-sm outline-none focus:border-accent"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="task-due" className="text-ink-faint text-[0.6875rem] font-medium uppercase tracking-wide">
            {t('tasks.due')}
          </label>
          <input
            id="task-due"
            type="datetime-local"
            value={due}
            onChange={(e) => setDue(e.target.value)}
            className="border-line text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none focus:border-accent"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="task-repeat" className="text-ink-faint text-[0.6875rem] font-medium uppercase tracking-wide">
            {t('tasks.repeatLabel')}
          </label>
          <select
            id="task-repeat"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value as TaskItem['repeat'])}
            className="border-line text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none focus:border-accent"
          >
            {REPEATS.map((r) => (
              <option key={r} value={r}>
                {t(`tasks.repeat.${r}`)}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={busy !== null || title.trim() === ''}
          className={cn(
            'bg-accent focus-visible:ring-accent flex cursor-pointer items-center gap-2 rounded-md px-4 py-2 text-sm text-white transition-transform outline-none active:translate-y-px focus-visible:ring-2 disabled:opacity-50',
            busy === 'new' && 'cursor-not-allowed',
          )}
        >
          <PlusIcon size={15} weight="bold" />
          {t('tasks.add')}
        </button>
      </form>

      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      {list.loading && !list.data && <Skeleton className="h-64" />}
      {list.data && tasks.length === 0 && <EmptyState body={t('tasks.empty')} />}

      {open.length > 0 && (
        <ul className="flex flex-col gap-3">
          {open.map(renderItem)}
        </ul>
      )}

      {done.length > 0 && (
        <section className="flex flex-col gap-2">
          <p className="text-ink-faint px-1 text-[0.6875rem] font-medium tracking-wide uppercase">
            {t('tasks.doneSection', { n: done.length })}
          </p>
          <ul className="flex flex-col gap-2 opacity-75">
            {done.map(renderItem)}
          </ul>
        </section>
      )}
    </motion.div>
  )
}
