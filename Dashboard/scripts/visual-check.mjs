// Visual + smoke check for the dashboard. Logs in against the running stack
// (compose nginx on 127.0.0.1:8080), walks every page, captures a full-page
// screenshot and reports console errors + failed API requests per route.
// Interaction probes: inbox rail switching + reply composer presence, and the
// reports generated/messages tab switch. No writes are ever performed.
//
// Usage (from Dashboard/):
//   node scripts/visual-check.mjs            # fr locale
//   LOCALE=ar node scripts/visual-check.mjs  # RTL pass
//
// Reads ADMIN_EMAIL / ADMIN_PASSWORD from the repo-root .env (the seeded
// director account). Screenshots go to $TMP/dashboard-shots/.
import { chromium } from 'playwright'
import { mkdirSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const BASE = process.env.DASHBOARD_URL ?? 'http://127.0.0.1:8080'
const SHOTS = join(tmpdir(), 'dashboard-shots')
mkdirSync(SHOTS, { recursive: true })

function readEnv(path) {
  const out = {}
  // Split on \r?\n, not '\n'. This file is edited on Windows, so the lines are
  // CRLF — and in JS `.` does not match `\r` (it is a line terminator), so a
  // trailing `\r` left on the line makes `(.*)$` fail on every line but the
  // last. The old pattern ended `\s*$`, which absorbed the `\r` by accident;
  // dropping that `\s*` for the super-linear-backtracking fix silently took the
  // CRLF handling with it and this parser found 1 key out of 25.
  for (const line of readFileSync(path, 'utf-8').split(/\r?\n/)) {
    // Still no trailing `\s*` before `$`: paired with `.*` it backtracks
    // super-linearly on long lines. Trim the value instead.
    const m = line.match(/^\s*([A-Z_]+)\s*=(.*)$/)
    if (m) out[m[1]] = m[2].trim()
  }
  return out
}

const env = readEnv(join(ROOT, '.env'))
const EMAIL = env.ADMIN_EMAIL
const PASSWORD = env.ADMIN_PASSWORD
if (!EMAIL || !PASSWORD) {
  console.error('ADMIN_EMAIL / ADMIN_PASSWORD missing from .env')
  process.exit(1)
}

const ROUTES = ['overview', 'inbox', 'reports', 'daily', 'weekly', 'automation', 'equipe', 'logs', 'queue']
const LOCALE = process.env.LOCALE ?? 'fr'
const PROBLEMS = []

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.addInitScript((locale) => {
  localStorage.setItem('aznet.locale', locale)
}, LOCALE)

page.on('console', (msg) => {
  if (msg.type() === 'error') PROBLEMS.push(`console: ${msg.text().slice(0, 300)}`)
})
page.on('pageerror', (err) => PROBLEMS.push(`pageerror: ${String(err).slice(0, 300)}`))
page.on('response', (res) => {
  const url = res.url()
  if (url.startsWith(BASE) && res.status() >= 400) {
    PROBLEMS.push(`http ${res.status()}: ${url.replace(BASE, '')}`)
  }
})

await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
await page.fill('input[type="email"]', EMAIL)
await page.fill('input[type="password"]', PASSWORD)
await page.click('button[type="submit"]')
await page.waitForSelector('nav', { timeout: 15000 })
console.log('login ok')

let failed = 0
for (const route of ROUTES) {
  await page.evaluate((r) => { window.location.hash = `#/${r}` }, route)
  await page.waitForTimeout(3500)
  const title = await page.title()
  if (!title.includes('—') || title === 'aznet — Rapports de chantier') {
    PROBLEMS.push(`${route}: tab title not per-route ("${title}")`)
  }
  const shot = join(SHOTS, `${LOCALE}-${route}.png`)
  await page.screenshot({ path: shot, fullPage: true })
  console.log(`${route} -> ${shot}`)
  const issues = await page.evaluate(() => {
    const out = []
    const vw = document.documentElement.clientWidth
    const sw = document.documentElement.scrollWidth
    if (sw > vw + 2) out.push(`horizontal overflow: ${sw}px wide viewport vs ${vw}px scrollWidth`)
    for (const img of document.querySelectorAll('img')) {
      if (!img.complete || img.naturalWidth === 0) out.push(`broken image: ${img.src.slice(0, 120)}`)
    }
    if (document.body.innerText.trim().length < 20) out.push('page appears blank')
    // Content wider than the viewport is only a bug when the *page* has to
    // scroll for it. A table, an org chart or a code block inside its own
    // `overflow-x: auto` box is the house rule, not a violation — and reporting
    // those made the equipe org chart emit six warnings a run until nobody read
    // the output any more.
    const scrolls = (el) => {
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX
        if (ox === 'auto' || ox === 'scroll') return true
      }
      return false
    }
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect()
      if (
        r.width > 0 &&
        r.right > vw + 4 &&
        el.children.length === 0 &&
        !el.closest('dialog, [role="dialog"]') &&
        !scrolls(el)
      ) {
        const cls = String(el.className).slice(0, 60)
        out.push(`element past right edge: <${el.tagName.toLowerCase()}> ${cls} right=${Math.round(r.right)}`)
      }
    }
    return out
  })
  for (const issue of issues) console.log(`  [${route}] ${issue}`)

  if (route === 'inbox') {
    const rail = page.locator('aside button[aria-pressed]')
    if ((await rail.count()) === 0) {
      console.log('  [inbox] no conversations to probe (empty data)')
    } else {
      const inactive = page.locator('aside button[aria-pressed="false"]').first()
      if (await inactive.count()) {
        const target = (await inactive.innerText()).split('\n')[0].trim()
        await inactive.click()
        await page.waitForTimeout(1200)
        const header = (await page.locator('section h2').first().innerText()).trim()
        if (header !== target) {
          PROBLEMS.push(`inbox: rail switch did not open "${target}" (header is "${header}")`)
        }
      }
      if (!(await page.locator('section textarea').count())) {
        PROBLEMS.push('inbox: reply composer textarea missing')
      }
    }
  }

  // The Reports page lost its second tab when the message ledger moved out, so
  // there is no tab bar left to switch. What has to hold now is that the page
  // resolves to one of its two real states — a list of stored reports, or the
  // empty state — rather than to nothing at all, which is what an unstored
  // report looked like from here.
  if (route === 'reports') {
    const rendered = await page.locator('main button[aria-expanded], main p').count()
    if (rendered === 0) PROBLEMS.push('reports: neither generated rows nor an empty state rendered')
  }

  const blocked = PROBLEMS.length
  await page.waitForTimeout(1500)
  if (PROBLEMS.length > blocked) failed++
}

/*
 * The rail's bell sits near the bottom of a full-height sticky column, so a
 * panel anchored to `top-full` opened *below the fold*: present in the DOM,
 * correct in every other way, and impossible to read. Nothing above catches
 * that — the page does not overflow, no request fails, no element crosses the
 * right edge — so it is checked on its own terms: open it, and require the
 * panel to be inside the viewport it was drawn in.
 */
{
  const bell = page.locator('nav button[aria-controls="bell-panel"]').last()
  await bell.click()
  const panel = page.locator('#bell-panel')
  await panel.waitFor({ state: 'visible', timeout: 5000 })
  // Playwright calls an element visible the moment it has a box, which for a
  // fading popover is somewhere around opacity 0.3 — the screenshot then shows
  // the rail straight through the panel and reads as a rendering bug that is
  // really a capture bug. Let the 120ms entrance finish first.
  await page.waitForTimeout(400)
  const box = await panel.boundingBox()
  const { width: vw, height: vh } = page.viewportSize()
  // Both axes. Checking only the vertical one is how a panel that had stopped
  // falling off the bottom went on hanging 80px off the left edge, with the
  // check reporting clean: the rail's bell is cornered on two sides, so a
  // half-check passes a half-fix.
  if (!box) {
    PROBLEMS.push('bell: panel has no box after opening')
  } else if (box.y < -2 || box.y + box.height > vh + 2 || box.x < -2 || box.x + box.width > vw + 2) {
    PROBLEMS.push(
      `bell: panel outside the viewport (x ${Math.round(box.x)}→${Math.round(box.x + box.width)} of ${vw}, ` +
        `y ${Math.round(box.y)}→${Math.round(box.y + box.height)} of ${vh})`,
    )
  }
  await page.screenshot({ path: join(SHOTS, `${LOCALE}-bell.png`) })
  console.log(`bell -> ${join(SHOTS, `${LOCALE}-bell.png`)}`)
  await page.keyboard.press('Escape')
}

await browser.close()
console.log('---')
for (const p of PROBLEMS) console.log(p)
if (PROBLEMS.length) {
  console.error(`${PROBLEMS.length} problem(s) found`)
  process.exit(2)
}
console.log('clean')
