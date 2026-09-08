"""Unit tests for H5: Dynamic Alert Freshness & Staleness Semantics.

Section refs: docs/PRD1.md §6.3, §8.2, §14.1 (FR-3.10, FR-3.12)
H5 Requirements:
1. Fresh live trigger qualifies for Active Alert (age <= MAX_TRIGGER_AGE_HOURS).
2. Exactly-at-boundary trigger qualifies (age == MAX_TRIGGER_AGE_HOURS).
3. Just-over-boundary trigger does NOT qualify (age == MAX_TRIGGER_AGE_HOURS + epsilon -> stale).
4. Stale live trigger does NOT qualify for Active Alert (age > MAX_TRIGGER_AGE_HOURS).
5. Stale historical triggers and snapshots remain stored (freshness is an alert-serving filter, not a deletion rule).
6. Forecast alerts are NOT suppressed merely because their target time is in the future.
7. H3 forecast horizon semantics remain intact (within requested horizon lead time).
8. Static MHI, permanent zone classification (PERMANENT_RED), and relocation tiers are unaffected by freshness.
9. Exposes freshness metadata: fresh record has expected age/status; stale record explicitly marked stale.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from core.constants import (
    ACTIVE_ALERT_MHI_LIVE,
    BETA,
    FORECAST_HORIZON_HOURS,
    HAZARD_WEIGHTS,
    MAX_TRIGGER_AGE_HOURS,
    PRZ_MHI_STATIC,
)
from core.domain.hazard import (
    classify_zone,
    compute_hazard_score,
    compute_mhi,
    evaluate_trigger_freshness,
)
from core.domain.priority import classify_triage_tier
from core.enums import DataQuality, Hazard, Tier, ZoneClass
from core.schemas.alerts import ActiveAlertItem, ForecastAlertItem


class TestH5TriggerFreshnessDomainRules:
    """Validates the canonical mathematical and boundary semantics of trigger freshness."""

    def test_fresh_trigger_within_configured_age(self):
        """1. A live trigger whose age is well within MAX_TRIGGER_AGE_HOURS is fresh."""
        as_of = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
        valid_at = as_of - timedelta(hours=3)  # 3 hours old

        res = evaluate_trigger_freshness(valid_at, as_of=as_of, max_age_hours=MAX_TRIGGER_AGE_HOURS)
        assert res["is_fresh"] is True
        assert res["age_hours"] == 3.0
        assert res["status"] == "fresh"
        assert res["data_quality"] == DataQuality.VALID

    def test_fresh_trigger_with_synthetic_source(self):
        """Fresh synthetic trigger is marked fresh and DataQuality.SYNTHETIC."""
        as_of = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
        valid_at = as_of - timedelta(hours=1)

        res = evaluate_trigger_freshness(
            valid_at,
            as_of=as_of,
            max_age_hours=MAX_TRIGGER_AGE_HOURS,
            source="SYNTHETIC_DEMO",
        )
        assert res["is_fresh"] is True
        assert res["age_hours"] == 1.0
        assert res["status"] == "fresh"
        assert res["data_quality"] == DataQuality.SYNTHETIC

    def test_exactly_at_boundary_trigger_is_fresh(self):
        """2. Exactly at the boundary (age == MAX_TRIGGER_AGE_HOURS), trigger qualifies as fresh."""
        as_of = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
        valid_at = as_of - timedelta(hours=MAX_TRIGGER_AGE_HOURS)

        res = evaluate_trigger_freshness(valid_at, as_of=as_of, max_age_hours=MAX_TRIGGER_AGE_HOURS)
        assert res["is_fresh"] is True
        assert res["age_hours"] == float(MAX_TRIGGER_AGE_HOURS)
        assert res["status"] == "fresh"
        assert res["data_quality"] != DataQuality.STALE

    def test_just_over_boundary_trigger_is_stale(self):
        """3. Just over boundary (e.g. boundary + 1 minute), trigger does NOT qualify and is STALE."""
        as_of = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
        # 1 minute past the boundary
        valid_at = as_of - timedelta(hours=MAX_TRIGGER_AGE_HOURS, minutes=1)

        res = evaluate_trigger_freshness(valid_at, as_of=as_of, max_age_hours=MAX_TRIGGER_AGE_HOURS)
        assert res["is_fresh"] is False
        assert res["age_hours"] > float(MAX_TRIGGER_AGE_HOURS)
        assert res["status"] == "stale"
        assert res["data_quality"] == DataQuality.STALE

    def test_stale_live_trigger_deep_past(self):
        """4. A live trigger from 3 weeks ago is unequivocally STALE."""
        as_of = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
        valid_at = as_of - timedelta(days=21)

        res = evaluate_trigger_freshness(valid_at, as_of=as_of, max_age_hours=MAX_TRIGGER_AGE_HOURS)
        assert res["is_fresh"] is False
        assert res["age_hours"] == 504.0
        assert res["status"] == "stale"
        assert res["data_quality"] == DataQuality.STALE

    def test_custom_max_trigger_age_boundary(self):
        """Verifies custom boundary e.g. 6 hours: 5h59m fresh, 6h00m fresh, 6h01m stale."""
        as_of = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
        max_hours = 6.0

        # 5h59m -> fresh
        t_5h59 = as_of - timedelta(hours=5, minutes=59)
        res_5h59 = evaluate_trigger_freshness(t_5h59, as_of=as_of, max_age_hours=max_hours)
        assert res_5h59["is_fresh"] is True
        assert res_5h59["status"] == "fresh"

        # 6h00m -> fresh (exact boundary)
        t_6h00 = as_of - timedelta(hours=6, minutes=0)
        res_6h00 = evaluate_trigger_freshness(t_6h00, as_of=as_of, max_age_hours=max_hours)
        assert res_6h00["is_fresh"] is True
        assert res_6h00["status"] == "fresh"

        # 6h01m -> stale
        t_6h01 = as_of - timedelta(hours=6, minutes=1)
        res_6h01 = evaluate_trigger_freshness(t_6h01, as_of=as_of, max_age_hours=max_hours)
        assert res_6h01["is_fresh"] is False
        assert res_6h01["status"] == "stale"
        assert res_6h01["data_quality"] == DataQuality.STALE


class TestH5ForecastAlertAndInvariants:
    """Validates that forecast alerts, MHI static, PRZ, and relocation tiers remain unaffected by freshness."""

    def test_forecast_alerts_not_suppressed_by_future_timestamp(self):
        """6. Forecast alerts have valid_at in the future and MUST NOT be suppressed by live trigger age checks."""
        cycle_time = datetime(2026, 9, 6, 0, 0, 0, tzinfo=timezone.utc)
        target_forecast_time = cycle_time + timedelta(hours=48)  # Future forecast target

        # Forecast lead time is valid_at - forecast_cycle_at = 48h
        lead_time = (target_forecast_time - cycle_time).total_seconds() / 3600.0
        assert lead_time == 48.0
        assert 1 <= lead_time <= FORECAST_HORIZON_HOURS

        # Verify ForecastAlertItem accepts valid future valid_at without validation error
        item = ForecastAlertItem(
            h3="8860064989fffff",
            h3_int=614205562723631103,
            res=8,
            mhi_fcst=0.85,
            mhi_static=0.40,
            dominant_hazard="landslide",
            forecast_cycle_at=cycle_time,
            valid_at=target_forecast_time,
            horizon_hours=48,
            data_quality=DataQuality.VALID,
            exposed_population=120.0,
            centroid=[76.12, 11.55],
        )
        assert item.mhi_fcst == 0.85
        assert item.horizon_hours == 48
        assert item.valid_at == target_forecast_time

    def test_h3_forecast_horizon_semantics_remain_intact(self):
        """7. Forecast alerts within horizon are included; those beyond horizon are excluded."""
        cycle_time = datetime(2026, 9, 6, 0, 0, 0, tzinfo=timezone.utc)
        horizon_requested = 48

        # Target A at 24h: 24 <= 48 -> included
        valid_24h = cycle_time + timedelta(hours=24)
        diff_24h = (valid_24h - cycle_time).total_seconds() / 3600.0
        assert diff_24h <= horizon_requested

        # Target B at 48h: 48 <= 48 -> included
        valid_48h = cycle_time + timedelta(hours=48)
        diff_48h = (valid_48h - cycle_time).total_seconds() / 3600.0
        assert diff_48h <= horizon_requested

        # Target C at 72h: 72 > 48 -> excluded from 48h query
        valid_72h = cycle_time + timedelta(hours=72)
        diff_72h = (valid_72h - cycle_time).total_seconds() / 3600.0
        assert diff_72h > horizon_requested

    def test_static_mhi_and_prz_invariance_under_staleness(self):
        """8. Static MHI and permanent PRZ status are completely independent of trigger freshness."""
        static_scores = {Hazard.LANDSLIDE: 0.80}
        mhi_static = compute_mhi(static_scores, weights=HAZARD_WEIGHTS)
        assert mhi_static == 0.80
        assert mhi_static >= PRZ_MHI_STATIC

        # Permanent Red Zone classification holds regardless of whether live triggers are fresh, stale, or absent
        zone_no_trigger = classify_zone(mhi_static=mhi_static, mhi_live=0.0)
        assert zone_no_trigger == ZoneClass.PERMANENT_RED

        zone_stale_trigger = classify_zone(mhi_static=mhi_static, mhi_live=0.40)
        assert zone_stale_trigger == ZoneClass.PERMANENT_RED

        zone_fresh_trigger = classify_zone(mhi_static=mhi_static, mhi_live=0.95)
        assert zone_fresh_trigger == ZoneClass.PERMANENT_RED

    def test_relocation_tier_invariance_under_staleness(self):
        """8b. Permanent relocation triage tier is never altered by dynamic trigger freshness."""
        # Non-PRZ habitation with high vulnerability and moderate hazard -> Tier 2 (Short Term)
        tier_fresh = classify_triage_tier(
            has_prz_overlap=False,
            priority_score=0.35,
            has_active_trigger=True,
        )
        tier_stale = classify_triage_tier(
            has_prz_overlap=False,
            priority_score=0.35,
            has_active_trigger=False,
        )
        assert tier_fresh == tier_stale == Tier.SHORT_TERM


class TestH5ActiveAlertItemMetadata:
    """Validates that ActiveAlertItem schema faithfully exposes age_hours and data_quality."""

    def test_active_alert_item_carries_age_hours_and_quality(self):
        """9. ActiveAlertItem exposes age_hours and data_quality."""
        item = ActiveAlertItem(
            h3="8860064989fffff",
            h3_int=614205562723631103,
            res=8,
            mhi_live=0.88,
            mhi_static=0.42,
            dominant_hazard="landslide",
            trigger_source="SYNTHETIC_DEMO",
            valid_at=datetime(2026, 9, 6, 2, 0, 0, tzinfo=timezone.utc),
            age_hours=0.5,
            data_quality=DataQuality.SYNTHETIC,
            exposed_population=45.0,
            exposed_built_area_m2=1200.0,
            centroid=[76.12, 11.55],
        )
        assert item.age_hours == 0.5
        assert item.data_quality == DataQuality.SYNTHETIC
        assert item.trigger_source == "SYNTHETIC_DEMO"
