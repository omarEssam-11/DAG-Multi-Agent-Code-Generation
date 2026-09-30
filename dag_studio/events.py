"""Async event bus used to stream studio events to connected UIs."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator


class EventBus:
    """Fan-out pub/sub. Subscribers receive JSON-serializable dicts."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    async def subscribe(self) -> AsyncGenerator[dict[str, Any], None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=2048)
        self._subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers.discard(queue)

    async def publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest to make room for newer events.
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass

    @staticmethod
    def dump(event: dict[str, Any]) -> str:
        return json.dumps(event, ensure_ascii=False, default=str)
