'use client';

import React from 'react';
import { EmptyState } from '@/components/common/EmptyState';

export interface DossierEmptyStateProps {
  title?: string;
  description?: string;
  /** Optional callback to inspect Wayanad's top risk forecast alert cell directly */
  onInspectWayanad?: () => void;
  /** Whether the system has active Wayanad live forecast alerts */
  hasWayanadForecast?: boolean;
  /** Number of active forecast cells in Wayanad */
  wayanadForecastCount?: number;
  className?: string;
}

export const DossierEmptyState: React.FC<DossierEmptyStateProps> = ({
  title = 'No cell selected',
  description = 'Click a hexagon on the map to open its dossier: score, coverage provenance, physical drivers, and live meteorological forecast triggers.',
  onInspectWayanad,
  hasWayanadForecast = true,
  wayanadForecastCount = 17,
  className = '',
}) => (
  <div className={['flex flex-col gap-4', className].filter(Boolean).join(' ')}>
    <EmptyState title={title} description={description} />

    {hasWayanadForecast && onInspectWayanad && (
      <div className="rounded-2xl border border-crimson/30 bg-crimson/5 dark:bg-crimson/10 p-4 transition-all hover:border-crimson/50 text-left">
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-1.5 text-xs font-mono font-bold text-crimson dark:text-red-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-crimson opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-crimson" />
            </span>
            <span>WAYANAD LIVE FORECAST ACTIVE</span>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-surface-2 text-text-secondary border border-line">
            {wayanadForecastCount} Threshold Alerts
          </span>
        </div>

        <p className="text-xs text-text-secondary leading-relaxed mb-3">
          ECMWF Open Data numerical weather prediction model indicates active rainfall triggers across the Western Ghats corridor. Peak forecast MHI reaches <span className="font-mono font-bold text-text-primary">0.9045</span>.
        </p>

        <button
          type="button"
          onClick={onInspectWayanad}
          className="w-full py-2 px-3 rounded-xl bg-crimson hover:bg-crimson/90 text-white font-mono text-xs font-medium shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 cursor-pointer active:scale-98"
        >
          <span className="material-symbols-outlined text-sm">visibility</span>
          <span>Inspect Wayanad Highest Risk Cell</span>
        </button>
      </div>
    )}
  </div>
);
