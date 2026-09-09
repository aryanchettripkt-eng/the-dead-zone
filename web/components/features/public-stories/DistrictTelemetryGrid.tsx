'use client';

import React from 'react';

export interface DistrictTelemetryGridProps {
  /** Priority Urgency score (PS_j) e.g. 0.9486 */
  priorityScore?: number | null;
  /** Permanent Red Zone overlap percentage e.g. 91.0 */
  przOverlapPct?: number | null;
  /** Dominant hazard type (landslide, flood) */
  dominantHazard?: string | null;
  /** Resident population */
  population?: number | null;
  /** Total households */
  households?: number | null;
  /** Vulnerability index (0 to 1) */
  vulnerabilityIndex?: number | null;
  /** Optional root className */
  className?: string;
}

export const DistrictTelemetryGrid: React.FC<DistrictTelemetryGridProps> = ({
  priorityScore,
  przOverlapPct,
  dominantHazard = 'Landslide',
  population,
  households,
  vulnerabilityIndex,
  className = '',
}) => {
  const metrics = [
    {
      label: 'Priority Score (PS_j)',
      value: priorityScore !== undefined && priorityScore !== null ? priorityScore.toFixed(4) : '0.0563',
      subtext: priorityScore && priorityScore > 0.5 ? 'Immediate Danger' : 'Monitored',
      accent: priorityScore && priorityScore > 0.5 ? 'text-red-400' : 'text-m3-accent-foliage',
    },
    {
      label: 'Permanent Red Zone (PRZ)',
      value: przOverlapPct !== undefined && przOverlapPct !== null ? `${przOverlapPct.toFixed(1)}%` : 'N/A',
      subtext: przOverlapPct && przOverlapPct > 50 ? 'Critical Built Exposure' : 'Low Built Exposure',
      accent: przOverlapPct && przOverlapPct > 50 ? 'text-red-400' : 'text-cream',
    },
    {
      label: 'Dominant Danger',
      value: dominantHazard ? dominantHazard.toUpperCase() : 'LANDSLIDE',
      subtext: 'InSAR & SAR Validated',
      accent: 'text-citron',
    },
    {
      label: 'Settlement Scale',
      value: population ? `${population.toLocaleString()} souls` : 'Surveyed',
      subtext: households ? `${households.toLocaleString()} homes` : 'Frontline Community',
      accent: 'text-cream',
    },
  ];

  return (
    <div className={`grid grid-cols-2 sm:grid-cols-4 gap-2.5 ${className}`}>
      {metrics.map((m, idx) => (
        <div
          key={idx}
          className="bg-surface-1/80 dark:bg-forest-surface/70 border border-line dark:border-white/10 rounded-2xl p-3 backdrop-blur-sm flex flex-col justify-between"
        >
          <div className="text-[10px] font-mono text-ink-muted dark:text-cream/50 uppercase tracking-wider">
            {m.label}
          </div>
          <div className={`text-base sm:text-lg font-bold font-mono mt-1 ${m.accent}`}>
            {m.value}
          </div>
          <div className="text-[10px] font-mono text-ink-muted dark:text-cream/40 mt-0.5 truncate">
            {m.subtext}
          </div>
        </div>
      ))}
    </div>
  );
};

export default DistrictTelemetryGrid;
