'use client';

import React, { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import { MetricCard } from '@/components/common/MetricCard';
import type { HazardCellDetail, ForecastAlertItem } from '@/lib/api/types';

export interface CellMetricsBoxProps {
  /** The static hazard cell detail dossier */
  detail: HazardCellDetail;
  /** PRZ threshold used to colour the score card */
  przThreshold?: number;
  /** Live forecast alert item if this cell matches the forecast system */
  forecastAlert?: ForecastAlertItem | null;
  /** True if the cell's district has an active forecast run (e.g. Wayanad) */
  districtForecastActive?: boolean;
  /** District-wide forecast summary statistics */
  districtForecastSummary?: {
    totalCells?: number;
    totalExposed?: number;
    cycleAt?: string | null;
    horizonHours?: number;
  } | null;
  className?: string;
  classNames?: {
    root?: string;
    grid?: string;
    telemetry?: string;
  };
}

/**
 * Information box rendering Susceptibility and Confidence alongside live forecast data.
 *
 * For Wayanad pilot cells, integrates real-time ECMWF / Open-Meteo numerical weather
 * prediction data (mhi_fcst, lead horizon, delta signal, and exposed population)
 * with the static susceptibility and normalised confidence scores.
 */
export const CellMetricsBox: React.FC<CellMetricsBoxProps> = ({
  detail,
  przThreshold = 0.85,
  forecastAlert,
  districtForecastActive = false,
  districtForecastSummary,
  className = '',
  classNames = {},
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      if (!containerRef.current) return;
      gsap.from('[data-metric-elem]', {
        y: 8,
        opacity: 0,
        duration: 0.35,
        stagger: 0.04,
        ease: 'power2.out',
      });
    },
    { scope: containerRef, dependencies: [detail.h3, forecastAlert?.h3] },
  );

  const scoreVariant =
    detail.quality_flag === 'no_coverage'
      ? 'default'
      : detail.susceptibility >= przThreshold
        ? 'critical'
        : detail.susceptibility >= 0.58
          ? 'warning'
          : 'safe';

  const isWayanad =
    detail.admin_name?.toLowerCase().includes('wayanad') ||
    forecastAlert?.admin_name?.toLowerCase().includes('wayanad') ||
    districtForecastActive;

  const hasLiveForecast = Boolean(forecastAlert);
  const mhiFcst = forecastAlert?.mhi_fcst ?? null;
  const mhiStatic = forecastAlert?.mhi_static ?? detail.susceptibility;
  const delta = mhiFcst !== null ? mhiFcst - mhiStatic : null;
  const isRainfallDriven = delta !== null && delta > 0.0005;

  const forecastVariant =
    mhiFcst !== null && mhiFcst >= 0.75
      ? 'critical'
      : mhiFcst !== null && mhiFcst >= 0.58
        ? 'warning'
        : 'info';

  const validTimeStr = forecastAlert?.valid_at
    ? new Date(forecastAlert.valid_at).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }) + ' UTC'
    : null;

  return (
    <div
      ref={containerRef}
      className={['flex flex-col gap-2.5', classNames.root ?? '', className]
        .filter(Boolean)
        .join(' ')}
    >
      {/* Live Forecast Telemetry Strip for Wayanad Pilot Zone */}
      {(hasLiveForecast || isWayanad) && (
        <div
          data-metric-elem
          className={[
            'rounded-xl border p-2.5 transition-all text-xs',
            hasLiveForecast
              ? 'bg-crimson/5 dark:bg-crimson/10 border-crimson/30 text-text-primary'
              : 'bg-surface-1/80 border-line text-text-secondary',
            classNames.telemetry ?? '',
          ].join(' ')}
        >
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <div className="flex items-center gap-1.5 font-mono font-semibold tracking-wide text-[11px]">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-crimson opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-crimson"></span>
              </span>
              <span className="text-crimson dark:text-red-400 uppercase font-bold">
                {hasLiveForecast
                  ? 'Wayanad Live Forecast Active'
                  : 'Wayanad Pilot Sector Active'}
              </span>
            </div>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-2 text-text-muted border border-line">
              ECMWF 72h
            </span>
          </div>

          <div className="flex items-center justify-between text-[10px] font-mono text-text-muted">
            <span>
              {hasLiveForecast
                ? `Hazard: ${(forecastAlert?.dominant_hazard ?? 'landslide').toUpperCase()}`
                : 'Hazard: LANDSLIDE & RUNOFF'}
            </span>
            <span>
              {validTimeStr ? `Valid thru ${validTimeStr}` : 'Cycle Synced'}
            </span>
          </div>
        </div>
      )}

      {/* Primary Metrics Grid: Susceptibility & Confidence */}
      <div
        className={[
          'grid grid-cols-2 gap-2',
          classNames.grid ?? '',
        ].join(' ')}
      >
        {/* Metric 1: Susceptibility */}
        <div data-metric-elem>
          <MetricCard
            label="Susceptibility"
            value={detail.susceptibility}
            numericValue={detail.susceptibility}
            formatNumeric={(v) => v.toFixed(3)}
            variant={scoreVariant}
            description={
              detail.quality_flag === 'no_coverage'
                ? 'Filled, not measured.'
                : hasLiveForecast
                  ? `Static Baseline · PRZ ≥ ${przThreshold.toFixed(2)}`
                  : `PRZ threshold ${przThreshold.toFixed(2)}`
            }
          />
        </div>

        {/* Metric 2: Confidence */}
        <div data-metric-elem>
          <MetricCard
            label="Confidence"
            value={detail.confidence_normalised}
            numericValue={detail.confidence_normalised}
            formatNumeric={(v) => `${Math.round(v * 100)}%`}
            variant="info"
            description={`Raw ${detail.confidence.toFixed(3)}, normalised against layer ceiling.`}
          />
        </div>

        {/* Live Forecast Metric Cards when Forecast Data exists */}
        {hasLiveForecast && forecastAlert && (
          <>
            {/* Metric 3: Live Forecast MHI */}
            <div data-metric-elem>
              <MetricCard
                label={
                  <span className="flex items-center gap-1.5 font-bold text-crimson dark:text-red-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-crimson animate-pulse" />
                    <span>Live Forecast MHI</span>
                  </span>
                }
                value={forecastAlert.mhi_fcst}
                numericValue={forecastAlert.mhi_fcst}
                formatNumeric={(v) => v.toFixed(4)}
                variant={forecastVariant}
                description={
                  forecastAlert.mhi_fcst >= 0.75
                    ? `Crosses Emergency Threshold (≥ 0.75)`
                    : `Below Emergency Cutoff (0.75)`
                }
              />
            </div>

            {/* Metric 4: Forecast Lead / Delta Signal */}
            <div data-metric-elem>
              <MetricCard
                label="Forecast Signal & Lead"
                value={
                  isRainfallDriven
                    ? `+${(delta ?? 0).toFixed(3)} Δ`
                    : `+${forecastAlert.horizon_hours}h Lead`
                }
                variant={isRainfallDriven ? 'warning' : 'safe'}
                description={
                  isRainfallDriven
                    ? `Rainfall exceedance over static floor`
                    : `Concurs with static floor · +${forecastAlert.horizon_hours}h`
                }
              />
            </div>
          </>
        )}

        {/* Metric 5: Estimated Population & Forecast Sector Exposure */}
        <div data-metric-elem className="col-span-2">
          <MetricCard
            label="Est. Population"
            value={
              detail.population !== null && detail.population !== undefined
                ? Math.round(detail.population).toLocaleString()
                : '0'
            }
            numericValue={detail.population ?? 0}
            formatNumeric={(v) => Math.round(v).toLocaleString()}
            variant={
              detail.population && detail.population > 500
                ? 'warning'
                : 'default'
            }
            description={
              hasLiveForecast && forecastAlert?.exposed_population
                ? `${Math.round(detail.population ?? 0).toLocaleString()} in cell · ${Math.round(
                    forecastAlert.exposed_population,
                  ).toLocaleString()} exposed in forecast alert sector`
                : districtForecastSummary?.totalExposed
                  ? `${Math.round(detail.population ?? 0).toLocaleString()} in cell · ${districtForecastSummary.totalExposed.toLocaleString()} exposed across Wayanad forecast alert zone`
                  : 'WorldPop 100m constrained sum across hexagon'
            }
          />
        </div>
      </div>
    </div>
  );
};
