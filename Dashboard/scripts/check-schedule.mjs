// Self-check for src/lib/schedule.ts — the only logic on the report pages that
// can be wrong without looking wrong (a next-run line is plausible whatever it
// says). Node 24 strips the types itself, so there is no test framework here.
//
//   node scripts/check-schedule.mjs
import assert from 'node:assert/strict'
import { nextDailyRun, nextWeeklyRun, relativeParts } from '../src/lib/schedule.ts'

const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`

// 2026-08-05 is a Wednesday.
const wedMorning = new Date(2026, 7, 5, 9, 0)
assert.equal(iso(nextDailyRun('18:30', wedMorning)), '2026-08-05 18:30', 'same day, hour not passed')

const wedEvening = new Date(2026, 7, 5, 19, 0)
assert.equal(iso(nextDailyRun('18:30', wedEvening)), '2026-08-06 18:30', 'hour passed → tomorrow')

// Saturday evening rolls over Sunday, which the scheduler skips.
const satEvening = new Date(2026, 7, 8, 19, 0)
assert.equal(iso(nextDailyRun('18:30', satEvening)), '2026-08-10 18:30', 'Sunday is skipped')

// Sunday itself must not answer "today".
const sunday = new Date(2026, 7, 9, 9, 0)
assert.equal(iso(nextDailyRun('18:30', sunday)), '2026-08-10 18:30', 'no report on Sunday')

// Garbage and missing values fall back to the scheduler's own defaults.
assert.equal(iso(nextDailyRun(undefined, wedMorning)), '2026-08-05 18:30', 'default 18:30')
assert.equal(iso(nextDailyRun('99:99', wedMorning)), '2026-08-05 18:30', 'invalid → default')

// weekly_day is Python's numbering: 0 = Monday, so 4 = Friday.
assert.equal(iso(nextWeeklyRun(4, '17:00', wedMorning)), '2026-08-07 17:00', 'Friday 17:00')
assert.equal(iso(nextWeeklyRun(0, '17:00', wedMorning)), '2026-08-10 17:00', 'next Monday')
assert.equal(iso(nextWeeklyRun(undefined, undefined, wedMorning)), '2026-08-07 17:00', 'defaults')
// Today, but the hour has passed → next week, not in a few minutes.
const friEvening = new Date(2026, 7, 7, 18, 0)
assert.equal(iso(nextWeeklyRun(4, '17:00', friEvening)), '2026-08-14 17:00', 'this week already sent')

assert.deepEqual(relativeParts(new Date(2026, 7, 5, 9, 30), wedMorning), [30, 'minute'])
assert.deepEqual(relativeParts(new Date(2026, 7, 5, 18, 30), wedMorning), [10, 'hour'])
assert.deepEqual(relativeParts(new Date(2026, 7, 8, 9, 0), wedMorning), [3, 'day'])

console.log('schedule: ok')
