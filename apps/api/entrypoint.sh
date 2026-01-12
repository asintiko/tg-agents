#!/bin/sh
set -e

cd /app

# Ждем, пока Postgres поднимется
python - <<'PY'
import asyncio
import os
import sys
from urllib.parse import urlparse

import asyncpg

url = os.environ.get("DATABASE_URL")
if not url:
    print("DATABASE_URL is not set", file=sys.stderr)
    sys.exit(1)

parsed = urlparse(url.replace("+asyncpg", ""))
dsn = {
    "user": parsed.username or "",
    "password": parsed.password or "",
    "database": (parsed.path or "/").lstrip("/"),
    "host": parsed.hostname or "localhost",
    "port": parsed.port or 5432,
}


async def wait_db():
    for attempt in range(30):
        try:
            conn = await asyncpg.connect(**dsn)
            await conn.close()
            print("Database is ready")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"DB not ready (attempt {attempt + 1}/30): {exc}")
            await asyncio.sleep(2)
    print("Database not reachable after retries", file=sys.stderr)
    sys.exit(1)


asyncio.run(wait_db())
PY

alembic -c apps/api/alembic.ini upgrade head

exec uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
