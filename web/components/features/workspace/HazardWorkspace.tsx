'use client';

import { useCallback, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';

import { Badge } from '@/components/ui/Badge';
import { ScreeningGradeNotice } from '@/components/common/ScreeningGradeNotice';
import {
  AppHeader,
  CenterPanel,
  LeftPanel,
  RightPanel,
  ThreePanelLayout,
} from '@/components/layout';
import { CellDossier } from '@/components/features/dossier';
import { TopRiskList } from '@/components/features/triage';
import { ForecastAlertPanel } from '@/components/features/forecast';
import { HazardLayerSelect } from '@/components/features/map/controls';
import { MapSkeleton } from '@/components/features/map/MapSkeleton';
import type { FloodHazardMapDisplayState } from '@/components/features/map/FloodHazardMap';
import { useHazardLayer } from '@/lib/hooks/useHazardLayer';
import { useHazardLayerList } from '@/lib/hooks/useHazardLayerList';
import { useForecastAlerts } from '@/lib/hooks/useForecastAlerts';
import type { HazardType } from '@/lib/api/types';
import {
  DEFAULT_CONFIDENCE_HATCH_THRESHOLD,
  HAZARD_LABELS,
  SOURCE_RESOLUTION,
} from '@/lib/map/constants';

import { LayerStatsPanel } from './LayerStatsPanel';

// MapLibre touches `window` at construction, so the map never renders on the server.
const FloodHazardMap = dynamic(
  () => import('@/components/features/map/FloodHazardMap').then((m) => m.FloodHazardMap),
  { ssr: false, loading: () => <MapSkeleton label="Initialising map…" /> },
);

export interface HazardWorkspaceProps {
  /** Layer shown on first load. */
  initialHazardType?: HazardType;
  /** Restricts the query to one district by admin id or LGD code. */
  admin?: number;
  title?: string;
  subtitle?: string;
  className?: string;
}

const DEFAULT_DISPLAY: FloodHazardMapDisplayState = {
  opacity: 0.65,
  showConfidenceHatch: true,
  confidenceThreshold: DEFAULT_CONFIDENCE_HATCH_THRESHOLD,
  showHardZero: true,
  showNoCoverage: true,
  resolution: SOURCE_RESOLUTION,
};

/** Full contract horizon; the API rejects anything above 72h. */
const DEFAULT_FORECAST_HORIZON_HOURS = 72;

/**
 * Top-level container for the hazard map screen.
 *
 * Holds every piece of shared state — active layer, selection, hover, display settings —
 * and passes it down. Nothing below this component fetches the layer itself.
 */
export const HazardWorkspace = ({
  initialHazardType = 'riverine_flood',
  admin,
  title = 'SETU-DRR',
  subtitle = 'Hazard red zone screening',
  className = '',
}: HazardWorkspaceProps) => {
  const [hazardType, setHazardType] = useState<HazardType>(initialHazardType);
  const [selectedH3, setSelectedH3] = useState<string | null>(null);
  const [hoveredH3, setHoveredH3] = useState<string | null>(null);
  const [display, setDisplay] = useState<FloodHazardMapDisplayState>(DEFAULT_DISPLAY);
  const [forecastHorizon, setForecastHorizon] = useState(DEFAULT_FORECAST_HORIZON_HOURS);
  const [showForecast, setShowForecast] = useState(true);

  const { layers: availableLayers, isLoading: layersLoading } = useHazardLayerList();

  const forecast = useForecastAlerts({ admin, horizonHours: forecastHorizon });

  const { data, cells, isLoading, error, refetch } = useHazardLayer({
    hazardType,
    admin,
    resolution: display.resolution,
    aggregation: 'max',
  });

  const handleDisplayChange = useCallback((next: Partial<FloodHazardMapDisplayState>) => {
    setDisplay((current) => ({ ...current, ...next }));
  }, []);

  const handleSelectLayer = useCallback((next: HazardType) => {
    setHazardType(next);
    setSelectedH3(null);
    setHoveredH3(null);
  }, []);

  const przThreshold = data?.legend.prz_susceptibility_threshold ?? 0.85;
  const breaks = useMemo(() => data?.legend.breaks ?? [], [data]);

  return (
    <ThreePanelLayout
      className={className}
      header={
        <AppHeader
          title={title}
          subtitle={subtitle}
          metaSlot={
            <>
              <Badge variant="info">{HAZARD_LABELS[hazardType] ?? hazardType}</Badge>
              {data ? <Badge variant="neutral">{data.model_version}</Badge> : null}
              {data?.truncated ? (
                <Badge variant="warning" title="The result set hit the request limit.">
                  Truncated
                </Badge>
              ) : null}
            </>
          }
        />
      }
      left={
        <LeftPanel>
          <div className="flex flex-col gap-4">
            <HazardLayerSelect
              layers={availableLayers}
              value={hazardType}
              isLoading={layersLoading}
              onValueChange={handleSelectLayer}
            />
            <LayerStatsPanel layer={data} isLoading={isLoading} />
            <TopRiskList
              cells={cells}
              breaks={breaks}
              przThreshold={przThreshold}
              selectedH3={selectedH3}
              onSelect={setSelectedH3}
              onHover={setHoveredH3}
            />
          </div>
        </LeftPanel>
      }
      center={
        <CenterPanel>
          <FloodHazardMap
            cells={cells}
            legend={data?.legend ?? null}
            coverage={data?.coverage ?? null}
            hazardType={hazardType}
            isLoading={isLoading}
            errorMessage={error?.message ?? null}
            errorCode={error?.code ?? null}
            requestId={error?.requestId ?? null}
            onRetry={refetch}
            selectedH3={selectedH3}
            hoveredH3={hoveredH3}
            onSelectCell={setSelectedH3}
            onHoverCell={setHoveredH3}
            display={display}
            onDisplayChange={handleDisplayChange}
            forecastItems={forecast.items}
            showForecastOverlay={showForecast}
            onForecastCellHover={(item) => setHoveredH3(item?.h3 ?? null)}
            onForecastCellClick={(item) => setSelectedH3(item?.h3 ?? null)}
          />
        </CenterPanel>
      }
      right={
        <RightPanel>
          <div className="flex flex-col gap-5">
            <ForecastAlertPanel
              items={forecast.items}
              rainfallDrivenItems={forecast.rainfallDrivenItems}
              forecastCycleAt={forecast.forecastCycleAt}
              totalExposedPopulation={forecast.data?.total_exposed_population ?? null}
              horizonHours={forecastHorizon}
              onHorizonChange={setForecastHorizon}
              overlayVisible={showForecast}
              onOverlayVisibleChange={setShowForecast}
              isLoading={forecast.isLoading}
              errorMessage={forecast.error?.message ?? null}
              onRetry={forecast.refetch}
            />
            <CellDossier h3={selectedH3} hazardType={hazardType} przThreshold={przThreshold} />
          </div>
        </RightPanel>
      }
      footer={<ScreeningGradeNotice notice={data?.screening_grade} />}
    />
  );
};
