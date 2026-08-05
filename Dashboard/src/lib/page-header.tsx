import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

/**
 * Lets a page hang its primary action off the page title.
 *
 * The `<h1>` lives in `App.tsx` — one header for every route, so the title
 * cannot drift page to page — while the action that belongs beside it (Generate
 * on Daily and Weekly) depends on that page's own state: whether a request is
 * in flight, whether the chosen day has any rows at all. Duplicating the title
 * inside the page to get them on one line gave two headings, one under the
 * other, saying the same words.
 *
 * So the page publishes a node and the header renders it. Not a portal: a
 * portal needs its target mounted first, and the header and the lazily-loaded
 * page do not have a guaranteed order.
 */
const Ctx = createContext<{
  action: ReactNode
  setAction: (node: ReactNode) => void
}>({ action: null, setAction: () => {} })

export function PageHeaderProvider({ children }: { readonly children: ReactNode }) {
  const [action, setAction] = useState<ReactNode>(null)
  const value = useMemo(() => ({ action, setAction }), [action])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

/** Read by `App.tsx` only, to render whatever the current page published. */
export function usePageAction() {
  return useContext(Ctx).action
}

/**
 * Publish this page's header action.
 *
 * `deps` is the page's own list — the node is rebuilt on every render, so
 * comparing it would re-set state forever. Unmounting clears the slot, which
 * is what stops a stale Generate button from surviving a navigation.
 */
export function useHeaderAction(node: ReactNode, deps: unknown[]) {
  const { setAction } = useContext(Ctx)
  useEffect(() => {
    setAction(node)
    return () => setAction(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
