'use client';

import React, { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import type { BackendHabitationRecord } from './districtBackendService';

export interface DistrictTelemetryGridProps {
  /** The currently inspected settlement spot */
  spot: BackendHabitationRecord;
  /** Primary district hazard */
  fallbackHazard?: string;
  /** Custom root className */
  className?: string;
}

export const DistrictTelemetryGrid: React.FC<DistrictTelemetryGridProps> = ({
  spot,
  fallbackHazard = 'Landslide & Hillslope Debris Flow',
  className = '',
}) => {
  const gridRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!gridRef.current) return;
    gsap.from(gridRef.current.children, {
      y: 12,
      opacity: 0,
      stagger: 0.05,
      duration: 0.35,
      ease: 'power2.out',
    });
  }, { scope: gridRef, dependencies: [spot.id] });

  const priorityScore = spot.priorityScore !== undefined ? spot.priorityScore.toFixed(3) : '0.948';
  const przOverlap = spot.przOverlapPct !== undefined ? `${spot.przOverlapPct.toFixed(1)}%` : '91.0%';
  const soviScore = spot.soviScore !== undefined ? spot.soviScore.toFixed(2) : '0.84';
  const hazardName = spot.hazardType || fallbackHazard;

  return (
    <div
      ref={gridRef}
      className={`grid grid-cols-2 sm:grid-cols-4 gap-3 ${className}`}
    >
      {/* Priority Urgency Score */}
      <div className="p-3.5 rounded-2xl bg-surface-1 dark:bg-white/5 border border-line dark:border-white/10 flex flex-col justify-between">
        <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted dark:text-cream/60">
          Priority Score (PS)
        </span>
        <div className="mt-2 flex items-baseline gap-1.5">
          <span className="text-xl sm:text-2xl font-mono font-bold text-red-600 dark:text-red-400">
            {priorityScore}
          </span>
          <span className="text-[10px] font-mono text-ink-faint dark:text-cream/40">/ 1.0</span>
        </div>
        <span className="text-[10px] text-ink-faint dark:text-cream/50 mt-1">
          {spot.tier}
        </span>
      </div>

      {/* PRZ Red Zone Overlap */}
      <div className="p-3.5 rounded-2xl bg-surface-1 dark:bg-white/5 border border-line dark:border-white/10 flex flex-col justify-between">
        <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted dark:text-cream/60">
          PRZ Overlap
        </span>
        <div className="mt-2 flex items-baseline gap-1">
          <span className="text-xl sm:text-2xl font-mono font-bold text-amber-600 dark:text-amber-400">
            {przOverlap}
          </span>
        </div>
        <span className="text-[10px] text-ink-faint dark:text-cream/50 mt-1">
          Red Zone Boundary
        </span>
      </div>

      {/* Population & Households */}
      <div className="p-3.5 rounded-2xl bg-surface-1 dark:bg-white/5 border border-line dark:border-white/10 flex flex-col justify-between">
        <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted dark:text-cream/60">
          Exposure Census
        </span>
        <div className="mt-2 flex items-baseline gap-1.5">
          <span className="text-xl sm:text-2xl font-mono font-bold text-ink dark:text-cream">
            {spot.population.toLocaleString()}
          </span>
          <span className="text-[10px] font-mono text-ink-faint dark:text-cream/40">pop</span>
        </div>
        <span className="text-[10px] text-ink-faint dark:text-cream/50 mt-1">
          {spot.households.toLocaleString()} households
        </span>
      </div>

      {/* SoVI / InSAR Status */}
      <div className="p-3.5 rounded-2xl bg-surface-1 dark:bg-white/5 border border-line dark:border-white/10 flex flex-col justify-between">
        <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted dark:text-cream/60">
          Vulnerability & Hazard
        </span>
        <div className="mt-1 flex flex-col">
          <span className="text-xs font-sans font-semibold text-ink dark:text-cream truncate" title={hazardName}>
            {hazardName}
          </span>
          <span className="text-[11px] font-mono text-ink-muted dark:text-cream/60 mt-0.5">
            SoVI: {soviScore} &bull; {spot.activeDeformation ? 'Active InSAR Creep' : 'Monitored Toe'}
          </span>
        </div>
        <span className="text-[10px] text-ink-faint dark:text-cream/40 mt-1">
          Type: {spot.type}
        </span>
      </div>
    </div>
  );
};

export default DistrictTelemetryGrid;
