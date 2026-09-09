'use client';

import React from 'react';

export interface HabitationSummary {
  id: number;
  name: string;
  population?: number | null;
  tier?: string | null;
  priority_score?: number | null;
  prz_overlap_pct?: number | null;
  dominant_hazard?: string | null;
}

export interface DistrictSpotSelectorProps {
  /** List of habitations / tourist destinations in district */
  spots: HabitationSummary[];
  /** Currently selected spot ID */
  selectedSpotId: number;
  /** Selection callback */
  onSelectSpot: (id: number) => void;
  /** Optional root className */
  className?: string;
}

export const DistrictSpotSelector: React.FC<DistrictSpotSelectorProps> = ({
  spots,
  selectedSpotId,
  onSelectSpot,
  className = '',
}) => {
  const getTierIndicator = (tier?: string | null) => {
    switch (tier) {
      case 'immediate':
        return { text: 'RED ZONE', color: 'bg-red-500/20 text-red-300 border-red-500/30' };
      case 'short_term':
        return { text: 'CAUTION', color: 'bg-amber-500/20 text-amber-300 border-amber-500/30' };
      case 'mitigate_in_situ':
        return { text: 'SAFE BASE', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' };
      default:
        return { text: 'MONITORED', color: 'bg-white/10 text-cream/70 border-white/10' };
    }
  };

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono uppercase tracking-wider text-ink-muted dark:text-cream/60">
          SELECT DESTINATION / SETTLEMENT ({spots.length})
        </span>
        <span className="text-[10px] font-mono text-m3-accent-foliage">
          Backend Habitations Queue
        </span>
      </div>

      <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-thin">
        {spots.map((spot) => {
          const isSelected = spot.id === selectedSpotId;
          const tierInfo = getTierIndicator(spot.tier);

          return (
            <button
              key={spot.id}
              type="button"
              onClick={() => onSelectSpot(spot.id)}
              className={`flex-shrink-0 flex items-center gap-2 px-3 py-1.5 rounded-xl border transition-all duration-200 cursor-pointer text-left ${
                isSelected
                  ? 'bg-citron text-[#081813] font-semibold border-citron shadow-md scale-102'
                  : 'bg-surface-1/70 dark:bg-white/5 hover:bg-surface-2 dark:hover:bg-white/10 text-ink dark:text-cream border-line dark:border-white/10'
              }`}
            >
              <span className="text-xs font-sans font-medium">{spot.name}</span>
              <span
                className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border ${
                  isSelected
                    ? 'bg-black/20 text-[#081813] border-black/20 font-bold'
                    : tierInfo.color
                }`}
              >
                {tierInfo.text}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default DistrictSpotSelector;
