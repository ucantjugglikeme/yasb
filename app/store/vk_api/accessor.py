import enum
import json
import random
import typing
from typing import Optional

from aiohttp import TCPConnector
from aiohttp.client import ClientSession

from app.base.base_accessor import BaseAccessor
from app.store.vk_api.dataclasses import Message  # , Update, UpdateObject
from app.store.vk_api.poller import Poller

if typing.TYPE_CHECKING:
    from app.web.app import Application

API_PATH = "https://api.vk.com/method/"


# TODO: fix this
class VkApiAccessor(BaseAccessor):
    def __init__(self, app: "Application", *args, **kwargs):
        super().__init__(app, *args, **kwargs)
        self.session: Optional[ClientSession] = None
        self.key: Optional[str] = None
        self.server: Optional[str] = None
        self.poller: Optional[Poller] = None
        self.ts: Optional[int] = None

    async def connect(self, app: "Application"):
        self.session = ClientSession(connector=TCPConnector(verify_ssl=False))
        try:
            await self._get_long_poll_service()
        except Exception as e:
            self.logger.error("Exception", exc_info=e)
        self.poller = Poller(app.store)
        self.logger.info("start polling")
        await self.poller.start()

    async def disconnect(self, app: "Application"):
        if self.poller:
            await self.poller.stop()
        if self.session:
            await self.session.close()

    @staticmethod
    def _build_query(host: str, method: str, params: dict) -> str:
        url = host + method + "?"
        if "v" not in params:
            params["v"] = "5.131"
        url += "&".join([f"{k}={v}" for k, v in params.items()])
        return url

    async def _get_long_poll_service(self):
        async with self.session.get(
                self._build_query(
                    host=API_PATH,
                    method="groups.getLongPollServer",
                    params={
                        "group_id": self.app.config.bot.group_id,
                        "access_token": self.app.config.bot.token,
                    },
                )
        ) as resp:
            data = (await resp.json())["response"]
            self.logger.info(data)
            self.key = data["key"]
            self.server = data["server"]
            self.ts = data["ts"]
            self.logger.info(self.server)

    async def poll(self):
        async with self.session.get(
                self._build_query(
                    host=self.server,
                    method="",
                    params={
                        "act": "a_check",
                        "key": self.key,
                        "ts": self.ts,
                        "wait": 30,
                    },
                )
        ) as resp:
            json_data = await resp.json()
            self.logger.info(json_data)
            try:
                self.ts = json_data["ts"]
                updates = json_data["updates"]
            except KeyError:
                match json_data["failed"]:
                    case VkApiFail.key_timeout.value:
                        await self._get_long_poll_service()
                        updates = []
            return updates

    async def send_message(self, message: Message, peer_id: int, reply_id: Optional[int] = None) -> None:
        (destination, id_) = ("user", message.user_id) if message.user_id == peer_id else ("chat", peer_id - 2000000000)
        peer_id = peer_id if message.user_id != peer_id else -self.app.config.bot.group_id
        params = {
            f"{destination}_id": id_,
            "random_id": random.randint(1, 2 ** 32),
            "peer_id": peer_id,
            "message": message.text,
            "access_token": self.app.config.bot.token,
        }
        if reply_id:
            params["forward"] = json.dumps({
                "peer_id": peer_id,
                "conversation_message_ids": [reply_id],
                "is_reply": True
            })
        async with self.session.get(
                self._build_query(
                    API_PATH,
                    "messages.send",
                    params=params,
                )
        ) as resp:
            data = await resp.json()
            self.logger.info(data)

    async def get_chat_user(self, chat_id: int, user_id: int) -> dict[str, int | str]:
        async with self.session.get(
            self._build_query(
                API_PATH,
                "messages.getConversationMembers",
                params={
                    "access_token": self.app.config.bot.token,
                    "peer_id": chat_id
                }
            )
        ) as resp:
            data = (await resp.json())["response"]
            self.logger.info(data)
            items = [
                {"member_id": item["member_id"], "is_admin": "is_admin" in item}
                for item in data["items"]
            ]
            profiles = [
                {"id": profile["id"], "first_name": profile["first_name"], "last_name": profile["last_name"]}
                for profile in data["profiles"]
            ]
            item = list(filter(lambda item: (item["member_id"] == user_id), items))[0]
            user = list(filter(lambda profile: (profile["id"] == user_id), profiles))[0]
            user = item | user
            print(user)
            return user

    async def post_doc(self, peer_id: int, user_id: int, doc_type: str = "doc"):
        async with self.session.get(
            self._build_query(
                API_PATH,
                "docs.getMessagesUploadServer",
                params={
                    "access_token": self.app.config.bot.token,
                    "type": doc_type,
                    "peer_id": peer_id
                }
            )
        ) as resp:
            data = (await resp.json())["response"]
            self.logger.info(data)


class VkApiFail(enum.Enum):
    key_timeout = 2
