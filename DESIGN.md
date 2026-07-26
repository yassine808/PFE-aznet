<!-- SEED: re-run $impeccable document once there's code to capture the actual tokens and components. -->
---
name: aznet Dashboard
description: Daily operations surface for Darija voice-note field reports and the pipeline that processes them.
---

# Design System: aznet Dashboard

## 1. Overview

**Creative North Star: "The Instrument Panel"**

An instrument panel is read, not admired. It is calm because nothing on it is decorative, and it is trusted because every reading is honest, including the bad ones. That is the whole posture of this dashboard: a manager glances at it each morning, learns what the field did and whether the machine held, and closes it. Nothing asks for attention that has not earned it.

The system is built from tinted neutrals and a single accent held under ten percent of any screen. Density is comfortable rather than compressed: the manager reads French prose summaries, not just numbers, so rows breathe. Depth comes from tonal steps and hairline rules, not from shadows. Both light and dark themes are first-class, and Arabic RTL is a native direction, not a mirrored afterthought.

Motion is the one place this system is not quiet. Live surfaces carry perpetual micro-motion: the pipeline status breathes, running stages pulse, the activity stream scrolls, freshly arrived rows settle into place with spring physics. This is deliberate; a dashboard whose job is to answer "is it still running?" should look alive when it is and still when it is not. All motion uses spring physics (`stiffness: 100, damping: 20`), never linear easing, and animates only `transform` and `opacity`. Every perpetual animation is isolated in its own memoized client component so it never re-renders the layout around it. `prefers-reduced-motion: reduce` disables all of it, and no state is ever conveyed by motion alone.

This system explicitly rejects the **generic AI/SaaS dashboard** (gradient hero metric blocks, endless identical rounded card grids, violet-to-blue gradient accents, emoji icons) and the **enterprise ERP admin panel** (grey chrome, stacked toolbars, hairline-dense legacy tables). Both are named anti-references in PRODUCT.md and both are prohibited here by name.

**Key Characteristics:**
- Tinted cool-slate neutrals; one accent, rationed
- Comfortable data density, prose-readable rows
- Flat by default; tonal layering instead of shadows
- Mono numerics, tabular and column-aligned
- Perpetual micro-motion on live surfaces, spring physics, isolated and memoized
- Light and dark are equals; RTL is native

## 2. Colors

Cool slate neutrals carrying the entire surface, with one deep blue-violet accent used sparingly and one strictly semantic status band.

### Primary
- **Desaturated Electric Blue** `[exact value to be resolved during implementation, OKLCH canonical]`: The single accent. Appears on focus rings, the active navigation item, links, and the primary action. Nowhere else. Saturation stays under 80% so it reads as considered rather than neon, and it is never applied as a gradient or an outer glow.

  The accent is anchored to the existing aznet brand mark (`assets/AZ-bot.png`), a circular blue badge whose hue sits in the same family. The mark is the only image in the system and appears once, in the navigation header.

  *Decision, 2026-07-26:* the original pick was deep blue-violet. Violet-blue is banned outright as the AI-dashboard signature, so the violet component is dropped and the accent moves to a desaturated electric blue. The cool slate family is unchanged.

### Neutral
- **Slate ramp, cool-tinted** `[to be resolved during implementation]`: Every background, surface, border, divider, and text color derives from one cool-tinted slate ramp. Pure `#000` and `#fff` are forbidden; every neutral carries a trace of the accent hue (chroma 0.005–0.01) so light and dark both feel authored.

### Status band (semantic only, never decorative)
- **Success / Warning / Error / Queued** `[to be resolved during implementation]`: Reserved exclusively for pipeline stage outcomes, extraction confidence, and retry-queue state. Never used for emphasis, category, or decoration. Each is always paired with a label or icon so meaning never rests on hue alone.

### Named Rules
**The Ten Percent Rule.** The accent covers at most ten percent of any screen. Its rarity is what makes an active nav item or a focus ring instantly findable. If two accented elements are visible at once, one of them is wrong.

**The Reserved Band Rule.** Status colors mean pipeline state and nothing else. The moment a status color is used to make something look important, the status vocabulary is dead and a real failure becomes invisible.

**The Earned Slate Rule.** Cool slate plus blue-violet is the single most predictable palette a dashboard can choose. It is only acceptable here if the execution earns it: unusual accent placement, restraint below the ten percent line, and neutrals tinted with visible intent. If a screenshot is indistinguishable from a stock admin template, the palette has failed and must be pushed off the default.

## 3. Typography

**Body Font:** Geist (variable)
**Numeric/Mono Font:** Geist Mono, tabular figures
**Arabic Font:** IBM Plex Sans Arabic, never a Latin font's fallback

Inter is prohibited. Serif faces are prohibited outright in this system: it is a dashboard, not an editorial page.

**Character:** One quiet sans carries all prose in three scripts; a tabular mono carries everything that must line up. The pairing is functional, not expressive: the type is a lens, not a voice.

### Hierarchy
- **Display** `[to be resolved]`: Rare. Section identity only, not a greeting.
- **Headline** `[to be resolved]`: Page and panel titles.
- **Title** `[to be resolved]`: Group headers, table captions.
- **Body** `[to be resolved]`: French résumé text and all reading copy. Capped at 65–75ch.
- **Label** `[to be resolved]`: Column headers, status labels, metadata.
- **Numeric** `[to be resolved]`: Mono, tabular figures. Quantities, timestamps, durations, correlation IDs, log lines.

### Named Rules
**The Aligned Column Rule.** Every number that appears in a column uses tabular figures. Ragged digits in a quantity column are a defect, not a style choice.

**The Script Parity Rule.** Arabic is set in a font chosen for Arabic, at its own optical size and line height. Latin metrics are never imposed on it.

## 4. Elevation

Flat by default. Depth is expressed through tonal steps in the neutral ramp and hairline rules, not through shadows. A surface sitting above another differs by one tonal step and, where a boundary matters, a one-pixel rule. Shadow is permitted only for genuinely floating layers, such as a popover or dropdown, and even then it is soft and low-contrast.

### Named Rules
**The Flat-At-Rest Rule.** Nothing casts a shadow while idle. If a card has a resting shadow, delete it and use a tonal step.

**The Hairline Rule.** Borders are one pixel. A colored border heavier than one pixel used as a side stripe on a card, row, callout, or alert is forbidden outright.

## 5. Components

Omitted. No components exist yet; this section is populated by the next scan-mode run of `$impeccable document`.

## 6. Do's and Don'ts

### Do:
- **Do** derive every neutral from one cool-tinted slate ramp, and tint it toward the accent hue rather than using pure grey.
- **Do** keep the accent under ten percent of any screen.
- **Do** pair every status color with a label or icon, so meaning never rests on hue alone.
- **Do** set all columnar numbers in tabular mono figures.
- **Do** write spacing, borders, and alignment with logical properties so Arabic RTL mirrors correctly without a second layout.
- **Do** design the failure state before the success state: a broken stage, a queued Sheet write, and a low-confidence extraction each get a state that cannot be missed.
- **Do** hold WCAG 2.2 AA contrast in both themes, and honor `prefers-reduced-motion: reduce`.
- **Do** treat light and dark as two authored designs, not one design with inverted values.

### Don't:
- **Don't** build a **generic AI/SaaS dashboard**: no gradient hero metric blocks, no endless identical rounded card grids, no violet-to-blue gradient accent, no emoji icons, no "Welcome back".
- **Don't** build an **enterprise ERP admin panel**: no grey chrome, no stacked toolbars, no legacy hairline-dense table styling.
- **Don't** use crypto/gamer neon, glassmorphism, or consumer-app playfulness such as mascots and illustrations.
- **Don't** apply `background-clip: text` with a gradient. Emphasis comes from weight and size.
- **Don't** use a colored `border-left` or `border-right` heavier than one pixel as an accent stripe.
- **Don't** reach for a modal first. Exhaust inline and progressive alternatives.
- **Don't** use `#000` or `#fff` anywhere.
- **Don't** animate layout properties. Animate `transform` and `opacity` only, with spring physics, never linear easing.
- **Don't** put perpetual motion on a static surface. Motion means the data behind it is live; decorative loops destroy that signal.
- **Don't** use Inter, and don't use a serif anywhere in this system.
- **Don't** use outer glows or neon shadows on the accent.
- **Don't** let a decorative element outweigh a number on screen.
- **Don't** soften a failure into a muted grey pill. A silent failure is the worst outcome this product can produce.
