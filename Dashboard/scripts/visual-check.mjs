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
  for (const line of readFileSync(path, 'utf-8').split('\n')) {
    // No trailing `\s*` before `$`: paired with `.*` it makes the match
    // super-linear on long lines. Trim the value instead.
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
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect()
      if (r.width > 0 && r.right > vw + 4 && el.children.length === 0 && !el.closest('dialog, [role="dialog"]')) {
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

  if (route === 'reports') {
    const tabs = page.locator('main fieldset:has(legend) button[aria-pressed]')
    if ((await tabs.count()) === 2) {
      await tabs.nth(1).click()
      await page.waitForTimeout(1200)
      const second = await tabs.nth(1).getAttribute('aria-pressed')
      const first = await tabs.nth(0).getAttribute('aria-pressed')
      if (second !== 'true' || first !== 'false') {
        PROBLEMS.push(`reports: tab switch broken (generated=${first}, messages=${second})`)
      }
    } else {
      console.log(`  [reports] unexpected tab bar: ${await tabs.count()} buttons`)
    }
  }

  const blocked = PROBLEMS.length
  await page.waitForTimeout(1500)
  if (PROBLEMS.length > blocked) failed++
}

await browser.close()
console.log('---')
for (const p of PROBLEMS) console.log(p)
if (PROBLEMS.length) {
  console.error(`${PROBLEMS.length} problem(s) found`)
  process.exit(2)
}
console.log('clean')
