# Frontend Architecture, Modular Components & GSAP Microinteractions

Apply these guidelines to all web and frontend development in `web/`:

## 1. Extreme Component Decomposition
- **Separate Everything**: Anything that can be isolated as an independent component must be extracted into its own file. Do not inline complex JSX, sub-views, or list/table item rows.
- **Single Responsibility**: Components should remain small, concise, and focused (target < 150 lines).
- **Structure**:
  - `web/components/ui/`: Atomic primitives (buttons, inputs, sliders, toggles, badges, drawers, modals).
  - `web/components/common/`: Shared composite items (metric cards, status pills, empty states).
  - `web/components/layout/`: Panel and navigation layout shells.
  - `web/components/features/`: Feature modules (`triage/`, `map/`, `dossier/`, `scenario/`).
- **Loading States**: Skeletons and loading indicators must have dedicated component files matching the shape of the component they placeholder.

## 2. Complete Modularity via Exported Interfaces
- **100% Configurable**: Every component must export its props interface (`export interface [ComponentName]Props { ... }`).
- **No Hardcoded Values**: Any text, icon, color, size, callback, or layout element that a developer might want to adjust must be exposed as a prop with sensible defaults.
- **Granular Styling Overrides**: Expose both `className?: string` for the root and `classNames?: { [element: string]: string }` for inner parts.
- **Slots & Callbacks**: Expose slots (`leftIcon`, `rightIcon`, `action`, `children`) and fully typed event handlers.
- **Type Exports**: Always export the interface and any associated type unions.

## 3. GSAP for All Animations & Microinteractions
- **Engine**: Use GreenSock (`gsap` and `@gsap/react`) for all animations, transitions, and microinteractions.
- **React 19 & Next.js Best Practices**:
  - Mark animated components with `'use client'`.
  - Use `useGSAP` from `@gsap/react` with a scoped `containerRef` (`{ scope: containerRef }`) to ensure safe execution and automatic cleanup on unmount.
- **Microinteractions**:
  - **Buttons**: Subtle hover scale (1.02–1.04x), tactile active depression (0.97x), glowing accents.
  - **Cards & Rows**: Subtle hover lift (`y: -3px`), shadow enhancement, border highlights.
  - **Inputs & Sliders**: Elastic thumb motion, animated numerical count transitions (GSAP number tweens).
  - **Lists & Tables**: Staggered entrance animations on load (`stagger: 0.04s`, `ease: 'power2.out'`).
  - **Drawers & Modals**: Smooth physics-based slide/fade transitions with cubic easing (`power3.out`, `back.out(1.2)`).
  - **Reduced Motion**: Gracefully respect `prefers-reduced-motion` settings.

## 4. Universal Light & Dark Mode Compliance (`ThemeProvider`)
- **Global Theme Context**: All components must refer to and support the global theme context (`useTheme()` from `@/components/providers`).
- **No Dark-Only Assumptions**: Never hardcode dark colors (`text-white`, `bg-[#0e261d]`, `border-white/10`) without providing corresponding light mode classes or using CSS variables.
- **Design Tokens**:
  - `bg-bg-base`, `bg-surface-0 dark:bg-forest-dark`, `bg-surface-1 dark:bg-forest-surface`
  - `text-ink dark:text-text-primary`, `text-text-secondary`, `text-text-muted`
  - `border-line dark:border-white/10`, `border-line-strong dark:border-white/20`
  - Utilities: `.glass-card`, `.capsule-pill`, `.pill-badge`, `.btn-citron`
- **WebGL / Canvases**: When working with Three.js or MapLibre, retrieve `{ resolvedTheme } = useTheme()` and dynamically switch scene lighting, background paint colors, and shaders.
- **Theme Switcher**: Use `<ThemeToggle />` from `@/components/ui/theme-toggle` (or `@/components/ui`) for user toggling.
