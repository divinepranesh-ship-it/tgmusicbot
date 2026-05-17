"""
queue_manager.py — Per-chat track queue management
"""

import random
from collections import deque
from typing import Optional


class QueueManager:
    def __init__(self):
        self._queues: dict[int, deque] = {}

    def _ensure(self, chat_id: int):
        if chat_id not in self._queues:
            self._queues[chat_id] = deque()

    def add(self, chat_id: int, track: dict):
        self._ensure(chat_id)
        self._queues[chat_id].append(track)

    def add_front(self, chat_id: int, track: dict):
        """Add a track to the front (for loop mode)."""
        self._ensure(chat_id)
        self._queues[chat_id].appendleft(track)

    def pop(self, chat_id: int) -> Optional[dict]:
        self._ensure(chat_id)
        try:
            return self._queues[chat_id].popleft()
        except IndexError:
            return None

    def get_queue(self, chat_id: int) -> list:
        self._ensure(chat_id)
        return list(self._queues[chat_id])

    def clear(self, chat_id: int):
        self._queues[chat_id] = deque()

    def shuffle(self, chat_id: int):
        self._ensure(chat_id)
        q = list(self._queues[chat_id])
        random.shuffle(q)
        self._queues[chat_id] = deque(q)

    def size(self, chat_id: int) -> int:
        self._ensure(chat_id)
        return len(self._queues[chat_id])
