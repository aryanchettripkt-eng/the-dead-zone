'use client';

import React, { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import type { BackendHabitationRecord } from './districtBackendService';

export interface DistrictSpotSelectorProps {
  /** List of habitations/tourist spots in the district */
  spots: BackendHabitationRecord[];
  /** Currently selected spot ID */
  selectedSpotId: number;
  /** Callback when user picks a spot */
  onSelectSpot: (spot: BackendHabitationRecord) => void;
  /** Custom root className */
  className?: string;
}

export const DistrictSpotSelector: React.FC<DistrictSpotSelectorProps> = ({
  spots,
  selectedSpotId,
  onSelectSpot,
  className = '',
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!scrollRef.current) return;
    gsap.from(scrollRef.current.children, {
      opacity: 0,
      x: 12,
      stagger: 0.03,
      duration: 0.3,
      ease: 'power2.out',
    });
  }, { scope: scrollRef, dependencies: [spots] });

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <div className="flex items-center justify-between text-[11px] font-mono text-ink-muted dark:text-cream/60">
        <span>EXPLORE SETTLEMENTS & CORRIDORS ({spots.length})</span>
        <span className="text-[10px] text-ink-faint dark:text-white/40">Select destination to inspect telemetry</span>
      </div>

      <div
        ref={scrollRef}
        className="flex items-center gap-2 overflow-x-auto pb-1.5 scrollbar-thin scrollbar-thumb-line dark:scrollbar-thumb-white/10"
      >
        {spots.map((spot) => {
          const isSelected = spot.id === selectedSpotId;
          const isTier1 = spot.tier.toLowerCase().includes('tier 1') || spot.tier.toLowerCase().includes('immediate');

          return (
            <button
              key={spot.id}
              type="button"
              onClick={() => onSelectSpot(spot)}
              className={`shrink-0 flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-sans transition-all cursor-pointer ${
                isSelected
                  ? 'bg-m3-accent-foliage/15 dark:bg-m3-accent-foliage/20 text-ink dark:text-cream border-m3-accent-foliage/40 shadow-sm scale-105 font-medium'
                  : 'bg-surface-1 dark:bg-white/5 hover:bg-surface-2 dark:hover:bg-white/10 text-ink-muted dark:text-cream/70 border-line dark:border-white/10'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  isTier1 ? 'bg-red-500' : 'bg-amber-400'
                }`}
              />
              <span>{spot.name}</span>
              {spot.przOverlapPct !== undefined && (
                <span className="text-[10px] font-mono opacity-60">
                  {spot.przOverlapPct.toFixed(0)}% PRZ
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default DistrictSpotSelector;
