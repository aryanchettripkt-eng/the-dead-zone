"""Unit tests for SETU-DRR Authorization Policy (Part 2).

Tests:
- has_permission matrix evaluation for all three canonical roles and permissions.
- Invariance: CIVILIAN has zero privileged permissions.
- Invariance: GOVERNMENT_OFFICIAL and SYSTEM_ADMIN have planning/scenario/capacity permissions.
- Invariance: RESCUE_OFFICER is excluded from Role enum and legacy strings fail safely.
- Invariance: Unknown roles and unknown permissions fail safely (return False).
- String and enum type compatibility.
"""

import pytest
from core.enums import Role
from core.domain.authorization import (
    Permission,
    ROLE_PERMISSIONS,
    has_permission,
)


def test_permission_enum_values():
    """Verify exact canonical permission strings."""
    assert Permission.ALLOCATION_RUN.value == "allocation.run"
    assert Permission.SCENARIO_RUN.value == "scenario.run"
    assert Permission.CAPACITY_RECOMPUTE.value == "capacity.recompute"


def test_civilian_role_has_no_privileged_permissions():
    """Civilian role must possess zero privileged permissions."""
    for perm in Permission:
        assert has_permission(Role.CIVILIAN, perm) is False
        assert has_permission(Role.CIVILIAN.value, perm.value) is False
        assert has_permission("CIVILIAN", perm.value) is False


def test_role_set_excludes_rescue_officer():
    """Verify RESCUE_OFFICER is not a member of Role enum, and legacy string fails safely."""
    assert not hasattr(Role, "RESCUE_OFFICER")
    for perm in (Permission.ALLOCATION_RUN, Permission.SCENARIO_RUN, Permission.CAPACITY_RECOMPUTE):
        assert has_permission("RESCUE_OFFICER", perm) is False
        assert has_permission("RESCUE_OFFICER", perm.value) is False


def test_system_admin_has_planning_permissions():
    """System Admin possesses allocation, scenario, and capacity permissions."""
    assert has_permission(Role.SYSTEM_ADMIN, Permission.ALLOCATION_RUN) is True
    assert has_permission(Role.SYSTEM_ADMIN, Permission.SCENARIO_RUN) is True
    assert has_permission(Role.SYSTEM_ADMIN, Permission.CAPACITY_RECOMPUTE) is True

    # Test string representations
    assert has_permission("SYSTEM_ADMIN", "allocation.run") is True
    assert has_permission("SYSTEM_ADMIN", "scenario.run") is True
    assert has_permission("SYSTEM_ADMIN", "capacity.recompute") is True


def test_government_official_has_planning_permissions():
    """Government Official possesses allocation, scenario, and capacity permissions."""
    assert has_permission(Role.GOVERNMENT_OFFICIAL, Permission.ALLOCATION_RUN) is True
    assert has_permission(Role.GOVERNMENT_OFFICIAL, Permission.SCENARIO_RUN) is True
    assert has_permission(Role.GOVERNMENT_OFFICIAL, Permission.CAPACITY_RECOMPUTE) is True

    # Test string representations
    assert has_permission("GOVERNMENT_OFFICIAL", "allocation.run") is True
    assert has_permission("GOVERNMENT_OFFICIAL", "scenario.run") is True
    assert has_permission("GOVERNMENT_OFFICIAL", "capacity.recompute") is True


def test_unknown_role_returns_false():
    """Any non-existent role returns False rather than raising unhandled exceptions."""
    assert has_permission("UNKNOWN_ROLE", Permission.ALLOCATION_RUN) is False
    assert has_permission("SUPERUSER", Permission.ALLOCATION_RUN) is False
    assert has_permission("ADMIN", Permission.ALLOCATION_RUN) is False
    assert has_permission("", Permission.ALLOCATION_RUN) is False


def test_unknown_permission_returns_false():
    """Any non-existent permission returns False."""
    assert has_permission(Role.GOVERNMENT_OFFICIAL, "unregistered.permission") is False
    assert has_permission(Role.GOVERNMENT_OFFICIAL, "briefing.export") is False
    assert has_permission(Role.CIVILIAN, "unregistered.permission") is False


def test_role_permissions_mapping_immutability():
    """Ensure ROLE_PERMISSIONS values are frozensets to prevent runtime tampering."""
    for role, perms in ROLE_PERMISSIONS.items():
        assert isinstance(perms, frozenset)
