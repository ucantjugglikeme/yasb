import asyncio
from asyncio import Future, Task
from aiohttp import ClientOSError
from typing import Optional

from app.store import Store
from app.store.vk_api.dataclasses import Update, UpdateObject


# TODO: fix this
class Poller:
    def __init__(self, store: Store):
        self.store = store
        self.is_running = False
        self.poll_task: Optional[Task] = None

    def _done_callback(self, future: Future):
        if future.exception():
            self.store.vk_api.app.logger.exception("polling failed", exc_info=future.exception())

    async def start(self):
        self.is_running = True
        self.poll_task = asyncio.create_task(self.poll())
        self.poll_task.add_done_callback(self._done_callback)

    async def stop(self):
        self.is_running = False
        if self.poll_task:
            await asyncio.wait([self.poll_task], timeout=30)

    async def poll(self):
        while self.is_running:
            try:
                raw_updates = await self.store.vk_api.poll()
            except ClientOSError:
                continue
            if raw_updates:
                updates = [
                    Update(
                        type="chat_invite_yabl00" if "action" in raw_update["object"]["message"] and
                        raw_update["object"]["message"]["action"]["type"] and
                        raw_update["object"]["message"]["action"]["member_id"] ==
                        -self.store.bots_manager.app.config.bot.group_id else raw_update["type"],
                        object=UpdateObject(
                            id=raw_update["object"]["message"]["id"],
                            user_id=raw_update["object"]["message"]["from_id"],
                            body=raw_update["object"]["message"]["text"],
                            peer_id=raw_update["object"]["message"]["peer_id"],
                        )
                    ) for raw_update in raw_updates if (raw_update["type"] == "message_new")
                ]
                await self.store.bots_manager.handle_updates(updates)
