# Barpeta Relocation Integration Documentation

## 1. Overview & Architectural Boundaries
The Barpeta relocation pipeline brings offline GIS outputs from an upstream partner pipeline into the SETU-DRR platform.

### Core Architectural Principle
- **Friend's Pipeline**: External offline data producer. Generates spatial candidate polygons, settlement points, and external offline relocation recommendations.
- **SETU-DRR**: Authoritative decision authority. Owns `PriorityScoringEngine`, `CandidateSitePolicy` (H7), `CapacityEngine`, and OR-Tools `AllocationEngine`.

The friend's recommendations **never** enter canonical `relocation_plan` and **never** create `allocation_run`. They are stored in `external_relocation_recommendation` linked to a `data_import_run` for inspection and benchmarking.

## 2. Ingested Artifacts
Located in `data/processed/relocation/barpeta/` and `data/raw/boundaries/`:
- `barpeta.geojson`: Bounding polygon for Barpeta Pilot AOI.
- `habitations.parquet`: 14 settlement locations with population and households.
- `candidate_site_rows.jsonl`: 629 candidate sites with developable land area and screening properties.
- `relocation_plan_rows.jsonl`: 14 offline relocation recommendations.
- `manifest.json`: Non-circular SHA-256 artifact checksums and expected counts.

## 3. Execution Commands
```bash
# Validate artifacts against manifest and polygon geometry (zero DB mutation)
uv run python pipeline/scripts/load_barpeta_relocation.py --check

# Dry-run database load in transaction and rollback
uv run python pipeline/scripts/load_barpeta_relocation.py --dry-run

# Commit load into PostgreSQL/PostGIS
uv run python pipeline/scripts/load_barpeta_relocation.py --load
```
