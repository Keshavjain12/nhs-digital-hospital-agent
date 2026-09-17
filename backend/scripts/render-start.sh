#!/bin/sh
# Start command for the API on Render's free tier - see render.yaml.
#
# Free web services cannot run pre-deploy commands or one-off jobs, so the steps the
# production compose stack runs as separate services happen here, in order, before the API
# accepts traffic. docker-compose.prod.yml keeps migrations in their own service because two
# replicas racing `alembic upgrade head` can corrupt a schema; a free instance is a single
# replica, so there is nothing to race.
set -eu

alembic upgrade head

# Idempotent, and quick once the data exists. Running it on every start also keeps the demo
# current: slots are generated forward from the day of seeding, and a free service restarts
# often enough (it sleeps after 15 minutes idle) that the appointments screen never ages into
# emptiness. Skipped when no demo password is configured.
if [ -n "${DEMO_PASSWORD:-}" ]; then
  python scripts/seed_demo.py
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
