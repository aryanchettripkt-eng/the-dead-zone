"""Shared domain constants.

Single source of truth for every mathematical constant and normative parameter
used across pipeline scoring and API scenario simulations.
Section refs are to docs/PRD1.md.
"""

from core.enums import Hazard, Tier, ZoneClass

# FR-3.5 — multi-hazard union weights
HAZARD_WEIGHTS: dict[Hazard, float] = {
    Hazard.LANDSLIDE: 1.0,
    Hazard.FLASH_FLOOD: 1.0,
    Hazard.STORM_SURGE: 0.9,
    Hazard.RIVERINE_FLOOD: 0.8,
    Hazard.COASTAL_EROSION: 0.7,
}

# FR-3.2 — trigger amplification in H_h = clamp(S_h * (1 + BETA * T_h), 0, 1)
BETA: float = 1.0

# FR-3.8 / 3.9 / 3.10 — zone thresholds
PRZ_MHI_STATIC: float = 0.75
PRZ_ANY_SUSCEPTIBILITY: float = 0.85
PRZ_FATAL_EVENT_MHI: float = 0.60
PRZ_FATAL_EVENT_YEARS: int = 25
CAUTION_MHI_MIN: float = 0.45
ACTIVE_ALERT_MHI_LIVE: float = 0.75

# FR-3.12 — forecast horizon, pilot districts only
FORECAST_HORIZON_HOURS: int = 72

# FR-3.10 / H5 — dynamic trigger freshness (max age in hours for live alert serving)
MAX_TRIGGER_AGE_HOURS: int = 24

# FR-4.1 — antecedent rainfall index
ARI_DECAY_K: float = 0.9
ARI_WINDOW_DAYS: int = 15

# FR-6.1 / 6.2 — priority score
PRIORITY_GAMMA: float = 0.5
LOSS_HALF_LIFE_YEARS: float = 10.0

# §9.3 — H3 resolutions
H3_RES_OVERVIEW: int = 6
H3_RES_NATIONAL: int = 7
H3_RES_PILOT: int = 8
H3_RES_SITE: int = 9

# FR-7.1 / 7.2 — candidate site generation and eligibility mask
SITE_SEARCH_RADIUS_KM: float = 15.0
SITE_MAX_MHI_STATIC: float = 0.25
SITE_MAX_SLOPE_DEG: float = 15.0
SITE_MIN_AREA_HA: float = 2.0

# §6.8 — carrying capacity norms
PLOT_AREA_M2: float = 90.0
INFRA_OVERHEAD: float = 0.40
AREA_PER_HOUSEHOLD_M2: float = round(PLOT_AREA_M2 * (1.0 + INFRA_OVERHEAD), 2)  # 126.0 m²
LPCD_RURAL: int = 55
LPCD_URBAN_SEWERED: int = 135
PHC_POP_PLAINS: int = 30_000
PHC_POP_HILLY_TRIBAL: int = 20_000
LIVELIHOOD_MULTIPLIER_RANGE: tuple[float, float] = (0.6, 1.0)

# NFR-8 & PRD §1.3 — persistent screening grade notice
SCREENING_GRADE_NOTICE: str = (
    "Screening Grade: Cell-level screening and prioritisation tool. "
    "Geotechnical investigation, hydraulic study, and community consultation "
    "required before executing relocation orders."
)

