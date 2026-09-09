'use client';

import React, { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import type { DistrictBackendProfile } from './districtBackendService';

export interface DistrictRiskHeaderProps {
  /** The district profile from backend or baseline */
  profile: DistrictBackendProfile;
  /** Whether the data was loaded live from backend */
  isLive?: boolean;
  /** Close callback */
  onClose: () => void;
  /** Custom root className */
  className?: string;
}

export const DistrictRiskHeader: React.FC<DistrictRiskHeaderProps> = ({
  profile,
  isLive = false,
  onClose,
  className = '',
}) => {
  const headerRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!headerRef.current) return;
    gsap.from(headerRef.current.children, {
      y: -10,
      opacity: 0,
      stagger: 0.05,
      duration: 0.35,
      ease: 'power2.out',
    });
  }, { scope: headerRef, dependencies: [profile.districtName] });

  const isCritical = profile.dangerLevel === 'Critical';

  return (
    <div
      ref={headerRef}
      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-line dark:border-white/10 pb-4 ${className}`}
    >
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2.5 flex-wrap">
          <h2 className="font-sans text-xl sm:text-2xl font-bold tracking-tight text-ink dark:text-cream">
            {profile.districtName}
          </h2>
          <span className="text-xs font-mono text-ink-muted dark:text-cream/60">
            {profile.state} &bull; LGD {profile.lgdCode}
          </span>
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase font-semibold border ${
              isCritical
                ? 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/25'
                : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isCritical ? 'bg-red-500 animate-pulse' : 'bg-amber-500'
              }`}
            />
            {profile.touristRiskRating}
          </span>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono text-ink-faint dark:text-cream/50">
          <span>Basin: {profile.riverBasin}</span>
          <span>&bull;</span>
          <span className="flex items-center gap-1">
            <span
              className={`w-2 h-2 rounded-full ${
                isLive ? 'bg-emerald-500' : 'bg-blue-400'
              }`}
            />
            {isLive ? 'Live API Synced' : 'Authoritative Baseline Verified'}
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={onClose}
        className="self-end sm:self-center w-8 h-8 rounded-full bg-surface-1 hover:bg-surface-2 dark:bg-white/10 dark:hover:bg-white/20 text-ink-muted hover:text-ink dark:text-cream/80 dark:hover:text-white flex items-center justify-center transition-all cursor-pointer hover:scale-105 active:scale-95"
        aria-label="Close District Assessment"
      >
        ✕
      </button>
    </div>
  );
};

export default DistrictRiskHeader;
