from aiohttp.web import (
    Application as AiohttpApplication,
    Request as AiohttpRequest,
    View as AiohttpView,
)
from typing import Optional
from app.web.config import Config, setup_config
from app.web.logger import setup_logging
from app.store import Store, setup_store
from app.store.database.database import Database
from app.admin.models import Admin
from app.web.routes import setup_routes
from app.web.middlewares import setup_middlewares

from aiohttp_apispec import setup_aiohttp_apispec
from aiohttp_session import setup as session_setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage


class Application(AiohttpApplication):
    config: Optional[Config] = None
    store: Optional[Store] = None
    database: Optional[Database] = None


class Request(AiohttpRequest):
    admin: Optional[Admin] = None

    @property
    def app(self) -> Application:
        return super().app()


class View(AiohttpView):
    @property
    def request(self) -> Request:
        return super().request

    @property
    def database(self):
        return self.request.app.database

    @property
    def store(self) -> Store:
        return self.request.app.store

    @property
    def data(self) -> dict:
        return self.request.get("data", {})


app = Application()


def setup_app(config_path: str):
    setup_logging(app)
    setup_config(app, config_path)
    session_setup(app, EncryptedCookieStorage(app.config.session.key))
    setup_routes(app)
    setup_aiohttp_apispec(
        app, title="YABL00", url="/docs/json", swagger_path="/docs"
    )
    setup_middlewares(app)
    setup_store(app)
    return app
