import re
from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class ThemeColors:
    hover_background: str = "#307DA5D7"
    selected_background: str = "#307DA5D7"
    correct_background: str = "#3A91C39A"
    incorrect_background: str = "#3ABE6970"
    text: str = "#B8DCE6F2"
    background: str = "#00121A28"
    outline: str = "#1AD7E6F8"

    def __post_init__(self) -> None:
        for value in vars(self).values():
            if not isinstance(value, str) or not re.fullmatch(
                r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", value
            ):
                raise ValueError("颜色必须为 #RRGGBB 或 #AARRGGBB")

    def color(self, name: str) -> QColor:
        return QColor(getattr(self, name))
