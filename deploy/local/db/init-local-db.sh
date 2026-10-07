#!/usr/bin/env bash
# Bring up local Postgres, create roles, the generic instance database and demo data.
# Idempotent. Per-instance databases after this: packages/core/scripts/ob_instance.py db-create <slug>
#   deploy/local/db/init-local-db.sh            # up + roles + ob_generic + demo
#   deploy/local/db/init-local-db.sh --no-demo  # skip demo schema
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$HERE/.env"
[[ -f "$ENV_FILE" ]] || { echo "Create $ENV_FILE from .env.example first"; exit 1; }
set -a; source "$ENV_FILE"; set +a
COMPOSE=(docker compose -f "$HERE/docker-compose.db.yml" --env-file "$ENV_FILE")

"${COMPOSE[@]}" up -d
echo -n "Waiting for Postgres"
for _ in $(seq 1 40); do
  status="$(docker inspect -f '{{.State.Health.Status}}' onboarded-pg 2>/dev/null || true)"
  [[ "$status" == "healthy" ]] && { echo " ✔"; break; }
  echo -n "."; sleep 2
done
[[ "${status:-}" == "healthy" ]] || { echo; docker logs --tail 40 onboarded-pg; exit 1; }

psql_su() { docker exec -i onboarded-pg psql -X -q -U postgres -d postgres "$@"; }
psql_su -v dba_password="$OB_DBA_PASSWORD" -v reader_password="$OB_READER_PASSWORD" -f /bootstrap/00_roles.sql
psql_su -v db_name=ob_generic -f /bootstrap/10_instance_db.sql
if [[ "${1:-}" != "--no-demo" ]]; then
  docker exec -i -e PGPASSWORD="$OB_DBA_PASSWORD" onboarded-pg \
    psql -X -q -h localhost -U ob_dba -d ob_generic -f /bootstrap/20_demo_schema.sql
fi
echo "Local Postgres ready: localhost:${OB_DB_PORT:-55432}  (roles: ob_dba, ob_reader; db: ob_generic)"
