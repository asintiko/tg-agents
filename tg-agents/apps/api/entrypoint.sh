#!/bin/sh
set -e

cd /app
alembic -c apps/api/alembic.ini upgrade head

exec uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
