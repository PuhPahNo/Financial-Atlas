# PRD: Mobile-Responsive Design (all pages/views)

Status: implemented

## Problem

The app is desktop-first. On phones (~360–430px): the Paper Trading 240px sidebar breaks
layout; inline `repeat(3/4,1fr)` stat grids and 2-column forms don't collapse (and being
inline, CSS media queries can't override them without `!important`); the top nav and the
7-tab company sub-nav overflow; hero/title fonts are oversized; wide tables need scroll.

## Solution

Mobile-first responsive pass across the shell and every view, using the smallest-blast-radius
technique per case:
- **Tailwind responsive prefixes** for class-based layout (shell padding, fonts, nav).
- **Mobile-only override classes with `!important`** (in `globals.css`) added to the inline-
  styled Paper Trading elements — a stylesheet `!important` rule beats a non-important inline
  style, so we collapse inline grids/sidebar without rewriting components.
- **Horizontal-scroll strips** (`overflow-x-auto` + `no-scrollbar`) for nav rows and wide
  tables, so nothing is clipped.

## Implementation Decisions

- `globals.css`: add `.no-scrollbar`; mobile breakpoints —
  `@media (max-width:680px){ .m-grid-2{grid-template-columns:repeat(2,1fr)!important} .m-grid-1{grid-template-columns:1fr!important} }`
  and `@media (max-width:760px){ .m-stack{grid-template-columns:1fr!important}; .pt-shell{grid-template-columns:1fr!important}; .pt-aside{→ horizontal scroll strip}; .pt-desk{display:none} }`.
- `AppShell` / `NavBar` / company `layout.tsx`: reduce padding on mobile (`px-4 sm:px-7`),
  compact + horizontally-scrollable nav and sub-nav tabs.
- Paper Trading `page.tsx`: add `pt-shell`/`pt-aside`/`pt-navlist`/`pt-desk` classes (keep
  desktop inline styles); h1 `fontSize` → `clamp(26px,5.5vw,38px)`.
- Inline grids: add `m-grid-2` to `repeat(4,1fr)`/`repeat(3,1fr)` tile grids
  (ModelDetail, TraderDetail, Builder), `m-stack` to two-column form/preview layouts
  (Builder, RuleBuilder, BacktestLab), `m-grid-1` to `1fr 1fr` form grids (RuleBuilder,
  TraderForm).
- Fonts: hero/title sizes scaled (`text-3xl sm:text-5xl`, `text-2xl sm:text-4xl`, etc.).
- Tables: ensure each wide table sits in an `overflow-x-auto` wrapper.

## Testing / QA

- `npm run build` passes.
- Mobile-width (~390px) preview of the shell/nav/paper-trading collapse where feasible
  (data is network-gated in the sandbox; layout still validates).
- No horizontal page overflow; nav/tabs scroll; grids stack; fonts fit.

## Out of Scope

- Per-table column hiding/stacking (kept as horizontal scroll for now).
- A dedicated mobile bottom-tab bar (compact scrollable nav used instead).
