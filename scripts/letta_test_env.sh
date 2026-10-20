#!/usr/bin/env bash
# Reproduce the Letta test environment used to develop and test the Letta adapter (Ubuntu 24.04, run as root).
#
# This is a TEST HARNESS, not a supported way to deploy Letta:
#  - Letta 0.16.7's wheel needs dependency versions from its release date (uv --exclude-newer),
#  - it needs PostgreSQL + pgvector,
#  - the wheel ships no alembic migrations, so tables are created from Letta's own ORM models and one sequence default
#    (messages.sequence_id) is added by hand. A real deployment should run Letta's migrations from its source repo.
# Afterwards:  RIFFNEL_LETTA_URL=http://localhost:8283 pytest tests/test_letta.py
#              riffnel-memguard demo letta-stale | letta-erasure
set -euo pipefail
WORK="${WORK:-/tmp/letta-env}"; PORT="${PORT:-8283}"
mkdir -p "$WORK"

apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql postgresql-16-pgvector
pg_ctlcluster 16 main start || true
su postgres -c "psql -qc \"CREATE USER letta WITH PASSWORD 'letta' SUPERUSER;\"" || true
su postgres -c "psql -qc \"CREATE DATABASE letta OWNER letta;\"" || true
su postgres -c "psql -d letta -qc 'CREATE EXTENSION IF NOT EXISTS vector;'"

python3 -m venv "$WORK/uv" && "$WORK/uv/bin/pip" install -q uv
"$WORK/uv/bin/uv" venv "$WORK/venv" -q
"$WORK/uv/bin/uv" pip install --python "$WORK/venv/bin/python" --exclude-newer 2026-04-01 "letta==0.16.7" asyncpg pgvector

export HOME="$WORK/home" LETTA_TELEMETRY=false OPENAI_API_KEY=dummy
export LETTA_PG_URI="postgresql://letta:letta@127.0.0.1:5432/letta"
mkdir -p "$HOME"
"$WORK/venv/bin/python" - <<'PY'
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import letta.orm
from letta.orm.base import Base
engine = create_async_engine("postgresql+asyncpg://letta:letta@127.0.0.1:5432/letta")
async def main():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    await engine.dispose()
asyncio.run(main())
PY
PGPASSWORD=letta psql -h 127.0.0.1 -U letta -d letta -qc "CREATE SEQUENCE IF NOT EXISTS message_seq_id;" \
  -c "ALTER TABLE messages ALTER COLUMN sequence_id SET DEFAULT nextval('message_seq_id');"

setsid nohup "$WORK/venv/bin/letta" server --port "$PORT" > "$WORK/letta.log" 2>&1 &
for _ in $(seq 1 60); do curl -sf "http://localhost:$PORT/v1/health/" >/dev/null && { echo "Letta is up on :$PORT"; exit 0; }; sleep 3; done
echo "Letta did not start; see $WORK/letta.log" >&2; exit 1
