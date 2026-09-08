'use client';

import { useMemo } from 'react';
import type { Layer, PickingInfo } from '@deck.gl/core';
import { H3HexagonLayer } from '@deck.gl/geo-layers';

import type { ForecastAlertItem } from '@/lib/api/types';
import {
  FORECAST_BASELINE_OUTLINE_COLOR,
  FORECAST_DRIVEN_FILL_COLOR,
  FORECAST_DRIVEN_OUTLINE_COLOR,
  type RGBAColor,
} from '@/lib/map/constants';

export interface UseForecastHexLayersOptions {
  items: ForecastAlertItem[];
  /** Hides the whole overlay without unmounting the map. */
  visible?: boolean;
  /** Fill opacity multiplier in [0, 1]. */
  opacity?: number;
  /**
   * Draws cells sitting at their static baseline as outlines. Turning this off leaves only
   * genuine rainfall-driven exceedances on screen.
   */
  showBaselineCells?: boolean;
  drivenFillColor?: RGBAColor;
  drivenOutlineColor?: RGBAColor;
  baselineOutlineColor?: RGBAColor;
  onCellClick?: (item: ForecastAlertItem | null) => void;
  onCellHover?: (item: ForecastAlertItem | null) => void;
}

/** A forecast cell counts as rainfall-driven only when the trigger lifted it above static. */
export function isRainfallDriven(item: ForecastAlertItem): boolean {
  return (item.mhi_fcst ?? 0) > (item.mhi_static ?? 0) + 1e-6;
}

/**
 * Builds the Forecast Alert Zone overlay, drawn above the static susceptibility stack.
 *
 * Cells are split by whether the forecast trigger actually moved them. Cells still at their
 * static floor are outlined rather than filled — they appear in the API response because
 * `mhi_fcst` defaults to the static baseline, not because rain is predicted on them.
 */
export function useForecastHexLayers(options: UseForecastHexLayersOptions): Layer[] {
  const {
    items,
    visible = true,
    opacity = 1,
    showBaselineCells = true,
    drivenFillColor = FORECAST_DRIVEN_FILL_COLOR,
    drivenOutlineColor = FORECAST_DRIVEN_OUTLINE_COLOR,
    baselineOutlineColor = FORECAST_BASELINE_OUTLINE_COLOR,
    onCellClick,
    onCellHover,
  } = options;

  const { driven, baseline } = useMemo(() => {
    const groups = { driven: [] as ForecastAlertItem[], baseline: [] as ForecastAlertItem[] };
    for (const item of items) {
      if (isRainfallDriven(item)) groups.driven.push(item);
      else groups.baseline.push(item);
    }
    return groups;
  }, [items]);

  return useMemo(() => {
    if (!visible) return [];

    const layers: Layer[] = [];
    const handleClick = (info: PickingInfo) =>
      onCellClick?.((info.object as ForecastAlertItem | undefined) ?? null);
    const handleHover = (info: PickingInfo) =>
      onCellHover?.((info.object as ForecastAlertItem | undefined) ?? null);

    // 1. Cells listed at their static floor: outline only. A fill here would assert a
    //    forecast exceedance the weather model never produced.
    if (showBaselineCells && baseline.length > 0) {
      layers.push(
        new H3HexagonLayer<ForecastAlertItem>({
          id: 'forecast-hex-baseline',
          data: baseline,
          getHexagon: (item) => item.h3,
          filled: false,
          stroked: true,
          extruded: false,
          getLineColor: baselineOutlineColor,
          getLineWidth: 1,
          lineWidthUnits: 'pixels',
          lineWidthMinPixels: 1,
          pickable: true,
          onClick: handleClick,
          onHover: handleHover,
        }),
      );
    }

    // 2. Genuine rainfall-driven exceedances, filled and outlined so they read as alerts.
    if (driven.length > 0) {
      layers.push(
        new H3HexagonLayer<ForecastAlertItem>({
          id: 'forecast-hex-driven',
          data: driven,
          getHexagon: (item) => item.h3,
          getFillColor: [
            drivenFillColor[0],
            drivenFillColor[1],
            drivenFillColor[2],
            Math.round(drivenFillColor[3] * opacity),
          ],
          filled: true,
          stroked: true,
          extruded: false,
          getLineColor: drivenOutlineColor,
          getLineWidth: 1.5,
          lineWidthUnits: 'pixels',
          lineWidthMinPixels: 1.5,
          pickable: true,
          onClick: handleClick,
          onHover: handleHover,
          updateTriggers: { getFillColor: [opacity, drivenFillColor] },
        }),
      );
    }

    return layers;
  }, [
    visible,
    driven,
    baseline,
    opacity,
    showBaselineCells,
    drivenFillColor,
    drivenOutlineColor,
    baselineOutlineColor,
    onCellClick,
    onCellHover,
  ]);
}
