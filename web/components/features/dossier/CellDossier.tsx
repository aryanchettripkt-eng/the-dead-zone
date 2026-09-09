'use client';

import React from 'react';
import { ErrorState } from '@/components/common/ErrorState';
import { ScreeningGradeNotice } from '@/components/common/ScreeningGradeNotice';
import { useHazardCellDetail } from '@/lib/hooks/useHazardCellDetail';
import { useForecastAlerts } from '@/lib/hooks/useForecastAlerts';
import type { HazardType, ForecastAlertItem } from '@/lib/api/types';

import { CoverageNotice } from './CoverageNotice';
import { DossierEmptyState } from './DossierEmptyState';
import { DossierHeader } from './DossierHeader';
import { DossierSkeleton } from './DossierSkeleton';
import { DriverBreakdown } from './DriverBreakdown';
import { CellMetricsBox } from './CellMetricsBox';

export interface CellDossierProps {
  /** Selected H3 index, or null for the empty state. */
  h3: string | null;
  hazardType?: HazardType;
  /** PRZ threshold used to colour the score card. */
  przThreshold?: number;
  /** Optional matching live forecast alert item for the selected cell */
  forecastAlert?: ForecastAlertItem | null;
  /** Optional complete list of forecast items */
  forecastItems?: ForecastAlertItem[];
  /** Optional callback to inspect Wayanad high risk cell from empty state */
  onInspectWayanad?: () => void;
  className?: string;
  classNames?: {
    root?: string;
    metrics?: string;
  };
}

/**
 * Right-panel dossier for the selected cell.
 *
 * Integrates static physical drivers and susceptibility/confidence with
 * real-time ECMWF / Open-Meteo live forecast data for Wayanad pilot cells.
 */
export const CellDossier: React.FC<CellDossierProps> = ({
  h3,
  hazardType = 'riverine_flood',
  przThreshold = 0.85,
  forecastAlert,
  forecastItems,
  onInspectWayanad,
  className = '',
  classNames = {},
}) => {
  const { detail, isLoading, error } = useHazardCellDetail(h3, hazardType);

  // Auto-fetch Wayanad forecast alerts if not provided by parent
  const internalForecast = useForecastAlerts({
    admin: 178,
    enabled: !forecastItems || forecastItems.length === 0,
  });

  const effectiveForecastItems = forecastItems && forecastItems.length > 0
    ? forecastItems
    : internalForecast.items;

  const resolvedForecastAlert =
    forecastAlert ??
    (h3 ? effectiveForecastItems.find((item) => item.h3 === h3) ?? null : null);

  const isWayanadDistrict =
    detail?.admin_name?.toLowerCase().includes('wayanad') ?? false;

  if (!h3) {
    return (
      <DossierEmptyState
        onInspectWayanad={onInspectWayanad}
        hasWayanadForecast={effectiveForecastItems.length > 0}
        wayanadForecastCount={effectiveForecastItems.length}
        className={className}
      />
    );
  }

  if (isLoading) return <DossierSkeleton className={className} />;

  if (error) {
    return (
      <ErrorState
        title="Cell unavailable"
        message={error.message}
        code={error.code}
        requestId={error.requestId}
        className={className}
      />
    );
  }

  if (!detail) {
    return (
      <DossierEmptyState
        onInspectWayanad={onInspectWayanad}
        hasWayanadForecast={effectiveForecastItems.length > 0}
        wayanadForecastCount={effectiveForecastItems.length}
        className={className}
      />
    );
  }

  return (
    <div
      className={['flex flex-col gap-3.5', classNames.root ?? '', className]
        .filter(Boolean)
        .join(' ')}
    >
      <DossierHeader detail={detail} />

      <CoverageNotice flag={detail.quality_flag} />

      {/* Information Box with Susceptibility, Confidence, and Wayanad Live Forecast */}
      <CellMetricsBox
        detail={detail}
        przThreshold={przThreshold}
        forecastAlert={resolvedForecastAlert}
        districtForecastActive={isWayanadDistrict}
        districtForecastSummary={{
          totalCells: internalForecast.data?.total_forecast_cells ?? effectiveForecastItems.length,
          totalExposed: internalForecast.data?.total_exposed_population ?? undefined,
          cycleAt: internalForecast.forecastCycleAt,
          horizonHours: internalForecast.data?.horizon_hours,
        }}
        classNames={{ root: classNames.metrics }}
      />

      {detail.drivers ? <DriverBreakdown drivers={detail.drivers} /> : null}

      <ScreeningGradeNotice notice={detail.screening_grade} className="rounded-xl border" />
    </div>
  );
};
