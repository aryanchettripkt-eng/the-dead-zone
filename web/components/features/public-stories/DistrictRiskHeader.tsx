'use client';

import React from 'react';

export interface DistrictRiskHeaderProps {
  /** Official administrative district name */
  districtName: string;
  /** State name */
  stateName: string;
  /** LGD administrative code */
  lgdCode?: number | string;
  /** Severity / Danger tier classification */
  dangerLevel: 'Critical' | 'High' | 'Moderate' | 'Monitored';
  /** Primary hazard (e.g. Landslide, Riverine Flood) */
  primaryHazard: string;
  /** Whether data is currently syncing from backend API */
  isLoading?: boolean;
  /** Modal close callback */
  onClose: () => void;
  /** Optional root className */
  className?: string;
}

export const DistrictRiskHeader: React.FC<DistrictRiskHeaderProps> = ({
  districtName,
  stateName,
  lgdCode,
  dangerLevel,
  primaryHazard,
  isLoading = false,
  onClose,
  className = '',
}) => {
  const getDangerBadgeClass = (level: string) => {
    switch (level) {
      case 'Critical':
        return 'bg-red-500/20 text-red-300 border-red-500/40';
      case 'High':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
      case 'Moderate':
        return 'bg-yellow-500/20 text-yellow-200 border-yellow-500/30';
      default:
        return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30';
    }
  };

  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-center justify-between border-b border-line dark:border-white/10 pb-4 mb-6 gap-3 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-2.5">
        {/* Live sync pulse */}
        <span
          className={`w-2.5 h-2.5 rounded-full ${
            isLoading ? 'bg-amber-400 animate-spin' : 'bg-citron animate-ping'
          }`}
        />
        <span className="font-mono text-xs uppercase tracking-widest text-m3-accent-foliage font-semibold">
          Tourist Safety Advisory
        </span>
        <span className="text-ink-faint dark:text-white/30 hidden sm:inline">|</span>
        <h2 className="text-base sm:text-lg font-sans font-bold text-ink dark:text-cream">
          {districtName}, <span className="font-normal text-cream/70">{stateName}</span>
        </h2>
        {lgdCode && (
          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface-1 dark:bg-white/10 text-ink-muted dark:text-cream/60">
            LGD: {lgdCode}
          </span>
        )}
        {/* Severity pill */}
        <span
          className={`text-[11px] font-mono font-semibold uppercase px-2.5 py-0.5 rounded-full border backdrop-blur-sm ${getDangerBadgeClass(
            dangerLevel
          )}`}
        >
          {dangerLevel} :: {primaryHazard}
        </span>
      </div>

      <button
        type="button"
        onClick={onClose}
        className="self-end sm:self-auto w-8 h-8 rounded-full bg-surface-1 hover:bg-surface-2 dark:bg-white/10 dark:hover:bg-white/20 text-ink-muted hover:text-ink dark:text-cream/80 dark:hover:text-white flex items-center justify-center transition-colors cursor-pointer"
        aria-label="Close District Safety Advisory"
      >
        ✕
      </button>
    </div>
  );
};

export default DistrictRiskHeader;
