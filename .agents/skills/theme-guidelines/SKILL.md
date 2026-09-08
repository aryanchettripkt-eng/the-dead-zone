---
name: theme-guidelines
description: Mandatory guidelines and standards for referencing ThemeProvider, useTheme, and implementing light/dark mode compatibility across all SETU-DRR components.
---

# Theme Guidelines — SETU-DRR Light & Dark Mode Standards

When writing, refactoring, or reviewing any UI component or page in the SETU-DRR application (`web/`), agents and developers must strictly follow these theme guidelines.

---

## 1. Global Theme Architecture

The SETU-DRR application utilizes a unified, reactive theme system:

- **Provider**: Located at `web/components/providers/ThemeProvider.tsx`, re-exported via `@/components/providers`.
- **Modes Supported**: `'light' | 'dark' | 'system'`.
- **Persistence**: Persisted automatically in `localStorage` under `'setu-drr-theme'`.
- **Anti-Flash Hydration**: Root `<head>` runs an inline script to prevent initial page flicker before React mounts.
- **Tailwind CSS v4 Hook**: Bound via `@custom-variant dark (&:where(.dark, .dark *));` in `web/app/globals.css`.

---

## 2. Mandatory Rules for Writing Components

### Rule 1: Never Assume Dark Mode by Default
Never hardcode pure dark values like:
- ❌ `text-white`
- ❌ `bg-[#0e261d]` or `bg-[#0b1c15]`
- ❌ `border-white/10` or `border-white/15`

Always provide theme-adaptive variants or use CSS token classes:
- ✅ `text-ink dark:text-text-primary` or `text-text-secondary`
- ✅ `bg-surface-0 dark:bg-forest-dark` or `bg-surface-1 dark:bg-forest-surface`
- ✅ `border-line dark:border-white/10` or `border-line-strong dark:border-white/20`

### Rule 2: Use Defined Semantic Design Tokens
In `web/app/globals.css`, both `:root, html.dark` and `html.light` define harmonious color tokens:

| Token / Class | Light Mode (Daylight Sage) | Dark Mode (Night Forest) | Purpose |
| :--- | :--- | :--- | :--- |
| `bg-bg-base` | `#edf3ef` | `#0b1c15` | Page root backgrounds |
| `bg-surface-0` | `#f4f8f5` | `#0e261d` | Main cards, panels, modals |
| `bg-surface-1` | `#e4ede7` | `#133327` | Sub-cards, input bars, headers |
| `bg-surface-2` | `#d5e3d9` | `#183f30` | Hover states, active items |
| `border-line` | `#c6d8cc` | `rgba(255,255,255,0.10)` | Subtle dividing borders |
| `border-line-strong` | `#9ebaa7` | `rgba(255,255,255,0.20)` | Accented / focus borders |
| `text-ink` | `#0d241a` | `#f0fdf4` | Primary high-contrast text |
| `text-text-secondary` | `#335c49` | `#86efac` | Secondary informational labels |
| `text-text-muted` | `#587a6a` | `#4ade80` | Muted captions, timestamps |
| `.glass-card` | Semi-translucent sage + white border | Deep translucent forest + white/10 | Glassmorphic containers |
| `.btn-citron` | Vibrant lime/citron with dark text | Vibrant lime/citron with dark text | Primary CTA buttons |

### Rule 3: WebGL, Three.js & MapLibre Integration
Canvases do not automatically inherit CSS text or background colors. Always hook into the theme state:

```tsx
import { useTheme } from '@/components/providers';

export const MapOrCanvasComponent = () => {
  const { theme, resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  useEffect(() => {
    // 1. Three.js: Update AmbientLight & Material Colors
    ambientLight.color.setHex(isDark ? 0x0e1b14 : 0x90a89d);
    ambientLight.intensity = isDark ? 1.2 : 2.4;

    // 2. MapLibre: Update Background Paint
    if (map.getLayer('background')) {
      map.setPaintProperty('background', 'background-color', isDark ? '#0b1c15' : '#f4f7f5');
    }
  }, [resolvedTheme]);

  return <div ref={containerRef} />;
};
```

### Rule 4: Theme Toggle Microinteraction
For any header, rail, or settings drawer that provides theme switching, use `<ThemeToggle />` from `@/components/ui/theme-toggle` (or `@/components/ui`). It provides smooth GSAP icon animations, tactile feedback, and accessible labeling.
