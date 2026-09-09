'use client';

import { useRef, type ReactNode } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';

import { usePrefersReducedMotion } from '@/lib/hooks/usePrefersReducedMotion';

export interface ForecastStat {
  key: string;
  label: ReactNode;
  value: ReactNode;
  /** Dims the tile when the figure is structurally zero rather than merely small. */
  muted?: boolean;
}

export interface ForecastStatRowProps {
  stats: ForecastStat[];
  className?: string;
  classNames?: { root?: string; tile?: string; label?: string; value?: string };
  animation?: { disabled?: boolean; duration?: number; stagger?: number };
}

/** Compact metric tiles summarising the loaded forecast cycle. */
export const ForecastStatRow = ({
  stats,
  className = '',
  classNames = {},
  animation,
}: ForecastStatRowProps) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const reduceMotion = usePrefersReducedMotion();

  useGSAP(
    () => {
      if (animation?.disabled || reduceMotion) return;
      gsap.from('.forecast-stat-tile', {
        y: 8,
        opacity: 0,
        duration: animation?.duration ?? 0.35,
        stagger: animation?.stagger ?? 0.04,
        ease: 'power2.out',
      });
    },
    { scope: rootRef, dependencies: [stats.map((s) => s.key).join('|'), reduceMotion] },
  );

  return (
    <div
      ref={rootRef}
      className={['grid grid-cols-2 gap-2', classNames.root ?? '', className].filter(Boolean).join(' ')}
    >
      {stats.map((stat) => (
        <div
          key={stat.key}
          className={[
            'forecast-stat-tile rounded-xl border border-line bg-surface-0 px-2.5 py-2 dark:border-white/10 dark:bg-forest-surface/60',
            stat.muted ? 'opacity-60' : '',
            classNames.tile ?? '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <p
            className={[
              'text-[9px] font-semibold uppercase tracking-wider text-text-muted',
              classNames.label ?? '',
            ].join(' ')}
          >
            {stat.label}
          </p>
          <p
            className={[
              'mt-0.5 font-mono text-sm font-semibold text-ink dark:text-text-primary',
              classNames.value ?? '',
            ].join(' ')}
          >
            {stat.value}
          </p>
        </div>
      ))}
    </div>
  );
};
