"""Configuration and Formula Governance for SETU-DRR.

Section refs: docs/PRD1.md §6.3, §6.4, §6.6, §6.7, §6.8, §9.3

Preserves the explicit classification of authority across:
1. Authoritative Scientific Definitions (zone thresholds, forecast horizon max, trigger decay)
2. Policy Parameters (carrying-capacity norms, loss decay, triage policy boundaries)
3. Operational Configuration (search radius, query limits, solver penalties)
4. Model / Provider Metadata (model version, dataset version, provider identity)

Every configurable/scientific category carries an explicit version/identity mechanism.
Provisional/scenario values are strictly separated from baseline authoritative values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from core.constants import (
    ACTIVE_ALERT_MHI_LIVE,
    AREA_PER_HOUSEHOLD_M2,
    ARI_DECAY_K,
    ARI_WINDOW_DAYS,
    BETA,
    CAUTION_MHI_MIN,
    FORECAST_HORIZON_HOURS,
    HAZARD_WEIGHTS,
    H3_RES_NATIONAL,
    H3_RES_OVERVIEW,
    H3_RES_PILOT,
    H3_RES_SITE,
    INFRA_OVERHEAD,
    LIVELIHOOD_MULTIPLIER_RANGE,
    LOSS_HALF_LIFE_YEARS,
    LPCD_RURAL,
    LPCD_URBAN_SEWERED,
    PHC_POP_HILLY_TRIBAL,
    PHC_POP_PLAINS,
    PLOT_AREA_M2,
    PRIORITY_GAMMA,
    PRZ_ANY_SUSCEPTIBILITY,
    PRZ_FATAL_EVENT_MHI,
    PRZ_FATAL_EVENT_YEARS,
    PRZ_MHI_STATIC,
    SCREENING_GRADE_NOTICE,
    SITE_MAX_MHI_STATIC,
    SITE_MAX_SLOPE_DEG,
    SITE_MIN_AREA_HA,
    SITE_SEARCH_RADIUS_KM,
)
from core.enums import Hazard, Tier, ZoneClass


@dataclass(frozen=True)
class AuthoritativeScientificDefinitions:
    """Non-negotiable scientific definitions approved in PRD §6.3, §6.4.
    
    These values represent physical, geological, and meteorological thresholds
    derived from scientific consensus (e.g., GSI guidelines, NDMA, CWC standards).
    They must NOT be treated as arbitrary policy parameters or mutated during scenarios.
    """
    version: str = "scientific-v1.0"
    
    # Zone thresholds (PRD §6.3, FR-3.8, FR-3.9, FR-3.10)
    prz_mhi_static: float = PRZ_MHI_STATIC
    prz_any_susceptibility: float = PRZ_ANY_SUSCEPTIBILITY
    prz_fatal_event_mhi: float = PRZ_FATAL_EVENT_MHI
    prz_fatal_event_years: int = PRZ_FATAL_EVENT_YEARS
    caution_mhi_min: float = CAUTION_MHI_MIN
    active_alert_mhi_live: float = ACTIVE_ALERT_MHI_LIVE

    # Maximum Meteorological Forecast Horizon (PRD §6.3, FR-3.12)
    max_forecast_horizon_hours: int = FORECAST_HORIZON_HOURS

    # Trigger amplification factor beta in H_h = clamp(S_h * (1 + beta * T_h), 0, 1) (FR-3.2)
    trigger_beta: float = BETA

    # Antecedent Rainfall Index physical parameters (FR-4.1)
    ari_decay_k: float = ARI_DECAY_K
    ari_window_days: int = ARI_WINDOW_DAYS

    # Authoritative baseline multi-hazard union weights (FR-3.5)
    baseline_hazard_weights: Mapping[Hazard, float] = field(default_factory=lambda: dict(HAZARD_WEIGHTS))

    # Grid resolutions (PRD §9.3)
    res_overview: int = H3_RES_OVERVIEW
    res_national: int = H3_RES_NATIONAL
    res_pilot: int = H3_RES_PILOT
    res_site: int = H3_RES_SITE


@dataclass(frozen=True)
class PolicyParameters:
    """Configurable administrative and planning policy parameters (PRD §6.6, §6.7, §6.8).
    
    These values reflect policy decisions and statutory norms (CPHEEO, IPHS, UDISE+)
    subject to state government or administrative policy review.
    """
    version: str = "policy-v1.0"

    # Carrying capacity norms (PRD §6.8)
    plot_area_m2: float = PLOT_AREA_M2
    infra_overhead_pct: float = INFRA_OVERHEAD
    area_per_hh_m2: float = AREA_PER_HOUSEHOLD_M2
    lpcd_rural: int = LPCD_RURAL
    lpcd_urban_sewered: int = LPCD_URBAN_SEWERED
    phc_norm_pop_plains: int = PHC_POP_PLAINS
    phc_norm_pop_hilly_tribal: int = PHC_POP_HILLY_TRIBAL
    children_per_hh: float = 1.2
    persons_per_hh: float = 4.5
    livelihood_multiplier_range: tuple[float, float] = LIVELIHOOD_MULTIPLIER_RANGE

    # Relocation site eligibility bounds (FR-7.2)
    site_min_area_ha: float = SITE_MIN_AREA_HA
    site_max_slope_deg: float = SITE_MAX_SLOPE_DEG
    site_max_mhi_static: float = SITE_MAX_MHI_STATIC

    # Loss history decay policy (FR-6.1, FR-6.2)
    priority_gamma: float = PRIORITY_GAMMA
    loss_half_life_years: float = LOSS_HALF_LIFE_YEARS

    # Triage tier criteria boundaries (FR-6.4, FR-6.5)
    triage_immediate_prz_pop_min: float = 0.60
    triage_immediate_hazard_min: float = 0.85
    triage_mitigate_in_situ_prz_pop_max: float = 0.30
    triage_short_term_priority_min: float = 0.30


@dataclass(frozen=True)
class OperationalConfig:
    """System operational runtime settings and boundary guards.
    
    Protects serving layer integrity, query bounds, and solver computational bounds.
    """
    version: str = "operational-v1.0"

    # Search radii bounds (FR-7.1)
    default_search_radius_km: float = SITE_SEARCH_RADIUS_KM
    min_search_radius_km: float = 0.5
    max_search_radius_km: float = 100.0

    # API pagination and query bounding box limits
    default_query_limit: int = 50
    max_query_limit: int = 500
    max_bbox_area_deg2: float = 5.0

    # Min-cost flow solver operational penalties (FR-8.1)
    solver_benefit_scale_factor: float = 100.0
    solver_unmet_demand_penalty: int = 50_000
    solver_base_offset: int = 10_000


@dataclass
class ModelProviderMetadata:
    """Container for upstream ML / sensor product metadata and provenance."""
    model_name: str
    model_version: str
    feature_schema_version: str
    provider: str
    dataset_version: str = "v1.0"
    calibration_version: Optional[str] = None
    trained_date: Optional[str] = None
    auc_score: Optional[float] = None
    data_quality: str = "observed"


# Singleton instances representing authoritative defaults
AUTHORITATIVE_SCIENTIFIC = AuthoritativeScientificDefinitions()
DEFAULT_POLICY_PARAMS = PolicyParameters()
DEFAULT_OPERATIONAL_CONFIG = OperationalConfig()
