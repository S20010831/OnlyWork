"""Fit horizontal option text into a sector, then wrap without changing its content."""

import math
import re
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainterPath, QTextLayout, QTextOption


@dataclass(frozen=True)
class OptionTextLayout:
    rect: QRect
    lines: tuple[str, ...]
    line_height: int
    clipped: bool


def sector_text_rects(
    region: QPainterPath,
    center: QPoint,
    angle: float,
    span: float,
    inner_radius: float,
    outer_radius: float,
    line_height: int,
) -> tuple[QRect, ...]:
    """Find safe candidates for each row count and position within the sector."""
    best = {}
    for offset in (0.0, -0.35, 0.35, -0.7, 0.7):
        radians = math.radians(angle + offset * span / 2)
        for radius in range(round(inner_radius + 14), round(outer_radius - 5), 4):
            x = round(center.x() + radius * math.cos(radians))
            y = round(center.y() + radius * math.sin(radians))
            for rows in range(1, 5):
                height = rows * line_height

                def rectangle(width: int) -> QRect:
                    return QRect(round(x - width / 2), round(y - height / 2), width, height)

                if not region.contains(QRectF(rectangle(2))):
                    continue
                low, high = 2, round(outer_radius * 2)
                while low < high:
                    width = (low + high + 1) // 2
                    if region.contains(QRectF(rectangle(width))):
                        low = width
                    else:
                        high = width - 1
                key = rows, offset
                if key not in best or low > best[key][0]:
                    best[key] = low, rectangle(low)
    return tuple(best[key][1] for key in sorted(best))


def wrap_option_text(text: str, font: QFont, rect: QRect) -> OptionTextLayout:
    """Use Qt's word/grapheme wrapping, preferring punctuation when a line overflows."""
    metrics = QFontMetrics(font)
    line_height = metrics.lineSpacing()
    source = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\u2028")
    encoded = source.encode("utf-16-le")
    layout = QTextLayout(source, font)
    options = QTextOption()
    options.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(options)
    lines = []
    consumed = 0
    too_wide = False
    layout.beginLayout()
    for _ in range(min(4, rect.height() // line_height)):
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(rect.width())
        start, length = line.textStart(), line.textLength()
        fragment = encoded[start * 2 : (start + length) * 2].decode("utf-16-le")
        boundaries = list(re.finditer(r"[;；,，、]\s*", fragment))
        if boundaries and (start + length) * 2 < len(encoded):
            prefix = fragment[: boundaries[-1].end()]
            if metrics.horizontalAdvance(prefix) >= rect.width() * 0.45:
                line.setNumColumns(len(prefix.encode("utf-16-le")) // 2)
                length = line.textLength()
                fragment = encoded[start * 2 : (start + length) * 2].decode("utf-16-le")
        too_wide |= line.naturalTextWidth() > rect.width()
        lines.append(fragment.replace("\u2028", "").strip())
        consumed = (start + length) * 2
    layout.endLayout()
    clipped = too_wide or bool(encoded[consumed:].decode("utf-16-le").strip())
    if clipped and lines:
        lines[-1] = metrics.elidedText(lines[-1] + "…", Qt.TextElideMode.ElideRight, rect.width())
    return OptionTextLayout(QRect(rect), tuple(lines), line_height, clipped)


def fit_option_text(
    text: str,
    font: QFont,
    rects: tuple[QRect, ...],
    center: QPoint,
    angle: float,
    span: float,
) -> OptionTextLayout:
    """Balance complete text, natural line breaks, and proximity to the sector center."""
    layouts = [wrap_option_text(text, font, rect) for rect in rects]

    def score(result: OptionTextLayout) -> tuple:
        delta = result.rect.center() - center
        direction = math.degrees(math.atan2(delta.y(), delta.x()))
        offset = abs((direction - angle + 180) % 360 - 180) / (span / 2)
        orphans = sum(len(line) == 1 for line in result.lines[:-1])
        reading_cost = len(result.lines) + offset * 2 + orphans * 1.5
        return (
            result.clipped,
            -sum(len(line.rstrip("…")) for line in result.lines)
            if result.clipped
            else reading_cost,
            reading_cost,
            -result.rect.width(),
            result.rect.height(),
        )

    return min(layouts, key=score)
