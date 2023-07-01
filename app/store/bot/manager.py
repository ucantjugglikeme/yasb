import typing
import enum
import re
from logging import getLogger

from app.store.vk_api.dataclasses import Message, Update
from app.russian_loto.models import GameSession, SessionPlayer
from app.store.bot.picturbation import Picturbator

if typing.TYPE_CHECKING:
    from app.web.app import Application


class BotManager:
    def __init__(self, app: "Application"):
        self.app = app
        self.bot = None
        self.logger = getLogger("handler")
        self.russian_loto = RussianLoto(app)
        self.bot_mention = f"(\[club{self.app.config.bot.group_id}\|[@]?[а-яА-Яa-zA-Z_0-9 ]+\][,]?)"

    async def handle_updates(self, updates: list[Update]):
        for update in updates:
            match update.type:
                case "message_new":
                    await self.handle_new_message(update)
                case "chat_invite_yabl00":
                    pass

    async def handle_new_message(self, update: Update):
        greetings = int(not(re.fullmatch(f"({self.bot_mention} )?Привет! *", update.object.body) is None))
        start_loto = int(not(
            re.fullmatch(f"({self.bot_mention} )?(начать) (лото)( [1|2])? *(!)? *", update.object.body.lower()) is None
        )) << 1
        join_loto = int(not(re.fullmatch(f" *\+ *", update.object.body) is None)) << 2
        fill_bag = int(not(
            re.fullmatch(f"({self.bot_mention} )?(заполнить) (мешок) *(!)? *", update.object.body.lower()) is None
        )) << 3
        pull_barrel = int(not (
                re.fullmatch(f"({self.bot_mention} )?(ход) *(!)? *", update.object.body.lower()) is None
        )) << 4
        stop_loto = int(not (
                re.fullmatch(f"({self.bot_mention} )?(стоп) (лото) *(!)? *", update.object.body.lower()) is None
        )) << 5
        command_flags = stop_loto | pull_barrel | fill_bag | join_loto | start_loto | greetings

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
            case Commands.fill_bag.value:
                user_id = update.object.user_id
                peer_id = update.object.peer_id
                message_id = update.object.message_id
                if user_id != peer_id:
                    await self.russian_loto.fill_bag(user_id, peer_id, message_id)
            case Commands.pull_barrel.value:
                pass
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
        self.picturbator = Picturbator(app)
        self.logger = getLogger("Russian Loto")

    async def start_session(self, lead_id, peer_id, game_type):
        session_id = await self.app.store.loto_games.create_new_session(peer_id, game_type)
        if session_id:
            await self.app.store.loto_games.add_lead_to_session(session_id, lead_id)
            await self.app.store.loto_games.set_session_status(peer_id, "adding players")
            msg = "Игра начата! Чтобы играть, отправьте \"%2B\". После того, как игроки будут набраны, " \
                  "ведущий сможет заполнить мешок бочонками командой \"Заполнить мешок!\"."
        else:
            msg = "Игра уже была начата. Чтобы начать новую игру, необходимо завершить текущую."
        await self.app.store.vk_api.send_message(Message(user_id=lead_id, text=msg), peer_id)

    async def add_players(self, player_id, peer_id, message_id):
        session: GameSession = await self.app.store.loto_games.get_session_by_chat_id(peer_id)
        if session and session.status == "adding players":
            card_number = await self.app.store.loto_games.get_random_free_card(session.chat_id)
            if card_number:
                await self.app.store.loto_games.add_player_to_session(session.chat_id, player_id, card_number)
                player_card = await self.app.store.loto_games.add_player_card(session.chat_id, player_id, card_number)
                if player_card:
                    doc_path = await self.picturbator.generate_card_picture(card_number, player_card)
                    doc_ref = await self.app.store.vk_api.post_doc(peer_id, doc_path, doc_type="doc")
                    msg = f"Вы участвуете. Номер вашей карты - {card_number}."
                    await self.app.store.vk_api.send_message(
                        Message(user_id=player_id, text=msg), peer_id, message_id, doc_ref
                    )
                    await self.picturbator.delete_card_picture(doc_path)
            else:
                msg = f"Вы не можете участвовать, поскольку в игре может быть до {self.app.cards.cards_amount} карт."
                await self.app.store.vk_api.send_message(Message(user_id=player_id, text=msg), peer_id, message_id)

    async def fill_bag(self, user_id, peer_id, message_id):
        players = await self.app.store.loto_games.get_session_players(peer_id)
        lead = next((player for player in players if player.role in ["leadplayer", "lead"]), None)
        if not lead:
            return

        match lead.role:
            case "leadplayer":
                min_amount = 2
            case _:
                min_amount = 3

        if len(players) >= min_amount and lead.player_id == user_id:
            await self.app.store.loto_games.set_session_status(peer_id, "filling bag")
            filled = await self.app.store.loto_games.add_barrels_to_session(peer_id)
            if filled:
                await self.app.store.vk_api.send_message(Message(
                    user_id=user_id,
                    text="Мешок заполнен! С этого момента ведущий вытаскивает из мешка бочонки сообщением \"Ход!\"."
                ), peer_id)
                await self.app.store.loto_games.set_session_status(peer_id, "handling moves")
        elif lead.player_id == user_id:
            msg = f"Для игры необходимо минимум 2 игрока. Пожалуйста, соберите команду. " \
                  f"Для участия игроки отправляют \"%2B\"."
            await self.app.store.vk_api.send_message(Message(user_id=user_id, text=msg), peer_id, message_id)

    async def lead_move(self, user_id, peer_id, ):
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
    greetings = 0b000001
    start_loto = 0b000010
    join_loto = 0b000100
    fill_bag = 0b001000
    pull_barrel = 0b010000
    stop_loto = 0b100000
