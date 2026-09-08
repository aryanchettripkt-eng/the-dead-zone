"""Unit tests for Active Alert Zones, Forecast Alert Zones, and Invariants (Day 6).

Section refs: docs/PRD1.md §6.3, §8.2, §14.1 (FR-3.8, FR-3.10, FR-3.12, FR-3.15)
"""

import pytest
from core.constants import ACTIVE_ALERT_MHI_LIVE, PRZ_MHI_STATIC
from core.domain.hazard import (
    classify_zone,
    compute_hazard_score,
    compute_mhi,
)
from core.enums import Hazard, Tier, ZoneClass


class TestActiveAndForecastAlertZones:
    """Tests for transient alert states, threshold crossings, and relocation-tier invariance."""

    def test_active_alert_zone_condition(self):
        """FR-3.10: MHI_live >= 0.75 AND MHI_static < 0.75 -> Active Alert Zone."""
        # Static baseline is safe/caution (0.50), live trigger elevates MHI to 0.82
        zone = classify_zone(
            mhi_static=0.50,
            max_susceptibility=0.60,
            has_fatal_event_25yr=False,
            mhi_live=0.82,
        )
        assert zone == ZoneClass.ACTIVE_ALERT

    def test_permanent_red_zone_takes_precedence_over_active_alert(self):
        """Permanent Red Zone is never downgraded or re-classified by dynamic triggers."""
        # MHI_static is already >= 0.75 (Permanent Red Zone)
        zone = classify_zone(
            mhi_static=0.78,
            max_susceptibility=0.70,
            has_fatal_event_25yr=False,
            mhi_live=0.95,
        )
        assert zone == ZoneClass.PERMANENT_RED

    def test_forecast_alert_zone_condition(self):
        """FR-3.12: MHI_fcst >= 0.75 AND MHI_static < 0.75 AND MHI_live < 0.75 -> Forecast Alert Zone."""
        zone = classify_zone(
            mhi_static=0.40,
            max_susceptibility=0.50,
            has_fatal_event_25yr=False,
            mhi_live=0.30,
            mhi_fcst=0.80,
        )
        assert zone == ZoneClass.FORECAST_ALERT

    def test_active_alert_takes_precedence_over_forecast_alert(self):
        """If cell is actively in alert right now, it is active_alert, not forecast_alert."""
        zone = classify_zone(
            mhi_static=0.40,
            max_susceptibility=0.50,
            has_fatal_event_25yr=False,
            mhi_live=0.85,
            mhi_fcst=0.88,
        )
        assert zone == ZoneClass.ACTIVE_ALERT

    def test_transient_alert_decay(self):
        """When live trigger decays, cell reverts back to static baseline (Caution or None)."""
        # During storm: T=1.5 -> score elevated -> MHI_live=0.80 -> active_alert
        zone_during_storm = classify_zone(mhi_static=0.50, mhi_live=0.80)
        assert zone_during_storm == ZoneClass.ACTIVE_ALERT

        # 48h after storm: T=0.0 -> MHI_live=0.50 -> reverts to Caution Zone
        zone_after_storm = classify_zone(mhi_static=0.50, mhi_live=0.50)
        assert zone_after_storm == ZoneClass.CAUTION

    def test_relocation_tier_invariance_under_dynamic_triggers(self):
        """Dynamic alerts are transient emergency notifications and MUST NEVER alter relocation tiers."""
        # Relocation tiers are assigned by structural vulnerability + static PRZ overlap + loss history.
        # Active alert flag or forecast crossing has zero impact on permanent triage assignment.
        from core.domain.priority import classify_triage_tier

        # Static baseline: PRZ overlap is False, priority score is 0.35 -> Short-term tier
        tier_without_alert = classify_triage_tier(
            has_prz_overlap=False,
            priority_score=0.35,
            has_active_trigger=False,
        )
        assert tier_without_alert == Tier.SHORT_TERM

        # During a live storm (has_active_trigger=True), permanent relocation tier remains unchanged:
        tier_with_active_alert = classify_triage_tier(
            has_prz_overlap=False,
            priority_score=0.35,
            has_active_trigger=True,
        )
        assert tier_with_active_alert == Tier.SHORT_TERM
