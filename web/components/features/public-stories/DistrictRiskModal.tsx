'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import { ZoneId, REGIONAL_STORIES } from './storyData';
import {
  BackendDistrictKey,
  DistrictBackendProfile,
  BackendHabitationRecord,
  getBackendProfileForZone,
  loadDistrictData,
} from './districtBackendService';
import { DistrictRiskHeader } from './DistrictRiskHeader';
import { DistrictSpotSelector } from './DistrictSpotSelector';
import { DistrictTelemetryGrid } from './DistrictTelemetryGrid';
import { DistrictDisasterHistory } from './DistrictDisasterHistory';
import { TravelAdvisoryBanner } from './TravelAdvisoryBanner';
import { DistrictPhotoShowcase } from './DistrictPhotoShowcase';

export interface DistrictRiskModalProps {
  /** Modal open state */
  isOpen: boolean;
  /** Active district or zone */
  zone: ZoneId;
  /** Close callback */
  onClose: () => void;
  /** Custom root className */
  className?: string;
}

export const DistrictRiskModal: React.FC<DistrictRiskModalProps> = ({
  isOpen,
  zone,
  onClose,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const modalBoxRef = useRef<HTMLDivElement>(null);

  const initialProfile = getBackendProfileForZone(zone);
  const [profile, setProfile] = useState<DistrictBackendProfile>(initialProfile);
  const [isLive, setIsLive] = useState(false);
  const [selectedSpot, setSelectedSpot] = useState<BackendHabitationRecord>(
    initialProfile.habitations[0]
  );

  // Re-fetch / load data when zone changes
  useEffect(() => {
    if (!isOpen) return;
    const base = getBackendProfileForZone(zone);
    setProfile(base);
    setSelectedSpot(base.habitations[0]);

    const controller = new AbortController();
    loadDistrictData(base.key as BackendDistrictKey, controller.signal).then(
      ({ profile: loaded, isLive: live }) => {
        setProfile(loaded);
        setIsLive(live);
        if (loaded.habitations.length > 0) {
          setSelectedSpot(loaded.habitations[0]);
        }
      }
    );

    return () => controller.abort();
  }, [zone, isOpen]);

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // GSAP Entrance
  useGSAP(() => {
    if (!isOpen || !modalBoxRef.current) return;
    gsap.fromTo(
      modalBoxRef.current,
      { scale: 0.93, opacity: 0, y: 16 },
      { scale: 1, opacity: 1, y: 0, duration: 0.35, ease: 'power3.out' }
    );
  }, { dependencies: [isOpen, profile.districtName] });

  if (!isOpen) return null;

  const normalizedKey = (
    profile.districtName === 'Wayanad' || zone === 'Wayanad' || zone === 'South'
      ? 'Wayanad'
      : profile.districtName === 'Kodagu' || zone === 'Kodagu' || zone === 'West'
      ? 'Kodagu'
      : 'Barpeta'
  ) as ZoneId;

  const regionalStory =
    REGIONAL_STORIES[normalizedKey] ||
    REGIONAL_STORIES[zone] ||
    REGIONAL_STORIES.Wayanad;

  return (
    <div
      ref={containerRef}
      className={`fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 lg:p-8 bg-black/80 backdrop-blur-xl ${className}`}
      onClick={(e) => {
        if (e.target === containerRef.current) onClose();
      }}
    >
      <div
        ref={modalBoxRef}
        className="w-full max-w-5xl glass-card bg-surface-0/95 dark:bg-[#0e261d]/95 border border-line dark:border-white/15 rounded-3xl p-5 sm:p-7 shadow-2xl flex flex-col gap-4 text-ink dark:text-cream max-h-[92vh] overflow-y-auto"
      >
        {/* 1. Header */}
        <DistrictRiskHeader
          profile={profile}
          isLive={isLive}
          onClose={onClose}
        />

        {/* 2. Main Visual & Telemetry Showcase Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4.5 items-start">
          {/* Left Column: Visual Photography Showcase & Travel Advisory */}
          <div className="lg:col-span-5 flex flex-col gap-3.5">
            <DistrictPhotoShowcase
              slides={regionalStory?.slides || []}
              fallbackImage={regionalStory?.previewImage || '/stories/south.jpg'}
              spotName={selectedSpot.name}
            />

            <TravelAdvisoryBanner
              profile={profile}
              spot={selectedSpot}
            />
          </div>

          {/* Right Column: Habitation Spots, Telemetry, and Disaster History */}
          <div className="lg:col-span-7 flex flex-col gap-3.5">
            <DistrictSpotSelector
              spots={profile.habitations}
              selectedSpotId={selectedSpot.id}
              onSelectSpot={(spot) => setSelectedSpot(spot)}
            />

            <DistrictTelemetryGrid
              spot={selectedSpot}
              fallbackHazard={profile.primaryHazard}
            />

            <DistrictDisasterHistory
              disasters={profile.disasters}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default DistrictRiskModal;
