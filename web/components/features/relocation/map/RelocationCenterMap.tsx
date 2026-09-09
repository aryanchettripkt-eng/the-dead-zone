'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { Map as MapLibreMap } from 'maplibre-gl';

import { MapContainer, type MapViewState } from '@/components/features/map/MapContainer';
import { useHazardHexLayers } from '@/components/features/map/layers/useHazardHexLayers';
import { useHazardLayer } from '@/lib/hooks/useHazardLayer';
import type {
  AllocationAssignment,
  AllocationPlanResponse,
  CandidateSiteItem,
  HabitationListItem,
} from '@/lib/api/types';

import { useRelocationArcLayers } from './layers/useRelocationArcLayers';
import { useRelocationFlowLayers } from './layers/useRelocationFlowLayers';

export interface RelocationCenterMapProps {
  habitation: HabitationListItem | null;
  sites: CandidateSiteItem[];
  selectedSiteId?: number | null;
  onSelectSite?: (site: CandidateSiteItem) => void;
  plan?: AllocationPlanResponse | null;
  habitations?: HabitationListItem[];
  onSelectAssignment?: (assignment: AllocationAssignment) => void;
  is3DMode: boolean;
  opacity: number;
  showConfidenceHatch: boolean;
  confidenceThreshold: number;
  showHardZero: boolean;
  showNoCoverage: boolean;
  className?: string;
}

const DEFAULT_CENTER: [number, number] = [76.155, 11.535]; // Mundakkai / Wayanad
const DEFAULT_INITIAL_VIEW: MapViewState = {
  longitude: DEFAULT_CENTER[0],
  latitude: DEFAULT_CENTER[1],
  zoom: 11.2,
  pitch: 52,
  bearing: -15,
};

export const RelocationCenterMap = ({
  habitation,
  sites,
  selectedSiteId,
  onSelectSite,
  plan = null,
  habitations = [],
  onSelectAssignment,
  is3DMode,
  opacity,
  showConfidenceHatch,
  confidenceThreshold,
  showHardZero,
  showNoCoverage,
  className = '',
}: RelocationCenterMapProps) => {
  const mapRef = useRef<MapLibreMap | null>(null);
  const radarMarkerRef = useRef<maplibregl.Marker | null>(null);

  // 1. Fetch background hazard cells (e.g. Wayanad / Kodagu landslides)
  const { data: hazardData, cells: hazardCells } = useHazardLayer({
    hazardType: 'landslide',
  });

  const breaks = useMemo(() => hazardData?.legend?.breaks ?? [0.2, 0.4, 0.6, 0.8], [hazardData]);
  const confidenceCeiling = hazardData?.legend?.confidence_ceiling ?? 1;

  // 2. Base Hazard Hex Layers
  const hexLayers = useHazardHexLayers({
    cells: hazardCells,
    breaks,
    confidenceCeiling,
    opacity,
    showConfidenceHatch,
    confidenceThreshold,
    showHardZero,
    showNoCoverage,
  });

  // 3. Candidate Corridors & Sites Arcs
  const arcLayers = useRelocationArcLayers({
    habitation,
    sites,
    selectedSiteId,
    onSelectSite,
  });

  // 4. Solved Allocation Flow Corridors
  const flowLayers = useRelocationFlowLayers({
    plan,
    habitations,
    sites,
    onSelectAssignment,
  });

  const allLayers = useMemo(() => {
    return [...hexLayers, ...arcLayers, ...flowLayers];
  }, [hexLayers, arcLayers, flowLayers]);

  // Handle map instance capture
  const handleMapLoad = useCallback((map: MapLibreMap) => {
    mapRef.current = map;
  }, []);

  // Camera flyTo on habitation selection
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !habitation?.centroid || habitation.centroid.length < 2) return;

    map.flyTo({
      center: [habitation.centroid[0], habitation.centroid[1]],
      zoom: 11.8,
      pitch: is3DMode ? 52 : 0,
      bearing: is3DMode ? -15 : 0,
      duration: 1000,
      essential: true,
    });
  }, [habitation, is3DMode]);

  // Camera easeTo on 3D/2D toggle
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    map.easeTo({
      pitch: is3DMode ? 52 : 0,
      bearing: is3DMode ? -15 : 0,
      duration: 700,
    });
  }, [is3DMode]);

  // Pulsing Radar Beacon DOM Marker
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (radarMarkerRef.current) {
      radarMarkerRef.current.remove();
      radarMarkerRef.current = null;
    }

    if (!habitation?.centroid || habitation.centroid.length < 2) return;

    // Create radar marker element
    const el = document.createElement('div');
    el.className = 'relocation-radar-marker';
    el.style.width = '36px';
    el.style.height = '36px';
    el.style.position = 'relative';
    el.style.pointerEvents = 'none';

    el.innerHTML = `
      <div style="position:absolute; inset:0; border-radius:50%; background:rgba(239, 68, 68, 0.4); animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
      <div style="position:absolute; inset:4px; border-radius:50%; background:rgba(239, 68, 68, 0.6); animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;"></div>
      <div style="position:absolute; inset:10px; border-radius:50%; background:#ef4444; border:2px solid #ffffff; box-shadow:0 0 12px rgba(239, 68, 68, 0.9);"></div>
    `;

    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([habitation.centroid[0], habitation.centroid[1]])
      .addTo(map);

    radarMarkerRef.current = marker;

    return () => {
      marker.remove();
    };
  }, [habitation]);

  return (
    <div className={['relative h-full w-full overflow-hidden', className].filter(Boolean).join(' ')}>
      <MapContainer
        layers={allLayers}
        initialViewState={DEFAULT_INITIAL_VIEW}
        onMapLoad={handleMapLoad}
      />
    </div>
  );
};
