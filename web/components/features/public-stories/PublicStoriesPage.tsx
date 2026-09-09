'use client';

import React, { useState } from 'react';
import { ZoneId, BackendDistrictId, FEATURED_DISTRICTS, REGIONAL_STORIES } from './storyData';
import { StoriesHeroText } from './StoriesHeroText';
import { StoriesHeaderCoordinates } from './StoriesHeaderCoordinates';
import { ZoneTickSelector } from './ZoneTickSelector';
import { IndiaStoriesMap } from './IndiaStoriesMap';
import { DistrictRiskModal } from './DistrictRiskModal';

export interface PublicStoriesPageProps {
  /** Target link for returning to landing page / overview (default '/') */
  overviewHref?: string;
  /** Target link for switching to Government Official Portal (default '/gov') */
  govHref?: string;
  /** Callback to return to landing page / overview */
  onBackToOverview?: () => void;
  /** Callback to switch to Government Official Portal */
  onSwitchToGovPortal?: () => void;
  /** Custom root className */
  className?: string;
}

export const PublicStoriesPage: React.FC<PublicStoriesPageProps> = ({
  overviewHref = '/',
  govHref = '/gov',
  onBackToOverview,
  onSwitchToGovPortal,
  className = '',
}) => {
  // Default to Wayanad — our primary active red zone with authoritative backend data
  const [selectedZone, setSelectedZone] = useState<ZoneId>('Wayanad');
  const [isSlideshowOpen, setIsSlideshowOpen] = useState(false);

  const activeStory = REGIONAL_STORIES[selectedZone] || REGIONAL_STORIES.Wayanad;

  const handleSelectDistrict = (zone: ZoneId, openPopup = true) => {
    setSelectedZone(zone);
    if (openPopup) {
      setIsSlideshowOpen(true);
    }
  };

  return (
    <div
      className={`relative w-screen h-screen overflow-hidden bg-bg-base text-text-primary dark:bg-[#0e261d] dark:text-cream flex flex-col justify-between p-6 sm:p-8 lg:p-10 select-none transition-colors duration-300 ${className}`}
    >
      {/* Background Subtle Ambient Vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-forest-mid/25 via-bg-base to-forest-deep/15 dark:from-[#143d2c]/40 dark:via-[#0e261d] dark:to-[#081813] pointer-events-none" />

      {/* 1. TOP HEADER: Navigation & Coordinates Readout */}
      <div className="relative z-20 w-full mb-2">
        <StoriesHeaderCoordinates
          latitude={activeStory.coordinates.display.lat}
          longitude={activeStory.coordinates.display.lng}
          overviewHref={overviewHref}
          govHref={govHref}
          onBackToOverview={onBackToOverview}
          onSwitchToGovPortal={onSwitchToGovPortal}
        />
      </div>

      {/* 2. MAIN INTERACTION CANVAS: Left Text + Center Map + Right Zone Selector */}
      <div className="relative z-10 flex-1 w-full grid grid-cols-1 lg:grid-cols-12 items-center gap-4 min-h-0">
        {/* Left Column: Headline & Tourist Hazard Advisory */}
        <div className="hidden lg:flex lg:col-span-3 h-full flex-col justify-center pl-2">
          <StoriesHeroText
            category="SETU-DRR TOURIST HAZARD ADVISORY"
            activeZoneLabel={`${activeStory.districtName} (${activeStory.stateName})`}
            summary={activeStory.shortSummary}
          />
        </div>

        {/* Center Column: Interactive India Map with Region Cutout */}
        <div className="col-span-1 lg:col-span-7 h-full w-full flex items-center justify-center relative">
          <IndiaStoriesMap
            selectedZone={selectedZone}
            onSelectZone={(zone) => handleSelectDistrict(zone, true)}
            onOpenSlideshow={() => setIsSlideshowOpen(true)}
          />
        </div>

        {/* Right Column: Zone/District Tick Ruler Selector */}
        <div className="hidden sm:flex col-span-1 lg:col-span-2 h-full flex-col justify-center items-end pr-4">
          <ZoneTickSelector
            selectedZone={selectedZone}
            onSelectZone={(zone) => handleSelectDistrict(zone, true)}
          />
        </div>
      </div>

      {/* Mobile/Tablet Fallback Footer District Selector */}
      <div className="sm:hidden relative z-20 flex items-center justify-center gap-2 pt-2 border-t border-white/10">
        {FEATURED_DISTRICTS.map((district) => (
          <button
            key={district}
            type="button"
            onClick={() => handleSelectDistrict(district, true)}
            className={`px-3 py-1.5 text-xs rounded-lg font-mono transition-colors ${
              selectedZone === district
                ? 'bg-[#a3e635] text-[#0e261d] font-bold'
                : 'text-cream/70 bg-white/5'
            }`}
          >
            {district}
          </button>
        ))}
      </div>

      {/* 3. DISTRICT RISK ASSESSMENT POP-UP (Connected to Live Backend) */}
      <DistrictRiskModal
        isOpen={isSlideshowOpen}
        zone={selectedZone}
        onClose={() => setIsSlideshowOpen(false)}
      />
    </div>
  );
};

export default PublicStoriesPage;
