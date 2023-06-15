from hashlib import sha256
import typing

from sqlalchemy import select, insert, literal_column, ChunkedIteratorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.exc import IntegrityError
from typing import Optional

from app.admin.models import Admin, AdminModel
from app.base.base_accessor import BaseAccessor

if typing.TYPE_CHECKING:
    from app.web.app import Application


class AdminAccessor(BaseAccessor):
    async def get_by_email(self, email: str) -> Optional[Admin]:
        query_get_admin = select(AdminModel).where(AdminModel.email == email)

        async with self.app.database.session() as get_session:
            res: ChunkedIteratorResult = await get_session.execute(query_get_admin)
            result = res.scalar()
            await get_session.commit()

        if result is None:
            return result
        else:
            return Admin(id=result.id, email=result.email, password=result.password)

    async def create_admin(self, email: str, password: str) -> Admin:
        hashed_psw = sha256(password.encode()).hexdigest()
        query_add_admin = insert(AdminModel).values(
            email=email, password=hashed_psw
        )

        async with self.app.database.session() as add_session:
            try:
                await add_session.execute(query_add_admin)
                await add_session.commit()
            except IntegrityError as e:
                self.logger.exception(
                    "Email must be unique\nNot big deal if message shows up during start", exc_info=e
                )
                await add_session.rollback()

        return Admin(id=1, email=email, password=hashed_psw)
    