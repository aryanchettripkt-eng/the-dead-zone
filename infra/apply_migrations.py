#!/usr/bin/env python3
"""Cross-platform migration runner for SETU-DRR using psycopg3.

Enforces deterministic numeric migration ordering and prevents execution
of ambiguous migration sets with duplicate sequence numbers (N4).
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Optional
import psycopg

from core.config import settings


class MigrationAmbiguityError(Exception):
    """Raised when migration set contains duplicate sequence numbers or ambiguous ordering."""
    pass


def discover_and_validate_migrations(migrations_dir: Optional[Path | str] = None) -> list[Path]:
    """Discovers .sql migrations and strictly verifies unique numeric sequence ordering.
    
    Raises:
        MigrationAmbiguityError: If duplicate sequence numbers or un-prefixed migrations exist.
    """
    if migrations_dir is None:
        repo_root = Path(__file__).resolve().parents[1]
        target_dir = repo_root / "infra" / "migrations"
    else:
        target_dir = Path(migrations_dir)

    sql_files = list(target_dir.glob("*.sql"))
    if not sql_files:
        return []

    prefix_map: dict[int, list[Path]] = {}
    for p in sql_files:
        m = re.match(r"^(\d+)_", p.name)
        if not m:
            raise MigrationAmbiguityError(
                f"Migration file '{p.name}' does not start with a numeric prefix."
            )
        seq = int(m.group(1))
        prefix_map.setdefault(seq, []).append(p)

    # Detect duplicate sequence numbers
    duplicates = {seq: files for seq, files in prefix_map.items() if len(files) > 1}
    if duplicates:
        details = "; ".join(
            f"prefix '{seq:03d}': {[f.name for f in files]}"
            for seq, files in sorted(duplicates.items())
        )
        raise MigrationAmbiguityError(
            f"Duplicate migration sequence number(s) detected: {details}. "
            f"Migration ordering is ambiguous and cannot be executed safely."
        )

    # Sort strictly by integer sequence number
    sql_files.sort(key=lambda p: (int(p.name.split("_", 1)[0]), p.name))
    return sql_files


def apply_migrations(
    conninfo: Optional[str] = None,
    migrations_dir: Optional[Path | str] = None,
) -> list[str]:
    """Applies pending migrations in deterministic numeric sequence."""
    target_conninfo = conninfo or settings.get_direct_psycopg_conninfo()
    sql_files = discover_and_validate_migrations(migrations_dir)

    if not sql_files:
        print("No migration files found.")
        return []

    applied_this_run: list[str] = []

    with psycopg.connect(target_conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            # 1. Create schema_migrations tracker
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)

            cur.execute("SELECT version FROM schema_migrations;")
            applied = {row[0] for row in cur.fetchall()}

            # 2. Apply pending migrations in numeric sequence
            for sql_path in sql_files:
                version = sql_path.stem
                if version in applied:
                    print(f"  [SKIP]  {sql_path.name} (already applied)")
                    continue

                print(f"  [APPLY] {sql_path.name} ...", end=" ", flush=True)
                sql_content = sql_path.read_text(encoding="utf-8")

                with conn.transaction():
                    cur.execute(sql_content)
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s);",
                        (version,)
                    )
                applied_this_run.append(version)
                print("DONE")

    print(f"[SUCCESS] All migrations up to date ({len(applied_this_run)} applied).")
    return applied_this_run


if __name__ == "__main__":
    try:
        apply_migrations()
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
