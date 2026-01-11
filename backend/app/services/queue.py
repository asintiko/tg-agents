from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..config import TelegramMode


@dataclass(slots=True)
class PostTask:
    chat_id: str
    content: str
    mode: TelegramMode
    job_id: int | None = None


class PostQueue:
    def __init__(self, max_size: int = 200) -> None:
        self._queue: asyncio.Queue[PostTask] = asyncio.Queue(maxsize=max_size)

    async def enqueue(self, task: PostTask) -> None:
        await self._queue.put(task)

    async def dequeue(self) -> PostTask:
        return await self._queue.get()

    def mark_done(self) -> None:
        self._queue.task_done()

    def size(self) -> int:
        return self._queue.qsize()

    def empty(self) -> bool:
        return self._queue.empty()
