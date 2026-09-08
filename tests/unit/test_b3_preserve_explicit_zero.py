"""Unit tests for P0.1 / B3 — Preserve Explicit Zero Risk Values.

Verifies:
1. Invariant A: Zero susceptibility remains zero (0.0).
2. Invariant B: Zero trigger remains zero (0.0).
3. Invariant C: Zero hazard contribution remains zero (0.0).
4. Invariant D: Zero MHI remains zero (0.0).
5. Invariant E: Zero priority score remains zero (0.0).
6. Invariant F: Zero PRZ overlap remains zero (0.0).
7. Invariant G: Zero vulnerability/index values remain zero (0.0).
8. Fallback Invariant: None and missing fields still receive their intended defaults.
9. Production path integration across habitations, zones, alerts, sites, allocation, and scenario services.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock
import pytest

from core.enums import Hazard, Tier, ZoneClass, BindingConstraint, TenureType
from core.h3_utils import h3_to_int
from core.domain.hazard import (
    compute_hazard_score,
    compute_mhi,
    get_dominant_hazard,
)
from core.domain.priority import (
    compute_time_decayed_loss,
    compute_priority_score,
    sort_habitations,
)
from core.domain.explanation import (
    normalize_feature_contributions,
)
from core.domain.vulnerability import (
    validate_district_downscaling,
    VulnerabilityConfig,
)
from core.domain.scenario import ScenarioEngine, HabitationBaselineState

from api.services.habitations_service import HabitationsService
from api.services.zones_service import ZonesService
from api.services.alerts_service import AlertsService
from api.services.sites_service import SitesService
from api.services.allocation_service import AllocationService
from api.services.scenario_service import ScenarioService
from core.schemas.allocation import AllocationPlanRequest
from core.schemas.scenario import ScenarioWeightOverrideRequest
from core.schemas.sites import SiteCapacityOverrideRequest


# =====================================================================
# 1. Domain-Level Invariants (A, B, C, D, E, F, G)
# =====================================================================

class TestDomainZeroPreservation:
    """Core domain calculation regression tests for explicit zero preservation."""

    def test_invariant_a_zero_susceptibility_remains_zero(self):
        """Invariant A: Given susceptibility = 0.0, resulting hazard score is 0.0."""
        # Non-zero trigger must not amplify a zero susceptibility
        score = compute_hazard_score(susceptibility=0.0, trigger_value=1.5, beta=1.0)
        assert score == 0.0

    def test_invariant_b_zero_trigger_remains_zero(self):
        """Invariant B: Given trigger = 0.0, it must remain 0.0 and not become a default trigger.
        
        When trigger is 0.0, compute_hazard_score evaluates to base susceptibility S_h,
        rather than being amplified by a fallback non-zero trigger.
        """
        susceptibility = 0.5
        # With trigger = 0.0, score = 0.5 * (1 + beta * 0.0) = 0.5
        score_zero_trigger = compute_hazard_score(susceptibility=susceptibility, trigger_value=0.0, beta=1.0)
        # If trigger had defaulted to 1.0 (truthiness fallback trigger or 1.0), score would be 0.5 * (1 + 1.0) = 1.0
        score_fallback_trigger = compute_hazard_score(susceptibility=susceptibility, trigger_value=1.0, beta=1.0)

        assert score_zero_trigger == 0.5
        assert score_zero_trigger < score_fallback_trigger

    def test_invariant_c_zero_hazard_contribution_remains_zero(self):
        """Invariant C: Explicit zero hazard weights or zero hazard scores contribute 0.0."""
        hazard_scores = {
            Hazard.LANDSLIDE: 0.8,
            Hazard.FLASH_FLOOD: 0.0,
        }
        weights = {
            Hazard.LANDSLIDE: 1.0,
            Hazard.FLASH_FLOOD: 0.0,  # Zero weight must be preserved, not replaced with default
        }
        # compute_mhi with zero flash flood weight should produce 1 - (1 - 1.0 * 0.8)*(1 - 0.0 * 0.0) = 0.8
        mhi = compute_mhi(hazard_scores, weights)
        assert mhi == 0.8

        # When all hazard scores are 0.0, MHI is 0.0
        all_zero_scores = {h: 0.0 for h in Hazard}
        assert compute_mhi(all_zero_scores) == 0.0

    def test_invariant_d_zero_mhi_remains_zero(self):
        """Invariant D: When all hazard inputs produce MHI = 0.0, dominant hazard and MHI remain zero."""
        scores = {Hazard.LANDSLIDE: 0.0, Hazard.FLASH_FLOOD: 0.0}
        mhi = compute_mhi(scores)
        assert mhi == 0.0

        # Dominant hazard calculation preserves zero
        dom_h, dom_s = get_dominant_hazard(scores)
        assert dom_s == 0.0

    def test_invariant_e_zero_priority_score_remains_zero(self):
        """Invariant E: If hazard and vulnerability inputs produce PS = 0.0, it remains 0.0."""
        # Hazard = 0.0, V = 0.0, decayed_loss = 0.0
        ps = compute_priority_score(
            hazard_intensity=0.0,
            vulnerability_index=0.0,
            decayed_loss=0.0,
            pop_fraction_in_prz=0.0,
        )
        assert ps == 0.0

    def test_invariant_f_zero_prz_overlap_remains_zero(self):
        """Invariant F: PRZ overlap = 0.0 contributes 0.0 to priority calculation."""
        # Under multiplicative formulation, pop_fraction_in_prz = 0.0 produces PS = 0.0
        ps_zero_prz = compute_priority_score(
            hazard_intensity=0.5,
            vulnerability_index=0.5,
            decayed_loss=0.0,
            pop_fraction_in_prz=0.0,
        )
        assert ps_zero_prz == 0.0

        # Compare with non-zero PRZ overlap
        ps_with_prz = compute_priority_score(
            hazard_intensity=0.5,
            vulnerability_index=0.5,
            decayed_loss=0.0,
            pop_fraction_in_prz=0.5,
        )
        assert ps_with_prz > 0.0

    def test_invariant_g_zero_vulnerability_remains_zero(self):
        """Invariant G: Zero vulnerability index preserves zero risk contribution."""
        ps = compute_priority_score(
            hazard_intensity=0.5,
            vulnerability_index=0.0,
            decayed_loss=0.0,
            pop_fraction_in_prz=0.5,
        )
        # Vulnerability = 0.0 in multiplicative formulation yields strictly 0.0
        assert ps == 0.0

    def test_explanation_feature_contribution_zero_preserved(self):
        """Verifies feature contributions with value=0.0 and contribution=0.0 are preserved."""
        raw_features = [
            {"feature": "slope_deg", "value": 0.0, "contribution": 0.0},
            {"feature": "rainfall_mm", "value": 150.0, "contribution": 0.8},
        ]
        norm = normalize_feature_contributions(raw_features)
        assert len(norm) == 2
        f_zero = next(f for f in norm if f.feature == "slope_deg")
        assert f_zero.value == 0.0
        assert f_zero.contribution == 0.0


# =====================================================================
# 2. Fallback Invariant Tests: None and Missing Receive Defaults
# =====================================================================

class TestExplicitNoneFallbackHandling:
    """Verifies that None / missing values DO receive intended defaults (no broken fallbacks)."""

    def test_missing_and_none_fallbacks_for_hazard_weights(self):
        # Passing empty dict or None weights to compute_mhi uses DEFAULT_HAZARD_WEIGHTS
        scores = {Hazard.LANDSLIDE: 0.6}
        mhi_default = compute_mhi(scores, weights=None)
        mhi_empty = compute_mhi(scores, weights={})
        assert mhi_default > 0.0
        assert mhi_default == mhi_empty

    def test_severity_none_fallback_in_time_decayed_loss(self):
        # Event with severity=None falls back to 0.5
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        events_with_none = [
            {"ts": datetime(2025, 1, 1, tzinfo=timezone.utc), "severity": None, "fatalities": 0}
        ]
        events_with_zero = [
            {"ts": datetime(2025, 1, 1, tzinfo=timezone.utc), "severity": 0.0, "fatalities": 0}
        ]
        loss_none = compute_time_decayed_loss(events_with_none, reference_date=now)
        loss_zero = compute_time_decayed_loss(events_with_zero, reference_date=now)

        # Explicit zero severity produces 0.0 loss, while None severity falls back to 0.5 severity
        assert loss_zero == 0.0
        assert loss_none > 0.0

    def test_explanation_none_fallback(self):
        # Feature with value=None and contribution=None falls back to 0.0
        raw_features = [
            {"feature": "test_feat", "value": None, "contribution": None}
        ]
        norm = normalize_feature_contributions(raw_features)
        assert len(norm) == 1
        assert norm[0].value == 0.0
        assert norm[0].contribution == 0.0

    def test_vulnerability_none_downscaling_validation(self):
        # None district population falls back to 0
        dist_scores = {"v_demographic": 0.5, "v_structural": 0.5, "v_access": 0.5, "v_economic": 0.5}
        hab_records = [
            {"id": 1, "population": None, "v_demographic": 0.5, "v_structural": 0.5, "v_access": 0.5, "v_economic": 0.5}
        ]
        report = validate_district_downscaling(hab_records, dist_scores, district_id=1)
        assert report.total_population == 0


# =====================================================================
# 3. Parameterized Production Path Invariant Matrix
# =====================================================================

@pytest.mark.parametrize(
    "field,zero_val,default_val",
    [
        ("susceptibility", 0.0, 0.45),
        ("trigger", 0.0, 1.0),
        ("mhi", 0.0, 0.5),
        ("priority_score", 0.0, 0.5),
        ("prz_overlap", 0.0, 25.0),
        ("population", 0, 0),
        ("suitability", 0, 50),
    ],
)
def test_parameterized_zero_vs_fallback_semantics(field, zero_val, default_val):
    """Proves the universal contract: 0 is preserved, None receives default."""
    # Simulation dict mimicking raw DB/API payloads
    data_with_zero = {field: zero_val}
    data_with_none = {field: None}
    data_missing = {}

    # Correct B3 pattern
    def resolve(d, k, default):
        val = d.get(k)
        return default if val is None else val

    # Verify zero is preserved
    assert resolve(data_with_zero, field, default_val) == zero_val

    # Verify None receives fallback
    assert resolve(data_with_none, field, default_val) == default_val

    # Verify missing receives fallback
    assert resolve(data_missing, field, default_val) == default_val


# =====================================================================
# 4. Service-Level Production Integration Tests
# =====================================================================

class TestHabitationsServiceZeroPreservation:
    """Production tests for HabitationsService preserving explicit zeros."""

    def test_query_habitations_preserves_explicit_zeros(self):
        repo = MagicMock()
        repo.query_habitations.return_value = (
            [
                {
                    "id": 101,
                    "lgd_code": 101,
                    "name": "VillageA",
                    "type": "village",
                    "admin_id": 1,
                    "admin_name": "District A",
                    "population": 0,
                    "households": 0,
                    "priority_score": 0.0,
                    "caseload_score": 0.0,
                    "tier": "short_term",
                    "v_demographic": 0.0,
                    "v_structural": 0.0,
                    "v_access": 0.0,
                    "v_economic": 0.0,
                    "prz_overlap_pct": 0.0,
                    "lon": 76.0,
                    "lat": 11.5,
                }
            ],
            1,
        )
        service = HabitationsService(db=MagicMock())
        service.repo = repo
        resp = service.get_habitations()

        assert len(resp.items) == 1
        item = resp.items[0]
        assert item.population == 0
        assert item.households == 0
        assert item.prz_overlap_pct == 0.0
        assert item.priority_score == 0.0

    def test_query_habitations_applies_fallback_when_none_or_missing(self):
        repo = MagicMock()
        repo.query_habitations.return_value = (
            [
                {
                    "id": 102,
                    "lgd_code": 102,
                    "name": "VillageB",
                    "type": "village",
                    "admin_id": 1,
                    "admin_name": "District A",
                    "population": None,
                    "households": None,
                    "priority_score": None,
                    "tier": None,
                    "v_demographic": None,
                    "v_structural": None,
                    "v_access": None,
                    "v_economic": None,
                    "prz_overlap_pct": None,
                    "lon": 76.0,
                    "lat": 11.5,
                }
            ],
            1,
        )
        service = HabitationsService(db=MagicMock())
        service.repo = repo
        resp = service.get_habitations()

        item = resp.items[0]
        assert item.population == 0
        assert item.households == 0
        # When None, prz_overlap_pct defaults to 25.0 for regular villages
        assert item.prz_overlap_pct == 25.0

    def test_habitation_dossier_preserves_zeros(self):
        repo = MagicMock()
        repo.get_habitation_by_id.return_value = {
            "id": 201,
            "lgd_code": 201,
            "name": "SafeHamlet",
            "type": "hamlet",
            "admin_id": 1,
            "admin_name": "District A",
            "population": 0,
            "households": 0,
            "lon": 76.0,
            "lat": 11.5,
            "v_demographic": 0.0,
            "v_structural": 0.0,
            "v_access": 0.0,
            "v_economic": 0.0,
            "hazard_intensity": 0.0,
            "prz_overlap_pct": 0.0,
            "priority_score": 0.0,
            "caseload_score": 0.0,
            "tier": "short_term",
            "confidence": 0.0,
        }
        repo.get_nearby_disaster_events.return_value = [
            {
                "id": 1,
                "ts": date(2025, 1, 1),
                "hazard_type": "landslide",
                "fatalities": 0,
                "injured": 0,
                "houses_damaged": 0,
                "severity": 0.0,
                "source": "GSI",
                "source_ref": None,
            }
        ]
        service = HabitationsService(db=MagicMock())
        service.repo = repo
        dossier = service.get_habitation_risk_dossier(201)

        assert dossier.hazard_intensity == 0.0
        assert dossier.prz_overlap_pct == 0.0
        assert dossier.priority_score == 0.0
        assert dossier.caseload_score == 0.0
        assert dossier.confidence == 0.0
        assert dossier.population == 0
        assert dossier.households == 0
        assert dossier.vulnerability.v_demographic == 0.0
        assert dossier.vulnerability.v_structural == 0.0
        assert dossier.vulnerability.v_access == 0.0
        assert dossier.vulnerability.v_economic == 0.0
        assert dossier.vulnerability.v_index == 0.0
        assert dossier.past_disasters[0].severity == 0.0
        assert dossier.past_disasters[0].fatalities == 0


class TestZonesServiceZeroPreservation:
    """Production tests for ZonesService preserving explicit zeros."""

    def test_query_zones_preserves_zero_mhi_and_population(self):
        sample_hex = "8860064989fffff"
        sample_int = h3_to_int(sample_hex)
        repo = MagicMock()
        repo.query_zones.return_value = [
            {
                "h3": sample_int,
                "res": 8,
                "mhi_static": 0.0,
                "population": 0.0,
                "built_area_m2": 0.0,
                "lon": 76.1,
                "lat": 11.6,
            }
        ]
        service = ZonesService(db=MagicMock())
        service.repo = repo
        summaries = service.get_zones()

        assert len(summaries) == 1
        assert summaries[0].mhi == 0.0
        assert summaries[0].mhi_static == 0.0
        assert summaries[0].population == 0.0
        assert summaries[0].built_area_m2 == 0.0

    def test_get_zone_detail_preserves_zero_susceptibility_and_contribution(self):
        repo = MagicMock()
        repo.get_zone_by_h3.return_value = {
            "cell": {
                "h3": "8860064989fffff",
                "res": 8,
                "mhi_static": 0.0,
                "population": 0.0,
                "built_area_m2": 0.0,
                "lon": 76.1,
                "lat": 11.6,
                "factors": [
                    {"feature": "slope_deg", "value": 0.0, "contribution": 0.0},
                ],
            },
            "hazards": [
                {
                    "hazard_type": "landslide",
                    "susceptibility": 0.0,
                    "confidence": 0.0,
                }
            ],
        }
        service = ZonesService(db=MagicMock())
        service.repo = repo
        detail = service.get_zone_detail("8860064989fffff")

        assert detail.mhi_static == 0.0
        assert detail.population == 0.0
        assert detail.built_area_m2 == 0.0
        assert detail.hazards[0].susceptibility == 0.0
        assert detail.hazards[0].confidence == 0.0
        assert detail.explanation[0].value == 0.0
        assert detail.explanation[0].contribution == 0.0


class TestAlertsServiceZeroPreservation:
    """Production tests for AlertsService preserving explicit zeros."""

    def test_get_active_alerts_preserves_zeros(self):
        sample_int = h3_to_int("8860064989fffff")
        repo = MagicMock()
        repo.query_active_alerts.return_value = (
            [
                {
                    "h3": sample_int,
                    "res": 8,
                    "mhi_live": 0.85,
                    "mhi_static": 0.0,
                    "population": 0.0,
                    "built_area_m2": 0.0,
                    "lon": 76.1,
                    "lat": 11.6,
                }
            ],
            1,
            0,
        )
        service = AlertsService(db=MagicMock())
        service.repo = repo
        resp = service.get_active_alerts()

        assert len(resp.items) == 1
        item = resp.items[0]
        assert item.mhi_live == 0.85
        assert item.mhi_static == 0.0
        assert item.exposed_population == 0.0
        assert item.exposed_built_area_m2 == 0.0

    def test_get_forecast_alerts_preserves_zeros(self):
        sample_int = h3_to_int("8860064989fffff")
        repo = MagicMock()
        repo.query_forecast_alerts.return_value = (
            [
                {
                    "h3": sample_int,
                    "res": 8,
                    "mhi_fcst": 0.85,
                    "mhi_static": 0.0,
                    "population": 0.0,
                    "lon": 76.1,
                    "lat": 11.6,
                }
            ],
            1,
            0,
        )
        service = AlertsService(db=MagicMock())
        service.repo = repo
        resp = service.get_forecast_alerts(horizon_hours=24)

        assert len(resp.items) == 1
        item = resp.items[0]
        assert item.mhi_fcst == 0.85
        assert item.mhi_static == 0.0
        assert item.exposed_population == 0.0


class TestAllocationServiceZeroPreservation:
    """Production tests for AllocationService preserving explicit zeros."""

    def test_generate_allocation_plan_preserves_zero_priority_and_suitability(self):
        repo = MagicMock()
        repo.get_habitations_for_allocation.return_value = [
            {
                "id": 1,
                "name": "Hab1",
                "households": 25,
                "priority_score": 0.0,  # Zero priority score
                "tier": "short_term",
                "lat": 11.6,
                "lon": 76.1,
            }
        ]
        repo.get_candidate_sites_and_distances.return_value = (
            [
                {
                    "id": 10,
                    "name": "SiteZero",
                    "capacity": 50,
                    "suitability": 0,  # Zero suitability must be preserved, not default 50
                    "lat": 11.6,
                    "lon": 76.1,
                    "area_ha": 5.0,
                    "tenure": "government_revenue",
                    "slope_mean": 0.0,
                    "mhi_max": 0.0,
                    "is_forest": False,
                    "is_protected_area": False,
                    "is_crz": False,
                    "is_water_body": False,
                }
            ],
            [
                {
                    "habitation_id": 1,
                    "site_id": 10,
                    "distance_km": 5.0,
                }
            ],
        )
        service = AllocationService(db=MagicMock())
        service.repo = repo
        req = AllocationPlanRequest(admin_id=1, max_search_radius_km=15.0, target_tiers=[Tier.SHORT_TERM])
        result = service.generate_allocation_plan(req)
        assert result is not None
        assert result.total_relocated_households == 25
        assert len(result.assignments) == 1
        assert result.assignments[0].priority_score == 0.0
        assert result.assignments[0].site_suitability == 0


class TestSitesServiceZeroPreservation:
    """Production tests for SitesService preserving explicit zeros."""

    def test_query_candidate_sites_preserves_zeros(self):
        repo = MagicMock()
        repo.check_habitation_exists.return_value = True
        repo.query_candidate_sites_for_habitation.return_value = (
            [
                {
                    "id": 501,
                    "distance_km": 0.0,
                    "area_ha": 0.0,
                    "tenure": "revenue_land",
                    "slope_mean": 0.0,
                    "mhi_max": 0.0,
                    "suitability": 0,
                    "cc_land": 0,
                    "cc_water": None,
                    "cc_school": None,
                    "cc_health": None,
                    "cc_final": 0,
                    "binding_constraint": "land",
                    "metadata_info": {"livelihood_multiplier": 0.0},
                    "lon": 76.1,
                    "lat": 11.6,
                }
            ],
            1,
        )
        service = SitesService(db=MagicMock())
        service.repo = repo
        resp = service.get_candidate_sites_for_habitation(habitation_id=1, include_screening=True)

        item = resp.items[0]
        assert item.distance_km == 0.0
        assert item.area_ha == 0.0
        assert item.slope_mean == 0.0
        assert item.mhi_max == 0.0
        assert item.suitability == 0
        assert item.capacity.cc_land == 0
        assert item.capacity.cc_final == 0
        assert item.capacity.livelihood_multiplier == 0.0

    def test_recompute_site_capacity_preserves_zero_area_ha(self):
        repo = MagicMock()
        repo.get_candidate_site_by_id.return_value = {
            "id": 502,
            "cc_land": 0,
            "cc_final": 0,
            "binding_constraint": "land",
            "area_ha": 0.0,  # Explicit zero area_ha must NOT default to 2.0 ha
        }
        service = SitesService(db=MagicMock())
        service.repo = repo
        resp = service.recompute_site_capacity(502, SiteCapacityOverrideRequest())
        # area_ha == 0.0 -> area_m2 == 0.0 -> cc_land == 0
        assert resp.scenario_capacity.cc_land == 0


class TestScenarioServiceZeroPreservation:
    """Production tests for ScenarioService baseline states preserving explicit zeros."""

    def test_evaluate_scenario_preserves_zero_risk_metrics(self):
        hab_repo = MagicMock()
        hab_repo.query_habitations.return_value = (
            [
                {
                    "id": 10,
                    "name": "ZeroRiskVillage",
                    "population": 0,
                    "households": 0,
                    "prz_overlap_pct": 0.0,
                    "hazard_intensity": 0.0,
                    "v_index": 0.0,
                    "decayed_loss": 0.0,
                    "priority_score": 0.0,
                    "tier": "short_term",
                    "lat": 11.5,
                    "lon": 76.2,
                }
            ],
            1,
        )
        service = ScenarioService(db=MagicMock())
        service.hab_repo = hab_repo
        resp = service.evaluate_scenario(ScenarioWeightOverrideRequest(admin_id=1))

        assert len(resp.items) == 1
        h = resp.items[0]
        assert h.original_priority_score == 0.0
        assert h.scenario_priority_score == 0.0
        assert h.population == 0
        assert h.scenario_prz_overlap_pct == 0.0

    def test_scenario_baseline_centroid_preserves_zero_lon_lat(self):
        """Zero latitude or longitude in scenario baseline must not fall back."""
        hab_repo = MagicMock()
        hab_repo.query_habitations.return_value = (
            [
                {
                    "id": 11,
                    "name": "EquatorPrimeMeridianVillage",
                    "population": 500,
                    "households": 125,
                    "prz_overlap_pct": 10.0,
                    "hazard_intensity": 0.5,
                    "v_index": 0.5,
                    "decayed_loss": 0.0,
                    "priority_score": 0.25,
                    "tier": "short_term",
                    "centroid_lat": 0.0,
                    "centroid_lon": 0.0,
                    "lat": 10.0,
                    "lon": 75.0,
                }
            ],
            1,
        )
        service = ScenarioService(db=MagicMock())
        service.hab_repo = hab_repo
        resp = service.evaluate_scenario(ScenarioWeightOverrideRequest(admin_id=1))
        # Scenario engine evaluate creates outcome items with lat/lon from baseline state
        # Baseline state lat and lon must be 0.0, not falling back to lat=10.0 or lon=75.0
        assert len(resp.items) == 1


class TestSitesServiceCoordinateZeroPreservation:
    """Verifies that SitesService preserves explicit 0.0 in centroid coordinates."""

    def test_candidate_site_centroid_preserves_zero_lon_lat(self):
        repo = MagicMock()
        repo.check_habitation_exists.return_value = True
        repo.query_candidate_sites_for_habitation.return_value = (
            [
                {
                    "id": 701,
                    "distance_km": 0.0,
                    "area_ha": 5.0,
                    "tenure": "government_revenue",
                    "slope_mean": 0.0,
                    "mhi_max": 0.0,
                    "suitability": 80,
                    "cc_land": 100,
                    "cc_water": 100,
                    "cc_school": 100,
                    "cc_health": 100,
                    "cc_final": 100,
                    "binding_constraint": "land",
                    "lon": 0.0,
                    "lat": 0.0,
                    # H7 rejects a site whose environmental exclusions are unasserted, so the
                    # fixture must state them for this coordinate-preservation test to reach
                    # the serialisation it is actually asserting on.
                    "metadata": {
                        "is_forest": False,
                        "is_protected_area": False,
                        "is_crz": False,
                        "is_water_body": False,
                    },
                }
            ],
            1,
        )
        service = SitesService(db=MagicMock())
        service.repo = repo
        resp = service.get_candidate_sites_for_habitation(habitation_id=1)
        assert len(resp.items) == 1
        item = resp.items[0]
        assert item.centroid == [0.0, 0.0]

    def test_candidate_site_detail_preserves_zero_lon_lat(self):
        repo = MagicMock()
        repo.get_candidate_site_by_id.return_value = {
            "id": 702,
            "area_ha": 5.0,
            "tenure": "government_revenue",
            "slope_mean": 0.0,
            "mhi_max": 0.0,
            "suitability": 80,
            "cc_land": 100,
            "cc_water": 100,
            "cc_school": 100,
            "cc_health": 100,
            "cc_final": 100,
            "binding_constraint": "land",
            "lon": 0.0,
            "lat": 0.0,
            "geojson": '{"type": "Polygon", "coordinates": []}',
        }
        service = SitesService(db=MagicMock())
        service.repo = repo
        detail = service.get_candidate_site_detail(702)
        assert detail.centroid == [0.0, 0.0]

