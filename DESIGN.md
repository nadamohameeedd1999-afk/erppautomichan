# DESIGN.md — NQ (الجودة الوطنية لتقنية المعلومات)

The one design system for every NQ screen: this dashboard, NQ Simulation, reports, and new NQ ERP pages.
Read it before building any screen. A value not listed here comes from the nearest token, never a new colour.

## 1. Identity

- One accent: **teal `#0F7C7A`**. Everything else is neutral. No violet, no rainbow gradients, no gradient text.
- Arabic first, RTL. Every layout also works LTR (logical properties: `margin-inline-start`, `inset-inline-end`).
- The screen says what needs the user now first; history and statistics come after.

## 2. Colour tokens

| Token | Light (`data-ui="teal"`) | Dark (`data-ui="nq-dark"`) | Use |
|---|---|---|---|
| `--g-acc` | `#0F7C7A` | `#2BB3AF` | primary button, active nav, links, focus |
| `--g-head` | `#0A5654` | `#F2F7F7` | headings, important values |
| `--g-text` | `#1C2B2A` | `#D9E5E4` | body text |
| `--g-muted` | `#6B7B7A` | `#8FA3A2` | labels, hints, time |
| `--g-bg` | `#F4F8F8` | `#0B1312` | page |
| `--g-panel` | `#FFFFFF` | `#121D1C` | cards |
| `--g-hover` / soft fill | `#E7F3F2` | `#17302E` | row hover, chips, filter strip |
| `--g-line` | `#D5E2E1` | `#223634` | borders, row separators |
| `--g-ok` | `#0F7C7A` | `#3CC9A0` | passed |
| `--g-bad` | `#C0392B` | `#F0706A` | failed, needs action |
| `--g-warn` | `#B7791F` | `#E8B04B` | slow, flaky, needs a look |

Status colours carry meaning only: a number is red because it is bad (a pass rate under 50%), never for decoration.
Text on any fill keeps WCAG AA contrast (4.5:1 body, 3:1 large numbers).

## 3. Type

- Screens: `Tahoma, "Segoe UI", system-ui, sans-serif`. Printed reports (DevExpress): **Microsoft Sans Serif**, bold for titles and headers.
- Scale (px): 12 label · 13 table · 14 body · 16 card title · 20 section · 28 KPI value · 32 page number on a report cover. Nothing else.
- Weights: 400 body, 700 titles and values. No 800/900 except the report title.
- Numbers: `font-variant-numeric: tabular-nums` in tables, KPIs and timers. Amounts `0,000.00`. Empty value: `—`.
- Headings: `text-wrap: balance`. Ellipsis character `…`, never `...`.

## 4. Space, radius, depth

- 4px grid: 4 · 8 · 12 · 16 · 24 · 32. Card padding 16 (12 on a phone). Gap between cards 14.
- Radius: 12 cards · 8 buttons and inputs · 999 chips. One radius scale per screen.
- Depth: one shadow `0 2px 10px rgba(10, 86, 84, .06)` on light; borders only on dark. No glass blur.

## 5. Components

- **Buttons:** primary = solid teal, white text; secondary = teal outline; danger = solid `--g-bad` only for destructive or "fix now" actions. One primary per screen area. Labels are a verb + object («شغّل الفاشلين»), 40px tall (44px on touch).
- **KPI tile:** label (12, muted, icon) → value (28, bold, `--g-head` or a status colour by rule) → one hint line. A sparkline only on desktop. Four tiles in a row on desktop, two per row on a phone.
- **Table:** header row solid `#0F7C7A`, white bold text; rows white with a thin `--g-line` bottom border only (no vertical borders); numbers centred, text right-aligned; row hover `--g-hover`.
- **Chip:** status word + icon, soft fill of its status colour (✓ ناجح · ✕ فاشل · ⏳ شغال).
- **Filter strip (reports):** light-teal rounded box `#E7F3F2`, label grey + value bold.
- **Empty state:** one line that says what to do next and a link to do it («لسه مفيش نتائج — شغّل الاختبار الآلي»). A widget with no data collapses; it never shows a chart of dashes.
- **Report page:** A4 landscape, RTL, 3-zone header (logo + company / title AR + EN / user + print date), thick teal rule, footer «صفحة X من Y».

## 6. Interaction

- Every control has a visible `:focus-visible` ring: `2px solid var(--g-acc)`, offset 2px. Never `outline: none` without a replacement.
- Hover changes colour or border only; nothing jumps more than 2px.
- Transitions list their properties (`background-color, border-color, color, box-shadow, transform`), 150–200ms. Never `transition: all`.
- `prefers-reduced-motion: reduce` stops pulses, sliding bars and counters.
- Icon-only buttons and links carry `aria-label`. Actions are `<button>`, navigation is `<a>`.
- Live updates (a run finished, a toast) sit in an `aria-live="polite"` region.

## 7. Never

- Violet / lavender / neon gradients, gradient-filled text, glass blur.
- Four equal tiles that all shout in different colours.
- A chart or donut full of «—» when there is no data.
- Hard-coded Arabic digits mixed with Latin ones in the same table.
- A floating button that covers content.
