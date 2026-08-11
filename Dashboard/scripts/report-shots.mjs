// Capture the dashboard for the PFE report: English, dark theme, 16:9.
//
// Deliberately NOT `fullPage`. A full-page capture of a long route produces an
// image several times taller than the sidebar, which on an A4 page shrinks to
// the point of being unreadable — the exact complaint that prompted this file.
// Every desktop shot is one 16:9 viewport; where a route has more below the
// fold, a second shot is taken after scrolling instead of stretching the first.
//
// Usage (from Dashboard/, stack running on :8080):
//   node scripts/report-shots.mjs
import { chromium, devices } from 'playwright'
import { mkdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const BASE = process.env.DASHBOARD_URL ?? 'http://127.0.0.1:8080'
const OUT = process.env.SHOTS_DIR ?? join(ROOT, 'Pres+report', 'screens')
mkdirSync(OUT, { recursive: true })

function readEnv(path) {
  const out = {}
  for (const line of readFileSync(path, 'utf-8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z_]+)\s*=(.*)$/)
    if (m) out[m[1]] = m[2].trim()
  }
  return out
}
const env = readEnv(join(ROOT, '.env'))
const { ADMIN_EMAIL: EMAIL, ADMIN_PASSWORD: PASSWORD } = env
if (!EMAIL || !PASSWORD) {
  console.error('ADMIN_EMAIL / ADMIN_PASSWORD missing from .env')
  process.exit(1)
}

const VIEWPORT = { width: 1600, height: 900 } // 16:9
const browser = await chromium.launch()

// Seeded before first paint: toggling after load would be captured mid-animation.
const seed = ([locale, theme]) => {
  localStorage.setItem('aznet.locale', locale)
  localStorage.setItem('aznet.theme', theme)
}

async function login(page, ready = 'nav') {
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[type="email"]', EMAIL)
  await page.fill('input[type="password"]', PASSWORD)
  await page.click('button[type="submit"]')
  // `ready` differs by viewport: the nav rail is `hidden md:flex`, so on a phone
  // it never becomes visible — waiting for it there would time out on a layout
  // that is behaving exactly as designed.
  await page.waitForSelector(ready, { timeout: 20000, state: 'visible' })
  await settle(page)
}

async function settle(page) {
  // Wait on the real condition, not a timer. Skeletons render as `.animate-pulse`
  // (components/states.tsx), so their absence is the app's own signal that data
  // has landed; a fixed delay captured half-loaded pages.
  try {
    await page.waitForFunction(
      () => document.querySelectorAll('.animate-pulse').length === 0,
      null, { timeout: 20000 })
  } catch {
    console.warn('  ! skeletons still present after 20s')
  }
  // Charts and the contribution graph animate in after their data arrives.
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(1200)
}

async function go(page, route) {
  await page.evaluate((r) => { window.location.hash = `#/${r}` }, route)
  await page.waitForTimeout(600)
  await settle(page)
}

const shot = async (page, name) => {
  await page.screenshot({ path: join(OUT, `${name}.png`) })
  console.log('  ->', name)
}

// ── Desktop, English, dark ────────────────────────────────────────────────
{
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 })
  await ctx.addInitScript(seed, ['en', 'dark'])
  const page = await ctx.newPage()
  await login(page)
  console.log('desktop en/dark')

  for (const route of ['overview', 'inbox', 'reports', 'daily', 'weekly',
                       'automation', 'tasks', 'logs', 'queue', 'equipe']) {
    await go(page, route)
    await shot(page, `en-${route}`)
  }

  // Long routes: a second viewport further down beats one giant image.
  for (const route of ['overview', 'equipe']) {
    await go(page, route)
    await page.evaluate(() => window.scrollTo(0, window.innerHeight * 0.85))
    await page.waitForTimeout(900)
    await shot(page, `en-${route}-2`)
  }

  // A route that matches nothing: the app says so instead of silently
  // landing on Overview.
  await go(page, 'this-route-does-not-exist')
  await shot(page, 'en-notfound')

  // Command palette, and specifically its no-match behaviour: the query below
  // matches no command, so the palette falls back to closest-string suggestions.
  await go(page, 'overview')
  await page.keyboard.press('Control+K')
  await page.waitForTimeout(700)
  await shot(page, 'en-palette')
  await page.keyboard.type('rapprt')      // deliberate misspelling
  await page.waitForTimeout(900)
  await shot(page, 'en-palette-fuzzy')
  await page.keyboard.press('Control+A')
  await page.keyboard.type('zzzzqqq')     // matches nothing at all
  await page.waitForTimeout(900)
  await shot(page, 'en-palette-noresult')
  await page.keyboard.press('Escape')

  // Light theme, one shot, to show the theme switch is real.
  await page.evaluate(() => {
    localStorage.setItem('aznet.theme', 'light')
    location.reload()
  })
  await page.waitForTimeout(3500)
  await shot(page, 'en-overview-light')

  await ctx.close()
}

// ── Login screen (no session) ─────────────────────────────────────────────
{
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 })
  await ctx.addInitScript(seed, ['en', 'dark'])
  const page = await ctx.newPage()
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2000)
  await shot(page, 'en-login')
  await ctx.close()
}

// ── Phone ─────────────────────────────────────────────────────────────────
{
  const ctx = await browser.newContext({ ...devices['iPhone 13'] })
  await ctx.addInitScript(seed, ['en', 'dark'])
  const page = await ctx.newPage()
  await login(page, 'main')
  console.log('phone en/dark')
  for (const route of ['overview', 'reports', 'equipe']) {
    await go(page, route)
    await shot(page, `mobile-${route}`)
  }
  await ctx.close()
}

// ── Arabic, to evidence the RTL claim ─────────────────────────────────────
{
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 })
  await ctx.addInitScript(seed, ['ar', 'dark'])
  const page = await ctx.newPage()
  await login(page)
  await go(page, 'overview')
  await shot(page, 'ar-overview')
  await ctx.close()
}

await browser.close()
console.log('done ->', OUT)
