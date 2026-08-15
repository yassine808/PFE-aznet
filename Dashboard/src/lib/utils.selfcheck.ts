/**
 * Runnable check for the phone helpers. Run with:
 *   npx tsx src/lib/utils.selfcheck.ts
 * Kept next to diff.selfcheck.ts rather than in a test runner the dashboard
 * does not have.
 */
import { formatPhone, toMsisdn } from './utils'

const eq = (got: string, want: string, label: string) => {
  if (got !== want) throw new Error(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)
}

for (const raw of ['+212661234567', '0661234567', '661234567', '00212661234567', '+212 (0) 661-234-567', '212661234567'])
  eq(toMsisdn(raw), '212661234567', `toMsisdn(${raw})`)
eq(toMsisdn('0712345678'), '212712345678', 'toMsisdn 07')
eq(toMsisdn('123456789'), '123456789', 'toMsisdn leaves a Telegram id alone')

eq(formatPhone('212661234567'), '06 61 23 45 67', 'formatPhone 06')
eq(formatPhone('212712345678'), '07 12 34 56 78', 'formatPhone 07')
eq(formatPhone('123456789'), '123456789', 'formatPhone leaves a Telegram id alone')
eq(formatPhone(null), '', 'formatPhone null')

console.log('utils.selfcheck: ok')
