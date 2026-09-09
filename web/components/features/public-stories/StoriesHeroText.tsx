'use client';

import React, { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';

export interface StoriesHeroTextProps {
  /** Optional custom category pill / super-title */
  category?: string;
  /** Active district/zone label e.g. Wayanad, Kodagu, Barpeta */
  activeZoneLabel?: string;
  /** Dynamic short summary of the active region */
  summary?: string;
  /** Custom root className */
  className?: string;
  /** Granular style overrides */
  classNames?: {
    root?: string;
    category?: string;
    title?: string;
    description?: string;
  };
}

export const StoriesHeroText: React.FC<StoriesHeroTextProps> = ({
  category = 'SETU-DRR TOURIST HAZARD ADVISORY',
  activeZoneLabel = 'Wayanad',
  summary = 'Authoritative geological, landslide, and flood risk assessment for travellers and tourists. Evaluate active danger levels, historical disaster records, and terrain vulnerability across high-risk destinations before planning your journey.',
  className = '',
  classNames = {},
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLParagraphElement>(null);

  useGSAP(() => {
    if (!containerRef.current) return;
    gsap.fromTo(
      containerRef.current.children,
      { y: 24, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.7, stagger: 0.1, ease: 'power3.out' }
    );
  }, { scope: containerRef });

  useGSAP(() => {
    if (!textRef.current) return;
    gsap.fromTo(
      textRef.current,
      { opacity: 0.3, y: 6 },
      { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }
    );
  }, { dependencies: [activeZoneLabel, summary] });

  return (
    <div
      ref={containerRef}
      className={`max-w-md select-none pointer-events-auto ${classNames.root || ''} ${className}`}
    >
      {/* Category Monospace Subtitle */}
      <div className="flex items-center gap-2 mb-4">
        <span className="w-2 h-2 rounded-full bg-citron animate-pulse" />
        <div
          className={`text-[11px] font-mono tracking-[0.25em] text-cream/70 uppercase ${
            classNames.category || ''
          }`}
        >
          {category}
        </div>
      </div>

      {/* Main Display Headline with Foliage Accent */}
      <h1
        className={`font-sans text-4xl sm:text-5xl lg:text-6xl font-normal text-cream tracking-tight leading-[1.1] mb-6 ${
          classNames.title || ''
        }`}
      >
        Assess{' '}
        <span className="text-m3-accent-foliage font-medium transition-colors duration-300">
          travel risk
        </span>
        <br />
        across India
      </h1>

      {/* Region Context Paragraph */}
      <p
        ref={textRef}
        className={`text-sm sm:text-base text-cream/70 leading-relaxed font-sans font-light tracking-wide ${
          classNames.description || ''
        }`}
      >
        {summary}
      </p>

      {/* Active Selection Indicator */}
      <div className="mt-5 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-forest-surface/70 border border-white/10 text-xs font-mono text-cream/80">
        <span className="text-m3-accent-foliage">●</span>
        <span>Active Assessment:</span>
        <span className="text-citron font-semibold">{activeZoneLabel}</span>
      </div>
    </div>
  );
};

export default StoriesHeroText;
