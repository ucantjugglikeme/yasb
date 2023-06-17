from datetime import datetime
from typing import Optional, TYPE_CHECKING
from random import shuffle, choice

from sqlalchemy import select, update, and_, ChunkedIteratorResult
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.functions import func

from app.russian_loto.models import *
from app.base.base_accessor import BaseAccessor

if TYPE_CHECKING:
    from app.web.app import Application

CARD_AMOUNT = 24


# TODO: test this
class RussianLotoAccessor(BaseAccessor):
    async def create_new_session(self, chat_id: int, game_type: str) -> (Optional[int], str):
        start_date = datetime.now()
        type_ = "short" if game_type == "2" else "simple"
        query_add_session = insert(GameSessionModel).values(
            chat_id=chat_id, type=type_, status="started", start_date=start_date, last_event_date=start_date
        )

        async with self.app.database.session() as add_session:
            try:
                await add_session.execute(query_add_session)
                await add_session.commit()
                session_id = chat_id
                msg = "Игра начата! Чтобы играть, отправьте \"%2B\"."
            except IntegrityError as e:
                session_id = None
                msg = "Игра уже была начата. Чтобы начать новую игру, необходимо завершить текущую."
                self.logger.exception(msg, exc_info=e)
                await add_session.rollback()
        return session_id, msg

    async def create_player_profile(self, chat_id: int, player_id: int):
        player_data = await self.app.store.vk_api.get_chat_user(chat_id, player_id)
        query_add_player = insert(PlayerModel).values(
            id=player_data["id"], name=" ".join([player_data["first_name"], player_data["last_name"]]),
            times_won=0, times_led=0, times_played=0
        )

        async with self.app.database.session() as add_session:
            await add_session.execute(query_add_player)
            await add_session.commit()

    async def add_lead_to_session(self, session_id: int, player_id: int):
        role = "lead"
        card_number = None
        query_add_lead = insert(SessionPlayerModel).values(
            session_id=session_id, player_id=player_id, role=role, card_number=card_number
        )

        async with self.app.database.session() as add_session:
            try:
                await add_session.execute(query_add_lead)
                await add_session.commit()
                return
            except IntegrityError as e:
                self.logger.exception("Creating new player", exc_info=e)
                await add_session.rollback()

        await self.create_player_profile(session_id, player_id)
        async with self.app.database.session() as new_add_session:
            await new_add_session.execute(query_add_lead)
            await new_add_session.commit()

    # insert into sessionplayer values ( 224, 123, "lead", null);
    # insert into sessionplayer values ( 224, 123, "player", card_number) on duplicate key
    # update role = if(role = "lead", "leadplayer", sessionplayer.role);
    async def add_player_to_session(self, session_id: int, player_id: int, card_number: int):
        role = "player"
        query_add_player = insert(SessionPlayerModel).values(
            session_id=session_id, player_id=player_id, role=role, card_number=card_number
        ).on_duplicate_key_update(card_number=func.ifnull(
            SessionPlayerModel.card_number, card_number
        ), role=func.IF(
            SessionPlayerModel.role == "lead", "leadplayer", SessionPlayerModel.role
        ))

        async with self.app.database.session() as add_session:
            try:
                smth = await add_session.execute(query_add_player)
                print(smth)
                await add_session.commit()
                return
            except IntegrityError as e:
                self.logger.exception("Creating new player", exc_info=e)
                await add_session.rollback()

        await self.create_player_profile(session_id, player_id)
        async with self.app.database.session() as new_add_session:
            smth = await new_add_session.execute(query_add_player)
            print(smth)
            await new_add_session.commit()

    async def set_session_status(self, chat_id: int, new_status):
        query_update_session = update(GameSessionModel).where(GameSessionModel.chat_id == chat_id).values(
            status=new_status
        )

        async with self.app.database.session() as update_session:
            await update_session.execute(query_update_session)
            await update_session.commit()

    # allocated_card_numbers = select card_number from sessionplayer where card_number not null and session_id == peer_i
    async def get_random_free_card(self, chat_id: int) -> Optional[int]:
        card_numbers = [x for x in range(1, CARD_AMOUNT + 1)]
        query_get_cards = select(SessionPlayerModel.card_number).where(
            and_(SessionPlayerModel.card_number.isnot(None), SessionPlayerModel.session_id == chat_id)
        )

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_cards)
            result = res.scalars().all()
            await get_session.commit()

        allocated_card_numbers = [card_number for card_number in result]
        free_card_numbers = list(set(card_numbers) - set(allocated_card_numbers))
        shuffle(free_card_numbers)
        try:
            random_free_card = choice(free_card_numbers)
        except IndexError:
            random_free_card = None
        return random_free_card

    async def get_session_by_chat_id(self, chat_id) -> Optional[GameSession]:
        query_get_session = select(GameSessionModel).where(GameSessionModel.chat_id == chat_id)

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_session)
            result = res.scalar()
            await get_session.commit()

        if result:
            return GameSession(
                chat_id=result.chat_id, start_date=result.start_date, last_event_date=result.last_event_date,
                type=result.type, status=result.status
            )
        return result

