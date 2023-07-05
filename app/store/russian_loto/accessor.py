from datetime import datetime
from typing import TYPE_CHECKING
from random import shuffle, choice

from sqlalchemy import select, update, delete, and_, ChunkedIteratorResult
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.functions import func

from app.base.base_accessor import BaseAccessor
from app.russian_loto.models import *

if TYPE_CHECKING:
    from app.web.app import Application


class RussianLotoAccessor(BaseAccessor):
    INDEX_OFFSET = 1
    BARRELS_AMOUNT = 90

    async def create_new_session(self, chat_id: int, game_type: str) -> Optional[int]:
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
            except IntegrityError as e:
                session_id = None
                self.logger.exception("Session has already been started", exc_info=e)
                await add_session.rollback()
        return session_id

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
                await add_session.execute(query_add_player)
                await add_session.commit()
                return
            except IntegrityError as e:
                self.logger.exception("Creating new player", exc_info=e)
                await add_session.rollback()

        await self.create_player_profile(session_id, player_id)
        async with self.app.database.session() as new_add_session:
            await new_add_session.execute(query_add_player)
            await new_add_session.commit()

    async def add_player_card(self, session_id: int, player_id: int, card_number: int) -> list[CardCell]:
        card_cells = []
        player_card = [
            self.app.cards.cards[card_number - self.INDEX_OFFSET].r_1,
            self.app.cards.cards[card_number - self.INDEX_OFFSET].r_2,
            self.app.cards.cards[card_number - self.INDEX_OFFSET].r_3,
        ]
        for i, card_row in enumerate(player_card):
            r_i_card_cells = [
                CardCellModel(
                    session_id=session_id, player_id=player_id,
                    row_index=i + self.INDEX_OFFSET, cell_index=j + self.INDEX_OFFSET,
                    barrel_number=value, is_covered=False
                ) for j, value in enumerate(card_row)
            ]
            card_cells.extend(r_i_card_cells)

        async with self.app.database.session() as add_session:
            try:
                add_session.add_all(card_cells)
                await add_session.commit()
                added = True
            except IntegrityError as e:
                self.logger.exception("Player has already received card", exc_info=e)
                added = False

        if added:
            new_player_card = [
                CardCell(
                    session_id=session_id, player_id=player_id,
                    row_index=card_cell.row_index, cell_index=card_cell.cell_index,
                    barrel_number=card_cell.barrel_number, is_covered=card_cell.is_covered
                ) for card_cell in card_cells
            ]
        else:
            new_player_card = []

        return new_player_card

    async def add_barrels_to_session(self, session_id) -> bool:
        barrels = [BarrelModel(bag_id=session_id, barrel_number=n) for n in range(1, self.BARRELS_AMOUNT + 1)]

        async with self.app.database.session() as add_session:
            try:
                add_session.add_all(barrels)
                await add_session.commit()
            except IntegrityError as e:
                self.logger.exception("Bag has already been filled with barrels", exc_info=e)
                return False

        return True

    async def set_session_status(self, chat_id: int, new_status):
        query_update_session = update(GameSessionModel).where(GameSessionModel.chat_id == chat_id).values(
            status=new_status
        )

        async with self.app.database.session() as update_session:
            await update_session.execute(query_update_session)
            await update_session.commit()

    async def set_players_status(self, players_ids: list[int], played=False, won=False, lead=False):
        updates = {}
        if played:
            updates["times_played"] = PlayerModel.times_played + 1
        if won:
            updates["times_won"] = PlayerModel.times_won + 1
        if lead:
            updates["times_led"] = PlayerModel.times_led + 1

        query_update_players = update(PlayerModel).where(PlayerModel.id.in_(players_ids)).values(updates)
        async with self.app.database.session() as update_session:
            await update_session.execute(query_update_players)
            await update_session.commit()

    async def cover_card_cells(self, session_id: int, picked_barrel_numbers: list[int]):
        query_update_cells = update(CardCellModel).where(
            and_(CardCellModel.session_id == session_id, CardCellModel.barrel_number.in_(picked_barrel_numbers))
        ).values(is_covered=True)

        async with self.app.database.session() as update_session:
            await update_session.execute(query_update_cells)
            await update_session.commit()

    async def get_random_free_card(self, chat_id: int) -> Optional[int]:
        card_numbers = [x for x in range(1, self.app.cards.cards_amount + 1)]
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

    async def get_session_leader(self, session_id) -> Optional[SessionPlayer]:
        query_get_session_player = select(SessionPlayerModel).where(
            and_(SessionPlayerModel.session_id == session_id, SessionPlayerModel.role.in_(("lead", "leadplayer")))
        )

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_session_player)
            result = res.scalar()
            await get_session.commit()

        if result:
            return SessionPlayer(
                session_id=result.session_id, player_id=result.player_id,
                card_number=result.card_number, role=result.role
            )
        return result

    async def get_session_players(self, session_id) -> list[SessionPlayer]:
        query_get_session_player = select(SessionPlayerModel).where(
            and_(SessionPlayerModel.session_id == session_id, SessionPlayerModel.role.in_(("leadplayer", "player")))
        )

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_session_player)
            result = res.scalars().all()
            await get_session.commit()

        if result:
            return [
                SessionPlayer(
                    session_id=player.session_id, player_id=player.player_id,
                    card_number=player.card_number, role=player.role
                ) for player in result
            ]
        return []

    async def get_players_by_ids(self, players_ids: list[int]) -> list[Player]:
        query_get_players = select(PlayerModel).where(PlayerModel.id.in_(players_ids))

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_players)
            result = res.scalars().all()
            await get_session.commit()

        if result:
            return [
                Player(
                    id=player.id, name=player.name,
                    times_won=player.times_won, times_led=player.times_led, times_played=player.times_played
                ) for player in result
            ]
        return []

    async def get_session_and_player(self, session_id, player_id) -> (Player, SessionPlayer):
        query_get_session_and_player = select(PlayerModel).where(
            PlayerModel.id == player_id
        ).options(joinedload(PlayerModel.session_player.and_(SessionPlayerModel.session_id == session_id)))

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_session_and_player)
            result = res.scalar()
            await get_session.commit()

        return Player(
            id=result.id, name=result.name,
            times_won=result.times_won, times_led=result.times_led, times_played=result.times_played
        ), SessionPlayer(
            session_id=result.session_player[0].session_id, player_id=result.session_player[0].player_id,
            card_number=result.session_player[0].card_number, role=result.session_player[0].role
        )

    async def get_session_and_lead(self, session_id) -> tuple[GameSession | None, SessionPlayer | None]:
        query_get_session_and_player = select(GameSessionModel).where(
            GameSessionModel.chat_id == session_id
        ).options(joinedload(GameSessionModel.session_player.and_(SessionPlayerModel.role.in_(["lead", "leadplayer"]))))

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_session_and_player)
            result = res.scalar()
            await get_session.commit()

        if result:
            return GameSession(
                chat_id=result.chat_id, start_date=result.start_date,
                last_event_date=result.last_event_date, type=result.type, status=result.status
            ), SessionPlayer(
                session_id=result.session_player[0].session_id, player_id=result.session_player[0].player_id,
                card_number=result.session_player[0].card_number, role=result.session_player[0].role
            )
        return None, None

    async def get_barrels_by_bag_id(self, bag_id) -> list[Barrel]:
        query_get_barrels = select(BarrelModel).where(BarrelModel.bag_id == bag_id)

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_barrels)
            result = res.scalars().all()
            await get_session.commit()

        if result:
            return [Barrel(id=player.id, bag_id=player.bag_id, barrel_number=player.barrel_number) for player in result]
        return []

    async def get_card_cells_from_session(self, session_id) -> list[CardCell]:
        query_get_card_cells = select(CardCellModel).where(CardCellModel.session_id == session_id)

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_card_cells)
            result = res.scalars().all()
            await get_session.commit()

        return [
            CardCell(
                session_id=session_id, player_id=card_cell.player_id,
                row_index=card_cell.row_index, cell_index=card_cell.cell_index,
                barrel_number=card_cell.barrel_number, is_covered=card_cell.is_covered
            ) for card_cell in result
        ]

    async def pull_barrels_from_bag(self, bag_id: int, picked_numbers: list[int]):
        query_delete_barrels = delete(BarrelModel).where(
            and_(BarrelModel.bag_id == bag_id, BarrelModel.barrel_number.in_(picked_numbers))
        )

        async with self.app.database.session() as delete_session:
            await delete_session.execute(query_delete_barrels)
            await delete_session.commit()

    async def delete_session(self, session_id):
        query_delete_session = delete(GameSessionModel).where(GameSessionModel.chat_id == session_id)

        async with self.app.database.session() as delete_session:
            await delete_session.execute(query_delete_session)
            await delete_session.commit()
