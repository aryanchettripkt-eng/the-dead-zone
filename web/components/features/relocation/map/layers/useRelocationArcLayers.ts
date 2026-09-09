'use client';

import { useMemo } from 'react';
import type { Layer } from '@deck.gl/core';
import { ArcLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';

import type { CandidateSiteItem, HabitationListItem } from '@/lib/api/types';

export interface UseRelocationArcLayersOptions {
  habitation: HabitationListItem | null;
  sites: CandidateSiteItem[];
  selectedSiteId?: number | null;
  onSelectSite?: (site: CandidateSiteItem) => void;
  visible?: boolean;
}

interface ArcData {
  site: CandidateSiteItem;
  source: [number, number];
  target: [number, number];
  distanceKm: number;
  allocatable: boolean;
  status: string;
}

export function useRelocationArcLayers({
  habitation,
  sites,
  selectedSiteId,
  onSelectSite,
  visible = true,
}: UseRelocationArcLayersOptions): Layer[] {
  const originCentroid = useMemo<[number, number] | null>(() => {
    if (!habitation?.centroid || habitation.centroid.length < 2) return null;
    return [habitation.centroid[0], habitation.centroid[1]];
  }, [habitation]);

  const arcData = useMemo<ArcData[]>(() => {
    if (!originCentroid || !sites.length) return [];
    return sites
      .filter((site) => site.centroid && site.centroid.length >= 2)
      .map((site) => ({
        site,
        source: originCentroid,
        target: [site.centroid[0], site.centroid[1]] as [number, number],
        distanceKm: site.distance_km,
        allocatable: site.allocatable,
        status: site.eligibility_status,
      }));
  }, [originCentroid, sites]);

  const layers = useMemo<Layer[]>(() => {
    if (!visible || !originCentroid) return [];

    const result: Layer[] = [];

    // 1. Origin Habitation Beacon Dot
    result.push(
      new ScatterplotLayer({
        id: 'relocation-origin-beacon',
        data: [{ position: originCentroid, name: habitation?.name }],
        getPosition: (d: { position: [number, number] }) => d.position,
        getFillColor: [239, 68, 68, 240],
        getRadius: 180,
        radiusMinPixels: 8,
        radiusMaxPixels: 24,
        stroked: true,
        getLineColor: [255, 255, 255, 220],
        lineWidthMinPixels: 2,
        pickable: true,
      }),
    );

    if (arcData.length > 0) {
      // 2. 3D Parabolic Glowing Arcs
      result.push(
        new ArcLayer<ArcData>({
          id: 'relocation-corridor-arcs',
          data: arcData,
          getSourcePosition: (d) => d.source,
          getTargetPosition: (d) => d.target,
          getSourceColor: [239, 68, 68, 220],
          getTargetColor: (d) =>
            d.allocatable
              ? [132, 204, 22, 240] // Safe / Allocatable green
              : d.status === 'unknown'
                ? [245, 158, 11, 220] // Warning amber
                : [239, 68, 68, 180], // Excluded red
          getWidth: (d) => (d.site.id === selectedSiteId ? 5 : 3.5),
          getHeight: 0.28,
          pickable: true,
          onClick: (info) => {
            if (info.object?.site && onSelectSite) {
              onSelectSite(info.object.site);
            }
          },
        }),
      );

      // 3. Destination Parcel Nodes
      result.push(
        new ScatterplotLayer<ArcData>({
          id: 'relocation-destination-nodes',
          data: arcData,
          getPosition: (d) => d.target,
          getFillColor: (d) =>
            d.allocatable
              ? [132, 204, 22, 240]
              : d.status === 'unknown'
                ? [245, 158, 11, 220]
                : [239, 68, 68, 180],
          getRadius: 120,
          radiusMinPixels: 6,
          radiusMaxPixels: 18,
          stroked: true,
          getLineColor: [255, 255, 255, 240],
          lineWidthMinPixels: 1.5,
          getLineWidth: (d: ArcData) => (d.site.id === selectedSiteId ? 3 : 1.5),
          pickable: true,
          onClick: (info) => {
            if (info.object?.site && onSelectSite) {
              onSelectSite(info.object.site);
            }
          },
        }),
      );

      // 4. Distance Chips / Labels
      result.push(
        new TextLayer<ArcData>({
          id: 'relocation-destination-labels',
          data: arcData,
          getPosition: (d) => d.target,
          getText: (d) => `${d.distanceKm.toFixed(1)} km`,
          getSize: 11,
          getColor: [255, 255, 255, 255],
          getBackgroundColor: [15, 23, 42, 200],
          background: true,
          backgroundPadding: [4, 2],
          getTextAnchor: 'middle',
          getAlignmentBaseline: 'bottom',
          getPixelOffset: [0, -10],
          fontFamily: 'JetBrains Mono, monospace',
        }),
      );
    }

    return result;
  }, [visible, originCentroid, arcData, habitation, selectedSiteId, onSelectSite]);

  return layers;
}
