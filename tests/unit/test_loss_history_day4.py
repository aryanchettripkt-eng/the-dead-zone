"""Unit tests for time-decayed loss history calculations.

Section refs: docs/PRD1.md §6.6, FR-6.2
"""

import pytest
from datetime import date
from core.domain.priority import compute_time_decayed_loss


class TestLossHistoryDay4:
    def test_exponential_decay_half_life_exact_values(self):
        """FR-6.2: Exponential decay L = sum e^(-lambda * dt) * severity."""
        ref_date = date(2026, 8, 30)

        # 0 years ago (today): weight = 1.0
        # 10 years ago (1 half-life): weight = 0.5
        # 20 years ago (2 half-lives): weight = 0.25
        # 30 years ago (3 half-lives): weight = 0.125
        events = [
            {"ts": date(2026, 8, 30), "severity": 1.0},
            {"ts": date(2016, 8, 30), "severity": 1.0},
            {"ts": date(2006, 8, 30), "severity": 1.0},
            {"ts": date(1996, 8, 30), "severity": 1.0},
        ]

        total_loss = compute_time_decayed_loss(events, reference_date=ref_date, half_life_years=10.0)
        # Expected sum: 1.0 + 0.5 + 0.25 + 0.125 = 1.875
        assert pytest.approx(total_loss, 0.01) == 1.875

    def test_custom_configurable_half_life(self):
        """Half-life parameter is fully configurable (e.g. 5-year half life)."""
        ref_date = date(2026, 8, 30)
        event_5y_ago = {"ts": date(2021, 8, 30), "severity": 2.0}

        loss = compute_time_decayed_loss([event_5y_ago], reference_date=ref_date, half_life_years=5.0)
        # 1 half-life ago with severity 2.0 -> 0.5 * 2.0 = 1.0
        assert pytest.approx(loss, 0.01) == 1.0

    def test_empty_or_missing_events_returns_zero(self):
        """Missing or empty events list returns 0.0 deterministically."""
        assert compute_time_decayed_loss([]) == 0.0
        assert compute_time_decayed_loss([{"invalid_key": 123}]) == 0.0

    def test_future_dates_clamped_safely(self):
        """Future disaster dates (data entry error) clamped to delta_days = 0."""
        ref_date = date(2026, 8, 30)
        event_future = {"ts": date(2030, 1, 1), "severity": 1.0}

        loss = compute_time_decayed_loss([event_future], reference_date=ref_date)
        assert pytest.approx(loss, 0.01) == 1.0
