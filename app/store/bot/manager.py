import typing
import enum
import re
from random import sample as rand_sample
from logging import getLogger

from app.store.vk_api.dataclasses import Message, Update
from app.russian_loto.models import GameSession, SessionPlayer
from app.store.bot.picturbation import Picturbator

if typing.TYPE_CHECKING:
    from app.web.app import Application

BARRELS_PER_STEP = 10


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
        greetings = int(not (re.fullmatch(f"({self.bot_mention} )?Привет! *", update.object.body) is None))
        start_loto = int(not (
                re.fullmatch(f"({self.bot_mention} )?(начать) (лото)( [1|2])? *(!)? *",
                             update.object.body.lower()) is None
        )) << 1
        join_loto = int(not (re.fullmatch(f" *\+ *", update.object.body) is None)) << 2
        fill_bag = int(not (
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
                user_id = update.object.user_id
                peer_id = update.object.peer_id
                if user_id != peer_id:
                    await self.russian_loto.lead_move(user_id, peer_id)
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
                    doc_ref = await self.app.store.vk_api.post_doc(doc_path)
                    msg = f"Вы участвуете. Номер вашей карты - {card_number}."
                    await self.app.store.vk_api.send_message(
                        Message(user_id=player_id, text=msg), peer_id, message_id, doc_ref
                    )
                    # await self.picturbator.delete_card_picture(doc_path)
            else:
                msg = f"Вы не можете участвовать, поскольку в игре может быть до {self.app.cards.cards_amount} карт."
                await self.app.store.vk_api.send_message(Message(user_id=player_id, text=msg), peer_id, message_id)

    async def fill_bag(self, user_id, peer_id, message_id):
        players = await self.app.store.loto_games.get_session_players(peer_id)
        lead = await self.app.store.loto_games.get_session_leader(peer_id)
        if not lead:
            return

        min_amount = 2

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

    async def lead_move(self, user_id, peer_id):
        session, session_lead = await self.app.store.loto_games.get_session_and_lead(peer_id)
        if not (session and session_lead):
            return
        if session.status != "handling moves" or session_lead.player_id != user_id:
            return

        game_type = session.type
        barrels = await self.app.store.loto_games.get_barrels_by_bag_id(session_lead.session_id)

        barrel_nums = [barrel.barrel_number for barrel in barrels]
        picked_barrel_nums = rand_sample(barrel_nums, BARRELS_PER_STEP)
        await self.app.store.loto_games.pull_barrels_from_bag(session_lead.session_id, picked_barrel_nums)
        await self.app.store.loto_games.cover_card_cells(session_lead.session_id, picked_barrel_nums)

        card_cells = await self.app.store.loto_games.get_card_cells_from_session(session_lead.session_id)
        players = await self.app.store.loto_games.get_session_players(session_lead.session_id)

        players_cards = [
            (player, list(filter(lambda card_cell: card_cell.player_id == player.player_id, card_cells)))
            for player in players
        ]
        players_ids_stats = {player.player_id: False for player in players}

        doc_refs = []
        for player, card in players_cards:
            doc_path = await self.picturbator.generate_card_picture(player.card_number, card)
            doc_ref = await self.app.store.vk_api.post_doc(doc_path)
            doc_refs.append(doc_ref)
            match game_type:
                case "simple":
                    covered_cells = list(filter(lambda card_cell: card_cell.is_covered is True, card))
                    if len(covered_cells) == 15:
                        players_ids_stats[player.player_id] = True
                case "short":
                    covered_cells = [
                        len(list(filter(
                            lambda card_cell: card_cell.is_covered is True and card_cell.row_index == i, card
                        ))) for i in range(1, 4)
                    ]
                    if covered_cells.count(5):
                        players_ids_stats[player.player_id] = True

        barrels_nums = ", ".join(list(map(str, picked_barrel_nums)))
        if len(barrels) == BARRELS_PER_STEP or True in players_ids_stats.values():  # last step or win
            await self.app.store.loto_games.set_session_status(session.chat_id, "summing up")
            winners_ids = [player_id for player_id, stat in players_ids_stats.items() if stat is True]
            players_ids = [player_id for player_id, stat in players_ids_stats.items() if stat is False]
            await self.app.store.loto_games.set_players_status(winners_ids, played=True, won=True)
            await self.app.store.loto_games.set_players_status(players_ids, played=True)
            await self.app.store.loto_games.set_players_status([session_lead.player_id], lead=True)

            winners = await self.app.store.loto_games.get_players_by_ids(winners_ids)

            winners_str = ", ".join([f"[id{winner.id}|{winner.name}]" for winner in winners])
            if winners:
                msg = f"Игра окончена! Номера за этот ход: {barrels_nums}. Победители: {winners_str}"
            else:
                msg = f"Игра окончена! Номера за этот ход: {barrels_nums}."
            await self.app.store.loto_games.delete_session(session_lead.session_id)
        else:
            msg = f"Номера за этот ход: {barrels_nums}. Ходов осталось: {len(barrels)//10 - 1}."

        attachment = ",".join(doc_refs)
        await self.app.store.vk_api.send_message(
            Message(user_id=session_lead.player_id, text=msg), session.chat_id, attachment=attachment
        )

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
