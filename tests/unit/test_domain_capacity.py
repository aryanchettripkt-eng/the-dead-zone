"""Unit tests for carrying capacity assessment, binding constraints, and augmentation."""

import pytest
from core.domain.capacity import (
    compute_land_capacity,
    compute_water_capacity,
    compute_school_capacity,
    compute_health_capacity,
    compute_carrying_capacity,
    compute_augmented_capacity,
)
from core.enums import BindingConstraint


def test_capacity_norms():
    """FR-7.4, Capacity Norms verification."""
    # Land: 12,600 m2 / 126 m2/HH = 100 HH
    assert compute_land_capacity(area_developable_m2=12600.0, area_per_hh_m2=126.0) == 100

    # Water: 55 LPCD * 4.5 = 247.5 L/HH/day. Yield = 24,750 L/day -> 100 HH
    assert compute_water_capacity(yield_liters_per_day=24750.0, lpcd=55, hh_size=4.5) == 100

    # School: 120 spare seats / 1.2 children/HH = 100 HH
    assert compute_school_capacity(spare_seats=120, children_per_hh=1.2) == 100

    # Health: (20,000 - 19,550) = 450 pop / 4.5 = 100 HH
    assert compute_health_capacity(phc_norm_pop=20000, catchment_pop=19550, hh_size=4.5) == 100


def test_carrying_capacity_strict_minimum_invariant():
    """Invariant: Capacity is the strict minimum, NEVER averaged."""
    cc_land = 500
    cc_water = 120  # Bottleneck
    cc_school = 300
    cc_health = 400

    final_cc, binding = compute_carrying_capacity(
        cc_land=cc_land,
        cc_water=cc_water,
        cc_school=cc_school,
        cc_health=cc_health,
        livelihood_multiplier=1.0,
    )
    assert final_cc == 120
    assert binding == BindingConstraint.WATER


def test_augmented_capacity():
    """FR-7.6: Relief of the binding constraint yields next bottleneck."""
    cc_land = 500
    cc_water = 120  # Bottleneck
    cc_school = 300
    cc_health = 400

    # Augment water supply to 600
    aug_cc, next_binding = compute_augmented_capacity(
        cc_land=cc_land,
        cc_water=cc_water,
        cc_school=cc_school,
        cc_health=cc_health,
        relieved_constraint=BindingConstraint.WATER,
        relieved_value=600,
        livelihood_multiplier=1.0,
    )
    assert aug_cc == 300
    assert next_binding == BindingConstraint.SCHOOL
