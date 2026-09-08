<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Frontend Architecture & Engineering Guidelines (`web/`)

These guidelines are mandatory for all frontend development in `web/` (Next.js 16 + React 19 + TypeScript + Tailwind CSS v4).

---

## 1. Granular Component Decomposition (Separate Everything)
- **Principle of Maximum Separation**: If a UI section, sub-element, or widget can exist as a standalone component, it **MUST** be extracted into its own file. Never write monolithic page files or multi-hundred-line JSX trees.
- **Single Responsibility Principle (SRP)**: Each component should do one thing exceptionally well. A component file should ideally stay under 100–150 lines of code.
- **Mandatory Extractions**:
  - List items, table rows, and repeated cards must never be inlined in `.map()` loops. Extract them into dedicated component files (e.g., `TriageTableRow.tsx`, `RelocationSiteCard.tsx`, `FilterChip.tsx`).
  - Headers, footers, control bars, action menus, metric widgets, empty states, error states, and tooltip triggers must each be distinct components.
  - Skeletons and loading indicators must have matching dedicated component files (e.g., `MetricCardSkeleton.tsx`) matching the shape of the component they placeholder.
  - Keep presentation components strictly decoupled from data fetching and orchestration containers.
- **Directory Layout Convention**:
  ```text
  components/
  ├── ui/               # Foundational atomic primitives (Button, Input, Slider, Badge, Switch, Tooltip, Modal, Drawer, etc.)
  ├── common/           # Shared composite widgets (MetricCard, StatusPill, EmptyState, SectionHeader, etc.)
  ├── layout/           # App layout components (ThreePanelLayout, LeftPanel, CenterPanel, RightPanel, Header, etc.)
  └── features/         # Domain-specific feature modules
      ├── triage/       # Triage table, filter chips, urgent vs caseload toggles
      ├── map/          # MapLibre container, H3 hexagonal overlays, map controls, time slider
      ├── dossier/      # Risk dossier, SoVI breakdown, loss timeline, SHAP charts
      └── scenario/     # Scenario simulation drawer, parameter sliders, rank delta cards
  ```
- **Barrel Exports**: Every component folder must feature an `index.ts` exporting the component, its prop interface, and auxiliary types.

---

## 2. Complete Modularity & Exported TypeScript Interfaces
- **100% Configurable via Typed Interfaces**: Every component **MUST** export a dedicated TypeScript `interface` detailing all props. Nothing that a developer or consumer might want to customize should be hardcoded.
  ```tsx
  // Example pattern for all components
  export interface MetricCardProps {
    /** Main numeric or string metric value */
    value: React.ReactNode;
    /** Label or title for the metric */
    label: React.ReactNode;
    /** Optional secondary subtitle or description */
    description?: React.ReactNode;
    /** Visual theme / severity intent */
    variant?: 'default' | 'critical' | 'warning' | 'success' | 'info';
    /** Icon element rendered on the card */
    icon?: React.ReactNode;
    /** Slot for auxiliary action (e.g. tooltip button, info popover) */
    action?: React.ReactNode;
    /** Additional CSS classes for root element */
    className?: string;
    /** Granular styling overrides for inner elements */
    classNames?: {
      root?: string;
      value?: string;
      label?: string;
      iconWrapper?: string;
    };
    /** Animation configuration overrides */
    animation?: {
      enableHover?: boolean;
      duration?: number;
      delay?: number;
    };
    /** Click event handler */
    onClick?: (event: React.MouseEvent<HTMLDivElement>) => void;
  }
  ```
- **Interface Checklist for Every Component**:
  - [x] **Content Slots**: Flexible `ReactNode` props for text, titles, subtitles, icons, and child elements.
  - [x] **Style Customization**: Top-level `className` and granular `classNames` object for styling sub-elements.
  - [x] **Variants & Sizes**: Strongly typed union types (`variant?: 'primary' | 'secondary' | ...`, `size?: 'sm' | 'md' | 'lg'`).
  - [x] **Event Callbacks**: Strongly typed interaction callbacks (`onClick`, `onValueChange`, `onHover`, etc.).
  - [x] **Animation Controls**: Props to toggle or customize animation behavior (`animation?: { ... }`).
  - [x] **Sensible Defaults**: Provide graceful default values for all optional props so components work out of the box.
  - [x] **Type Exports**: Always export the props interface and any associated union types/enums from the component file.

---

## 3. GSAP for All Animations & Rich Microinteractions
- **Animation Standard**: Use **GreenSock (GSAP)** along with `@gsap/react` for **all animations, transitions, and microinteractions**. Do not rely on ad-hoc CSS keyframes or external animation libraries when GSAP can provide unified, high-performance orchestration.
  - Dependencies: `gsap` and `@gsap/react` (`pnpm --filter web add gsap @gsap/react`).
- **Next.js & React 19 GSAP Rules**:
  - Components with GSAP animations must include the `'use client'` directive.
  - Always use the official `useGSAP` hook from `@gsap/react`.
  - Always pass a `scope` ref to `useGSAP` to keep animations scoped to the component root and ensure automatic cleanup/revert on unmount:
    ```tsx
    'use client';

    import { useRef } from 'react';
    import { useGSAP } from '@gsap/react';
    import gsap from 'gsap';

    export const InteractiveCard = ({ ... }: InteractiveCardProps) => {
      const containerRef = useRef<HTMLDivElement>(null);

      useGSAP(() => {
        gsap.from('.animate-target', {
          y: 16,
          opacity: 0,
          duration: 0.4,
          stagger: 0.05,
          ease: 'power2.out',
        });
      }, { scope: containerRef });

      return <div ref={containerRef}>...</div>;
    };
    ```
- **Universal Microinteractions (Every Component Feels Alive)**:
  - **Buttons & Interactive Elements**: Subtle hover scale (1.02–1.04x), tactile active press (0.97x), smooth background/border highlights.
  - **Cards & Panels**: Elevation lift on hover (`y: -3px`, shadow expansion), subtle border glow or gradient shimmer.
  - **Sliders & Numeric Inputs**: Elastic thumb feedback, animated counter transitions when numeric values update (using GSAP tweening numbers).
  - **Lists & Tables**: Staggered entrance animations on data load (`stagger: 0.03–0.05s`), smooth row hover states.
  - **Alerts & Badges**: Subtle pulse / breathing effect for critical red-zone hazards; smooth status color transitions.
  - **Drawers & Modals**: Smooth slide-and-fade entrance timelines with cubic easing (`power3.out`, `back.out(1.2)`), paired with backdrop blur fade-in.
  - **Respect User Accessibility**: Use `window.matchMedia('(prefers-reduced-motion: reduce)')` or GSAP's `matchMedia()` to disable or soften animations when the user requests reduced motion.
