'use client';

import type { ReactNode } from 'react';

import type { ForecastAlertItem } from '@/lib/api/types';
import { Toggle } from '@/components/ui/Toggle';

import { ForecastCycleBadge } from './ForecastCycleBadge';
import { ForecastHorizonSlider } from './ForecastHorizonSlider';
import { ForecastSignalNotice, type ForecastSignalState } from './ForecastSignalNotice';
import { ForecastStatRow, type ForecastStat } from './ForecastStatRow';

export interface ForecastAlertPanelProps {
  items: ForecastAlertItem[];
  rainfallDrivenItems: ForecastAlertItem[];
  forecastCycleAt?: string | null;
  totalExposedPopulation?: number | null;
  horizonHours: number;
  onHorizonChange?: (hours: number) => void;
  /** Overlay visibility, lifted so the map and this panel stay in sync. */
  overlayVisible?: boolean;
  onOverlayVisibleChange?: (visible: boolean) => void;
  isLoading?: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
  title?: ReactNode;
  /** Overrides the district label; defaults to the first `admin_name` in the response. */
  areaLabel?: ReactNode;
  thresholdMmPerHour?: number;
  className?: string;
  classNames?: { root?: string; header?: string; body?: string };
}

function formatCount(value: number | null | undefined): string {
  return typeof value === 'number' ? value.toLocaleString() : '—';
}

/**
 * Forecast Alert Zone panel: cycle provenance, lead-time control, and an explicit statement
 * of whether the cycle carries a rainfall signal at all.
 *
 * Purely presentational — data arrives via props so the panel can be driven by the hook,
 * a fixture, or a story without change.
 */
export const ForecastAlertPanel = ({
  items,
  rainfallDrivenItems,
  forecastCycleAt = null,
  totalExposedPopulation = null,
  horizonHours,
  onHorizonChange,
  overlayVisible = true,
  onOverlayVisibleChange,
  isLoading = false,
  errorMessage = null,
  onRetry,
  title = 'Forecast alert zones',
  areaLabel = null,
  thresholdMmPerHour = 10,
  className = '',
  classNames = {},
}: ForecastAlertPanelProps) => {
  const signalState: ForecastSignalState = !forecastCycleAt
    ? 'no-cycle'
    : rainfallDrivenItems.length > 0
      ? 'driven'
      : 'flat';

  const stats: ForecastStat[] = [
    { key: 'cells', label: 'Cells at threshold', value: formatCount(items.length) },
    {
      key: 'driven',
      label: 'Rainfall-driven',
      value: formatCount(rainfallDrivenItems.length),
      muted: rainfallDrivenItems.length === 0,
    },
    { key: 'population', label: 'Exposed people', value: formatCount(totalExposedPopulation) },
    { key: 'lead', label: 'Lead window', value: `+1h–${horizonHours}h` },
  ];

  return (
    <section
      className={['flex flex-col gap-3', classNames.root ?? '', className].filter(Boolean).join(' ')}
    >
      <header className={['flex items-center justify-between gap-2', classNames.header ?? ''].join(' ')}>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">{title}</h3>
        <Toggle
          checked={overlayVisible}
          onCheckedChange={onOverlayVisibleChange}
          label="Overlay"
        />
      </header>

      <div className={['flex flex-col gap-3', classNames.body ?? ''].join(' ')}>
        <ForecastCycleBadge
          forecastCycleAt={forecastCycleAt}
          horizonHours={horizonHours}
          areaLabel={areaLabel ?? items.find((item) => item.admin_name)?.admin_name ?? null}
        />

        {errorMessage ? (
          <div className="rounded-xl border border-danger/45 bg-danger/10 px-3 py-2">
            <p className="text-[11px] font-semibold text-ink dark:text-text-primary">
              Forecast unavailable
            </p>
            <p className="mt-1 text-[10px] leading-relaxed text-text-secondary">{errorMessage}</p>
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="mt-2 rounded-lg border border-line px-2 py-1 text-[10px] font-semibold text-ink transition-colors hover:bg-surface-1 dark:border-white/15 dark:text-text-primary"
              >
                Retry
              </button>
            ) : null}
          </div>
        ) : (
          <>
            <ForecastStatRow stats={stats} />
            <ForecastSignalNotice
              state={signalState}
              drivenCount={rainfallDrivenItems.length}
              totalCount={items.length}
              thresholdMmPerHour={thresholdMmPerHour}
            />
          </>
        )}

        <ForecastHorizonSlider
          value={horizonHours}
          disabled={isLoading || !forecastCycleAt}
          onValueChange={onHorizonChange}
        />
      </div>
    </section>
  );
};
