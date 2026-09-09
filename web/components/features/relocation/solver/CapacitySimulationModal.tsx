'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';

import { Button, Slider } from '@/components/ui';
import { overrideSiteCapacity } from '@/lib/api/relocation';
import type { CandidateSiteItem, CapacityBreakdown } from '@/lib/api/types';
import { usePrefersReducedMotion } from '@/lib/hooks/usePrefersReducedMotion';

import { BindingConstraintBadge } from '../sites/BindingConstraintBadge';

export interface CapacitySimulationModalProps {
  site: CandidateSiteItem | null;
  isOpen: boolean;
  onClose: () => void;
  onApplyOverride?: (siteId: number, simulatedCapacity: CapacityBreakdown) => void;
}

const DEFAULT_NORMS = {
  plotAreaM2: 126,
  waterLpcd: 55,
  spareSchoolSeats: 200,
  spareHealthPop: 800,
};

interface SimulationDialogContentProps {
  site: CandidateSiteItem;
  onClose: () => void;
  onApplyOverride?: (siteId: number, simulatedCapacity: CapacityBreakdown) => void;
}

const SimulationDialogContent = ({
  site,
  onClose,
  onApplyOverride,
}: SimulationDialogContentProps) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const deltaRef = useRef<HTMLSpanElement>(null);
  const prefersReducedMotion = usePrefersReducedMotion();

  // Initialize directly from site props without needing useEffect setState
  const [plotAreaM2, setPlotAreaM2] = useState<number>(DEFAULT_NORMS.plotAreaM2);
  const [waterLpcd, setWaterLpcd] = useState<number>(DEFAULT_NORMS.waterLpcd);
  const [spareSchoolSeats, setSpareSchoolSeats] = useState<number>(() =>
    site.capacity.cc_school != null ? Math.round(site.capacity.cc_school * 0.8) : DEFAULT_NORMS.spareSchoolSeats,
  );
  const [spareHealthPop, setSpareHealthPop] = useState<number>(() =>
    site.capacity.cc_health != null ? Math.round(site.capacity.cc_health * 4.5) : DEFAULT_NORMS.spareHealthPop,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  // Real-time client-side calculation matching core.domain.capacity
  const scenario = useMemo(() => {
    const baseCc = site.capacity.cc_final ?? 0;
    const baseLand = site.capacity.cc_land ?? Math.floor((site.area_ha * 10000 * 0.7) / 126);
    const scenLand = Math.floor((baseLand * 126) / plotAreaM2);

    const baseWater = site.capacity.cc_water ?? 200;
    const scenWater = Math.floor((baseWater * 55) / waterLpcd);

    const scenSchool = Math.floor(spareSchoolSeats / 0.8);
    const scenHealth = Math.floor(spareHealthPop / 4.5);

    const dims = [
      { key: 'land' as const, val: scenLand },
      { key: 'water' as const, val: scenWater },
      { key: 'school' as const, val: scenSchool },
      { key: 'health' as const, val: scenHealth },
    ];

    let minVal = Infinity;
    let minKey: 'land' | 'water' | 'school' | 'health' = 'land';
    for (const d of dims) {
      if (d.val < minVal) {
        minVal = d.val;
        minKey = d.key;
      }
    }

    const mult = site.capacity.livelihood_multiplier ?? 1.0;
    const scenFinal = Math.floor(minVal * mult);
    const delta = scenFinal - baseCc;

    return {
      land: scenLand,
      water: scenWater,
      school: scenSchool,
      health: scenHealth,
      final: scenFinal,
      binding: minKey,
      delta,
      baseFinal: baseCc,
    };
  }, [site, plotAreaM2, waterLpcd, spareSchoolSeats, spareHealthPop]);

  useGSAP(
    () => {
      if (!modalRef.current) return;
      gsap.fromTo(
        modalRef.current,
        { scale: 0.95, opacity: 0 },
        { scale: 1, opacity: 1, duration: 0.25, ease: 'power2.out' },
      );
    },
    { scope: modalRef },
  );

  useGSAP(
    () => {
      if (!scenario || !deltaRef.current || prefersReducedMotion) return;
      const target = deltaRef.current;
      const counter = { val: 0 };
      gsap.to(counter, {
        val: scenario.delta,
        duration: 0.4,
        ease: 'power2.out',
        onUpdate: () => {
          const rounded = Math.round(counter.val);
          target.textContent = `${rounded >= 0 ? '+' : ''}${rounded.toLocaleString()}`;
        },
      });
    },
    { dependencies: [scenario?.delta, prefersReducedMotion] },
  );

  const handleApply = useCallback(async () => {
    if (!scenario) return;
    setIsSubmitting(true);
    setServerError(null);

    try {
      const response = await overrideSiteCapacity(site.id, {
        plot_area_m2: plotAreaM2,
        water_lpcd: waterLpcd,
        spare_school_seats: spareSchoolSeats,
        spare_health_capacity_pop: spareHealthPop,
      });

      if (response && onApplyOverride) {
        onApplyOverride(site.id, response.scenario_capacity);
      }
      onClose();
    } catch {
      // Fallback calculation for offline / non-auth sessions
      if (onApplyOverride) {
        onApplyOverride(site.id, {
          ...site.capacity,
          cc_land: scenario.land,
          cc_water: scenario.water,
          cc_school: scenario.school,
          cc_health: scenario.health,
          cc_final: scenario.final,
          binding_constraint: scenario.binding,
        });
      }
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  }, [
    site,
    scenario,
    plotAreaM2,
    waterLpcd,
    spareSchoolSeats,
    spareHealthPop,
    onApplyOverride,
    onClose,
  ]);

  return (
    <div
      ref={modalRef}
      className="flex w-full max-w-2xl flex-col gap-5 rounded-2xl border border-line bg-surface-0 p-6 shadow-2xl text-ink"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Modal Header */}
      <div className="flex items-start justify-between gap-4 border-b border-line pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-accent/15 px-2 py-0.5 font-mono text-[11px] font-bold text-accent">
              SITE #{site.id}
            </span>
            <h2 className="text-base font-bold text-ink">Simulate Carrying Capacity Norms</h2>
          </div>
          <p className="mt-1 text-xs text-ink-muted">
            Tweak rural cluster plot areas, LPCD water standards, and institutional spare limits to
            test infrastructure augmentation scenarios.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-line/60 bg-surface-1/50 text-ink-muted hover:bg-surface-2 hover:text-ink cursor-pointer transition-colors"
        >
          ✕
        </button>
      </div>

      {/* Delta Comparison Banner */}
      <div className="flex items-center justify-between rounded-xl border border-line/60 bg-surface-1/40 p-4">
        <div>
          <span className="text-[10px] uppercase font-bold tracking-wider text-ink-faint">
            Baseline vs. Scenario Capacity
          </span>
          <div className="flex items-baseline gap-3 mt-1">
            <span className="font-mono text-xl font-bold text-ink-faint">
              {scenario.baseFinal.toLocaleString()} HH
            </span>
            <span className="text-ink-faint">→</span>
            <span className="font-mono text-2xl font-black text-ink">
              {scenario.final.toLocaleString()} HH
            </span>
            <span className="text-xs text-ink-muted">households</span>
          </div>
        </div>

        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase font-bold tracking-wider text-ink-faint">
            Net Delta (Δ HH)
          </span>
          <div
            className={[
              'mt-1 flex items-center gap-1.5 rounded-lg px-2.5 py-1 font-mono text-sm font-bold',
              scenario.delta >= 0 ? 'bg-safe/15 text-safe' : 'bg-critical/15 text-critical',
            ].join(' ')}
          >
            <span ref={deltaRef}>
              {scenario.delta >= 0 ? '+' : ''}
              {scenario.delta.toLocaleString()}
            </span>
            <span>HH</span>
          </div>
        </div>
      </div>

      {/* Sliders Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Slider
          label="Plot Area Norm"
          value={plotAreaM2}
          min={80}
          max={220}
          step={2}
          formatValue={(v) => `${v} m²`}
          description="Net usable land area per household (Cluster standard)."
          onValueChange={setPlotAreaM2}
        />

        <Slider
          label="Water Supply Norm"
          value={waterLpcd}
          min={35}
          max={85}
          step={5}
          formatValue={(v) => `${v} LPCD`}
          description="Litres per capita per day (Jal Jeevan norm)."
          onValueChange={setWaterLpcd}
        />

        <Slider
          label="Spare Primary School Seats"
          value={spareSchoolSeats}
          min={50}
          max={500}
          step={10}
          formatValue={(v) => `${v} seats`}
          description="UDISE+ capacity within 3km catchment."
          onValueChange={setSpareSchoolSeats}
        />

        <Slider
          label="Spare Health PHC Capacity"
          value={spareHealthPop}
          min={200}
          max={2000}
          step={50}
          formatValue={(v) => `${v} pop`}
          description="Primary Health Centre spare patient population."
          onValueChange={setSpareHealthPop}
        />
      </div>

      {/* 4-Dimension Scenario Waterfall Preview */}
      <div className="flex flex-col gap-2 rounded-xl border border-line/60 bg-surface-1/20 p-3">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-ink-faint">
            Scenario Capacity Breakdown
          </span>
          <BindingConstraintBadge constraint={scenario.binding} />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div className="rounded-lg border border-line/40 bg-surface-0/60 p-2">
            <span className="text-[10px] text-ink-faint block">Land</span>
            <span className="font-mono font-bold text-ink">{scenario.land} HH</span>
          </div>
          <div className="rounded-lg border border-line/40 bg-surface-0/60 p-2">
            <span className="text-[10px] text-ink-faint block">Water</span>
            <span className="font-mono font-bold text-ink">{scenario.water} HH</span>
          </div>
          <div className="rounded-lg border border-line/40 bg-surface-0/60 p-2">
            <span className="text-[10px] text-ink-faint block">School</span>
            <span className="font-mono font-bold text-ink">{scenario.school} HH</span>
          </div>
          <div className="rounded-lg border border-line/40 bg-surface-0/60 p-2">
            <span className="text-[10px] text-ink-faint block">Health</span>
            <span className="font-mono font-bold text-ink">{scenario.health} HH</span>
          </div>
        </div>
      </div>

      {serverError && <p className="text-xs text-critical">{serverError}</p>}

      {/* Modal Actions */}
      <div className="flex items-center justify-between border-t border-line pt-3">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setPlotAreaM2(DEFAULT_NORMS.plotAreaM2);
            setWaterLpcd(DEFAULT_NORMS.waterLpcd);
            setSpareSchoolSeats(DEFAULT_NORMS.spareSchoolSeats);
            setSpareHealthPop(DEFAULT_NORMS.spareHealthPop);
          }}
        >
          Reset to Norms
        </Button>

        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" variant="primary" disabled={isSubmitting} onClick={handleApply}>
            {isSubmitting ? 'Simulating…' : 'Apply Scenario Override'}
          </Button>
        </div>
      </div>
    </div>
  );
};

export const CapacitySimulationModal = ({
  site,
  isOpen,
  onClose,
  onApplyOverride,
}: CapacitySimulationModalProps) => {
  if (!isOpen || !site) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs transition-opacity"
      onClick={onClose}
    >
      <SimulationDialogContent
        key={site.id}
        site={site}
        onClose={onClose}
        onApplyOverride={onApplyOverride}
      />
    </div>
  );
};
