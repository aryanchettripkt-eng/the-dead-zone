'use client';

import { useState } from 'react';
import { Slider, Toggle } from '@/components/ui';

export interface RelocationMapLayerCardProps {
  opacity: number;
  onOpacityChange: (val: number) => void;
  showConfidenceHatch: boolean;
  onShowConfidenceHatchChange: (val: boolean) => void;
  confidenceThreshold: number;
  onConfidenceThresholdChange: (val: number) => void;
  showHardZero: boolean;
  onShowHardZeroChange: (val: boolean) => void;
  showNoCoverage: boolean;
  onShowNoCoverageChange: (val: boolean) => void;
  className?: string;
}

export const RelocationMapLayerCard = ({
  opacity,
  onOpacityChange,
  showConfidenceHatch,
  onShowConfidenceHatchChange,
  confidenceThreshold,
  onConfidenceThresholdChange,
  showHardZero,
  onShowHardZeroChange,
  showNoCoverage,
  onShowNoCoverageChange,
  className = '',
}: RelocationMapLayerCardProps) => {
  const [isMinimized, setIsMinimized] = useState(false);

  if (isMinimized) {
    return (
      <button
        type="button"
        onClick={() => setIsMinimized(false)}
        className={[
          'absolute right-4 top-20 z-20 flex items-center gap-2 rounded-xl border border-line/80',
          'bg-surface-0/90 dark:bg-forest-surface/90 px-3 py-2 shadow-lg backdrop-blur-md',
          'text-xs font-semibold text-ink hover:bg-surface-1 cursor-pointer transition-all active:scale-95',
          className,
        ]
          .filter(Boolean)
          .join(' ')}
        title="Show GIS Layer Controls"
      >
        <svg className="h-4 w-4 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
        </svg>
        <span>GIS Controls</span>
      </button>
    );
  }

  return (
    <div
      className={[
        'absolute right-4 top-20 z-20 flex w-72 flex-col gap-3 rounded-2xl border border-line/80',
        'bg-surface-0/95 dark:bg-forest-surface/95 p-4 shadow-xl backdrop-blur-md transition-colors',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {/* Header with minimize button */}
      <div className="flex items-center justify-between border-b border-line/50 pb-2">
        <span className="text-[11px] font-bold uppercase tracking-wider text-ink">
          GIS Layer Settings
        </span>
        <button
          type="button"
          onClick={() => setIsMinimized(true)}
          title="Minimize card"
          className="flex h-5 w-5 items-center justify-center rounded-md text-ink-faint hover:bg-surface-1 hover:text-ink cursor-pointer"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {/* Opacity Slider */}
      <Slider
        label="Layer opacity"
        value={Math.round(opacity * 100)}
        min={10}
        max={100}
        step={5}
        formatValue={(v) => `${v}%`}
        onValueChange={(val) => onOpacityChange(val / 100)}
      />

      {/* Confidence Hatch Toggle */}
      <Toggle
        label="Confidence hatch"
        description="Marks provisional cells (FR-9.3)"
        checked={showConfidenceHatch}
        onCheckedChange={onShowConfidenceHatchChange}
      />

      {/* Hatch Below Slider */}
      {showConfidenceHatch && (
        <Slider
          label="Hatch below"
          value={confidenceThreshold}
          min={0.1}
          max={0.9}
          step={0.05}
          formatValue={(v) => v.toFixed(2)}
          description="Normalised against layer confidence ceiling"
          onValueChange={onConfidenceThresholdChange}
        />
      )}

      {/* Safe by Terrain Toggle */}
      <Toggle
        label="Safe by terrain"
        description="HAND > 30 m or slope > 15° (FR-3.17)"
        checked={showHardZero}
        onCheckedChange={onShowHardZeroChange}
      />

      {/* No-data cells toggle */}
      <Toggle
        label="No-data cells"
        description="Outlined, never filled"
        checked={showNoCoverage}
        onCheckedChange={onShowNoCoverageChange}
      />
    </div>
  );
};
