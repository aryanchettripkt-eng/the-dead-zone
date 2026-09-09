'use client';

import React, { useState, useEffect, useRef } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import { ZoneId, BackendDistrictId, REGIONAL_STORIES, ZoneStoryData } from './storyData';
import { DistrictRiskHeader } from './DistrictRiskHeader';
import { DistrictSpotSelector, HabitationSummary } from './DistrictSpotSelector';
import { DistrictTelemetryGrid } from './DistrictTelemetryGrid';
import { DistrictDisasterHistory, PastDisasterItem } from './DistrictDisasterHistory';
import { TravelAdvisoryBanner } from './TravelAdvisoryBanner';
import { fetchHabitations, fetchHabitationRisk } from '@/lib/api/relocation';
import type { HabitationRiskDossier } from '@/lib/api/types';

export interface DistrictRiskModalProps {
  /** Modal open status */
  isOpen: boolean;
  /** Active district/zone being explored */
  zone: ZoneId;
  /** Callback to close modal */
  onClose: () => void;
  /** Custom root className */
  className?: string;
}

// Authentic preloaded fallbacks derived directly from backend tables to ensure 0ms render latency
const PRELOADED_BACKEND_HABITATIONS: Record<BackendDistrictId, HabitationSummary[]> = {
  Wayanad: [
    { id: 725, name: 'Mundakkai', population: 2150, tier: 'immediate', priority_score: 0.9486, prz_overlap_pct: 91.0, dominant_hazard: 'landslide' },
    { id: 724, name: 'Chooralmala', population: 3840, tier: 'immediate', priority_score: 0.7694, prz_overlap_pct: 82.5, dominant_hazard: 'landslide' },
    { id: 727, name: 'Vythiri', population: 9800, tier: 'short_term', priority_score: 0.0993, prz_overlap_pct: 48.0, dominant_hazard: 'landslide' },
    { id: 726, name: 'Meppadi', population: 14200, tier: 'short_term', priority_score: 0.0621, prz_overlap_pct: 35.0, dominant_hazard: 'landslide' },
    { id: 729, name: 'Mananthavady', population: 28400, tier: null, priority_score: 0.0258, prz_overlap_pct: 18.5, dominant_hazard: 'landslide' },
    { id: 728, name: 'Kalpetta', population: 31500, tier: 'mitigate_in_situ', priority_score: 0.0139, prz_overlap_pct: 12.0, dominant_hazard: 'landslide' },
  ],
  Kodagu: [
    { id: 731, name: 'Bhagamandala', population: 4100, tier: 'immediate', priority_score: 0.4858, prz_overlap_pct: 74.0, dominant_hazard: 'landslide' },
    { id: 730, name: 'Madikeri', population: 33400, tier: null, priority_score: 0.0373, prz_overlap_pct: 28.0, dominant_hazard: 'landslide' },
    { id: 732, name: 'Somwarpet', population: 11200, tier: 'mitigate_in_situ', priority_score: 0.0337, prz_overlap_pct: 22.0, dominant_hazard: 'landslide' },
  ],
  Barpeta: [
    { id: 775, name: 'Howly', population: 2870, tier: null, priority_score: 0.0563, prz_overlap_pct: 25.0, dominant_hazard: 'riverine_flood' },
    { id: 776, name: 'Pathsala', population: 3241, tier: null, priority_score: 0.0563, prz_overlap_pct: 25.0, dominant_hazard: 'riverine_flood' },
    { id: 782, name: 'Barpeta Road', population: 3243, tier: null, priority_score: 0.0563, prz_overlap_pct: 25.0, dominant_hazard: 'riverine_flood' },
    { id: 781, name: 'Sorbogh', population: 1893, tier: null, priority_score: 0.0563, prz_overlap_pct: 25.0, dominant_hazard: 'riverine_flood' },
    { id: 783, name: 'Sarthebari', population: 629, tier: null, priority_score: 0.0563, prz_overlap_pct: 25.0, dominant_hazard: 'riverine_flood' },
  ],
};

const PRELOADED_DISASTERS: Record<BackendDistrictId, PastDisasterItem[]> = {
  Wayanad: [
    {
      id: 220,
      ts: '2024-07-30',
      hazard_type: 'Landslide',
      fatalities: 350,
      injured: 280,
      houses_damaged: 420,
      severity: 1.0,
      source: 'GSI / Kerala SDMA',
      source_ref: 'Chooralmala-Mundakkai Debris Flow 2024',
    },
    {
      id: 221,
      ts: '2019-08-08',
      hazard_type: 'Landslide',
      fatalities: 17,
      injured: 12,
      houses_damaged: 65,
      severity: 0.75,
      source: 'Kerala SDMA',
      source_ref: 'Puthumala Landslide 2019',
    },
  ],
  Kodagu: [
    {
      id: 222,
      ts: '2018-08-17',
      hazard_type: 'Landslide',
      fatalities: 18,
      injured: 35,
      houses_damaged: 210,
      severity: 0.85,
      source: 'Karnataka SDMA',
      source_ref: 'Kodagu Multi-Landslide Event 2018',
    },
  ],
  Barpeta: [
    {
      id: 223,
      ts: '2022-06-20',
      hazard_type: 'Riverine Flood',
      fatalities: 24,
      injured: 60,
      houses_damaged: 1850,
      severity: 0.8,
      source: 'Assam SDMA',
      source_ref: 'Lower Brahmaputra Embankment Breach 2022',
    },
  ],
};

export const DistrictRiskModal: React.FC<DistrictRiskModalProps> = ({
  isOpen,
  zone,
  onClose,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const modalBoxRef = useRef<HTMLDivElement>(null);

  // Normalize zone to one of the 3 backend districts
  let districtKey: BackendDistrictId = 'Wayanad';
  if (zone === 'Kodagu' || zone === 'West' || zone === 'Central') districtKey = 'Kodagu';
  else if (zone === 'Barpeta' || zone === 'East') districtKey = 'Barpeta';
  else districtKey = 'Wayanad';

  const districtData = REGIONAL_STORIES[districtKey];

  const [habitations, setHabitations] = useState<HabitationSummary[]>(
    PRELOADED_BACKEND_HABITATIONS[districtKey] || []
  );
  const [selectedHabitationId, setSelectedHabitationId] = useState<number>(
    PRELOADED_BACKEND_HABITATIONS[districtKey]?.[0]?.id ?? 725
  );
  const [liveDossier, setLiveDossier] = useState<HabitationRiskDossier | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Update selected habitation when district changes
  useEffect(() => {
    const fallbackSpots = PRELOADED_BACKEND_HABITATIONS[districtKey] || [];
    setHabitations(fallbackSpots);
    if (fallbackSpots.length > 0) {
      setSelectedHabitationId(fallbackSpots[0].id);
    }
  }, [districtKey]);

  // Fetch live habitations from backend
  useEffect(() => {
    if (!isOpen) return;
    const controller = new AbortController();

    async function loadLiveHabitations() {
      try {
        setIsLoading(true);
        const res = await fetchHabitations(
          { admin: districtData.adminId, limit: 50 },
          controller.signal
        );
        if (res && res.items && res.items.length > 0) {
          const mapped: HabitationSummary[] = res.items.map((h) => ({
            id: h.id,
            name: h.name,
            population: h.population,
            tier: h.tier,
            priority_score: h.priority_score,
            prz_overlap_pct: h.prz_overlap_pct,
            dominant_hazard: h.dominant_hazard,
          }));
          setHabitations(mapped);
          // Keep current selection if in list, else pick first
          if (!mapped.some((m) => m.id === selectedHabitationId)) {
            setSelectedHabitationId(mapped[0].id);
          }
        }
      } catch (err) {
        // Fallback already preloaded
      } finally {
        setIsLoading(false);
      }
    }

    loadLiveHabitations();
    return () => controller.abort();
  }, [isOpen, districtData.adminId]);

  // Fetch live risk dossier for the selected habitation
  useEffect(() => {
    if (!isOpen || !selectedHabitationId) return;
    const controller = new AbortController();

    async function loadRiskDossier() {
      try {
        const dossier = await fetchHabitationRisk(selectedHabitationId, controller.signal);
        setLiveDossier(dossier);
      } catch (err) {
        setLiveDossier(null);
      }
    }

    loadRiskDossier();
    return () => controller.abort();
  }, [isOpen, selectedHabitationId]);

  // Escape key navigation
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // GSAP entrance animation
  useGSAP(() => {
    if (!isOpen || !modalBoxRef.current) return;
    gsap.fromTo(
      modalBoxRef.current,
      { scale: 0.94, opacity: 0, y: 20 },
      { scale: 1, opacity: 1, y: 0, duration: 0.4, ease: 'power3.out' }
    );
  }, { dependencies: [isOpen] });

  if (!isOpen || !districtData) return null;

  const currentHabitation =
    habitations.find((h) => h.id === selectedHabitationId) || habitations[0];

  const pastDisasters: PastDisasterItem[] =
    liveDossier?.past_disasters && liveDossier.past_disasters.length > 0
      ? (liveDossier.past_disasters as PastDisasterItem[])
      : PRELOADED_DISASTERS[districtKey] || [];

  return (
    <div
      ref={containerRef}
      className={`fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 lg:p-10 bg-black/80 backdrop-blur-xl ${className}`}
      onClick={(e) => {
        if (e.target === containerRef.current) onClose();
      }}
    >
      <div
        ref={modalBoxRef}
        className="w-full max-w-5xl max-h-[92vh] glass-card bg-surface-0/95 dark:bg-[#0e261d]/95 border border-line dark:border-white/15 rounded-3xl p-5 sm:p-8 shadow-2xl flex flex-col relative overflow-y-auto text-ink dark:text-cream scrollbar-thin"
      >
        {/* 1. Header Bar with Danger Badge & Live Indicator */}
        <DistrictRiskHeader
          districtName={districtData.districtName}
          stateName={districtData.stateName}
          lgdCode={districtData.lgdCode}
          dangerLevel={districtData.dangerLevel}
          primaryHazard={districtData.primaryHazard}
          isLoading={isLoading}
          onClose={onClose}
        />

        {/* 2. Top Visual Photographic Corridor & Tourist Highlights */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 mb-5 items-stretch">
          <div className="lg:col-span-6 relative h-48 sm:h-56 rounded-2xl overflow-hidden border border-line dark:border-white/10 shadow-lg group">
            <Image
              src={districtData.previewImage}
              alt={districtData.regionName}
              fill
              sizes="(max-width: 1024px) 100vw, 50vw"
              className="object-cover transition-transform duration-700 group-hover:scale-105"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent" />
            <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between text-[11px] font-mono text-cream/90">
              <span className="bg-black/50 px-2.5 py-1 rounded-lg backdrop-blur-md">
                Geo-Coordinates: {districtData.coordinates.display.lat}
              </span>
              <span className="text-citron font-semibold">Autoritative DRR Data</span>
            </div>
          </div>

          <div className="lg:col-span-6 flex flex-col justify-between p-4 rounded-2xl bg-surface-1/60 dark:bg-white/5 border border-line dark:border-white/10">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-widest text-m3-accent-foliage font-semibold">
                District Tourist Profile
              </span>
              <h3 className="text-base sm:text-lg font-bold text-ink dark:text-cream mt-1 mb-2">
                {districtData.regionName}
              </h3>
              <p className="text-xs text-ink-muted dark:text-cream/70 leading-relaxed font-sans font-light">
                {districtData.shortSummary}
              </p>
            </div>

            <div className="mt-3">
              <span className="text-[10px] font-mono text-ink-muted dark:text-cream/50 uppercase tracking-wider block mb-1.5">
                Popular Tourist Destinations in Sector:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {districtData.popularTouristSpots.map((spot, idx) => (
                  <span
                    key={idx}
                    className="text-[11px] font-sans px-2.5 py-0.5 rounded-full bg-surface-2 dark:bg-white/10 text-ink dark:text-cream border border-line dark:border-white/10"
                  >
                    {spot}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* 3. Habitations / Tourist Spot Switcher */}
        <DistrictSpotSelector
          spots={habitations}
          selectedSpotId={selectedHabitationId}
          onSelectSpot={(id) => setSelectedHabitationId(id)}
          className="mb-5"
        />

        {/* 4. Telemetry Metrics from Live Backend */}
        <DistrictTelemetryGrid
          priorityScore={currentHabitation?.priority_score}
          przOverlapPct={currentHabitation?.prz_overlap_pct}
          dominantHazard={currentHabitation?.dominant_hazard || districtData.primaryHazard}
          population={currentHabitation?.population}
          vulnerabilityIndex={liveDossier?.vulnerability?.v_index}
          className="mb-5"
        />

        {/* 5. Travel Advisory & Geotechnical Rationale */}
        <TravelAdvisoryBanner
          tier={currentHabitation?.tier}
          spotName={currentHabitation?.name || districtData.districtName}
          districtName={districtData.districtName}
          rationale={liveDossier?.triage_rationale || districtData.touristAdvisory}
          className="mb-5"
        />

        {/* 6. Past Fatal Disaster Breaches */}
        <DistrictDisasterHistory disasters={pastDisasters} className="mb-5" />

        {/* 7. Modal Bottom Action Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between border-t border-line dark:border-white/10 pt-4 mt-2 gap-3">
          <div className="text-[11px] font-mono text-ink-muted dark:text-cream/60">
            <span>SETU-DRR Platform — Verified with Sentinel-1 SAR & InSAR Inundation Geodesy</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-surface-1 hover:bg-surface-2 dark:bg-white/10 dark:hover:bg-white/20 text-ink dark:text-cream text-xs font-mono transition-colors cursor-pointer border border-line dark:border-transparent"
            >
              Close Advisory
            </button>
            <Link
              href={`/workspace?admin=${districtData.adminId}`}
              className="px-4 py-2 rounded-xl bg-citron hover:bg-citron-hover text-[#06100c] font-semibold text-xs font-sans transition-transform hover:scale-105 active:scale-95 flex items-center gap-1.5 cursor-pointer shadow-md"
            >
              <span>View DRR Hex Map</span>
              <span className="material-symbols-outlined text-sm">open_in_new</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DistrictRiskModal;
