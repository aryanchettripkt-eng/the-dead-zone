"""Regression tests for H7 eligibility agreement between the site-listing and allocation paths.

Defect being locked down: `GET /habitations/{id}/sites` reported sites as
`eligibility_status: eligible, allocatable: true` while `POST /plan/allocate` dropped those same
sites and returned `total_relocated_households: 0` with "No eligible candidate sites with positive
carrying capacity available."

Cause: the listing path omitted the four environmental exclusion flags and inherited
`evaluate_site_eligibility()`'s `False` defaults, while the allocation path read them from the
row's `metadata` JSON and passed `None` when absent. Both now resolve the row through
`api.services.site_eligibility`.
"""

from __future__ import annotations

import pytest

from api.services.site_eligibility import (
    evaluate_row_eligibility,
    extract_exclusion_flags,
    parse_bool,
)
from core.domain.capacity import CandidateSitePolicy, CapacityEngine

ENGINE = CapacityEngine()
POLICY = CandidateSitePolicy()


def _fixture_row(**overrides):
    """A candidate-site row shaped as the repositories return it, fully asserted and eligible."""
    row = {
        "id": 69,
        "name": "Kalpetta Revenue Plain East",
        "area_ha": 12.0,
        "tenure": "government_revenue",
        "slope_mean": 3.5,
        "mhi_max": 0.04,
        "metadata": {
            "is_forest": False,
            "is_protected_area": False,
            "is_crz": False,
            "is_water_body": False,
            "provenance": "synthetic_pilot_fixture",
        },
    }
    row.update(overrides)
    return row


class TestExclusionFlagResolution:
    def test_flags_resolve_from_metadata(self):
        flags = extract_exclusion_flags(_fixture_row())
        assert flags == {
            "is_forest": False,
            "is_protected_area": False,
            "is_crz": False,
            "is_water_body": False,
        }

    def test_absent_flags_stay_none_not_false(self):
        """A flag the data never asserted must not read as 'asserted safe'."""
        flags = extract_exclusion_flags({"metadata": {"provenance": "x"}})
        assert all(v is None for v in flags.values())

    def test_top_level_column_wins_over_metadata(self):
        row = _fixture_row(is_forest=True)
        assert extract_exclusion_flags(row)["is_forest"] is True

    def test_metadata_accepted_as_json_string(self):
        row = _fixture_row(metadata='{"is_crz": true}')
        assert extract_exclusion_flags(row)["is_crz"] is True

    def test_metadata_info_alias_is_read(self):
        """sites_repo aliases the column as `metadata_info`; allocation_repo does not."""
        row = {"metadata_info": {"is_water_body": True}}
        assert extract_exclusion_flags(row)["is_water_body"] is True

    @pytest.mark.parametrize(
        "raw,expected",
        [(True, True), ("true", True), ("no", False), (1, True), (0, False), (None, None), ("maybe", None)],
    )
    def test_parse_bool(self, raw, expected):
        assert parse_bool(raw) is expected


class TestEligibilityAgreement:
    def test_fully_asserted_site_is_eligible(self):
        assert evaluate_row_eligibility(ENGINE, _fixture_row(), POLICY).is_eligible

    def test_listing_and_allocation_agree_on_same_row(self):
        """The listing path passes no distance; the allocation path requires one.

        Aside from that deliberate difference, both must reach the same verdict — this is the
        exact divergence that produced an empty allocation from sites marked allocatable.
        """
        row = _fixture_row()
        listing = evaluate_row_eligibility(ENGINE, row, POLICY)
        allocation = evaluate_row_eligibility(
            ENGINE, row, POLICY, distance_km=12.89, require_distance=True
        )
        assert listing.is_eligible == allocation.is_eligible is True

    def test_row_without_flags_is_rejected_by_both_paths(self):
        """Unverified exclusions must reject consistently, never pass the listing and fail allocation."""
        row = _fixture_row(metadata={"provenance": "stale_seed"})
        listing = evaluate_row_eligibility(ENGINE, row, POLICY)
        allocation = evaluate_row_eligibility(
            ENGINE, row, POLICY, distance_km=5.0, require_distance=True
        )
        assert listing.is_eligible is False
        assert allocation.is_eligible is False
        assert any("forest" in r.lower() for r in listing.rejection_reasons)

    def test_missing_slope_is_not_treated_as_flat(self):
        """`float(row.get('slope_mean') or 0.0)` used to turn absent terrain data into 0°."""
        result = evaluate_row_eligibility(ENGINE, _fixture_row(slope_mean=None), POLICY)
        assert result.is_eligible is False
        assert any("slope" in r.lower() for r in result.rejection_reasons)

    def test_missing_area_is_rejected(self):
        result = evaluate_row_eligibility(ENGINE, _fixture_row(area_ha=None), POLICY)
        assert result.is_eligible is False
        assert any("area" in r.lower() for r in result.rejection_reasons)

    def test_unverified_tenure_still_rejected(self):
        """H7's tenure rule must survive the refactor unchanged."""
        result = evaluate_row_eligibility(ENGINE, _fixture_row(tenure="tenure_unverified"), POLICY)
        assert result.is_eligible is False

    def test_forest_overlap_rejected(self):
        row = _fixture_row()
        row["metadata"] = {**row["metadata"], "is_forest": True}
        assert evaluate_row_eligibility(ENGINE, row, POLICY).is_eligible is False

    def test_site_beyond_radius_rejected(self):
        result = evaluate_row_eligibility(
            ENGINE, _fixture_row(), POLICY, distance_km=99.0, require_distance=True
        )
        assert result.is_eligible is False
