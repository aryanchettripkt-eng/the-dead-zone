#!/usr/bin/env bash
# Applies infra/migrations/*.sql in sequence order, once each.
# Replaces alembic: the schema is defined once in PRD §9.5, not evolved for years.
#
#   ./infra/migrate.sh                 # uses $DATABASE_URL
#   DATABASE_URL=postgresql://... ./infra/migrate.sh
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL (see .env.example)}"
cd "$(dirname "$0")/migrations"

# 1. Defensive validation: detect duplicate sequence numbers
duplicates=$(ls -1 *.sql 2>/dev/null | cut -d_ -f1 | sort | uniq -d || true)
if [ -n "$duplicates" ]; then
  echo "[ERROR] Duplicate migration sequence number(s) detected: $duplicates" >&2
  for d in $duplicates; do
    echo "  Conflicting files for prefix '$d':" >&2
    ls -1 "${d}_"*.sql >&2
  done
  exit 1
fi

# 2. Ensure schema_migrations table
psql "$DATABASE_URL" -q -v ON_ERROR_STOP=1 -c \
  'create table if not exists schema_migrations (
     version text primary key,
     applied_at timestamptz not null default now()
   );'

# 3. Apply migrations in numeric order
for f in $(ls -1 *.sql | sort -V); do
  version="${f%.sql}"
  applied=$(psql "$DATABASE_URL" -Atc \
    "select 1 from schema_migrations where version = '${version}'")
  if [ "$applied" = "1" ]; then
    echo "  skip  $f"
    continue
  fi
  echo "  apply $f"
  psql "$DATABASE_URL" -q -v ON_ERROR_STOP=1 --single-transaction \
    -f "$f" \
    -c "insert into schema_migrations (version) values ('${version}');"
done
echo "migrations up to date"
