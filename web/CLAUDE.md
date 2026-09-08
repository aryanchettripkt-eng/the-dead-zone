@AGENTS.md

# Frontend Instructions (`web/`)

## Quick Commands
```bash
pnpm dev              # Launch dev server on http://localhost:3000
pnpm build            # Production build
pnpm lint             # ESLint check
pnpm generate:types   # Sync TypeScript API types from openapi.json
pnpm add gsap @gsap/react # Install GSAP and React hook
```

## Core Frontend Directives
1. **Granular Component Separation**:
   - Anything that can be a separate component MUST be extracted into its own component file.
   - No giant JSX blocks or monolithic components.
   - List items, table rows, cards, badges, buttons, headers, and skeletons must each be independent files.
2. **Complete Modularity & Exported TypeScript Interfaces**:
   - Every single component MUST export an interface for its props (`export interface [Name]Props { ... }`).
   - Every configurable property (labels, variants, sizes, styles, sub-element classes, event handlers, animation toggles) must be exposed via the interface.
3. **GSAP for All Animations & Microinteractions**:
   - Use GSAP (`gsap` and `@gsap/react` `useGSAP`) for all animations and transitions.
   - Add microinteractions across all components (button hover/press scaling, card elevation lifts, elastic slider reactions, animated number counters, staggered list entries).
   - Ensure proper cleanup with scoped refs and support `prefers-reduced-motion`.
