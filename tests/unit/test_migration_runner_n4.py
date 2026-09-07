"""Unit and Regression Tests for Batch F / N4 Migration Runner Integrity & Ordering.

Verifies:
1. All repository migration sequence numbers are strictly unique and sequential (001 through 011).
2. The migration runner rejects duplicate sequence numbers (the original duplicate-007 flaw).
3. The migration runner rejects un-prefixed migration filenames.
4. Migration execution applies pending migrations in numeric order and skips applied ones.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from infra.apply_migrations import (
    MigrationAmbiguityError,
    discover_and_validate_migrations,
    apply_migrations,
)


class TestRepositoryMigrationIntegrity:
    """Verifies that the SETU-DRR repository migrations are structurally sound, unique, and sequential."""

    def test_repo_migrations_are_unique_and_sequential(self):
        """All committed migrations in infra/migrations must form a sequential 1..N chain with no duplicate numbers."""
        repo_root = Path(__file__).resolve().parents[2]
        migrations_dir = repo_root / "infra" / "migrations"

        sql_files = discover_and_validate_migrations(migrations_dir)

        assert len(sql_files) == 15, f"Expected exactly 15 canonical migrations, found {len(sql_files)}"

        expected_sequence = [
            (1, "001_extensions"),
            (2, "002_core_schema"),
            (3, "003_indexes"),
            (4, "004_habitation_risk"),
            (5, "005_candidate_site_metadata"),
            (6, "006_dynamic_alerts_optimization"),
            (7, "007_habitation_risk_deformation_monsoon"),
            (8, "008_habitation_risk_triage_inputs"),
            (9, "009_auth_identity_sessions"),
            (10, "010_user_jurisdiction"),
            (11, "011_flood_hazard_detail"),
            (12, "012_consolidate_rescue_officer_role"),
            (13, "013_barpeta_relocation_integration"),
            (14, "014_derived_settlement_habitations"),
            (15, "015_derived_candidate_sites"),
        ]

        for (exp_seq, exp_stem), p in zip(expected_sequence, sql_files):
            seq = int(p.name.split("_", 1)[0])
            assert seq == exp_seq, f"Expected sequence {exp_seq}, got {seq} for {p.name}"
            assert p.stem == exp_stem, f"Expected version {exp_stem}, got {p.stem}"
            assert p.exists(), f"File {p} must exist"

        # Explicit assertion: no duplicate sequence numbers exist in the repository
        sequences = [int(p.name.split("_", 1)[0]) for p in sql_files]
        assert len(sequences) == len(set(sequences)), "All migration sequence numbers must be strictly unique"


class TestMigrationRunnerHardening:
    """Tests defensive validation and error handling in the migration runner."""

    def test_runner_rejects_duplicate_007_migration_ambiguity(self, tmp_path: Path):
        """Regression test for N4: Runner must fail loudly with MigrationAmbiguityError on duplicate sequence numbers."""
        # Reproduce the exact pre-fix state with duplicate 007 prefixes
        (tmp_path / "001_extensions.sql").write_text("-- 001", encoding="utf-8")
        (tmp_path / "007_flood_hazard_detail.sql").write_text("-- 007 flood", encoding="utf-8")
        (tmp_path / "007_habitation_risk_deformation_monsoon.sql").write_text("-- 007 monsoon", encoding="utf-8")

        with pytest.raises(MigrationAmbiguityError) as exc_info:
            discover_and_validate_migrations(tmp_path)

        err_msg = str(exc_info.value)
        assert "Duplicate migration sequence number" in err_msg
        assert "007" in err_msg
        assert "007_flood_hazard_detail.sql" in err_msg
        assert "007_habitation_risk_deformation_monsoon.sql" in err_msg

    def test_runner_rejects_unprefixed_filename(self, tmp_path: Path):
        """Runner must reject migration filenames that do not start with numeric prefixes."""
        (tmp_path / "001_extensions.sql").write_text("-- 001", encoding="utf-8")
        (tmp_path / "schema_patch.sql").write_text("-- un-prefixed", encoding="utf-8")

        with pytest.raises(MigrationAmbiguityError) as exc_info:
            discover_and_validate_migrations(tmp_path)

        assert "does not start with a numeric prefix" in str(exc_info.value)
        assert "schema_patch.sql" in str(exc_info.value)

    def test_empty_directory_returns_empty_list(self, tmp_path: Path):
        """Discovering migrations in an empty directory returns an empty list without error."""
        result = discover_and_validate_migrations(tmp_path)
        assert result == []

    def test_runner_applies_pending_and_skips_applied(self, tmp_path: Path):
        """Runner applies only migrations not present in applied set, recording each in schema_migrations."""
        (tmp_path / "001_extensions.sql").write_text("CREATE EXTENSION test;", encoding="utf-8")
        (tmp_path / "002_core_schema.sql").write_text("CREATE TABLE test_tbl ();", encoding="utf-8")

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # 001 already applied, 002 pending
        mock_cur.fetchall.return_value = [("001_extensions",)]

        executed_statements = []

        def mock_execute(stmt, params=None):
            executed_statements.append((stmt, params))

        mock_cur.execute.side_effect = mock_execute

        with patch("psycopg.connect") as mock_connect:
            mock_connect.return_value.__enter__.return_value = mock_conn
            applied = apply_migrations(conninfo="postgresql://fake", migrations_dir=tmp_path)

        assert applied == ["002_core_schema"]
        # Verify 002 SQL was executed
        assert any("CREATE TABLE test_tbl ();" in s[0] for s in executed_statements)
        # Verify 002 was recorded into schema_migrations
        assert any(
            "INSERT INTO schema_migrations" in s[0] and s[1] == ("002_core_schema",)
            for s in executed_statements
        )
        # Verify 001 SQL was NOT re-executed
        assert not any("CREATE EXTENSION test;" in s[0] for s in executed_statements)
