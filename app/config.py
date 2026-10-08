"""Versioned settings with field-level validation and atomic writes."""

import logging
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from .paths import DATA_DIR
from .storage import read_json, write_json
from .theme import ThemeColors

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BehaviorSettings:
    feedback_delay_ms: int = 650
    cursor_arm_delay_ms: int = 200
    hide_delay_ms: int = 0
    fade_duration_ms: int = 140

    def __post_init__(self) -> None:
        limits = {
            "feedback_delay_ms": (100, 10000),
            "cursor_arm_delay_ms": (0, 2000),
            "hide_delay_ms": (0, 3000),
            "fade_duration_ms": (0, 2000),
        }
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} 必须为 {low}～{high} 的整数")


@dataclass(frozen=True)
class AppSettings:
    theme: ThemeColors = ThemeColors()
    behavior: BehaviorSettings = BehaviorSettings()


def decode_fields(cls, raw: object):
    result = cls()
    if isinstance(raw, dict):
        for field in fields(cls):
            if field.name in raw:
                try:
                    result = replace(result, **{field.name: raw[field.name]})
                except (ValueError, TypeError):
                    logger.warning("invalid settings field ignored: %s", field.name)
    return result


class SettingsManager:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA_DIR / "settings.json"
        self.settings = AppSettings()
        self.load()

    @property
    def colors(self) -> ThemeColors:
        return self.settings.theme

    @property
    def behavior(self) -> BehaviorSettings:
        return self.settings.behavior

    def load(self) -> None:
        try:
            raw = read_json(self.path)
            if not isinstance(raw, dict) or raw.get("version", 1) != 1:
                raise ValueError("unsupported settings format")
            self.settings = AppSettings(
                decode_fields(ThemeColors, raw.get("theme")),
                decode_fields(BehaviorSettings, raw.get("behavior")),
            )
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            logger.warning("settings unavailable; using defaults", exc_info=True)

    def _commit(self, updated: AppSettings) -> None:
        write_json(self.path, {"version": 1, **asdict(updated)})
        self.settings = updated

    def set_color(self, name: str, color) -> None:
        from PySide6.QtGui import QColor

        value = color.name(QColor.NameFormat.HexArgb).upper()
        self._commit(replace(self.settings, theme=replace(self.colors, **{name: value})))

    def reset_colors(self) -> None:
        self._commit(replace(self.settings, theme=ThemeColors()))

    def set_behavior(self, **changes: int) -> None:
        self._commit(replace(self.settings, behavior=replace(self.behavior, **changes)))
