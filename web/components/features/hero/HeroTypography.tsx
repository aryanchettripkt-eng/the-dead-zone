'use client';

import React from 'react';

export interface HeroTypographyProps {
  /** First headline word */
  line1?: string;
  /** Second headline word */
  line2?: string;
  /** Third headline word */
  line3?: string;
  /** Tagline line 1 */
  tagline1?: string;
  /** Tagline line 2 (accent colored) */
  tagline2?: string;
  /** Description paragraph text */
  description?: string;
  /** Custom root className */
  className?: string;
}

export const HeroTypography: React.FC<HeroTypographyProps> = ({
  line1 = 'THE',
  line2 = 'DEAD',
  line3 = 'ZONE',
  tagline1 = 'Change the World',
  tagline2 = 'Live Safely!',
  description = 'T.E.R.R.A. (Terrain-based Environmental Risk and Relocation Analytics) — National Disaster Red Zone Decision Support & Autonomous Resettlement Routing Engine.',
  className = '',
}) => {
  return (
    <div className={`flex flex-col items-start select-none ${className}`}>
      {/* Monumental Condensed Grotesque Headline */}
      <h1 className="hero-headline flex flex-col font-sans font-black text-5xl sm:text-7xl lg:text-[clamp(3.5rem,min(5.5vw,9.2vh),6.8rem)] tracking-tight leading-[0.88] text-m3-on-surface mb-3 sm:mb-4 lg:mb-5 drop-shadow-xs">
        <span className="hero-word-line inline-block">{line1}</span>
        <span className="hero-word-line inline-block">{line2}</span>
        <span className="hero-word-line inline-block">{line3}</span>
      </h1>

      {/* Expressive Tagline */}
      <div className="hero-tagline mb-2 sm:mb-3">
        <h2 className="font-sans text-xl sm:text-3xl lg:text-[clamp(1.35rem,min(2.2vw,3.4vh),2.25rem)] font-extrabold tracking-tight leading-tight text-m3-on-surface">
          <span className="block">{tagline1}</span>
          <span className="block text-m3-accent-foliage">{tagline2}</span>
        </h2>
      </div>

      {/* Descriptive Mission Text */}
      <p className="hero-description text-xs sm:text-sm lg:text-[clamp(0.8rem,min(1vw,1.5vh),0.95rem)] text-m3-on-surface-variant font-sans max-w-md leading-relaxed mb-4 sm:mb-6">
        {description}
      </p>
    </div>
  );
};
