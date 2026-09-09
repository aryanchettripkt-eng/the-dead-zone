'use client';

import React from 'react';

export interface PastDisasterItem {
  id?: number;
  ts: string;
  hazard_type: string;
  fatalities: number;
  injured?: number | null;
  houses_damaged?: number | null;
  severity?: number;
  source: string;
  source_ref?: string | null;
}

export interface DistrictDisasterHistoryProps {
  /** Array of historical disasters from backend */
  disasters: PastDisasterItem[];
  /** Optional root className */
  className?: string;
}

export const DistrictDisasterHistory: React.FC<DistrictDisasterHistoryProps> = ({
  disasters,
  className = '',
}) => {
  if (!disasters || disasters.length === 0) {
    return (
      <div
        className={`p-3.5 rounded-2xl bg-surface-1/50 dark:bg-white/5 border border-line dark:border-white/10 text-xs font-mono text-ink-muted dark:text-cream/60 flex items-center gap-2.5 ${className}`}
      >
        <span className="material-symbols-outlined text-m3-accent-foliage text-base">
          check_circle
        </span>
        <span>Zero major fatal disaster breaches recorded in this sector over recent observation periods.</span>
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-2.5 ${className}`}>
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-red-400 text-sm">history_toggle_off</span>
        <span className="text-xs font-mono uppercase tracking-wider text-ink-muted dark:text-cream/70 font-semibold">
          Recorded Disaster Breaches & Fatal Impact ({disasters.length})
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {disasters.map((d, idx) => (
          <div
            key={idx}
            className="p-3 rounded-2xl bg-red-950/20 dark:bg-red-950/30 border border-red-500/30 flex flex-col justify-between text-xs"
          >
            <div>
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="font-mono text-[10px] text-red-400 font-semibold uppercase">
                  {d.ts} :: {d.hazard_type}
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-red-500/20 text-red-300">
                  {d.fatalities} Fatalities
                </span>
              </div>
              <h4 className="font-sans font-semibold text-ink dark:text-cream text-xs leading-snug">
                {d.source_ref || `${d.hazard_type.toUpperCase()} Breach`}
              </h4>
            </div>

            <div className="mt-2 pt-2 border-t border-red-500/20 flex items-center justify-between text-[10px] font-mono text-ink-muted dark:text-cream/60">
              <span>Damage: {d.houses_damaged ? `${d.houses_damaged} homes` : 'N/A'}</span>
              <span className="truncate max-w-[150px] text-right">Source: {d.source}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default DistrictDisasterHistory;
