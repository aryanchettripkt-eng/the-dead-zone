'use client';

import type { HabitationListItem } from '@/lib/api/types';

export interface RelocationMapTopHudProps {
  habitation: HabitationListItem | null;
  totalSites: number;
  allocatableCount: number;
  isDrawerOpen: boolean;
  onToggleDrawer: () => void;
  is3DMode: boolean;
  onToggle3D: () => void;
  className?: string;
}

export const RelocationMapTopHud = ({
  habitation,
  totalSites,
  allocatableCount,
  isDrawerOpen,
  onToggleDrawer,
  is3DMode,
  onToggle3D,
  className = '',
}: RelocationMapTopHudProps) => {
  return (
    <div
      className={[
        'absolute left-4 right-4 top-4 z-20 flex flex-wrap items-center justify-between gap-3',
        'rounded-2xl border border-line/80 bg-surface-0/90 dark:bg-forest-surface/90 px-4 py-2.5 shadow-lg backdrop-blur-md transition-colors',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {/* Origin -> Destination Corridor Status */}
      <div className="flex items-center gap-4 flex-wrap">
        {habitation ? (
          <>
            {/* Origin Status */}
            <div className="flex items-center gap-2.5">
              <span className="relative flex h-3.5 w-3.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-critical opacity-75" />
                <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-critical" />
              </span>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-critical block leading-none">
                  Evacuate Hazard Zone
                </span>
                <span className="text-sm font-bold text-ink leading-tight">
                  {habitation.name}
                </span>
              </div>
            </div>

            {/* Separator / Arrow */}
            <span className="text-citron font-bold text-sm hidden sm:inline">≫</span>

            {/* Destination Status */}
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-accent-emerald-bright dark:text-citron block leading-none">
                {totalSites} Safe {totalSites === 1 ? 'Haven' : 'Havens'} Found
              </span>
              <span className="text-xs text-ink-muted leading-tight">
                {allocatableCount} allocatable {allocatableCount === 1 ? 'parcel' : 'parcels'}
              </span>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            <span className="inline-block h-2 w-2 rounded-full bg-ink-faint animate-pulse" />
            <span>Select a habitation from the triage queue to inspect evacuation corridors</span>
          </div>
        )}
      </div>

      {/* Action Controls */}
      <div className="flex items-center gap-2 ml-auto">
        <button
          type="button"
          onClick={onToggleDrawer}
          className={[
            'flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-all active:scale-95 cursor-pointer',
            isDrawerOpen
              ? 'border-accent bg-accent/20 text-accent shadow-xs'
              : 'border-line/70 bg-surface-1/70 text-ink hover:border-line-strong hover:bg-surface-2',
          ].join(' ')}
          title="Toggle candidate parcels drawer"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
          </svg>
          <span>PARCELS</span>
          <span className="rounded-md bg-surface-2/80 px-1.5 py-0.2 font-mono text-[10px]">
            {allocatableCount}/{totalSites}
          </span>
        </button>

        <button
          type="button"
          onClick={onToggle3D}
          className={[
            'flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-all active:scale-95 cursor-pointer',
            is3DMode
              ? 'border-citron bg-citron/20 text-ink dark:text-citron shadow-xs'
              : 'border-line/70 bg-surface-1/70 text-ink hover:border-line-strong hover:bg-surface-2',
          ].join(' ')}
          title={is3DMode ? 'Switch to 2D Nadir View' : 'Switch to 3D Perspective Glow'}
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
            />
          </svg>
          <span>{is3DMode ? '3D GLOW' : '2D VIEW'}</span>
        </button>
      </div>
    </div>
  );
};
