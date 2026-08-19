import { Component, type ErrorInfo, type ReactNode } from 'react'
import { ArrowClockwiseIcon, WarningIcon } from '@phosphor-icons/react'

/**
 * The one thing that keeps a bad cell from taking the whole dashboard down.
 *
 * React unmounts the entire tree when a render throws and nothing catches it,
 * so before this existed a single `TypeError` inside one table cell replaced
 * the app with a blank white page — no message, no route, no way back except
 * a reload. That is exactly what happened on Chantiers: the API sent
 * `qte_marche` as a string, `.toFixed()` threw, and opening a site "made the
 * page disappear". The string is fixed at the source (`logs._iso`), but the
 * blanking was its own defect and would have come back on the next one.
 *
 * Deliberately a class: `getDerivedStateFromError` has no hook equivalent —
 * this is the only thing React still requires a class for.
 *
 * Keyed by the caller on the route, so navigating away clears the error
 * instead of leaving the boundary latched on a page the user has left.
 */
export class ErrorBoundary extends Component<
  { readonly children: ReactNode; readonly labels: { title: string; body: string; retry: string } },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept: the stack is the only record of what actually threw, and a
    // boundary that swallows it silently trades a blank page for a mystery.
    console.error('[dashboard] render error', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    const { title, body, retry } = this.props.labels
    return (
      <div className="border-status-fail/30 bg-status-fail/5 flex flex-col items-start gap-3 rounded-lg border p-6">
        <p className="text-status-fail flex items-center gap-2 text-sm font-medium">
          <WarningIcon size={16} weight="fill" />
          {title}
        </p>
        <p className="text-ink-muted max-w-[65ch] text-xs leading-relaxed">{body}</p>
        <p className="text-ink-faint tabular max-w-[65ch] text-[0.6875rem] break-all">
          {error.message}
        </p>
        <button
          type="button"
          onClick={() => this.setState({ error: null })}
          className="border-line text-ink hover:bg-surface-raised inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px"
        >
          <ArrowClockwiseIcon size={13} />
          {retry}
        </button>
      </div>
    )
  }
}
