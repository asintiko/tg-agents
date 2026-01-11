# tg-agents monorepo

Стек: FastAPI API, фоновые задачи на Python и админ-панель Next.js с Postgres/Redis через Docker Compose.

## Структура
- `apps/api` — сервис FastAPI с эндпоинтами `/health` и `/ready`, проверками БД/Redis и бизнес-логикой.
- `apps/worker` — фоновый воркер (планировщик, парсер RSS и публикация в Telegram).
- `apps/web` — админ-панель Next.js, обращается к API.
- `docker-compose.yml` — postgres, redis, api, worker, web.
- `.env.example` — пример переменных окружения для Docker и локального запуска.

## Основные переменные (API)
- `DATABASE_URL` (async драйвер, например `postgresql+asyncpg://...`)
- `REDIS_URL`
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN` (опционально)
- `TELETHON_API_ID` / `TELETHON_API_HASH` (опционально)
- `ENCRYPTION_KEY` (ключ Fernet; генерируется один раз и хранится в секрете)
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` (создаются при старте API для входа администратора)
- `APP_DATA_DIR` (по умолчанию `./data`; кэш картинок и общий том)

## Требования
- Python 3.11+
- Node.js 18+
- `uv` (`pip install uv`)
- Docker + Docker Compose v2

## Локальный запуск (без Docker)
1. `cd tg-agents`
2. Скопируйте переменные: `cp .env.example .env` и при необходимости отредактируйте.
3. Установите зависимости с dev-инструментами: `uv sync --extra dev`.
4. API: `uv run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000`.
5. Worker: `uv run python -m apps.worker.main` (в логе будет `worker alive` и сердцебиения).
6. Frontend: `cd apps/web && npm install && npm run dev -- --hostname 0.0.0.0 --port 3000`.
7. Если запускаете API без Docker, один раз примените миграции: `uv run alembic -c apps/api/alembic.ini upgrade head`.

## Проверки качества
- Тесты: `uv run pytest`
- Линт: `uv run ruff check .`
- Типы: `uv run mypy`

## Docker Compose
1. `cd tg-agents`
2. `cp .env.example .env`
3. `docker compose up --build`
   - API: http://localhost:8000/health и http://localhost:8000/ready
   - Web: http://localhost:3000 (админ-панель tg-agents, отображает статус API)
   - Worker: пишет `worker alive` при старте

Том `postgres_data` хранит данные Postgres, `shared_data` монтируется в `/data` для api/worker. Контейнер API запускает `alembic upgrade head` перед uvicorn.
