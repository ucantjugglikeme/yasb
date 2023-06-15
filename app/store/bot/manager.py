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
        greetings = int(not(re.fullmatch(f" *{self.BOT_MENTION}? *Привет! *", update.object.body) is None))
        start_loto = int(not(
            re.fullmatch(f" *{self.BOT_MENTION}? *(начать) *(лото) *(!)? *", update.object.body.lower()) is None
        )) << 1
        join_loto = int(not(re.fullmatch(f" *\+ *", update.object.body) is None)) << 2
        stop_loto = int(not(
            re.fullmatch(f" *{self.BOT_MENTION}? *(стоп) *(лото) *(!)? *", update.object.body.lower()) is None
        )) << 3
        command_flags = stop_loto | join_loto | start_loto | greetings

        match command_flags:
            case Commands.greetings.value:
                await self.app.store.vk_api.send_message(
                    Message(user_id=update.object.user_id, text="Привет!"), update.object.peer_id
                )
            case Commands.start_loto.value:
                pass
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
        self.fsm_state = FSMState.started

    async def fsm_transition(self):
        match self.fsm_state:
            case FSMState.started:
                pass
            case FSMState.adding_players:
                pass
            case FSMState.dealing_cards:
                pass
            case FSMState.filling_bag:
                pass
            case FSMState.handling_moves:
                pass
            case FSMState.closed:
                pass

    async def _start_session(self):
        pass

    async def _add_players(self):
        pass

    async def _fill_bag(self):
        pass

    async def _lead_move(self):
        pass

    async def _close_session(self):
        pass


class FSMState(enum.Enum):
    started = 0
    adding_players = 1
    dealing_cards = 2
    filling_bag = 3
    handling_moves = 4
    closed = 5


class Commands(enum.Enum):
    greetings = 0b0001
    start_loto = 0b0010
    join_loto = 0b0100
    stop_loto = 0b1000

