'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { fetchForecastAlerts, type FetchForecastAlertsParams } from '@/lib/api/alerts';
import { ApiError } from '@/lib/api/client';
import type { ForecastAlertItem, ForecastAlertsResponse } from '@/lib/api/types';

export interface UseForecastAlertsOptions extends FetchForecastAlertsParams {
  enabled?: boolean;
  /** Debounce applied before refetching, so dragging the horizon slider issues one request. */
  debounceMs?: number;
}

export interface UseForecastAlertsResult {
  data: ForecastAlertsResponse | null;
  items: ForecastAlertItem[];
  isLoading: boolean;
  error: ApiError | null;
  /** Cycle anchor the API resolved, or null when no READY cycle exists. */
  forecastCycleAt: string | null;
  /**
   * Cells whose forecast MHI actually exceeds their static baseline — i.e. the ones the
   * rainfall trigger moved. When this is empty but `items` is not, every listed cell is at
   * its static floor and the forecast contributed no signal this cycle.
   */
  rainfallDrivenItems: ForecastAlertItem[];
  /** True when a cycle is loaded and no cell was moved by rainfall. */
  isRainfallSignalFlat: boolean;
  refetch: () => void;
}

interface AlertState {
  key: string;
  data: ForecastAlertsResponse | null;
  error: ApiError | null;
}

/**
 * Loads Forecast Alert Zones for a cycle and separates rainfall-driven exceedances from
 * cells merely sitting at their static baseline.
 *
 * That split matters: `mhi_fcst` falls back to the static hazard floor when a cell has no
 * forecast trigger, so a populated response does not by itself mean the weather model
 * predicted anything. Callers should render the distinction rather than hide it.
 */
export function useForecastAlerts(options: UseForecastAlertsOptions = {}): UseForecastAlertsResult {
  const {
    admin,
    horizonHours = 72,
    minMhi,
    limit = 500,
    offset,
    enabled = true,
    debounceMs = 250,
  } = options;

  const [state, setState] = useState<AlertState | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const requestKey = [admin ?? '', horizonHours, minMhi ?? '', limit, offset ?? '', reloadToken].join('|');

  useEffect(() => {
    if (!enabled) return;

    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetchForecastAlerts({ admin, horizonHours, minMhi, limit, offset }, controller.signal)
        .then((data) => {
          if (controller.signal.aborted) return;
          setState({ key: requestKey, data, error: null });
        })
        .catch((cause: unknown) => {
          if (controller.signal.aborted) return;
          if (cause instanceof DOMException && cause.name === 'AbortError') return;
          setState({
            key: requestKey,
            data: null,
            error:
              cause instanceof ApiError
                ? cause
                : new ApiError('Unexpected error loading forecast alerts.', 0, 'INTERNAL_ERROR'),
          });
        });
    }, debounceMs);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [admin, horizonHours, minMhi, limit, offset, enabled, debounceMs, requestKey]);

  const items = useMemo(() => state?.data?.items ?? [], [state]);

  const rainfallDrivenItems = useMemo(
    () => items.filter((item) => (item.mhi_fcst ?? 0) > (item.mhi_static ?? 0) + 1e-6),
    [items],
  );

  const refetch = useCallback(() => setReloadToken((token) => token + 1), []);

  return {
    data: state?.data ?? null,
    items,
    isLoading: enabled && state?.key !== requestKey,
    error: state?.error ?? null,
    forecastCycleAt: state?.data?.forecast_cycle_at ?? null,
    rainfallDrivenItems,
    isRainfallSignalFlat: Boolean(state?.data) && rainfallDrivenItems.length === 0,
    refetch,
  };
}
