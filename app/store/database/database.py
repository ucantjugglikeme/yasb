from typing import Optional, TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.store.database import db

if TYPE_CHECKING:
    from app.web.app import Application


class Database:
    def __init__(self, app: "Application"):
        self.app = app
        self._engine: Optional[AsyncEngine] = None
        self._db: Optional[declarative_base] = None
        self.session: Optional[sessionmaker] = None

    async def connect(self, *_: list, **__: dict) -> None:
        self._db = db

        db_config = self.app.config.database
        self._engine = create_async_engine(
            f"mysql+aiomysql://{db_config.user}:{db_config.password}"
            f"@{db_config.host}:{db_config.port}/{db_config.database}",
            echo=True, future=True
        )

        self.session = sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            class_=AsyncSession
        )

        admin = self.app.config.admin
        await self.app.store.admins.create_admin(admin.email, admin.password)

    async def disconnect(self, *_: list, **__: dict) -> None:
        if self._engine:
            await self._engine.dispose()
