import typing
from logging import getLogger

from app.store.vk_api.dataclasses import Message, Update

if typing.TYPE_CHECKING:
    from app.web.app import Application


class BotManager:
    def __init__(self, app: "Application"):
        self.app = app
        self.bot = None
        self.logger = getLogger("handler")

    async def handle_updates(self, updates: list[Update]):
        for update in updates:
            if update.type == "message_new":
                await self.handle_new_message(update)

    async def handle_new_message(self, update: Update):
        match update.object.body:
            case "Привет!":
                await self.app.store.vk_api.send_message(
                    Message(user_id=update.object.user_id, text="Привет!"), update.object.peer_id
                )
