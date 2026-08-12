// Render Pres+report/diagrams/*.mmd to PNG for the report and the deck.
//
// mermaid-cli is not installed and pulling it in drags a second Chromium behind
// it; Playwright is already here for report-shots.mjs, so the diagram is
// rendered in the browser we already have. The mermaid library is fetched from
// a CDN by that page — the diagram source never leaves this machine.
//
// By default only sources with no PNG beside them are rendered. The thirteen
// existing figures were produced by an earlier run and re-rendering them with a
// different mermaid version would silently restyle every figure in the report,
// so they are left alone unless named explicitly.
//
// Usage (from Dashboard/):
//   node scripts/render-diagrams.mjs              # only the missing ones
//   node scripts/render-diagrams.mjs 14-devops    # force one, by stem
import { chromium } from 'playwright'
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const DIR = join(ROOT, 'Pres+report', 'diagrams')
const MERMAID = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs'

const only = process.argv.slice(2)
const targets = readdirSync(DIR)
  .filter((f) => f.endsWith('.mmd'))
  .map((f) => f.replace(/\.mmd$/, ''))
  .filter((stem) =>
    only.length ? only.includes(stem) : !existsSync(join(DIR, `${stem}.png`)),
  )

if (!targets.length) {
  console.log('nothing to render (pass a stem to force)')
  process.exit(0)
}

const browser = await chromium.launch()
const ctx = await browser.newContext({
  viewport: { width: 2000, height: 1400 },
  deviceScaleFactor: 3, // print-grade: the report places these at 14.7 cm wide
})
const page = await ctx.newPage()

for (const stem of targets) {
  const src = readFileSync(join(DIR, `${stem}.mmd`), 'utf-8')
  await page.setContent(
    `<!doctype html><meta charset="utf-8">
     <style>body{margin:0;padding:24px;background:#fff;font-family:Arial,sans-serif}</style>
     <div id="d" class="mermaid">${src.replace(/</g, '&lt;')}</div>
     <script type="module">
       import mermaid from '${MERMAID}'
       mermaid.initialize({ startOnLoad: false, theme: 'default', flowchart: { htmlLabels: true, useMaxWidth: false } })
       try { await mermaid.run({ nodes: [document.getElementById('d')] }); window.__ok = true }
       catch (e) { window.__err = String(e) }
     </script>`,
    { waitUntil: 'networkidle' },
  )
  await page.waitForFunction(() => window.__ok || window.__err, { timeout: 30_000 })
  const err = await page.evaluate(() => window.__err)
  if (err) throw new Error(`${stem}: ${err}`)

  const svg = page.locator('#d svg')
  const box = await svg.boundingBox()
  await svg.screenshot({ path: join(DIR, `${stem}.png`) })
  // keep the vector alongside, it costs nothing and survives a rescale
  writeFileSync(join(DIR, `${stem}.svg`), await svg.evaluate((n) => n.outerHTML))
  console.log(`${stem}.png  ${Math.round(box.width)}x${Math.round(box.height)} css px @3x`)
}

await browser.close()
console.log('done ->', DIR)
