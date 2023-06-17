import typing
import enum
import re
from logging import getLogger

from app.store.vk_api.dataclasses import Message, Update

if typing.TYPE_CHECKING:
    from app.web.app import Application


class BotManager:
    def __init__(self, app: "Application"):
        self.app = app
        self.bot = None
        self.logger = getLogger("handler")
        self.russian_loto = RussianLoto(app)
        self.BOT_MENTION = f"(\[club{self.app.config.bot.group_id}\|[@]?[а-яА-Яa-zA-Z_0-9 ]+\][,]?)"

    async def handle_updates(self, updates: list[Update]):
        for update in updates:
            match update.type:
                case "message_new":
                    await self.handle_new_message(update)
                case "chat_invite_yabl00":
                    pass

    async def handle_new_message(self, update: Update):
        greetings = int(not(re.fullmatch(f"({self.BOT_MENTION} )?Привет! *", update.object.body) is None))
        start_loto = int(not(
            re.fullmatch(f"({self.BOT_MENTION} )?(начать) (лото)( [1|2])? *(!)? *", update.object.body.lower()) is None
        )) << 1
        join_loto = int(not(re.fullmatch(f" *\+ *", update.object.body) is None)) << 2
        stop_loto = int(not(
            re.fullmatch(f"({self.BOT_MENTION} )?(стоп) (лото) *(!)? *", update.object.body.lower()) is None
        )) << 3
        command_flags = stop_loto | join_loto | start_loto | greetings
        print(command_flags)

        match command_flags:
            case Commands.greetings.value:
                await self.app.store.vk_api.send_message(
                    Message(user_id=update.object.user_id, text="Привет!"), update.object.peer_id
                )
            case Commands.start_loto.value:
                lead_id = update.object.user_id
                peer_id = update.object.peer_id
                game_type = re.sub("\D", "", update.object.body)
                await self.russian_loto.start_session(lead_id, peer_id, game_type)
            case Commands.join_loto.value:
                pass
            case Commands.stop_loto.value:
                pass
            case _:
                pass


class RussianLoto:
    def __init__(self, app: "Application"):
        self.app = app
        self.logger = getLogger("Russian Loto")

    async def start_session(self, lead_id, peer_id, game_type):
        session_id, response = await self.app.store.loto_games.create_new_session(peer_id, game_type)
        await self.app.store.vk_api.send_message(Message(user_id=lead_id, text=response), peer_id)
        if session_id:
            await self.app.store.loto_games.add_lead_to_session(session_id, lead_id)

    async def add_players(self):
        pass

    async def fill_bag(self):
        pass

    async def lead_move(self):
        pass

    async def close_session(self):
        pass


class Commands(enum.Enum):
    greetings = 0b0001
    start_loto = 0b0010
    join_loto = 0b0100
    stop_loto = 0b1000
