'use client';

import React, { useRef, useState } from 'react';
import Image from 'next/image';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import type { StorySlide } from './storyData';

export interface DistrictPhotoShowcaseProps {
  /** Slides with pictures and metadata */
  slides: StorySlide[];
  /** Default fallback image if slides are empty */
  fallbackImage?: string;
  /** Active spot or destination name */
  spotName?: string;
  /** Custom root className */
  className?: string;
}

export const DistrictPhotoShowcase: React.FC<DistrictPhotoShowcaseProps> = ({
  slides = [],
  fallbackImage = '/stories/south.jpg',
  spotName,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const imageBoxRef = useRef<HTMLDivElement>(null);
  const [slideIndex, setSlideIndex] = useState(0);

  const activeIndex = Math.min(slideIndex, Math.max(0, slides.length - 1));
  const activeSlide = slides[activeIndex];
  const currentImage = activeSlide?.image || fallbackImage;
  const currentTitle = activeSlide?.title || (spotName ? `${spotName} Terrain Corridor` : 'District Terrain Monitoring');
  const currentSubtitle = activeSlide?.subtitle || 'Sentinel-1 InSAR Interferometry';
  const currentHazard = activeSlide?.hazardType || 'Geotechnical Slope Hazard';
  const currentSeverity = activeSlide?.riskSeverity || 'Critical';

  useGSAP(() => {
    if (!imageBoxRef.current) return;
    gsap.fromTo(
      imageBoxRef.current,
      { opacity: 0.7, scale: 0.98 },
      { opacity: 1, scale: 1, duration: 0.4, ease: 'power2.out' }
    );
  }, { scope: containerRef, dependencies: [activeIndex, currentImage] });

  const handlePrev = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSlideIndex((prev) => (prev > 0 ? prev - 1 : slides.length - 1));
  };

  const handleNext = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSlideIndex((prev) => (prev < slides.length - 1 ? prev + 1 : 0));
  };

  const isCritical = currentSeverity.toLowerCase() === 'critical';

  return (
    <div
      ref={containerRef}
      className={`relative w-full rounded-2xl overflow-hidden border border-line dark:border-white/15 shadow-xl bg-black/40 group select-none ${className}`}
    >
      <div ref={imageBoxRef} className="relative w-full h-56 sm:h-64 lg:h-72">
        <Image
          src={currentImage}
          alt={currentTitle}
          fill
          sizes="(max-width: 1024px) 100vw, 50vw"
          priority
          className="object-cover transition-transform duration-700 group-hover:scale-105"
        />

        {/* Ambient Dark/Vignette Overlay for High-Contrast Legibility */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/35 to-black/30 pointer-events-none" />

        {/* Top Badges */}
        <div className="absolute top-3 left-3 right-3 flex items-center justify-between gap-2 pointer-events-none">
          <span
            className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider border backdrop-blur-md ${
              isCritical
                ? 'bg-red-500/25 text-red-200 border-red-400/40 shadow-sm'
                : 'bg-amber-500/25 text-amber-200 border-amber-400/40 shadow-sm'
            }`}
          >
            {currentSeverity} &bull; {currentHazard}
          </span>

          {spotName && (
            <span className="px-2.5 py-1 rounded-full text-[10px] font-mono text-cream/90 bg-black/50 backdrop-blur-md border border-white/15">
              {spotName} Sector
            </span>
          )}
        </div>

        {/* Bottom Captions & Narrative */}
        <div className="absolute bottom-3 left-3 right-3 flex flex-col gap-1 text-cream">
          <span className="text-[10px] font-mono text-m3-accent-foliage uppercase tracking-wider font-semibold">
            {currentSubtitle}
          </span>
          <h4 className="font-display text-base sm:text-lg font-bold leading-tight drop-shadow-md">
            {currentTitle}
          </h4>

          {/* Verification Bar & Carousel Navigation */}
          <div className="flex items-center justify-between pt-2 mt-1 border-t border-white/15 text-[10px] font-mono text-cream/70">
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              InSAR Geodesy Verified Terrain
            </span>

            {slides.length > 1 && (
              <div className="flex items-center gap-2 pointer-events-auto">
                <span className="text-[10px] font-mono text-cream/60">
                  {activeIndex + 1} / {slides.length}
                </span>
                <button
                  type="button"
                  onClick={handlePrev}
                  className="w-6 h-6 rounded-full bg-white/15 hover:bg-white/30 text-white flex items-center justify-center transition-colors cursor-pointer"
                  aria-label="Previous photograph"
                >
                  ‹
                </button>
                <button
                  type="button"
                  onClick={handleNext}
                  className="w-6 h-6 rounded-full bg-white/15 hover:bg-white/30 text-white flex items-center justify-center transition-colors cursor-pointer"
                  aria-label="Next photograph"
                >
                  ›
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DistrictPhotoShowcase;
