"""Unit tests for SETU-DRR Jurisdiction Authorization (Part 3).

Tests:
- Pure has_jurisdiction predicate behavior on canonical admin_boundary.id primary keys.
- Explicit security test against identifier confusion (LGD code 555 vs admin_id 158).
- Unassigned user and null target rejections.
- Non-mutating effective_admin_id resolution.
"""

import pytest
from core.domain.authorization import has_jurisdiction
from core.errors import ForbiddenError


def test_has_jurisdiction_matching_canonical_admin_id():
    """Matching canonical admin_boundary.id values must evaluate to True."""
    assert has_jurisdiction(user_admin_id=158, target_canonical_admin_id=158) is True
    assert has_jurisdiction(user_admin_id=159, target_canonical_admin_id=159) is True


def test_has_jurisdiction_different_canonical_admin_id():
    """Different canonical admin_boundary.id values must evaluate to False."""
    assert has_jurisdiction(user_admin_id=158, target_canonical_admin_id=159) is False
    assert has_jurisdiction(user_admin_id=159, target_canonical_admin_id=158) is False


def test_has_jurisdiction_rejects_identifier_confusion():
    """Security Invariant: LGD code must NEVER match canonical admin_id directly.
    
    Wayanad has admin_boundary.id = 158, lgd_code = 555.
    Passing target_canonical_admin_id = 555 for a user assigned to 158 must return False.
    """
    wayanad_admin_id = 158
    wayanad_lgd_code = 555

    kodagu_admin_id = 159
    kodagu_lgd_code = 540

    # Direct confusion between LGD code and admin_id
    assert has_jurisdiction(user_admin_id=wayanad_admin_id, target_canonical_admin_id=wayanad_lgd_code) is False
    assert has_jurisdiction(user_admin_id=kodagu_admin_id, target_canonical_admin_id=kodagu_lgd_code) is False


def test_has_jurisdiction_unassigned_user_rejected():
    """User with no assigned jurisdiction (None) cannot operate on localized targets."""
    assert has_jurisdiction(user_admin_id=None, target_canonical_admin_id=158) is False
    assert has_jurisdiction(user_admin_id=None, target_canonical_admin_id=159) is False


def test_has_jurisdiction_null_target_rejected():
    """Null target_canonical_admin_id must evaluate to False in predicate."""
    assert has_jurisdiction(user_admin_id=158, target_canonical_admin_id=None) is False
    assert has_jurisdiction(user_admin_id=None, target_canonical_admin_id=None) is False


def test_resolve_effective_admin_id_helper():
    """Tests resolve_effective_admin_id resolution without mutating requests."""
    from api.dependencies import resolve_effective_admin_id
    from unittest.mock import MagicMock

    user_with_wayanad = MagicMock()
    user_with_wayanad.admin_id = 158
    user_with_wayanad.role = "GOVERNMENT_OFFICIAL"

    # An unassigned, non-privileged user (should never reach here past require_permission,
    # but the guard must still hold).
    user_without_jurisdiction = MagicMock()
    user_without_jurisdiction.admin_id = None
    user_without_jurisdiction.role = "CIVILIAN"

    # A national operations account: privileged role, no assigned district.
    national_official = MagicMock()
    national_official.admin_id = None
    national_official.role = "GOVERNMENT_OFFICIAL"

    # 1. Omitted request (None) defaults to user's assigned jurisdiction
    effective = resolve_effective_admin_id(user_with_wayanad, requested_admin_id=None)
    assert effective == 158

    # 2. Matching requested admin_id returns canonical ID
    effective_explicit = resolve_effective_admin_id(user_with_wayanad, requested_admin_id=158)
    assert effective_explicit == 158

    # 3. Foreign requested admin_id raises ForbiddenError
    with pytest.raises(ForbiddenError) as exc_foreign:
        resolve_effective_admin_id(user_with_wayanad, requested_admin_id=159)
    assert "Operation outside assigned administrative jurisdiction" in str(exc_foreign.value)

    # 4. Identifier confusion (submitting LGD 555 as admin_id) raises ForbiddenError
    with pytest.raises(ForbiddenError) as exc_lgd:
        resolve_effective_admin_id(user_with_wayanad, requested_admin_id=555)
    assert "Operation outside assigned administrative jurisdiction" in str(exc_lgd.value)

    # 5. Unassigned non-privileged user raises ForbiddenError
    with pytest.raises(ForbiddenError) as exc_no_jur:
        resolve_effective_admin_id(user_without_jurisdiction, requested_admin_id=158)
    assert "User has no administrative jurisdiction assigned" in str(exc_no_jur.value)

    # 6. National operations account: authorized for any explicitly named district
    assert resolve_effective_admin_id(national_official, requested_admin_id=159) == 159
    assert resolve_effective_admin_id(national_official, requested_admin_id=158) == 158

    # 7. National account must still name a district; an unscoped call is rejected
    with pytest.raises(ForbiddenError) as exc_national_unscoped:
        resolve_effective_admin_id(national_official, requested_admin_id=None)
    assert "explicit district" in str(exc_national_unscoped.value)
