'use client';

import { useRef, type ReactNode } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';

import { usePrefersReducedMotion } from '@/lib/hooks/usePrefersReducedMotion';

export interface ForecastCycleBadgeProps {
  /** ISO cycle anchor from the API, or null when no READY cycle exists. */
  forecastCycleAt?: string | null;
  /** Current lead-time window in hours. */
  horizonHours?: number;
  /**
   * District the cycle covers. Worth showing explicitly: the forecast is a single-district
   * pilot, so it will often describe different ground than the hazard layer on screen.
   */
  areaLabel?: ReactNode;
  label?: ReactNode;
  /** Shown when `forecastCycleAt` is null. */
  emptyLabel?: ReactNode;
  /** Provider/model attribution line. */
  sourceLabel?: ReactNode;
  className?: string;
  classNames?: {
    root?: string;
    label?: string;
    value?: string;
    source?: string;
  };
  animation?: {
    disabled?: boolean;
    duration?: number;
  };
}

function formatCycle(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.toISOString().slice(0, 16).replace('T', ' ')}Z`;
}

/**
 * Shows which forecast cycle the map is currently rendering.
 *
 * The anchor is a derived provider-run anchor, not a verified ECMWF model initialisation
 * time — the wording here stays deliberately non-committal about that.
 */
export const ForecastCycleBadge = ({
  forecastCycleAt = null,
  horizonHours = 72,
  areaLabel = null,
  label = 'Forecast cycle',
  emptyLabel = 'No forecast cycle available',
  sourceLabel = 'Open-Meteo · ECMWF IFS HRES (~9 km)',
  className = '',
  classNames = {},
  animation,
}: ForecastCycleBadgeProps) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const reduceMotion = usePrefersReducedMotion();

  useGSAP(
    () => {
      if (animation?.disabled || reduceMotion) return;
      gsap.from('.forecast-cycle-line', {
        y: 6,
        opacity: 0,
        duration: animation?.duration ?? 0.35,
        stagger: 0.04,
        ease: 'power2.out',
      });
    },
    { scope: rootRef, dependencies: [forecastCycleAt, reduceMotion] },
  );

  return (
    <div
      ref={rootRef}
      className={[
        'rounded-xl border border-line bg-surface-0 px-3 py-2 dark:border-white/10 dark:bg-forest-surface/60',
        classNames.root ?? '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="forecast-cycle-line flex items-center justify-between gap-2">
        <p
          className={[
            'text-[10px] font-semibold uppercase tracking-wider text-text-muted',
            classNames.label ?? '',
          ].join(' ')}
        >
          {label}
        </p>
        {areaLabel ? (
          <span className="rounded-full border border-line px-1.5 text-[9px] font-semibold uppercase tracking-wider text-text-secondary dark:border-white/15">
            {areaLabel}
          </span>
        ) : null}
      </div>
      <p
        className={[
          'forecast-cycle-line font-mono text-[13px] font-semibold text-ink dark:text-text-primary',
          classNames.value ?? '',
        ].join(' ')}
      >
        {forecastCycleAt ? formatCycle(forecastCycleAt) : emptyLabel}
      </p>
      {forecastCycleAt ? (
        <p
          className={[
            'forecast-cycle-line mt-0.5 text-[10px] leading-snug text-text-secondary',
            classNames.source ?? '',
          ].join(' ')}
        >
          {sourceLabel} · window +1h to +{horizonHours}h
        </p>
      ) : null}
    </div>
  );
};
