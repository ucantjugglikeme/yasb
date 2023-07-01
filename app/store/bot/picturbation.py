from datetime import datetime
from pandas import DataFrame
from pandas.io.formats.style import Styler
from dataframe_image import export
import os
import typing

from logging import getLogger

from app.russian_loto.models import CardCell, SessionPlayer

if typing.TYPE_CHECKING:
    from app.web.app import Application

INDEX_OFFSET = 1


class Picturbator:
    RED = '#E20D13'
    SHIFT_I = 1
    SHIFT_J = 2
    TABLE_STYLES = [
        {
            'selector': 'th', 'props': 'text-align: center; background-color: white;'
        },
        {
            'selector': 'th:nth-child(1)', 'props': 'border-top: 1px solid white;'
        },
        {
            'selector': 'td', 'props': [
                ('font-size', '24pt'), ('font-weight', 'bold'), ('border', '1px solid black'),
                ('text-align', 'center'), ('width', '44px'), ('border-color', 'black')
            ]
        },
        {
            'selector': 'caption', 'props': [
                ('text-align', 'left'), ('font-size', '12pt'), ('font-weight', 'normal'), ('font-style', 'italic')
            ]
        }
    ]
    BARREL_IMG_PATH = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "images/barrel.png"
    ).replace("\\", "/")
    COLUMNS = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
    INDEXES = ["1", "2", "3"]

    def __init__(self, app: "Application"):
        self.app = app
        self.logger = getLogger("handler")

    async def generate_card_picture(self, card_number, card: list[CardCell]) -> str:
        """По данным о переданной карте формирует изображение и возвращает путь к файлу"""

        card_numbers = [
            [
                str(card.barrel_number) if card.barrel_number else ""
                for card in list(filter(lambda card_cell: card_cell.row_index == 1, card))
            ],
            [
                str(card.barrel_number) if card.barrel_number else ""
                for card in list(filter(lambda card_cell: card_cell.row_index == 2, card))
            ],
            [
                str(card.barrel_number) if card.barrel_number else ""
                for card in list(filter(lambda card_cell: card_cell.row_index == 3, card))
            ]
        ]
        card_barrels = [
            [card.is_covered for card in list(filter(lambda card_cell: card_cell.row_index == 1, card))],
            [card.is_covered for card in list(filter(lambda card_cell: card_cell.row_index == 2, card))],
            [card.is_covered for card in list(filter(lambda card_cell: card_cell.row_index == 3, card))]
        ]

        t_styles = self.TABLE_STYLES
        df = DataFrame(card_numbers, columns=self.COLUMNS, index=self.INDEXES)
        for i, row in enumerate(card_numbers):
            for j, cell in enumerate(row):
                props = [
                    ('background-repeat', 'no-repeat'), ('background-position', 'center'),
                    ('background-size', '64px 64px'),
                    ('background-image', f'url("{self.BARREL_IMG_PATH}")'), ('color', self.RED)
                ] if (card_numbers[i][j] and card_barrels[i][j] is True) else []

                t_styles.append(
                    {'selector': f'tr:nth-child({i + self.SHIFT_I}) td:nth-child({j + self.SHIFT_J})', 'props': props})

        df_styled = df.style.set_table_styles(t_styles)

        player, session_player = await self.app.store.loto_games.get_session_and_player(
            card[0].session_id, card[0].player_id
        )

        df_styled.set_caption(f'Карта №{card_number}<br>{session_player.role} - {player.name}')

        unique_pic_name = "_".join(["doc", str(session_player.session_id), str(session_player.player_id)])
        pic_path = f"images/{unique_pic_name}.png"
        export(df_styled, pic_path)

        return pic_path

    async def delete_card_picture(self, card_path):
        os.remove(card_path)
