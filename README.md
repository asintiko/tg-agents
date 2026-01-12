# tg-agents (Telethon user-only)

Единый стек: FastAPI API + worker (APScheduler, RSS, Telethon) + Next.js админка. Работает только через пользовательский аккаунт Telegram (Telethon, вход по QR/2FA). Таймзона - Europe/Moscow.
Важно: все исходные файлы должны быть в UTF-8; не коммитьте node_modules.

## Структура
- `apps/api` - FastAPI, Alembic, эндпоинты `/health`, `/ready`.
- `apps/worker` - планировщик (MSK), RSS, генерация/публикация постов.
- `apps/web` - Next.js админка (RU).
- `docker-compose.yml` - postgres, redis, api, worker, web.
- `docs/` - вспомогательные файлы (DIAGNOSTICS и др.).
- `legacy/` - старые файлы, не используются compose.

## Подготовка окружения
1. Скопируйте `.env.example` > `.env`.
2. Заполните: `TELETHON_API_ID`, `TELETHON_API_HASH`, `ADMIN_PASSWORD`, при необходимости `GEMINI_API_KEY`.
3. Порты снаружи: API 8001, Web 3001 (`NEXT_PUBLIC_API_BASE_URL` по умолчанию `http://localhost:8001`).
4. Не коммитьте `node_modules`; сборка Docker использует `npm ci`.
5. Проекты создаются с готовой конфигурацией агента и базовыми футбольными RSS-источниками.
6. Режим изображений `og_image` подтягивает OG/Twitter image по ссылке новости, `link_preview` использует превью Telegram без скачивания картинки.
5. Все исходные файлы должны быть в UTF-8; не сохраняйте TSX/MD в UTF-16.

## Запуск (Docker Desktop, Windows)
```powershell
docker compose up --build --detach
```
- API: http://localhost:8001/health
- Web: http://localhost:3001
- Volume `postgres_data` - база; `shared_data` > `/data` (Telethon-сессии, вложения).
- Если 8001/3001 заняты на хосте Docker Desktop - меняйте только левую часть маппинга в `docker-compose.yml`, внутренние порты оставьте 8000/3000.
- Healthchecks: `/health`, `/ready` (API) и healthcheck в compose следят за API/DB/Redis.

### Сброс БД (dev)
```powershell
docker compose down -v
docker compose up --build --detach
```

### Планировщик (MSK)
- Планирование постов: 00:05 по Москве.
- Отправка запланированных: каждые 60 секунд.
- Время хранится в UTC, в UI показывается в Europe/Moscow.

## Подключение Telegram (кратко)
1. Войти в админку, создать проект.
2. На странице <Старт> нажать <Получить QR>, сканировать в телефоне: **Телефон > Telegram > Настройки > Устройства > Подключить устройство (QR)**. При необходимости ввести 2FA-пароль.
3. На странице <Каналы> нажать <Найти мои каналы>, выбрать и сохранить.
4. На странице <Старт> нажать <Опубликовать тестовый пост>.

## REST (для отладки)
- Telegram: `POST /api/telegram/qr/start`, `/api/telegram/qr/wait`, `/api/telegram/qr/password`, `GET /api/telegram/status`, `DELETE /api/telegram/session` (сброс сессии Telethon в `/data/telethon`).
- RSS/контент: `POST /api/rss/pull`, `GET /api/news/latest`, `POST /api/preview/next`, `POST /api/publish/next`.

## Частые проблемы
- QR истёк: нажмите <Получить QR> снова и пересканируйте.
- Неверный 2FA-пароль: перепроверьте пароль Telegram, введите заново.
- Нет TELETHON_API_ID/HASH: заполните в `.env`, перезапустите `docker compose up --build --detach`.
- Сессия испорчена: на <Старт> нажмите <Сбросить сессию> и подключитесь заново.

## Проверки
- `curl.exe http://localhost:8001/health`
- `docker compose logs --tail=50 api`
- `docker compose exec api uv run --extra dev pytest -q`
- UI: http://localhost:3001 (пароль ADMIN_PASSWORD)
