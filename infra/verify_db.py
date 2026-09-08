#!/usr/bin/env python3
"""Database and extension verification tool for SETU-DRR (Day 0).

Verifies:
1. Direct connection to PostgreSQL on Neon / Local container.
2. PostGIS extension installation and functionality.
3. H3 and h3_postgis extension installation and H3 indexing functions.
4. Schema migration status.
"""

import sys
import os
import argparse
from typing import Any
import psycopg


from core.config import settings


def get_conninfo(explicit_url: str | None = None, direct: bool = True) -> str:
    if explicit_url:
        return explicit_url
    
    return settings.get_direct_psycopg_conninfo()


def run_checks(conninfo: str) -> bool:
    print("=" * 70)
    print("[*] SETU-DRR -- DATABASE & EXTENSION VERIFICATION (DAY 0)")
    print("=" * 70)
    
    # Mask password for display
    masked_conninfo = conninfo
    if "@" in conninfo and ":" in conninfo.split("@")[0]:
        prefix, rest = conninfo.split("@", 1)
        proto_user = prefix.split(":")[0] + ":" + prefix.split(":")[1]
        masked_conninfo = f"{proto_user}:****@{rest}"
    print(f"Connecting to: {masked_conninfo}\n")
    
    all_passed = True
    
    try:
        with psycopg.connect(conninfo, autocommit=True) as conn:
            with conn.cursor() as cur:
                # 1. PostgreSQL Version
                cur.execute("SELECT version();")
                pg_ver = cur.fetchone()[0]
                print(f"[OK] [1/5] PostgreSQL Connected: {pg_ver.split(',')[0]}")
                
                # 2. Check Installed Extensions
                cur.execute("SELECT extname, extversion FROM pg_extension ORDER BY extname;")
                extensions = dict(cur.fetchall())
                print(f"\n[INFO] [2/5] Installed Extensions ({len(extensions)} found):")
                for name, ver in extensions.items():
                    print(f"    - {name}: v{ver}")
                
                required_exts = ["postgis", "postgis_raster", "h3", "h3_postgis"]
                missing_exts = [ext for ext in required_exts if ext not in extensions]
                
                if missing_exts:
                    print(f"\n[WARN] Missing required extensions: {', '.join(missing_exts)}")
                    print("   Run `infra/migrate.sh` or apply `infra/migrations/001_extensions.sql`.")
                    all_passed = False
                else:
                    print("[OK] All required extensions (postgis, postgis_raster, h3, h3_postgis) are present.")
                
                # 3. Test PostGIS Functions
                if "postgis" in extensions:
                    try:
                        cur.execute("SELECT PostGIS_Version();")
                        postgis_ver = cur.fetchone()[0]
                        print(f"\n[OK] [3/5] PostGIS Functionality Verified (v{postgis_ver})")
                    except Exception as e:
                        print(f"\n[ERROR] [3/5] PostGIS check failed: {e}")
                        all_passed = False
                else:
                    print("\n[SKIP] [3/5] Skipping PostGIS function test (extension not installed)")
                
                # 4. Test H3 / H3_PostGIS Functions
                if "h3" in extensions or "h3_postgis" in extensions:
                    try:
                        # Wayanad coordinates: lon 76.1320, lat 11.6854
                        cur.execute("SELECT h3_lat_lng_to_cell(ST_SetSRID(ST_MakePoint(76.1320, 11.6854), 4326), 8);")
                        h3_cell = cur.fetchone()[0]
                        
                        cur.execute("SELECT h3_cell_to_parent(%s, 7);", (h3_cell,))
                        parent_cell = cur.fetchone()[0]
                        
                        cur.execute("SELECT ST_AsText(h3_cell_to_boundary_geometry(%s));", (h3_cell,))
                        boundary_wkt = cur.fetchone()[0]
                        
                        print(f"\n[OK] [4/5] H3 & H3-PostGIS Functionality Verified:")
                        print(f"    - Coordinate (Lon: 76.1320, Lat: 11.6854) -> H3 Res 8: {h3_cell}")
                        print(f"    - Parent H3 Res 7: {parent_cell}")
                        print(f"    - Hexagon Boundary (sample): {boundary_wkt[:60]}...")
                    except Exception as e:
                        print(f"\n[ERROR] [4/5] H3 function verification failed: {e}")
                        all_passed = False
                else:
                    print("\n[SKIP] [4/5] Skipping H3 test (extensions not installed)")
                
                # 5. Schema & Tables Inspection
                cur.execute("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public' 
                    ORDER BY tablename;
                """)
                tables = [r[0] for r in cur.fetchall()]
                print(f"\n[INFO] [5/5] Existing Public Tables ({len(tables)} found):")
                if tables:
                    for t in tables:
                        print(f"    - {t}")
                else:
                    print("    (No tables created yet. Ready for Day 1 migrations.)")
                    
    except Exception as e:
        print(f"\n[ERROR] FATAL: Could not connect to PostgreSQL: {e}")
        return False
        
    print("\n" + "=" * 70)
    if all_passed:
        print("[SUCCESS] DAY 0 DATABASE VERIFICATION COMPLETE: SYSTEM READY FOR DAY 1 BUILD")
    else:
        print("[WARN] VERIFICATION COMPLETED WITH WARNINGS/FAILURES -- SEE ABOVE")
    print("=" * 70)
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Verify PostgreSQL, PostGIS, and H3 extensions.")
    parser.add_argument("--url", default=None, help="Explicit connection string.")
    parser.add_argument("--pooled", action="store_true", help="Test pooled connection rather than direct.")
    args = parser.parse_args()
    
    conninfo = get_conninfo(explicit_url=args.url, direct=not args.pooled)
    success = run_checks(conninfo)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
