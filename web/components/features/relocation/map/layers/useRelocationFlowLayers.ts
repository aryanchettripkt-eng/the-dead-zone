'use client';

import { useMemo } from 'react';
import type { Layer } from '@deck.gl/core';
import { ArcLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';

import type {
  AllocationAssignment,
  AllocationPlanResponse,
  CandidateSiteItem,
  HabitationListItem,
} from '@/lib/api/types';

export interface UseRelocationFlowLayersOptions {
  plan: AllocationPlanResponse | null;
  habitations: HabitationListItem[];
  sites: CandidateSiteItem[];
  onSelectAssignment?: (assignment: AllocationAssignment) => void;
  visible?: boolean;
}

interface FlowData {
  assignment: AllocationAssignment;
  source: [number, number];
  target: [number, number];
  households: number;
  width: number;
}

export function useRelocationFlowLayers({
  plan,
  habitations,
  sites,
  onSelectAssignment,
  visible = true,
}: UseRelocationFlowLayersOptions): Layer[] {
  const flowData = useMemo<FlowData[]>(() => {
    const assignments = plan?.assignments ?? [];
    if (!visible || !plan || !assignments.length) return [];

    const habitationsMap = new Map<number, HabitationListItem>();
    for (const h of habitations) habitationsMap.set(h.id, h);

    const sitesMap = new Map<number, CandidateSiteItem>();
    for (const s of sites) sitesMap.set(s.id, s);

    const flows: FlowData[] = [];
    for (const assignment of assignments) {
      const hab = habitationsMap.get(assignment.habitation_id);
      const site = sitesMap.get(assignment.site_id);

      if (
        hab?.centroid &&
        hab.centroid.length >= 2 &&
        site?.centroid &&
        site.centroid.length >= 2
      ) {
        const hh = assignment.households;
        // Scale width with log2 of households
        const width = Math.max(3, Math.min(12, Math.log2(Math.max(2, hh)) * 1.8));
        flows.push({
          assignment,
          source: [hab.centroid[0], hab.centroid[1]],
          target: [site.centroid[0], site.centroid[1]],
          households: hh,
          width,
        });
      }
    }

    return flows;
  }, [visible, plan, habitations, sites]);

  const layers = useMemo<Layer[]>(() => {
    if (!flowData.length) return [];

    return [
      // Solved Glowing Flow Corridors
      new ArcLayer<FlowData>({
        id: 'relocation-solved-flow-arcs',
        data: flowData,
        getSourcePosition: (d) => d.source,
        getTargetPosition: (d) => d.target,
        getSourceColor: [16, 185, 129, 240], // Vibrant emerald
        getTargetColor: [56, 189, 248, 255], // Vibrant cyan
        getWidth: (d) => d.width,
        getHeight: 0.35,
        pickable: true,
        onClick: (info) => {
          if (info.object?.assignment && onSelectAssignment) {
            onSelectAssignment(info.object.assignment);
          }
        },
      }),

      // Destination Household Badges
      new ScatterplotLayer<FlowData>({
        id: 'relocation-flow-target-points',
        data: flowData,
        getPosition: (d) => d.target,
        getFillColor: [56, 189, 248, 240],
        getRadius: 160,
        radiusMinPixels: 8,
        radiusMaxPixels: 22,
        stroked: true,
        getLineColor: [255, 255, 255, 255],
        lineWidthMinPixels: 2,
      }),

      new TextLayer<FlowData>({
        id: 'relocation-flow-labels',
        data: flowData,
        getPosition: (d) => d.target,
        getText: (d) => `+${d.households} HH`,
        getSize: 12,
        getColor: [255, 255, 255, 255],
        getBackgroundColor: [6, 78, 59, 220],
        background: true,
        backgroundPadding: [4, 2],
        getTextAnchor: 'middle',
        getAlignmentBaseline: 'top',
        getPixelOffset: [0, 10],
        fontFamily: 'JetBrains Mono, monospace',
        fontWeight: 'bold',
      }),
    ];
  }, [flowData, onSelectAssignment]);

  return layers;
}
