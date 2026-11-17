---
name: figma-fidelity
description: Implement UI exactly as designed in Figma / Figma Make. Use whenever a task involves building, porting, or modifying a screen, component, or layout that has a Figma design, a Figma Make export, or a reference screenshot. Enforces pixel-faithful implementation via design tokens, component reuse, per-section work, and a screenshot-diff verification loop. Supports RTL (Persian) and LTR (English).
---

# Figma Fidelity Skill

Goal: the coded result must be visually and structurally identical to the Figma / Figma Make design. You are a **translator, not a designer**. Never improvise style. If something is not in the design or the design system, ask or reuse the closest existing pattern.

## 0. Golden rules

1. **Source of truth order:** (1) Figma MCP data for the frame, (2) Figma Make exported code already in the repo, (3) reference screenshot, (4) existing components in the repo. Never your own taste.
2. **Reuse before create.** Search `src/components/ui` and existing pages first. A new component is allowed only if nothing equivalent exists, and it must follow the same patterns.
3. **No hardcoded style values.** No raw hex, arbitrary px, ad-hoc shadows or radii. Use tokens (CSS variables / Tailwind theme). If a needed value has no token, add the token first, then use it.
4. **Work in small pieces.** One section or component at a time. Never "build the whole page" in one pass.
5. **Verify visually after every piece.** A piece is not done until it is compared against the target screenshot.
6. **Do not rewrite what already matches.** Existing Make-exported screens are references and must not be restyled.

## 1. Phase A: Discovery (before writing any UI code)

Do all of these and write a short summary of findings before coding:

1. Read the token files: `globals.css` / `theme.css` / `tailwind.config.*` / fonts setup. List: colors (semantic names), radius scale, shadow scale, spacing scale, type scale, font families per language.
2. List existing UI components (`src/components/ui`, `src/components`) and their variants.
3. Open the closest existing page (e.g. Dashboard) and note the shared patterns: page header, KPI card, table/list row, status badge, sidebar item, button variants, icon library and size, empty/loading states.
4. Fetch the target design via Figma MCP (see section 2). If no Figma link is provided, use the screenshot and the closest existing page.
5. Decide direction: **RTL (Persian) or LTR (English)** for this screen. The design is the same system in both directions, mirrored (see section 5).

## 2. Figma MCP usage

For each target frame / node (ask the user for the link if missing):

1. `get_screenshot` on the frame: this is the visual target.
2. `get_design_context` on the frame: layout, auto-layout direction, spacing, sizes, text styles, and referenced components. Treat its code as a **spec, not a final answer**: adapt it to the repo's components and tokens, never paste it raw.
3. `get_variable_defs`: map Figma variables to the repo's tokens. If Figma variable and repo token differ, report it, do not silently choose.
4. `get_metadata` for the node tree when a frame is large; then fetch children one by one.
5. If the Figma file has Code Connect mappings, use the mapped component instead of generating a new one.
6. Large frames: split by top-level sections (sidebar, header, KPI row, table, panel...) and fetch/implement each separately.

If the design is a Figma Make file and MCP data is thin, use the exported Make code in the repo as the spec.

## 3. Phase B: Implementation loop (per section)

Repeat for each section:

1. **Spec**: write a 5-10 line spec for the section: layout (flex/grid, direction, gap), sizes, tokens used, components reused, states.
2. **Build** using existing components and tokens only.
3. **Run** the app and open the page (use Playwright MCP or the dev server).
4. **Screenshot** the section at the same viewport width as the target.
5. **Compare** with the target on this checklist:
   - Layout & alignment (start/end edges, centering)
   - Spacing (padding, gaps, margins between siblings)
   - Sizes (card height, row height, icon size, avatar size)
   - Typography (family, size, weight, line-height, letter-spacing, color)
   - Colors (background, border, text, status colors)
   - Radius, border width/color, shadows
   - Icons (same icon, same size, same stroke)
   - States (hover, active, selected, disabled, focus)
   - Direction (RTL/LTR correct, mirrored icons where needed)
6. **Fix** every difference. Repeat 3-5 until no visible difference remains. Do not move to the next section before this passes.

## 4. Phase C: Whole-page pass

After all sections:

1. Full-page screenshot vs. full target screenshot.
2. Check responsive behavior at the breakpoints used in the existing pages (at least desktop and one smaller width) and sidebar collapse behavior if present.
3. Check long text, empty data, loading, error, and many-rows scenarios (no layout breakage, truncation with tooltip where the design does it).
4. Run lint, type-check, and build. Fix all errors and warnings you introduced.
5. Confirm no new hardcoded colors/sizes: grep your diff for `#[0-9a-fA-F]{3,8}`, `px-\[`, `w-\[`, `text-\[`, `rgb(`; justify or replace each.

## 5. RTL / LTR rules (Persian + English)

- Use **logical properties**: `ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`, `text-start`, `text-end`, `border-s`, `rounded-s-*`. Avoid `left/right/ml/mr/pl/pr` unless the design is intentionally fixed.
- Set `dir="rtl"` / `dir="ltr"` on the root per language; do not hack with `flex-row-reverse` when `dir` solves it.
- Mirror directional icons (chevrons, arrows, "back/next"); do not mirror logos, play icons, charts' time axis (unless design does), or numeric/phone/code content.
- Fonts: Persian uses the Persian font defined in the tokens (e.g. Vazirmatn), English uses the Latin font (e.g. Inter). Keep line-height adjusted for Persian (taller). Do not use one font for both unless the design does.
- Digits: follow the design (Persian digits in Persian UI if the design shows them). Format numbers/dates through one shared helper; Persian UI dates use the Jalali calendar if the design does.
- Sidebar sits on the **right** in RTL and **left** in LTR; same for drawers, toasts, and dropdown alignment.
- Tables: first column on the start side; numeric columns align per design; scroll shadows/chevrons flip.
- Test both directions for any screen that must support both.

## 6. Anti-patterns (do not do these)

- Redesigning "to look better" or "more modern". Fidelity beats taste.
- Using default shadcn/Tailwind look when the design has its own tokens.
- Inventing new colors, radii, shadows, spacing, icon sets.
- Copying Figma-generated absolute-positioned code literally; rebuild with flex/grid and tokens.
- Inline styles for things that tokens or classes cover.
- Building the page first and checking later.
- Fixing a visual diff by guessing; measure it (computed styles, devtools values, Figma values).
- Marking work done without a screenshot comparison.

## 7. Measuring instead of guessing

When something looks off:

1. Get the exact value from Figma (`get_design_context` / node properties).
2. Get the rendered value (Playwright `evaluate` with `getComputedStyle` / `getBoundingClientRect`).
3. Change the code until the numbers match.

## 8. Components checklist (match these exactly from the design system)

Page header (title, subtitle, actions) · Sidebar (item, active state, badge, collapsed) · Top bar (status pill, bell with badge, refresh) · KPI card (icon chip, value, label, delta, sparkline) · Status badge (colors per status) · Table/list row (job icon, name, sub-label, server chip, progress bar, time columns, row chevron) · Tabs/segmented control · Search input · Filter chips with counts · Buttons (primary, secondary, ghost, icon) · Banner/alert strip · Footer/pagination text · User block · Empty/loading/error states.

## 9. Output expectations for each task

At the end of a task, report briefly:
- Which Figma nodes / screenshots were used as source.
- Which existing components were reused and which (if any) new ones were created and why.
- Any token added or any mismatch between Figma and repo tokens.
- What was verified (screenshots compared, directions tested, build/lint status).
- Remaining known differences, if any, with the reason.

## 10. When uncertain

- Missing Figma link or unclear frame: ask for it. Do not guess the design.
- Design conflicts with an existing component: prefer the design, extend the component through a variant rather than duplicating.
- Behavior not specified in the design (hover, loading, errors): copy the pattern from the closest existing screen.
