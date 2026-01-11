from __future__ import annotations

from pathlib import Path

import httpx


class TelegramBotAPI:
    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self.token = token
        self.client = client

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML") -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }
        async with self._get_client() as client:
            resp = await client.post(self._url("sendMessage"), json=payload)
            resp.raise_for_status()

    async def send_photo(
        self, chat_id: str, image_path: str, caption: str | None = None, parse_mode: str = "HTML"
    ) -> None:
        path = Path(image_path)
        if not path.exists():
            msg = f"изображение не найдено по пути {image_path}"
            raise FileNotFoundError(msg)
        files = {"photo": (path.name, path.read_bytes())}
        data = {"chat_id": chat_id, "parse_mode": parse_mode}
        if caption:
            data["caption"] = caption
        async with self._get_client() as client:
            resp = await client.post(self._url("sendPhoto"), data=data, files=files)
            resp.raise_for_status()

    def _get_client(self) -> httpx.AsyncClient:
        if self.client:
            return self.client
        return httpx.AsyncClient(timeout=10.0)


async def send_to_channels(
    token: str,
    chat_ids: list[str],
    text: str,
    image_path: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    api = TelegramBotAPI(token, client=client)
    for chat_id in chat_ids:
        if image_path:
            await api.send_photo(chat_id, image_path=image_path, caption=text)
        else:
            await api.send_message(chat_id, text=text)
