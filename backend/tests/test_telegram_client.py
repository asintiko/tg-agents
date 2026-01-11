from __future__ import annotations

from httpx import Response
import pytest
import respx

from app.services.telegram_client import BotTelegramClient


@pytest.mark.asyncio
@respx.mock
async def test_bot_client_sends_message() -> None:
    route = respx.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=Response(200, json={"ok": True})
    )
    client = BotTelegramClient("TOKEN")
    await client.send_message("chat", "hello")
    await client.close()
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_bot_client_raises_on_failure() -> None:
    respx.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=Response(500, json={"ok": False})
    )
    client = BotTelegramClient("TOKEN")
    with pytest.raises(RuntimeError):
        await client.send_message("chat", "hello")
    await client.close()
