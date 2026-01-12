# Диагностический отчет (PROMPT 1)

## Выполненные команды
- `docker compose down -v`
- `docker compose up --build --detach`
- `docker compose logs --no-color --tail=300 api`
- `docker compose logs --no-color --tail=300 web`
- `docker compose logs --no-color --tail=300 worker`
- `curl.exe http://localhost:8001/health`
- `docker compose exec api uv run --extra dev pytest -q`

## Первый сбой
- При первом запуске `docker compose up --build` контейнер `web` не стартовал: `Bind for 0.0.0.0:3000 failed: port is already allocated` (аналогично порт 8000 был занят). Это порты, которые резервирует `com.docker.backend` на хосте Windows.

## Причина
- Конфликт хостовых портов 8000 и 3000 с сервисом Docker Desktop (`com.docker.backend` / `wslrelay`), из-за чего прокидывание портов контейнеров наружу не работало.

## План исправления
1. Переключить публикацию портов на свободные (API → 8001, Web → 3001) и обновить связанные переменные окружения/документацию.
2. Пересобрать и поднять стек через `docker compose up --build --detach`.
3. Проверить `/health` и базовые логи сервисов.
4. Запустить тесты `pytest -q` через `uv run --extra dev` внутри контейнера API.

## Что сделано дальше
- Порты перенесены на 8001/3001, `.env` и `.env.example` обновлены, Dockerfile Web и переменные сборки выставлены на новый API-URL.
- После перезапуска `docker compose ps`: все сервисы в статусе Up, `/health` возвращает 200, логи API/worker/web без ошибок.
- `pytest -q` внутри контейнера API завершился успешно (25 тестов).

## Следующие шаги
- Довести админку до полноценного русского UI (тексты сейчас частично повреждены кодировкой).
- Убедиться, что остаётся только Telethon (user account, QR + 2FA), без Telegram Bot API.
- Проверить e2e: подключение по QR → просмотр каналов → отправка тестового поста.
