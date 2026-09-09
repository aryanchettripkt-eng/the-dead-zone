'use client';

import { useCallback, useMemo, useState } from 'react';

import {
  AppHeader,
  CenterPanel,
  LeftPanel,
  RightPanel,
  ThreePanelLayout,
} from '@/components/layout';
import { useAllocationPlan } from '@/lib/hooks/useAllocationPlan';
import { useDistricts } from '@/lib/hooks/useDistricts';
import { useCandidateSites } from '@/lib/hooks/useCandidateSites';
import { useHabitationQueue } from '@/lib/hooks/useHabitationQueue';
import type {
  AllocationAssignment,
  CandidateSiteItem,
  CapacityBreakdown,
  HabitationListItem,
} from '@/lib/api/types';

import { DistrictSelect } from './DistrictSelect';
import { RelocationHeaderMeta } from './RelocationHeaderMeta';
import { HabitationQueue } from './triage/HabitationQueue';
import { RelocationCenterPanel } from './map/RelocationCenterPanel';
import {
  AllocationControls,
  type AllocationSettings,
} from './solver/AllocationControls';
import { AllocationPanel } from './solver/AllocationPanel';
import { CapacitySimulationModal } from './solver/CapacitySimulationModal';

export interface RelocationWorkspaceProps {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Solver parameters the workspace opens with. */
  initialSettings?: Partial<AllocationSettings>;
  className?: string;
}

const DEFAULT_SETTINGS: AllocationSettings = {
  maxSearchRadiusKm: 15,
  targetTier: 'immediate',
  allowGroupSplits: true,
  distancePenaltyWeight: 1,
};

/**
 * Relocation planning workspace: triage demand, inspect GIS safe havens, and solve optimal distribution.
 *
 * Left panel: Demand triage queue (vulnerable settlements)
 * Center panel: 3D MapLibre & Deck.gl GIS corridors, radar beacon, and candidate parcel drawer
 * Right panel: Allocation optimization engine and solved plan
 *
 * All panels are fully collapsible for maximum GIS map focus.
 */
export const RelocationWorkspace = ({
  title = 'Relocation planning',
  subtitle = 'Match displaced households to candidate sites under carrying-capacity limits',
  initialSettings,
  className = '',
}: RelocationWorkspaceProps) => {
  const [districtId, setDistrictId] = useState<number | null>(null);
  const [explicitSelectedHabitation, setExplicitSelectedHabitation] = useState<HabitationListItem | null>(null);
  const [selectedSiteId, setSelectedSiteId] = useState<number | null>(null);
  const [includeScreening, setIncludeScreening] = useState(false);

  // Collapsible panels state
  const [isLeftCollapsed, setIsLeftCollapsed] = useState(false);
  const [isRightCollapsed, setIsRightCollapsed] = useState(false);

  // Capacity simulation modal state
  const [simulationSite, setSimulationSite] = useState<CandidateSiteItem | null>(null);
  const [siteOverrides, setSiteOverrides] = useState<Record<number, CapacityBreakdown>>({});

  const [settings, setSettings] = useState<AllocationSettings>({
    ...DEFAULT_SETTINGS,
    ...initialSettings,
  });

  const queue = useHabitationQueue({ admin: districtId ?? undefined, limit: 50 });
  const { districts } = useDistricts();
  const activeDistrictId = districtId ?? districts[0]?.id ?? null;

  // Selected habitation derives first queue item as default without triggering cascading renders
  const selectedHabitation = explicitSelectedHabitation ?? queue.habitations[0] ?? null;

  const sites = useCandidateSites({
    habitationId: selectedHabitation?.id ?? null,
    radiusKm: settings.maxSearchRadiusKm,
  });

  // Merge any simulated capacity overrides
  const enhancedSites = useMemo(() => {
    return sites.sites.map((site) => {
      const override = siteOverrides[site.id];
      if (override) {
        return {
          ...site,
          capacity: override,
          allocatable: (override.cc_final ?? 0) > 0,
        };
      }
      return site;
    });
  }, [sites.sites, siteOverrides]);

  const enhancedAllocatable = useMemo(() => {
    return enhancedSites.filter((s) => s.allocatable);
  }, [enhancedSites]);

  const allocation = useAllocationPlan();

  const handleSelectHabitation = useCallback((habitation: HabitationListItem) => {
    setExplicitSelectedHabitation(habitation);
    setSelectedSiteId(null);
  }, []);

  const handleSelectDistrict = useCallback((adminId: number) => {
    setDistrictId(adminId);
    setExplicitSelectedHabitation(null);
    setSelectedSiteId(null);
  }, []);

  const handleSolve = useCallback(() => {
    void allocation.solve({
      admin_id: activeDistrictId ?? undefined,
      max_search_radius_km: settings.maxSearchRadiusKm,
      target_tiers: [settings.targetTier],
      allow_group_splits: settings.allowGroupSplits,
      distance_penalty_weight: settings.distancePenaltyWeight,
    });
  }, [allocation, activeDistrictId, settings]);

  const handleSelectSite = useCallback(
    (site: CandidateSiteItem) =>
      setSelectedSiteId((current) => (current === site.id ? null : site.id)),
    [],
  );

  const handleSelectAssignment = useCallback(
    (assignment: AllocationAssignment) => {
      setSelectedSiteId(assignment.site_id);
    },
    [],
  );

  const handleApplyOverride = useCallback(
    (siteId: number, simulatedCapacity: CapacityBreakdown) => {
      setSiteOverrides((prev) => ({
        ...prev,
        [siteId]: simulatedCapacity,
      }));
    },
    [],
  );

  return (
    <>
      <ThreePanelLayout
        className={className}
        header={
          <AppHeader
            title={title}
            subtitle={subtitle}
            metaSlot={
              <RelocationHeaderMeta
                totalHabitations={queue.total}
                selectedHabitation={selectedHabitation}
                plan={allocation.plan}
              />
            }
          />
        }
        left={
          <LeftPanel
            width={isLeftCollapsed ? 0 : 320}
            className={[
              'transition-all duration-300 ease-in-out',
              isLeftCollapsed ? 'w-0 overflow-hidden border-r-0 !p-0 opacity-0 pointer-events-none' : 'opacity-100',
            ].join(' ')}
            classNames={{
              scroll: isLeftCollapsed ? '!p-0' : 'p-3',
            }}
          >
            <HabitationQueue
              habitations={queue.habitations}
              total={queue.total}
              isLoading={queue.isLoading}
              error={queue.error}
              selectedId={selectedHabitation?.id ?? null}
              onSelect={handleSelectHabitation}
              onRetry={queue.refetch}
              onToggleCollapse={() => setIsLeftCollapsed(true)}
              actionSlot={
                districts.length > 1 ? (
                  <DistrictSelect
                    options={districts}
                    value={activeDistrictId}
                    onValueChange={handleSelectDistrict}
                  />
                ) : null
              }
            />
          </LeftPanel>
        }
        center={
          <CenterPanel className="overflow-hidden">
            <RelocationCenterPanel
              habitation={selectedHabitation}
              sites={enhancedSites}
              allocatableSites={enhancedAllocatable}
              totalInRange={sites.total}
              radiusKm={settings.maxSearchRadiusKm}
              isLoadingSites={sites.isLoading}
              selectedSiteId={selectedSiteId}
              onSelectSite={handleSelectSite}
              onSimulateCapacity={(site) => setSimulationSite(site)}
              onRetrySites={sites.refetch}
              includeScreening={includeScreening}
              onIncludeScreeningChange={setIncludeScreening}
              plan={allocation.plan}
              habitations={queue.habitations}
              onSelectAssignment={handleSelectAssignment}
              isLeftCollapsed={isLeftCollapsed}
              onToggleLeftCollapse={() => setIsLeftCollapsed((c) => !c)}
              isRightCollapsed={isRightCollapsed}
              onToggleRightCollapse={() => setIsRightCollapsed((c) => !c)}
            />
          </CenterPanel>
        }
        right={
          <RightPanel
            width={isRightCollapsed ? 0 : 360}
            className={[
              'transition-all duration-300 ease-in-out',
              isRightCollapsed ? 'w-0 overflow-hidden border-l-0 !p-0 opacity-0 pointer-events-none' : 'opacity-100',
            ].join(' ')}
            classNames={{
              scroll: isRightCollapsed ? '!p-0' : 'p-3',
            }}
          >
            <AllocationPanel
              plan={allocation.plan}
              isSolving={allocation.isSolving}
              error={allocation.error}
              highlightedHabitationId={selectedHabitation?.id ?? null}
              onSelectAssignment={handleSelectAssignment}
              onToggleCollapse={() => setIsRightCollapsed(true)}
              description={
                activeDistrictId
                  ? `Solving across ${districts.find((d) => d.id === activeDistrictId)?.name ?? 'the district'}`
                  : undefined
              }
              controlsSlot={
                <AllocationControls
                  settings={settings}
                  onSettingsChange={setSettings}
                  onSolve={handleSolve}
                  isSolving={allocation.isSolving}
                />
              }
            />
          </RightPanel>
        }
      />

      {/* Interactive Policy Norms Simulation Modal */}
      <CapacitySimulationModal
        site={simulationSite}
        isOpen={Boolean(simulationSite)}
        onClose={() => setSimulationSite(null)}
        onApplyOverride={handleApplyOverride}
      />
    </>
  );
};
