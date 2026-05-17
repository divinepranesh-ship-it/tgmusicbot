"""
database.py — In-memory store for current track & loop state.
For persistence, swap the dicts for a Redis or MongoDB backend.
"""

from typing import Optional


class Database:
    def __init__(self):
        self._current: dict[int, dict] = {}
        self._loop: dict[int, bool] = {}

    async def get_current(self, chat_id: int) -> Optional[dict]:
        return self._current.get(chat_id)

    async def set_current(self, chat_id: int, track: dict):
        self._current[chat_id] = track

    async def del_current(self, chat_id: int):
        self._current.pop(chat_id, None)

    async def get_loop(self, chat_id: int) -> bool:
        return self._loop.get(chat_id, False)

    async def toggle_loop(self, chat_id: int) -> bool:
        state = not self._loop.get(chat_id, False)
        self._loop[chat_id] = state
        return state


db = Database()
