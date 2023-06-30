import typing
import yaml
from dataclasses import dataclass

if typing.TYPE_CHECKING:
    from app.web.app import Application


@dataclass
class SessionConfig:
    key: str


@dataclass
class AdminConfig:
    email: str
    password: str


@dataclass
class BotConfig:
    token: str
    group_id: int


@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"
    database: str = "project"


@dataclass
class Config:
    admin: AdminConfig
    session: SessionConfig = None
    bot: BotConfig = None
    database: DatabaseConfig = None


@dataclass
class CardConfig:
    r_1: list[int | None]
    r_2: list[int | None]
    r_3: list[int | None]


@dataclass
class CardsConfig:
    cards: list[CardConfig]
    cards_amount: int = 24


def setup_config(app: "Application", config_path: str):
    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)

    app.config = Config(
        session=SessionConfig(
            key=raw_config["session"]["key"],
        ),
        admin=AdminConfig(
            email=raw_config["admin"]["email"],
            password=raw_config["admin"]["password"],
        ),
        bot=BotConfig(
            token=raw_config["bot"]["token"],
            group_id=raw_config["bot"]["group_id"],
        ),
        database=DatabaseConfig(**raw_config["database"]),
    )


def setup_cards_config(app: "Application", cards_config_path: str):
    with open(cards_config_path, "r") as f:
        raw_config = yaml.safe_load(f)

    cards = [
        CardConfig(r_1=card[1], r_2=card[2], r_3=card[3]) for card in
        [raw_config["cards"][card_number] for card_number in raw_config["cards"].keys()]
    ]

    app.cards = CardsConfig(
        cards=cards,
        cards_amount=len(cards)
    )
