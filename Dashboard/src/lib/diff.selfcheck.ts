/**
 * ponytail: one runnable check for the diff, no framework.
 * Run with `npx tsx src/lib/diff.selfcheck.ts` (or import it once from a page while
 * debugging). It throws on the first wrong answer.
 */
import { diffCounts, diffLines } from './diff'

function eq(actual: unknown, expected: unknown, what: string) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a !== e) throw new Error(`${what}\n  expected ${e}\n  got      ${a}`)
}

// Identical text has no changes at all.
eq(diffCounts(diffLines('a\nb', 'a\nb')), { added: 0, removed: 0 }, 'no change')

// An inserted line is one addition, and the untouched lines keep their numbers.
const inserted = diffLines('a\nc', 'a\nb\nc')
eq(diffCounts(inserted), { added: 1, removed: 0 }, 'one insertion')
eq(
  inserted.map((l) => [l.kind, l.line]),
  [
    ['same', 1],
    ['added', 2],
    ['same', 3],
  ],
  'insertion keeps later line numbers in the new document',
)

// A rewritten line is a removal plus an addition, never a silent "modified".
eq(diffCounts(diffLines('a\nold\nc', 'a\nnew\nc')), { added: 1, removed: 1 }, 'rewrite')

// Deleting everything removes every line and adds the one empty line left.
eq(diffCounts(diffLines('a\nb\nc', '')), { added: 1, removed: 3 }, 'cleared document')

// Removed lines carry no line number: they do not exist in the current draft.
if (diffLines('a\nb', 'a').some((l) => l.kind === 'removed' && l.line !== null)) {
  throw new Error('a removed line must not claim a line number in the new document')
}

console.log('diff: all checks passed')
