# Barpeta Relocation Provenance & Lifecycle

## 1. Import Run Lifecycle
Import runs are tracked in `data_import_run` through deterministic lifecycle states:
- `STAGED`: Import created, files read and verified.
- `VALIDATED`: All database records inserted, constraints checked, manifest row counts verified.
- `PROMOTED`: Dataset active and servable by API.
- `SUPERSEDED`: Obsolete run superseded by newer dataset version (remains preserved for audit).
- `FAILED`: Aborted or failed import rolled back.

## 2. Immutability & Referential Integrity
- Promoted import runs cannot be deleted (`ON DELETE RESTRICT`).
- Foreign keys from `external_relocation_recommendation`, `candidate_site`, and `habitation` use `ON DELETE RESTRICT` to ensure complete historical auditability.
- Re-importing identical artifacts (`manifest_hash`) is a safe no-op.
