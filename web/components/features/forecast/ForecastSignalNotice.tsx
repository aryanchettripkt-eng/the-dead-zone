'use client';

import { useRef, type ReactNode } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';

import { usePrefersReducedMotion } from '@/lib/hooks/usePrefersReducedMotion';

export type ForecastSignalState = 'driven' | 'flat' | 'no-cycle';

export interface ForecastSignalNoticeProps {
  /**
   * `driven` — rainfall lifted at least one cell above its static baseline.
   * `flat`   — a cycle is loaded but no cell was moved by rainfall.
   * `no-cycle` — no READY forecast cycle exists to serve.
   */
  state: ForecastSignalState;
  /** Number of cells the trigger actually moved. */
  drivenCount?: number;
  /** Total cells listed at or above the alert threshold. */
  totalCount?: number;
  /** Trigger threshold in mm/h, for the flat-signal explanation. */
  thresholdMmPerHour?: number;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  classNames?: { root?: string; title?: string; body?: string };
  animation?: { disabled?: boolean; duration?: number };
}

const TONE: Record<ForecastSignalState, string> = {
  driven: 'border-warning/45 bg-warning/10',
  flat: 'border-line bg-surface-1 dark:border-white/10 dark:bg-forest-surface/50',
  'no-cycle': 'border-line bg-surface-1 dark:border-white/10 dark:bg-forest-surface/50',
};

/**
 * States plainly whether the forecast cycle carries a rainfall signal.
 *
 * This exists because a populated `/alerts/forecast` response is not evidence that rain is
 * predicted: `mhi_fcst` falls back to the static hazard floor for any cell without a
 * forecast trigger. Without this notice a flat cycle renders identically to a live one.
 */
export const ForecastSignalNotice = ({
  state,
  drivenCount = 0,
  totalCount = 0,
  thresholdMmPerHour = 10,
  title,
  children,
  className = '',
  classNames = {},
  animation,
}: ForecastSignalNoticeProps) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const reduceMotion = usePrefersReducedMotion();

  useGSAP(
    () => {
      if (animation?.disabled || reduceMotion) return;
      gsap.from(rootRef.current, {
        y: 8,
        opacity: 0,
        duration: animation?.duration ?? 0.4,
        ease: 'power2.out',
      });
    },
    { scope: rootRef, dependencies: [state, reduceMotion] },
  );

  const resolvedTitle =
    title ??
    (state === 'driven'
      ? `${drivenCount} cell${drivenCount === 1 ? '' : 's'} driven by forecast rainfall`
      : state === 'flat'
        ? 'No rainfall-driven exceedance this cycle'
        : 'No forecast cycle available');

  const body =
    children ??
    (state === 'driven' ? (
      <>
        Filled hexes crossed the threshold because of forecast precipitation. The remaining{' '}
        {Math.max(totalCount - drivenCount, 0)} outlined cell
        {totalCount - drivenCount === 1 ? '' : 's'} sit at their static hazard baseline.
      </>
    ) : state === 'flat' ? (
      <>
        All {totalCount} listed cell{totalCount === 1 ? '' : 's'} sit at their static hazard
        baseline. Peak forecast intensity stayed below the {thresholdMmPerHour} mm/h trigger
        threshold, so the prototype heuristic produced a zero trigger everywhere and the
        forecast channel adds no signal over the static layer.
      </>
    ) : (
      <>
        No forecast cycle has reached READY. A cycle still being ingested is deliberately not
        served, so the map falls back to the static hazard layer.
      </>
    ));

  return (
    <div
      ref={rootRef}
      className={['rounded-md border px-3 py-2', TONE[state], classNames.root ?? '', className]
        .filter(Boolean)
        .join(' ')}
    >
      <p
        className={[
          'text-[11px] font-semibold text-ink dark:text-text-primary',
          classNames.title ?? '',
        ].join(' ')}
      >
        {resolvedTitle}
      </p>
      <p
        className={[
          'mt-1 text-[10px] leading-relaxed text-text-secondary',
          classNames.body ?? '',
        ].join(' ')}
      >
        {body}
      </p>
    </div>
  );
};
