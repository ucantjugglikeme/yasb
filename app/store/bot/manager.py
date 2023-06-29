import typing
import enum
import re
from logging import getLogger

from app.store.vk_api.dataclasses import Message, Update
from app.russian_loto.models import GameSession, SessionPlayer
from app.store.russian_loto.accessor import CARD_AMOUNT

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

        match command_flags:
            case Commands.greetings.value:
                await self.app.store.vk_api.send_message(
                    Message(user_id=update.object.user_id, text="Привет!"), update.object.peer_id
                )
            case Commands.start_loto.value:
                lead_id = update.object.user_id
                peer_id = update.object.peer_id
                game_type = re.sub("\D", "", update.object.body)
                if lead_id != peer_id:
                    await self.russian_loto.start_session(lead_id, peer_id, game_type)
            case Commands.join_loto.value:
                player_id = update.object.user_id
                peer_id = update.object.peer_id
                message_id = update.object.message_id
                if player_id != peer_id:
                    await self.russian_loto.add_players(player_id, peer_id, message_id)
            case Commands.stop_loto.value:
                user_id = update.object.user_id
                peer_id = update.object.peer_id
                if user_id != peer_id:
                    await self.russian_loto.close_session(user_id, peer_id)
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
            await self.app.store.loto_games.set_session_status(peer_id, "adding players")

    async def add_players(self, player_id, peer_id, message_id):
        session: GameSession = await self.app.store.loto_games.get_session_by_chat_id(peer_id)
        if session and session.status == "adding players":
            card_number = await self.app.store.loto_games.get_random_free_card(session.chat_id)
            if card_number:
                await self.app.store.loto_games.add_player_to_session(session.chat_id, player_id, card_number)
                await self.app.store.vk_api.post_doc(peer_id, player_id, "doc")
                msg = f"Вы в игре. Номер вашей карты - {card_number}"
            else:
                msg = f"Вы не можете участвовать, поскольку в игре может быть до {CARD_AMOUNT} карт."

    async def fill_bag(self):
        pass

    async def lead_move(self):
        pass

    async def close_session(self, user_id, peer_id):
        leader: SessionPlayer = await self.app.store.loto_games.get_session_leader(peer_id)
        if not leader:
            return

        if leader.player_id == user_id:
            await self.app.store.loto_games.delete_session(leader.session_id)
            await self.app.store.vk_api.send_message(Message(user_id=user_id, text="Игра окончена досрочно!"), peer_id)
        else:
            player_data = await self.app.store.vk_api.get_chat_user(leader.session_id, user_id)
            if player_data["is_admin"]:
                await self.app.store.loto_games.delete_session(leader.session_id)
                await self.app.store.vk_api.send_message(Message(
                    user_id=user_id, text="Игра окончена досрочно!"
                ), peer_id)


class Commands(enum.Enum):
    greetings = 0b0001
    start_loto = 0b0010
    join_loto = 0b0100
    stop_loto = 0b1000
