'use client';

import React, { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import type { BackendHabitationRecord, DistrictBackendProfile } from './districtBackendService';

export interface TravelAdvisoryBannerProps {
  /** The district profile */
  profile: DistrictBackendProfile;
  /** The selected spot */
  spot: BackendHabitationRecord;
  /** Custom root className */
  className?: string;
}

export const TravelAdvisoryBanner: React.FC<TravelAdvisoryBannerProps> = ({
  profile,
  spot,
  className = '',
}) => {
  const bannerRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!bannerRef.current) return;
    gsap.from(bannerRef.current, {
      opacity: 0,
      y: 8,
      duration: 0.3,
      ease: 'power2.out',
    });
  }, { scope: bannerRef, dependencies: [spot.id] });

  const isHighDanger =
    spot.tier.toLowerCase().includes('tier 1') ||
    profile.dangerLevel === 'Critical';

  return (
    <div
      ref={bannerRef}
      className={`p-4 rounded-2xl border transition-colors ${
        isHighDanger
          ? 'bg-red-500/5 dark:bg-red-500/10 border-red-500/30'
          : 'bg-amber-500/5 dark:bg-amber-500/10 border-amber-500/30'
      } ${className}`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className={`w-2 h-2 rounded-full ${
            isHighDanger ? 'bg-red-500 animate-ping' : 'bg-amber-500'
          }`}
        />
        <span
          className={`font-mono text-xs uppercase font-bold tracking-wider ${
            isHighDanger
              ? 'text-red-700 dark:text-red-300'
              : 'text-amber-700 dark:text-amber-300'
          }`}
        >
          {isHighDanger
            ? 'Tourist Warning: Avoid Non-Essential Travel in Red Zone'
            : 'Travel Advisory: Heightened Monsoon Precaution'}
        </span>
        <span className="text-xs font-mono text-ink-muted dark:text-cream/50 ml-auto">
          Peak Window: {profile.peakDangerWindow}
        </span>
      </div>

      <p className="text-xs sm:text-sm font-sans leading-relaxed text-ink dark:text-cream/90 mb-2">
        {profile.touristAdvisory}
      </p>

      <div className="flex items-center gap-2 text-[11px] font-mono text-ink-muted dark:text-cream/70 pt-2 border-t border-black/5 dark:border-white/10">
        <span className="font-semibold text-m3-accent-foliage">SAFE HAVEN GUIDANCE:</span>
        <span>{profile.safeHavenGuidance}</span>
      </div>
    </div>
  );
};

export default TravelAdvisoryBanner;
