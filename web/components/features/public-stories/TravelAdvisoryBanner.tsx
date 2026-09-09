'use client';

import React from 'react';

export interface TravelAdvisoryBannerProps {
  /** Triage tier: 'immediate' | 'short_term' | 'mitigate_in_situ' | null */
  tier?: string | null;
  /** Habitation name */
  spotName: string;
  /** District name */
  districtName: string;
  /** Triage rationale from backend */
  rationale?: string | null;
  /** Optional root className */
  className?: string;
}

export const TravelAdvisoryBanner: React.FC<TravelAdvisoryBannerProps> = ({
  tier,
  spotName,
  districtName,
  rationale,
  className = '',
}) => {
  const getAdvisoryContent = () => {
    switch (tier) {
      case 'immediate':
        return {
          icon: 'warning',
          title: 'STRICT TRAVEL WARNING — ACTIVE RED ZONE',
          text: `${spotName} has been classified under the IMMEDIATE RELOCATION TIER due to severe terrain instability. Tourists are strongly advised to avoid overnight stays, camping, and non-essential visits during monsoon cloudbursts. Flash landslides and debris surges can occur with minimal warning lead time.`,
          border: 'border-red-500/40 bg-red-950/25',
          accent: 'text-red-400',
        };
      case 'short_term':
        return {
          icon: 'crisis_alert',
          title: 'TRAVEL CAUTION — TRANSIT HIGHWAY CORRIDOR',
          text: `${spotName} features moderate slope exposure along regional access routes. Heavy precipitation may trigger isolated mudslips and ghat pass blockades. Confirm State Disaster Management Authority (SDMA) road status prior to departures.`,
          border: 'border-amber-500/40 bg-amber-950/20',
          accent: 'text-amber-400',
        };
      case 'mitigate_in_situ':
        return {
          icon: 'verified',
          title: 'RECOMMENDED SAFE BASE FOR TRAVELERS',
          text: `${spotName} is situated in a geologically protected valley terrace with low direct red-zone exposure. It provides official hospital access, emergency NDRF coordination centers, and safe staging for visiting ${districtName}.`,
          border: 'border-emerald-500/40 bg-emerald-950/20',
          accent: 'text-emerald-400',
        };
      default:
        return {
          icon: 'info',
          title: 'MONITORED ALLUVIAL / FOOTHILL SECTOR',
          text: `${spotName} sits within monitored boundary coordinates. Exercise routine travel precautions, observe local weather bulletins, and stay clear of braided riverbanks during high monsoon discharge.`,
          border: 'border-white/20 bg-white/5',
          accent: 'text-citron',
        };
    }
  };

  const advisory = getAdvisoryContent();

  return (
    <div
      className={`p-4 rounded-2xl border ${advisory.border} backdrop-blur-md flex flex-col gap-2 ${className}`}
    >
      <div className="flex items-center gap-2">
        <span className={`material-symbols-outlined text-lg ${advisory.accent}`}>
          {advisory.icon}
        </span>
        <h4 className={`text-xs font-mono font-bold tracking-wider uppercase ${advisory.accent}`}>
          {advisory.title}
        </h4>
      </div>

      <p className="text-xs text-ink/90 dark:text-cream/80 leading-relaxed font-sans font-light">
        {advisory.text}
      </p>

      {rationale && (
        <div className="mt-1 pt-2 border-t border-white/10 text-[11px] font-mono text-ink-muted dark:text-cream/60">
          <strong className="text-m3-accent-foliage">Geotechnical Rationale: </strong>
          {rationale}
        </div>
      )}
    </div>
  );
};

export default TravelAdvisoryBanner;
