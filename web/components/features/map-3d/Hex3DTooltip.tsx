'use client';

import React, { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import type { HazardCell, ForecastAlertItem } from '@/lib/api/types';

export interface Hex3DTooltipProps {
  cell: HazardCell | null;
  position: { x: number; y: number } | null;
  przThreshold?: number;
  isDark?: boolean;
  forecastItem?: ForecastAlertItem | null;
}

/**
 * Modern floating HUD tooltip for 3D subcontinent hazard cell inspection.
 * Shows Susceptibility and Confidence, plus real-time live forecast data for Wayanad cells.
 */
export const Hex3DTooltip: React.FC<Hex3DTooltipProps> = ({
  cell,
  position,
  przThreshold = 0.85,
  forecastItem,
}) => {
  const rootRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!cell || !rootRef.current) return;
    gsap.fromTo(
      rootRef.current,
      { opacity: 0, scale: 0.94, y: 8 },
      { opacity: 1, scale: 1, y: 0, duration: 0.2, ease: 'power2.out' },
    );
  }, [cell?.h3]);

  if (!cell || !position) return null;

  const isPrz =
    cell.quality_flag !== 'no_coverage' && cell.susceptibility >= przThreshold;

  const hasLiveForecast = Boolean(forecastItem);

  return (
    <div
      ref={rootRef}
      className="pointer-events-none fixed z-50 rounded-2xl glass-card p-3 shadow-2xl border border-line dark:border-white/15 backdrop-blur-xl transition-all"
      style={{
        left: `${position.x + 14}px`,
        top: `${position.y - 48}px`,
        maxWidth: hasLiveForecast ? '280px' : '260px',
      }}
    >
      <div className="flex items-center justify-between gap-2 border-b border-line dark:border-white/10 pb-1.5 mb-2">
        <span className="font-mono text-[11px] font-semibold text-text-muted">
          H3 :: {cell.h3.slice(0, 10)}...
        </span>
        <div className="flex items-center gap-1">
          {hasLiveForecast && (
            <span className="flex items-center gap-1 rounded bg-crimson/20 border border-crimson/40 px-1.5 py-0.5 text-[9px] font-mono font-bold text-crimson animate-pulse">
              <span className="w-1 h-1 rounded-full bg-crimson" />
              LIVE ALERT
            </span>
          )}
          {isPrz ? (
            <span className="rounded bg-crimson/20 border border-crimson/40 px-1.5 py-0.5 text-[10px] font-mono font-bold text-crimson">
              PRZ CRITICAL
            </span>
          ) : (
            <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono text-text-secondary">
              {cell.quality_flag}
            </span>
          )}
        </div>
      </div>

      <div className={`grid ${hasLiveForecast ? 'grid-cols-3' : 'grid-cols-2'} gap-2 text-xs`}>
        <div>
          <div className="text-[10px] text-text-muted">Susceptibility</div>
          <div className="font-mono text-sm font-bold text-text-primary">
            {cell.quality_flag === 'no_coverage'
              ? 'N/A'
              : cell.susceptibility.toFixed(3)}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-text-muted">Confidence</div>
          <div className="font-mono text-sm font-bold text-citron dark:text-[#a3e635]">
            {Math.round(cell.confidence * 100)}%
          </div>
        </div>
        {hasLiveForecast && forecastItem && (
          <div>
            <div className="text-[10px] text-crimson dark:text-red-400 font-semibold flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-crimson animate-pulse" />
              Live MHI
            </div>
            <div className="font-mono text-sm font-bold text-crimson dark:text-red-400">
              {forecastItem.mhi_fcst.toFixed(3)}
            </div>
          </div>
        )}
      </div>

      {hasLiveForecast && forecastItem && (
        <div className="mt-2 pt-1.5 border-t border-line dark:border-white/10 flex items-center justify-between text-[10px] font-mono text-text-muted">
          <span>{forecastItem.dominant_hazard.toUpperCase()}</span>
          <span>+{forecastItem.horizon_hours}h lead</span>
        </div>
      )}
    </div>
  );
};
