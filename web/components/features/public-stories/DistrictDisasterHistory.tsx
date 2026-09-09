'use client';

import React, { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import type { BackendDisasterRecord } from './districtBackendService';

export interface DistrictDisasterHistoryProps {
  /** Historical disaster events for this district */
  disasters: BackendDisasterRecord[];
  /** Custom root className */
  className?: string;
}

export const DistrictDisasterHistory: React.FC<DistrictDisasterHistoryProps> = ({
  disasters,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!containerRef.current) return;
    gsap.from(containerRef.current.children, {
      opacity: 0,
      y: 10,
      stagger: 0.05,
      duration: 0.35,
      ease: 'power2.out',
    });
  }, { scope: containerRef, dependencies: [disasters] });

  if (!disasters || disasters.length === 0) return null;

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex items-center justify-between text-[11px] font-mono text-ink-muted dark:text-cream/60">
        <span>AUTHORITATIVE HISTORICAL DISASTER AUDIT</span>
        <span className="text-[10px] text-ink-faint dark:text-white/40">NDRF / SDMA Records</span>
      </div>

      <div
        ref={containerRef}
        className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-48 overflow-y-auto pr-1"
      >
        {disasters.map((event, idx) => (
          <div
            key={idx}
            className="p-3 rounded-xl bg-surface-1 dark:bg-white/5 border border-line dark:border-white/10 flex flex-col justify-between text-xs transition-all hover:bg-surface-2 dark:hover:bg-white/10"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-semibold text-ink dark:text-cream leading-tight">
                {event.eventTitle}
              </span>
              <span className="shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded bg-red-500/10 text-red-500 font-bold">
                {event.date}
              </span>
            </div>

            <div className="flex items-center gap-3 mt-2 text-[11px] font-mono text-ink-muted dark:text-cream/70">
              <span>{event.fatalities} fatalities</span>
              <span>&bull;</span>
              <span>{event.housesDamaged} homes damaged</span>
            </div>

            <div className="flex items-center justify-between text-[10px] font-mono text-ink-faint dark:text-cream/40 mt-1.5 pt-1.5 border-t border-line/60 dark:border-white/5">
              <span>Hazard: {event.hazardType}</span>
              <span>Source: {event.source}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default DistrictDisasterHistory;
