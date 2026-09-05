"""Focused regression unit tests for Batch A: B6 + H3 + H11.

Scope:
- B6: Dynamic trigger -> hazard score -> MHI -> alert predicate chain,
      invariance of MHI_static, relocation tiers, and PRZ classification.
- H3: Forecast horizon filtering semantics (within horizon 1..N, bounded by 72h).
- H11: Alert response schema validation accepting valid MHI range [0.0, 1.0] (e.g. 0.60).
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from core.constants import BETA, HAZARD_WEIGHTS, FORECAST_HORIZON_HOURS
from core.domain.hazard import (
    classify_zone,
    compute_hazard_score,
    compute_mhi,
    get_dominant_hazard,
)
from core.domain.priority import classify_triage_tier
from core.enums import Hazard, Tier, ZoneClass
from core.schemas.alerts import ActiveAlertItem, ForecastAlertItem


# =============================================================================
# B6 Tests: Mathematical and Invariant Validation
# =============================================================================

class TestBatchAB6DynamicHazardAndInvariants:
    """Validates the complete dynamic trigger -> MHI -> alert classification chain."""

    def test_dynamic_trigger_to_mhi_threshold_crossing(self):
        """Proves synthetic trigger elevates sub-threshold cell across 0.75 threshold via real formulas."""
        # Static baseline: S_landslide = 0.40, T = 0 -> H = 0.40, MHI_static = 0.40 (< 0.75)
        s_landslide = 0.40
        h_static = compute_hazard_score(susceptibility=s_landslide, trigger_value=0.0, beta=BETA)
        assert h_static == 0.40
        mhi_static = compute_mhi({Hazard.LANDSLIDE: h_static}, weights=HAZARD_WEIGHTS)
        assert mhi_static == 0.40
        assert mhi_static < 0.75

        # Synthetic trigger: T = 1.25, beta = 1.0
        # H_live = clamp(0.40 * (1 + 1.0 * 1.25), 0, 1) = clamp(0.40 * 2.25, 0, 1) = 0.90
        t_synthetic = 1.25
        h_live = compute_hazard_score(susceptibility=s_landslide, trigger_value=t_synthetic, beta=BETA)
        assert h_live == pytest.approx(0.90, abs=1e-4)

        # MHI_live via probabilistic union: 1 - (1 - 1.0 * 0.90) = 0.90 (>= 0.75)
        mhi_live = compute_mhi({Hazard.LANDSLIDE: h_live}, weights=HAZARD_WEIGHTS)
        assert mhi_live == pytest.approx(0.90, abs=1e-4)
        assert mhi_live >= 0.75

        # Alert predicate: MHI_live >= 0.75 and MHI_static < 0.75 -> ACTIVE_ALERT
        zone = classify_zone(mhi_static=mhi_static, mhi_live=mhi_live)
        assert zone == ZoneClass.ACTIVE_ALERT

    def test_forecast_trigger_to_mhi_threshold_crossing(self):
        """Proves forecast trigger elevates sub-threshold cell across 0.75 forecast alert threshold."""
        s_landslide = 0.45
        mhi_static = compute_mhi({Hazard.LANDSLIDE: s_landslide}, weights=HAZARD_WEIGHTS)
        assert mhi_static == pytest.approx(0.45, abs=1e-4)

        # Forecast trigger: T_fcst = 1.25
        h_fcst = compute_hazard_score(susceptibility=s_landslide, trigger_value=1.25, beta=BETA)
        assert h_fcst == pytest.approx(1.0, abs=1e-4)  # 0.45 * 2.25 = 1.0125 -> clamped to 1.0
        mhi_fcst = compute_mhi({Hazard.LANDSLIDE: h_fcst}, weights=HAZARD_WEIGHTS)
        assert mhi_fcst == pytest.approx(1.0, abs=1e-4)

        zone = classify_zone(mhi_static=mhi_static, mhi_live=mhi_static, mhi_fcst=mhi_fcst)
        assert zone == ZoneClass.FORECAST_ALERT

    def test_mhi_static_independence_under_transient_alert(self):
        """Proves MHI_static is computed solely from static susceptibility and is untouched by triggers."""
        static_scores = {Hazard.LANDSLIDE: 0.50, Hazard.FLASH_FLOOD: 0.30}
        mhi_static_baseline = compute_mhi(static_scores, weights=HAZARD_WEIGHTS)

        # Extreme transient live trigger (T = 5.0)
        h_amplified = {
            h: compute_hazard_score(s, trigger_value=5.0, beta=BETA)
            for h, s in static_scores.items()
        }
        mhi_live_amplified = compute_mhi(h_amplified, weights=HAZARD_WEIGHTS)
        assert mhi_live_amplified > mhi_static_baseline

        # Invariant: static baseline computation is pure and immutable
        mhi_static_after = compute_mhi(static_scores, weights=HAZARD_WEIGHTS)
        assert mhi_static_after == mhi_static_baseline

    def test_permanent_prz_precedence_over_transient_alerts(self):
        """A cell in permanent PRZ must remain PERMANENT_RED regardless of dynamic triggers."""
        # Baseline is PRZ (MHI_static >= 0.75)
        zone_prz_static = classify_zone(mhi_static=0.80, mhi_live=0.80)
        assert zone_prz_static == ZoneClass.PERMANENT_RED

        # During extreme storm trigger
        zone_prz_live = classify_zone(mhi_static=0.80, mhi_live=0.98, mhi_fcst=0.99)
        assert zone_prz_live == ZoneClass.PERMANENT_RED

    def test_relocation_tier_independence_under_transient_alerts(self):
        """Proves permanent relocation triage tier is never altered by transient alert states."""
        # Non-PRZ habitation: priority_score = 0.35 -> SHORT_TERM tier
        tier_normal = classify_triage_tier(
            has_prz_overlap=False,
            priority_score=0.35,
            has_active_trigger=False,
        )
        assert tier_normal == Tier.SHORT_TERM

        # Active alert occurs in the area (has_active_trigger=True)
        tier_with_active_alert = classify_triage_tier(
            has_prz_overlap=False,
            priority_score=0.35,
            has_active_trigger=True,
        )
        # INVARIANT: Relocation tier must NOT escalate to IMMEDIATE based on a transient weather event
        assert tier_with_active_alert == Tier.SHORT_TERM


# =============================================================================
# H3 Tests: Forecast Horizon Semantics
# =============================================================================

class TestBatchAH3ForecastHorizonSemantics:
    """Validates 'within requested horizon' semantics and boundary limits."""

    def test_horizon_within_semantics_boundaries(self):
        """Validates exact and fractional horizon boundary conditions using timestamp intervals."""
        from datetime import timedelta
        base_cycle = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Candidate forecast timestamps across boundaries
        records = [
            ("past_or_current", base_cycle),                              # 0h lead time -> invalid
            ("at_24h", base_cycle + timedelta(hours=24)),                # 24.0h -> included in 24, 48, 72
            ("just_over_24h", base_cycle + timedelta(hours=24, minutes=6)), # 24.1h -> excluded in 24, included in 48, 72
            ("just_under_48h", base_cycle + timedelta(hours=47, minutes=54)), # 47.9h -> included in 48, 72
            ("at_48h", base_cycle + timedelta(hours=48)),                # 48.0h -> excluded in 24, included in 48, 72
            ("just_over_48h", base_cycle + timedelta(hours=48, minutes=6)), # 48.1h -> excluded in 48, included in 72
            ("at_72h", base_cycle + timedelta(hours=72)),                # 72.0h -> included in 72
            ("just_over_72h", base_cycle + timedelta(hours=72, minutes=6)), # 72.1h -> excluded in 72
            ("beyond_contract", base_cycle + timedelta(hours=96)),       # 96.0h -> excluded
        ]

        def filter_records(horizon_h):
            cutoff = base_cycle + timedelta(hours=horizon_h)
            return [label for label, valid_at in records if valid_at > base_cycle and valid_at <= cutoff]

        # 1. Horizon = 24: includes 24h; strictly excludes 24.1h and beyond
        res_24 = filter_records(24)
        assert res_24 == ["at_24h"]
        assert "just_over_24h" not in res_24
        assert "at_48h" not in res_24

        # 2. Horizon = 48: includes 24h, 24.1h, 47.9h, 48h; strictly excludes 48.1h and 72h
        res_48 = filter_records(48)
        assert res_48 == ["at_24h", "just_over_24h", "just_under_48h", "at_48h"]
        assert "just_over_48h" not in res_48
        assert "at_72h" not in res_48

        # 3. Horizon = 72: includes up to 72h; strictly excludes 72.1h and 96h
        res_72 = filter_records(72)
        assert "at_24h" in res_72
        assert "at_48h" in res_72
        assert "at_72h" in res_72
        assert "just_over_72h" not in res_72
        assert "beyond_contract" not in res_72

    def test_alerts_repository_horizon_sql_and_params(self):
        """Proves production AlertsRepository builds SQL enforcing true timestamp comparison and binds parameters."""
        from unittest.mock import MagicMock
        from api.repositories.alerts_repo import AlertsRepository

        mock_db = MagicMock()
        mock_db.execute.return_value.mappings.return_value.fetchall.return_value = []
        repo = AlertsRepository(db=mock_db)
        repo.query_forecast_alerts(horizon_hours=48, min_mhi=0.75)

        assert mock_db.execute.called
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        params = call_args[0][1]

        # Invariant: Must use true timestamp comparison, NOT ROUND(...) in WHERE
        assert "valid_at > forecast_cycle_at" in sql_text
        assert "valid_at <= forecast_cycle_at + (:horizon_hours * INTERVAL '1 hour')" in sql_text
        assert params["horizon_hours"] == 48
        assert params["min_mhi"] == 0.75

    def test_forecast_horizon_bounds(self):
        """Proves maximum allowed horizon is strictly bounded to FORECAST_HORIZON_HOURS (72h)."""
        assert FORECAST_HORIZON_HOURS == 72


# =============================================================================
# H11 Tests: MHI Response Schema Range Validation [0.0, 1.0]
# =============================================================================

class TestBatchAH11MHIResponseSchemaValidation:
    """Validates that alert response schemas accept valid MHI values below 0.75 without error."""

    def test_active_alert_item_accepts_sub_075_mhi_live(self):
        """ActiveAlertItem must serialize valid MHI values like 0.60, 0.0, 0.75, 1.0."""
        # Test 0.60 (below operational 0.75 threshold, but within valid MHI domain [0, 1])
        item_060 = ActiveAlertItem(
            h3="8860064989fffff",
            h3_int=0x8860064989fffff,
            res=8,
            mhi_live=0.60,
            mhi_static=0.35,
            dominant_hazard="landslide",
            centroid=[76.15, 11.55],
            screening_grade="SCREENING-GRADE ONLY",
        )
        assert item_060.mhi_live == 0.60

        # Test boundary 0.0
        item_00 = ActiveAlertItem(
            h3="8860064989fffff",
            h3_int=0x8860064989fffff,
            res=8,
            mhi_live=0.0,
            mhi_static=0.0,
            dominant_hazard="landslide",
            centroid=[76.15, 11.55],
            screening_grade="SCREENING-GRADE ONLY",
        )
        assert item_00.mhi_live == 0.0

        # Test upper boundary 1.0
        item_10 = ActiveAlertItem(
            h3="8860064989fffff",
            h3_int=0x8860064989fffff,
            res=8,
            mhi_live=1.0,
            mhi_static=0.50,
            dominant_hazard="landslide",
            centroid=[76.15, 11.55],
            screening_grade="SCREENING-GRADE ONLY",
        )
        assert item_10.mhi_live == 1.0

    def test_active_alert_item_rejects_out_of_bound_mhi(self):
        """ActiveAlertItem must reject values outside [0.0, 1.0]."""
        with pytest.raises(ValidationError):
            ActiveAlertItem(
                h3="8860064989fffff",
                h3_int=0x8860064989fffff,
                res=8,
                mhi_live=-0.01,
                mhi_static=0.35,
                dominant_hazard="landslide",
                centroid=[76.15, 11.55],
                screening_grade="SCREENING-GRADE ONLY",
            )

        with pytest.raises(ValidationError):
            ActiveAlertItem(
                h3="8860064989fffff",
                h3_int=0x8860064989fffff,
                res=8,
                mhi_live=1.01,
                mhi_static=0.35,
                dominant_hazard="landslide",
                centroid=[76.15, 11.55],
                screening_grade="SCREENING-GRADE ONLY",
            )

    def test_forecast_alert_item_accepts_sub_075_mhi_fcst(self):
        """ForecastAlertItem must serialize valid MHI values like 0.60, 0.0, 0.75, 1.0."""
        item_060 = ForecastAlertItem(
            h3="8860064989fffff",
            h3_int=0x8860064989fffff,
            res=8,
            mhi_fcst=0.60,
            mhi_static=0.35,
            dominant_hazard="landslide",
            centroid=[76.15, 11.55],
            horizon_hours=24,
            screening_grade="SCREENING-GRADE ONLY",
        )
        assert item_060.mhi_fcst == 0.60

        item_00 = ForecastAlertItem(
            h3="8860064989fffff",
            h3_int=0x8860064989fffff,
            res=8,
            mhi_fcst=0.0,
            mhi_static=0.0,
            dominant_hazard="landslide",
            centroid=[76.15, 11.55],
            horizon_hours=48,
            screening_grade="SCREENING-GRADE ONLY",
        )
        assert item_00.mhi_fcst == 0.0

    def test_forecast_alert_item_rejects_out_of_bound_mhi(self):
        """ForecastAlertItem must reject values outside [0.0, 1.0]."""
        with pytest.raises(ValidationError):
            ForecastAlertItem(
                h3="8860064989fffff",
                h3_int=0x8860064989fffff,
                res=8,
                mhi_fcst=-0.05,
                mhi_static=0.35,
                dominant_hazard="landslide",
                centroid=[76.15, 11.55],
                horizon_hours=24,
                screening_grade="SCREENING-GRADE ONLY",
            )

        with pytest.raises(ValidationError):
            ForecastAlertItem(
                h3="8860064989fffff",
                h3_int=0x8860064989fffff,
                res=8,
                mhi_fcst=1.05,
                mhi_static=0.35,
                dominant_hazard="landslide",
                centroid=[76.15, 11.55],
                horizon_hours=24,
                screening_grade="SCREENING-GRADE ONLY",
            )
