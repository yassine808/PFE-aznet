/**
 * Line diff between two versions of a report.
 *
 * Hand-written rather than a dependency: the whole algorithm is one LCS table
 * and a walk back through it, the inputs are a manager's paragraphs (tens of
 * lines, not a source tree), and a diff library would arrive with a renderer
 * and a theme we would then have to fight.
 */

export type DiffKind = 'same' | 'added' | 'removed'

export interface DiffLine {
  kind: DiffKind
  text: string
  /** 1-based line number in the current draft. Null for a removed line. */
  line: number | null
}

/**
 * Longest common subsequence of two line arrays, as a table of lengths.
 *
 * O(n·m) in time and memory. That is the honest ceiling here: a report is
 * prose, so n and m are in the dozens and the table is a few thousand numbers.
 * ponytail: swap for Myers' diff only if this is ever pointed at whole files.
 */
function lcsTable(a: string[], b: string[]): number[][] {
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  )
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1])
    }
  }
  return table
}

/**
 * What changed going from `before` to `after`.
 *
 * A changed line shows as a removal followed by an addition, which is what a
 * line-based diff can honestly claim: "these two lines are a rewrite of each
 * other" is a guess, and a wrong guess in a diff is worse than two plain facts.
 */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split('\n')
  const b = after.split('\n')
  const table = lcsTable(a, b)
  const out: DiffLine[] = []

  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ kind: 'same', text: b[j], line: j + 1 })
      i += 1
      j += 1
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      out.push({ kind: 'removed', text: a[i], line: null })
      i += 1
    } else {
      out.push({ kind: 'added', text: b[j], line: j + 1 })
      j += 1
    }
  }
  while (i < a.length) {
    out.push({ kind: 'removed', text: a[i], line: null })
    i += 1
  }
  while (j < b.length) {
    out.push({ kind: 'added', text: b[j], line: j + 1 })
    j += 1
  }
  return out
}

/** How many lines came and went — the headline over the diff. */
export function diffCounts(lines: DiffLine[]): { added: number; removed: number } {
  return {
    added: lines.filter((l) => l.kind === 'added').length,
    removed: lines.filter((l) => l.kind === 'removed').length,
  }
}
