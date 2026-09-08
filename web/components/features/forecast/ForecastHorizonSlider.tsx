'use client';

import type { ReactNode } from 'react';

import { Slider } from '@/components/ui/Slider';

export interface ForecastHorizonSliderProps {
  /** Lead-time window in hours. */
  value: number;
  label?: ReactNode;
  description?: ReactNode;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  onValueChange?: (hours: number) => void;
  className?: string;
  classNames?: {
    root?: string;
    label?: string;
    value?: string;
    track?: string;
    description?: string;
  };
  animation?: {
    disabled?: boolean;
    duration?: number;
  };
}

/** Formats an hour count as a lead time, e.g. `+18h` or `+2d 4h`. */
export function formatLeadTime(hours: number): string {
  if (hours < 24) return `+${hours}h`;
  const days = Math.floor(hours / 24);
  const rest = hours % 24;
  return rest === 0 ? `+${days}d` : `+${days}d ${rest}h`;
}

/**
 * Selects the forecast lead-time window.
 *
 * Drives the API's `horizon` parameter, so the map answers "which cells are predicted to
 * cross the threshold within this many hours of the cycle anchor".
 */
export const ForecastHorizonSlider = ({
  value,
  label = 'Forecast lead time',
  description = 'Cells predicted to cross the alert threshold within this window.',
  min = 1,
  max = 72,
  step = 1,
  disabled = false,
  onValueChange,
  className = '',
  classNames = {},
  animation,
}: ForecastHorizonSliderProps) => (
  <Slider
    label={label}
    description={description}
    value={value}
    min={min}
    max={max}
    step={step}
    disabled={disabled}
    formatValue={formatLeadTime}
    onValueChange={(next) => onValueChange?.(Math.round(next))}
    className={className}
    classNames={classNames}
    animation={animation}
  />
);
