'use client';

import React, { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import { ZoneId, BackendDistrictId, FEATURED_DISTRICTS } from './storyData';

export interface DistrictItem {
  id: BackendDistrictId;
  label: string;
  state: string;
}

export interface ZoneTickSelectorProps {
  /** Currently selected zone/district */
  selectedZone: ZoneId;
  /** Callback when zone/district changes */
  onSelectZone: (zone: ZoneId) => void;
  /** Custom root className */
  className?: string;
}

const DISTRICTS: DistrictItem[] = [
  { id: 'Wayanad', label: 'Wayanad', state: 'Kerala' },
  { id: 'Kodagu', label: 'Kodagu', state: 'Karnataka' },
  { id: 'Barpeta', label: 'Barpeta', state: 'Assam' },
];

export const ZoneTickSelector: React.FC<ZoneTickSelectorProps> = ({
  selectedZone,
  onSelectZone,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeTickRef = useRef<HTMLDivElement>(null);

  // Normalize selected index against featured districts
  let normalizedZone = selectedZone;
  if (selectedZone === 'South' || selectedZone === 'North') normalizedZone = 'Wayanad';
  else if (selectedZone === 'West' || selectedZone === 'Central') normalizedZone = 'Kodagu';
  else if (selectedZone === 'East') normalizedZone = 'Barpeta';

  const selectedIndex = Math.max(
    0,
    DISTRICTS.findIndex((d) => d.id === normalizedZone)
  );

  useGSAP(() => {
    if (!activeTickRef.current) return;
    const targetY = selectedIndex * 54 + 6;
    gsap.to(activeTickRef.current, {
      y: targetY,
      duration: 0.35,
      ease: 'power3.out',
    });
  }, { dependencies: [selectedIndex] });

  return (
    <div
      ref={containerRef}
      className={`select-none pointer-events-auto flex flex-col items-end ${className}`}
    >
      {/* Title */}
      <span className="text-[10px] sm:text-xs font-mono tracking-[0.2em] text-cream/50 uppercase mb-4">
        CHOOSE DISTRICT
      </span>

      {/* District list with ruler */}
      <div className="relative flex items-center gap-3">
        {/* District Names & State Chips */}
        <div className="flex flex-col gap-3 text-right">
          {DISTRICTS.map((item) => {
            const isSelected = item.id === normalizedZone;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectZone(item.id)}
                onMouseEnter={() => onSelectZone(item.id)}
                className={`group flex flex-col items-end px-3 py-1.5 rounded-xl transition-all duration-200 cursor-pointer text-right ${
                  isSelected
                    ? 'bg-forest-surface/80 border border-[#a3e635]/40 text-cream shadow-md translate-x-[-2px]'
                    : 'text-cream/50 hover:text-cream/90 hover:bg-forest-surface/40 border border-transparent'
                }`}
              >
                <span
                  className={`text-sm sm:text-base font-sans font-medium tracking-wide transition-colors ${
                    isSelected ? 'text-cream font-semibold' : 'group-hover:text-cream'
                  }`}
                >
                  {item.label}
                </span>
                <span
                  className={`text-[10px] font-mono tracking-wider uppercase transition-colors ${
                    isSelected ? 'text-m3-accent-foliage font-semibold' : 'text-cream/40'
                  }`}
                >
                  {item.state}
                </span>
              </button>
            );
          })}
        </div>

        {/* Vertical Tick-Mark Ruler */}
        <div className="relative h-[180px] w-4 flex flex-col justify-between py-1">
          {/* Subtle vertical spine line */}
          <div className="absolute top-1 bottom-1 right-[2px] w-[1px] bg-cream/15" />

          {/* Individual ruler ticks */}
          {Array.from({ length: 22 }).map((_, i) => (
            <div
              key={i}
              className={`h-[1px] ml-auto ${
                i % 4 === 0 ? 'w-3 bg-cream/35' : 'w-1.5 bg-cream/15'
              }`}
            />
          ))}

          {/* Active Highlight Notch */}
          <div
            ref={activeTickRef}
            className="absolute top-0 right-0 w-3.5 h-[2px] bg-[#a3e635] shadow-[0_0_8px_#a3e635] transition-transform"
          />
        </div>
      </div>
    </div>
  );
};

export default ZoneTickSelector;
