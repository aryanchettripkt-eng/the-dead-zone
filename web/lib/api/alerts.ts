/** Alert-zone endpoints: active dynamic triggers and forecast threshold crossings. */

import { apiGet } from './client';
import type { ActiveAlertsResponse, ForecastAlertsResponse } from './types';

export interface FetchForecastAlertsParams {
  /** Admin id or LGD code (Wayanad pilot = 555). Omit for the national view. */
  admin?: number;
  /** Lead-time window in hours; the API bounds this to [1, 72]. */
  horizonHours?: number;
  /** Minimum forecast MHI to qualify as an alert. API default is 0.75. */
  minMhi?: number;
  limit?: number;
  offset?: number;
}

/**
 * Forecast Alert Zones (FAZ) for a forecast cycle.
 *
 * The API resolves the latest cycle whose `pipeline_run` reached READY, so a run still
 * writing rows is never served half-ingested.
 */
export function fetchForecastAlerts(
  params: FetchForecastAlertsParams = {},
  signal?: AbortSignal,
): Promise<ForecastAlertsResponse> {
  const { admin, horizonHours, minMhi, limit, offset } = params;
  return apiGet<ForecastAlertsResponse>(
    '/alerts/forecast',
    {
      admin,
      horizon: horizonHours,
      min_mhi: minMhi,
      limit,
      offset,
    },
    signal,
  );
}

export interface FetchActiveAlertsParams {
  admin?: number;
  minMhi?: number;
  dominantHazard?: string;
  limit?: number;
  offset?: number;
}

/** Currently active dynamic alert cells (observed triggers within the freshness window). */
export function fetchActiveAlerts(
  params: FetchActiveAlertsParams = {},
  signal?: AbortSignal,
): Promise<ActiveAlertsResponse> {
  const { admin, minMhi, dominantHazard, limit, offset } = params;
  return apiGet<ActiveAlertsResponse>(
    '/alerts/active',
    {
      admin,
      min_mhi: minMhi,
      dominant_hazard: dominantHazard,
      limit,
      offset,
    },
    signal,
  );
}
