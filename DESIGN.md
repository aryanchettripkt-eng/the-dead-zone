---
name: SETU-DRR
description: Hazard Red Zone & Relocation Decision Support Platform
colors:
  primary: "#d4f15d"
  primary-hover: "#c4e14d"
  secondary: "#10b981"
  tertiary: "#38bdf8"
  hazard-red: "#ef4444"
  hazard-orange: "#f97316"
  hazard-amber: "#f59e0b"
  hazard-green: "#10b981"
  neutral-bg: "#101712"
  neutral-surface: "#0b1612"
  neutral-surface-hover: "#10221c"
  neutral-border: "#1f2a38"
  neutral-ink: "#e6edf5"
  neutral-ink-muted: "#9dabbd"
  dock-surface: "#161e19"
  foliage-accent: "#8ee638"
typography:
  display:
    fontFamily: "Space Grotesk, sans-serif"
    fontSize: "clamp(2rem, 5vw, 3.5rem)"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Space Grotesk, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "normal"
  body:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.05em"
rounded:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "28px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  "2xl": "48px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#06100c"
    rounded: "{rounded.full}"
    padding: "10px 20px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "#06100c"
    rounded: "{rounded.full}"
  button-secondary:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.neutral-ink}"
    rounded: "{rounded.md}"
    padding: "9px 14px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.neutral-ink-muted}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  card-glass:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.neutral-ink}"
    rounded: "{rounded.lg}"
    padding: "16px 20px"
  chip-pill:
    backgroundColor: "{colors.neutral-surface-hover}"
    textColor: "{colors.primary}"
    rounded: "{rounded.full}"
    padding: "4px 12px"
---

# Design System: SETU-DRR

## Overview

**Creative North Star: "The Cartographic Resilience Console"**

SETU-DRR is an atmospheric, high-density disaster decision-support and geospatial intelligence environment. Built for mission-critical command rooms and frontline emergency planners, the interface merges geotechnical precision with the atmospheric depth of Western Ghats mountain mist and deep river valleys. The visual tone is authoritative, scientific, and un-sensationalized—eschewing frivolous decoration in favor of high-legibility telemetry, luminous hazard contrasts, and tactile microinteractions.

Surfaces inhabit a dual-mode universe: by default, deep evergreen-tinted carbons (`#101712`) allow neon telemetry accents (`#d4f15d`) and multi-tiered hazard signals to radiate without ocular fatigue during prolonged night deployments. In light mode, the system transforms into a sunlit field console, utilizing crisp sage-tinted neutral papers (`#eaf1e6`) with high-contrast dark forest ink (`#0d1a14`), ensuring total clarity under direct daylight in emergency field vehicles or district collectorate briefings.

The density is calibrated for high information bandwidth: compact monospace coordinates, tabular numerical meters, and dense multi-panel grids sit alongside frosted glass overlays and floating pill navigation docks. Every interaction is alive, driven by responsive GSAP physics that provide immediate, tangible feedback to the user's cursor.

**Key Characteristics:**
- Deep atmospheric forest dark ground coupled with razor-sharp luminous accents.
- Full dual-theme parity (dark operations console / light field clipboard) with zero missing contrast tokens.
- Tactile GSAP microinteractions with spring physics on interactive cards, sliders, and buttons.
- Multi-hazard chromatic hierarchy reserved strictly for physical danger triage.
- High-precision typography pairing geometric display headers with dense monospace telemetry.

## Colors

The palette grounds high-bandwidth geotechnical analytics in an atmospheric forest landscape illuminated by high-voltage neon citron telemetry.

### Primary
- **Neon Citron** (#d4f15d / #d2f83f light): Reserved for primary user actions, active states, and focal telemetry targets. Used sparingly to draw immediate executive attention.
- **Citron Glow Hover** (#c4e14d / #c0e62d light): Shifted state indicating tactile affordance and immediate interactive readiness.

### Secondary
- **Resilience Emerald** (#10b981 / #059669 light): Denotes verified safe carrying capacity, stabilized habitations, and positive relocation feasibility.

### Tertiary
- **Geotechnical Cyan** (#38bdf8 / #0284c7 light): Represents hydrological metrics, InSAR satellite baseline telemetry, and interactive map vector overlays.

### Neutral
- **Forest Midnight Ground** (#101712 / #eaf1e6 light): Foundational application canvas establishing depth and atmospheric context.
- **Console Panel Surface** (#0b1612 / #ffffff light): Slightly lifted container plane providing crisp card and table containment.
- **Hovered Surface** (#10221c / #f1f6ee light): Reactive tonal lift for hovered list items, table rows, and interactive chips.
- **Cartographic Grid Line** (#1f2a38 / #c3d2c8 light): Precision partition lines separating triage queues, map viewports, and risk dossiers.
- **Command Telemetry Ink** (#e6edf5 / #0d1a14 light): Crisp, high-contrast foreground typography for critical readings and titles.
- **Sub-label Muted Ink** (#9dabbd / #3d5449 light): Secondary metadata, timestamps, and coordinate captions.
- **Dock Core Plane** (#161e19 / #384134 light): Anchored dark floating header dock surface maintained consistently across both theme environments.

### Named Rules
**The Telemetry Reserve Rule.** Neon Citron is strictly restricted to ≤8% of viewport pixels. It is never used for cosmetic backgrounds or secondary borders—its rarity guarantees instantaneous focal orientation.

**The Hazard Exclusivity Rule.** Chromatic reds (#ef4444), ambers (#f59e0b), and oranges (#f97316) are strictly forbidden in decorative UI elements or standard brand marks. They are exclusively reserved for verified geotechnical hazard severity levels (Critical, Warning, Caution).

## Typography

**Display Font:** Space Grotesk (with sans-serif fallback)
**Body Font:** Plus Jakarta Sans (with Geist Sans, system-ui fallback)
**Label/Mono Font:** JetBrains Mono (with monospace fallback)

**Character:** Space Grotesk lends a technical, architectural authority to large telemetry numerals and section banners, balanced by the neutral, highly legible rhythm of Plus Jakarta Sans in body text and the uncompromising tabular alignment of JetBrains Mono in coordinate readings.

### Hierarchy
- **Display** (Bold 700, clamp(2rem, 5vw, 3.5rem), 1.1 line-height, -0.03em tracking): High-impact mission titles, district hero headings, and global hazard counters.
- **Headline** (SemiBold 600, 1.75rem / 28px, 1.2 line-height, -0.02em tracking): Panel headers, major triage section dividers, and modal titles.
- **Title** (SemiBold 600, 1.125rem / 18px, 1.3 line-height): Metric card labels, candidate site names, and scenario parameters.
- **Body** (Regular 400, 0.875rem / 14px, 1.5 line-height, max-width 65-75ch): Geotechnical dossiers, evacuation notes, methodology descriptions, and policy briefs.
- **Label** (Medium 500, 0.6875rem / 11px, 1.4 line-height, 0.05em tracking, Uppercase): Coordinates, H3 hex indices, timestamps, triage tier badges, and status pills.

### Named Rules
**The Tabular Telemetry Rule.** Every numeric data point representing physical measurements (rainfall in mm, displacement in mm/yr, population counts, triage ranks) must render using tabular numbers (`tabular-nums`) in JetBrains Mono to preserve vertical column alignment during live updates.

## Layout

The spatial framework relies on a rigid 4px/8px baseline grid designed for high-density multi-panel situational awareness.

The flagship desktop command center operates across a fixed-height, zero-outer-scroll Three-Panel layout (`h-dvh overflow-hidden`):
- **Left Panel (Triage Queue):** 360px–420px width; vertical scrolling table of habitations sorted by Per-Capita Urgency or Caseload.
- **Center Panel (Cartographic Canvas):** Fluid flex-grow viewport hosting MapLibre GL 3D terrain, H3 hexagonal hazard meshes, and floating time-scrubber controls.
- **Right Panel (Risk Dossier & Allocation Studio):** 400px–480px width; tabbed inspector displaying SoVI radar charts, SHAP attribution bars, carrying capacity binding constraints, and scenario simulation sliders.

On secondary public / research screens (`/stories`, `/about`), the layout expands into a fluid editorial grid (12-column, 1280px max-width container, 24px column gutters) designed for narrative pacing and comparative district analysis.

Spacing rhythm strictly scales in 4px increments: 4px (`xs`), 8px (`sm`), 16px (`md`), 24px (`lg`), 32px (`xl`), and 48px (`2xl`).

## Elevation & Depth

SETU-DRR conveys spatial hierarchy primarily through tonal layering, frosted glassmorphism (`backdrop-filter: blur(24px)`), and delicate 1px border strokes rather than heavy drop shadows. Surfaces are flat and quiet at rest; depth emerges dynamically in response to user interaction or critical alert triggers.

### Shadow Vocabulary
- **Subtle Surface Lift** (`box-shadow: 0 1px 2px rgba(0, 0, 0, 0.5), 0 1px 3px 1px rgba(0, 0, 0, 0.3)`): Applied to elevated cards and buttons at rest in dark mode.
- **Tactile Hover Elevation** (`box-shadow: 0 4px 8px 3px rgba(0, 0, 0, 0.3), 0 1px 3px rgba(0, 0, 0, 0.5)`): Activated when hovering over interactive cards, Habitation triage rows, or candidate relocation sites.
- **Floating Dock & Modal Shroud** (`box-shadow: 0 25px 50px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.08)`): Used on top-level floating navigation docks, district modal dialogs, and scenario drawers.
- **Hazard Radial Aura** (`box-shadow: 0 0 25px rgba(239, 68, 68, 0.45)`): Emitted exclusively by active Permanent Red Zone hazard indicators and critical alert banners.

### Named Rules
**The Ghost Border Fallback Rule.** Every transparent or frosted glass card must carry a 1px solid border (`border: 1px solid rgba(255, 255, 255, 0.1)` dark, `border: 1px solid rgba(0, 0, 0, 0.08)` light). This guarantees crisp structural separation even on monitors with low contrast or miscalibrated gamma.

**The Rest-Flat Rule.** Containers, panels, and table rows rest without diffuse shadows. Shadows and radiant glows are state-driven behaviors that activate solely upon hover, active selection, or hazard trigger.

## Shapes

The form language balances military-grade tactical precision with organic ergonomic curves:

- **Radius Hierarchy:**
  - Micro (`xs` - 4px): Input fields, status tags, table cell indicators.
  - Standard (`sm` - 8px / `md` - 12px): Metric cards, triage rows, popover menus, modal dialog inners.
  - Container (`lg` - 16px): Parent panels, floating detail windows, scenario drawers.
  - Macro Pill (`xl` - 28px / `full` - 9999px): Primary action buttons, segmented controls, filter pills, and the central navigation dock.
- **Borders & Dividers:** Subtle, crisp 1px strokes (`--line`) define boundaries without visual clutter. Inset 1px highlights (`inset 0 1px 0 rgba(255,255,255,0.08)`) mimic machined, chamfered glass edges.
- **Capsule Silhouettes:** Floating operational elements (the floating header dock, filter chips, category switchers) embrace the pill form (`rounded-full`), visually floating over the cartographic canvas.

## Components

Components are engineered with extreme granularity, typed TypeScript interfaces, dual-theme compliance, and GSAP microinteractions.

### Buttons
- **Shape:** Pill silhouette (`rounded-full` / 9999px radius) for primary and icon buttons; rounded rectangle (`rounded-md` / 12px) for console secondary buttons.
- **Primary (Citron Action):** Solid `#d4f15d` fill, `#06100c` deep forest typography, 10px 20px padding. Hover lifts scale to 1.03x with an ambient citron glow; active press compresses to 0.97x.
- **Secondary (Console Neutral):** `#111823` surface fill, 1px `#1f2a38` border, `#e6edf5` typography. Lifts to 1.02x on hover with border highlight.
- **Ghost / Tertiary:** Transparent background with `#9dabbd` text; adopts `#18212e` fill on hover.

### Chips & Badges
- **Style:** Compact capsule badges (`rounded-full` or `rounded-md`, 4px 10px padding, JetBrains Mono 10px-11px).
- **Hazard Variants:**
  - Critical (Rose): `bg-hazard-red/15 text-hazard-red border-hazard-red/30` with pulsing live radar ping dot.
  - Warning (Amber): `bg-hazard-amber/15 text-hazard-amber border-hazard-amber/30`.
  - Safe (Emerald): `bg-citron/15 text-citron border-citron/30`.
  - Telemetry (Slate): `bg-forest-mid text-text-secondary border-white/10`.

### Cards & Containers
- **Corner Style:** 12px (`rounded-md`) for sub-cards; 16px (`rounded-lg`) for primary feature panels.
- **Background:** Frosted glass composite (`rgba(20, 31, 24, 0.78)` dark, `rgba(255, 255, 255, 0.88)` light) with 24px backdrop blur.
- **Internal Padding:** 12px for compact telemetry cards (`MetricCard`), 20px–24px for major modal bodies.
- **Hover Microinteraction:** GSAP translateY (-3px) and subtle border glow.

### Inputs & Fields
- **Style:** 1px solid stroke (`--line`), 8px radius (`rounded-md`), surface background (`--surface-1`), crisp monospace or sans typography.
- **Focus State:** 2px high-visibility accent ring (`focus-visible:outline-accent`) with subtle interior glow.

### Navigation (Floating Pill Dock)
- **Signature Component:** The centered floating pill dock (`.m3-floating-dock`) hovers permanently at `top-4`, featuring an invariant dark tinted base (`#161e19` dark, `#384134` light) with `backdrop-filter: blur(20px)`.
- **Items:** Animated pill selectors (`rounded-full`) that glide smoothly across active route indicators with GSAP elastic easing.

## Do's and Don'ts

### Do:
- **Do** maintain dual theme parity on every single component using semantic CSS variables (`bg-surface-0 dark:bg-forest-dark`, `text-ink dark:text-text-primary`).
- **Do** scope every GSAP animation with `useGSAP({ scope: containerRef })` and respect the `usePrefersReducedMotion` hook.
- **Do** format all geographic coordinates, time offsets, and numerical measures in tabular `JetBrains Mono`.
- **Do** extract all sub-elements, table rows, and status indicators into granular, dedicated component files under 150 lines.
- **Do** use `.glass-card` with 1px border fallback for all floating panels overlaying MapLibre or Three.js viewports.

### Don't:
- **Don't** use chromatic hazard red, orange, or amber for non-hazard UI decoration, marketing banners, or neutral status icons.
- **Don't** hardcode dark-only hex values (`#000`, `#0e261d`, `text-white`) without an equivalent light-mode token.
- **Don't** exceed 8% viewport surface coverage for the Neon Citron accent color.
- **Don't** write monolithic multi-hundred-line JSX pages; decompose into reusable atomic primitives and feature components.
- **Don't** render un-animated sudden UI state jumps when GSAP microinteractions can provide smooth 150ms–300ms transitions.
