import math
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QSize


@dataclass(frozen=True)
class RadialMetrics:
    size: int = 240
    inner_radius: float = 58
    outer_radius: float = 114
    center_card_width: int = 120
    center_card_height: int = 120


def sector_angle(count: int) -> float:
    if count <= 0:
        raise ValueError("选项数量必须大于零")
    return 360.0 / count


def option_angle(index: int, count: int) -> float:
    return -90.0 + index * sector_angle(count)


def option_index(dx: float, dy: float, count: int, outer_radius: float) -> int | None:
    if math.hypot(dx, dy) > outer_radius:
        return None
    angle_from_top = (math.degrees(math.atan2(dy, dx)) + 90) % 360
    return int((angle_from_top + sector_angle(count) / 2) // sector_angle(count)) % count


def overlay_top_left(cursor: QPoint, available: QRect, size: int) -> QPoint:
    half = size // 2
    x = max(available.left(), min(cursor.x() - half, available.right() - size + 1))
    y = max(available.top(), min(cursor.y() - half, available.bottom() - size + 1))
    return QPoint(x, y)


def bubble_position(
    anchor: QRect,
    available: QRect,
    size: QSize,
    preferred: str | None = None,
    target: QPoint | None = None,
) -> tuple[QPoint, str]:
    """Use a preferred fitting side, or the roomiest side, aligned to the target."""
    gap = 4
    target = anchor.center() if target is None else target
    x = max(
        available.left(),
        min(target.x() - size.width() // 2, available.right() - size.width() + 1),
    )
    y = max(
        available.top(),
        min(target.y() - size.height() // 2, available.bottom() - size.height() + 1),
    )
    candidates = {
        "right": QPoint(anchor.right() + gap + 1, y),
        "left": QPoint(anchor.left() - gap - size.width(), y),
        "bottom": QPoint(x, anchor.bottom() + gap + 1),
        "top": QPoint(x, anchor.top() - gap - size.height()),
    }
    room = {
        "right": (available.right() - anchor.right()) * available.height(),
        "left": (anchor.left() - available.left()) * available.height(),
        "bottom": (available.bottom() - anchor.bottom()) * available.width(),
        "top": (anchor.top() - available.top()) * available.width(),
    }
    directions = sorted(candidates, key=room.get, reverse=True)
    if preferred in candidates:
        directions.remove(preferred)
        directions.insert(0, preferred)
    for direction in directions:
        point = candidates[direction]
        if available.contains(QRect(point, size)):
            return point, direction
    return QPoint(x, y), max(room, key=room.get)
