from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImageReader,
    QMovie,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
    QStyle,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .models import AssetModel, BoardItemModel
from .theme import COLORS


class MediaItem(QGraphicsObject):
    frame_changed = Signal(int)
    playback_changed = Signal(bool)
    geometry_changed = Signal()

    def __init__(
        self,
        model: BoardItemModel,
        asset: AssetModel,
        source_path: Path,
        changed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.model_id = model.id
        self.asset_id = asset.id
        self.asset = asset
        self.source_path = source_path
        self._changed = changed
        self._movie: Optional[QMovie] = None
        self._pixmap = QPixmap()
        self._playing = False
        self._dragging = False
        self._width = model.width
        self._height = model.height

        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsFocusable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setPos(model.x, model.y)
        self.setScale(model.scale)
        self.setRotation(model.rotation)
        self.setZValue(model.z)
        self.setData(0, model.id)

        if asset.frame_count > 1:
            self._movie = QMovie(str(source_path))
            self._movie.setParent(self)
            self._movie.setCacheMode(QMovie.CacheAll)
            self._movie.frameChanged.connect(self._on_frame_changed)
            self._movie.jumpToFrame(0)
            self._movie.setSpeed(max(1, int(model.playback_rate * 100)))
            self._pixmap = self._movie.currentPixmap()
        else:
            reader = QImageReader(str(source_path))
            reader.setAutoTransform(True)
            image = reader.read()
            self._pixmap = QPixmap.fromImage(image)

        if self._pixmap.isNull():
            self._width = max(self._width, 240)
            self._height = max(self._height, 135)
        elif model.width <= 0 or model.height <= 0:
            self._set_default_size(self._pixmap.width(), self._pixmap.height())

    def _set_default_size(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            return
        max_width = 480.0
        max_height = 360.0
        factor = min(max_width / width, max_height / height, 1.0)
        self.prepareGeometryChange()
        self._width = max(80.0, width * factor)
        self._height = max(60.0, height * factor)

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, self._width, self._height)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        del widget
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = self.boundingRect()
        painter.fillRect(rect, QColor("#FFFFFF"))
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                rect.size().toSize(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            x = (rect.width() - scaled.width()) / 2
            y = (rect.height() - scaled.height()) / 2
            painter.drawPixmap(QPointF(x, y), scaled)
        else:
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(rect, Qt.AlignCenter, f"Unable to preview\n{self.asset.name}")

        if option.state & QStyle.State_Selected:
            pen = QPen(QColor(COLORS["selection"]), 2.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

    def _on_frame_changed(self, frame_number: int) -> None:
        if self._movie is None:
            return
        self._pixmap = self._movie.currentPixmap()
        self.update()
        self.frame_changed.emit(frame_number)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        result = super().itemChange(change, value)
        if change in {
            QGraphicsItem.ItemPositionHasChanged,
            QGraphicsItem.ItemTransformHasChanged,
            QGraphicsItem.ItemRotationHasChanged,
        }:
            self.geometry_changed.emit()
            if self._changed:
                self._changed()
        return result

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and not self._dragging:
            distance = (
                event.screenPos() - event.buttonDownScreenPos(Qt.LeftButton)
            ).manhattanLength()
            if distance < QApplication.startDragDistance():
                event.accept()
                return
            self._dragging = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self._dragging = False

    @property
    def is_animated(self) -> bool:
        return self._movie is not None

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def playback_rate(self) -> float:
        if self._movie is None:
            return 1.0
        return self._movie.speed() / 100.0

    def play(self) -> None:
        if self._movie is None:
            return
        self._movie.start()
        self._playing = True
        self.playback_changed.emit(True)

    def pause(self) -> None:
        if self._movie is None:
            return
        self._movie.setPaused(True)
        self._playing = False
        self.playback_changed.emit(False)

    def toggle_playback(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def set_playback_rate(self, rate: float) -> None:
        if self._movie is not None:
            self._movie.setSpeed(max(1, int(rate * 100)))

    def step_frame(self, delta: int) -> None:
        if self._movie is None:
            return
        self.pause()
        frame_count = max(1, self._movie.frameCount())
        target = (self._movie.currentFrameNumber() + delta) % frame_count
        self._movie.jumpToFrame(target)

    def jump_to_frame(self, frame_number: int) -> None:
        if self._movie is None:
            return
        self.pause()
        frame_count = max(1, self._movie.frameCount())
        self._movie.jumpToFrame(max(0, min(frame_number, frame_count - 1)))

    def current_frame(self) -> int:
        return self._movie.currentFrameNumber() if self._movie else 0

    def dispose(self) -> None:
        if self._movie is None:
            return
        self._movie.stop()
        try:
            self._movie.frameChanged.disconnect(self._on_frame_changed)
        except (RuntimeError, TypeError):
            pass
        self._movie.deleteLater()
        self._movie = None


class NoteItem(QGraphicsTextItem):
    geometry_changed = Signal()
    editing_started = Signal()
    editing_finished = Signal()
    cursor_format_changed = Signal()

    def __init__(
        self,
        model: BoardItemModel,
        changed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.model_id = model.id
        self._changed = changed
        self._dragging = False
        self.background_color = QColor(model.background_color)
        font = QFont()
        font.setPointSize(model.font_size)
        self.document().setDefaultFont(font)
        self.setDefaultTextColor(QColor(model.text_color))
        self.setFont(font)
        if model.rich_text:
            self.setHtml(model.rich_text)
        else:
            self.setPlainText(model.text or "Double-click to edit")
        self.setTextWidth(model.width)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsFocusable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setPos(model.x, model.y)
        self.setScale(model.scale)
        self.setRotation(model.rotation)
        self.setZValue(model.z)
        self.setData(0, model.id)
        self.document().contentsChanged.connect(self._contents_changed)

    def boundingRect(self) -> QRectF:
        return super().boundingRect().adjusted(-12, -10, 12, 10)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        path = QPainterPath()
        path.addRoundedRect(self.boundingRect(), 6, 6)
        painter.fillPath(path, self.background_color)
        border = QColor(COLORS["selection"] if self.isSelected() else COLORS["border"])
        pen = QPen(border, 2 if self.isSelected() else 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawPath(path)
        super().paint(painter, option, widget)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.start_editing(Qt.MouseFocusReason)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if (
            event.buttons() & Qt.LeftButton
            and not self._dragging
            and not self.textInteractionFlags() & Qt.TextEditorInteraction
        ):
            distance = (
                event.screenPos() - event.buttonDownScreenPos(Qt.LeftButton)
            ).manhattanLength()
            if distance < QApplication.startDragDistance():
                event.accept()
                return
            self._dragging = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self._dragging = False
        if self.is_editing:
            self.cursor_format_changed.emit()

    def keyReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().keyReleaseEvent(event)
        if self.is_editing:
            self.cursor_format_changed.emit()

    @property
    def is_editing(self) -> bool:
        return bool(self.textInteractionFlags() & Qt.TextEditorInteraction)

    def start_editing(
        self,
        reason: Qt.FocusReason = Qt.OtherFocusReason,
        select_all: bool = False,
    ) -> None:
        was_editing = self.is_editing
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(reason)
        if select_all:
            cursor = self.textCursor()
            cursor.select(QTextCursor.Document)
            self.setTextCursor(cursor)
        if not was_editing:
            self.editing_started.emit()
        self.cursor_format_changed.emit()

    def finish_editing(self) -> None:
        was_editing = self.is_editing
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            self.setTextCursor(cursor)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        if was_editing:
            self.editing_finished.emit()

    def focusOutEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().focusOutEvent(event)

    def current_format_state(self) -> dict[str, object]:
        cursor = self.textCursor()
        character_format = cursor.charFormat()
        font = character_format.font()
        point_size = character_format.fontPointSize()
        if point_size <= 0:
            point_size = font.pointSizeF()
        if point_size <= 0:
            point_size = self.document().defaultFont().pointSizeF()

        foreground = character_format.foreground()
        color = (
            foreground.color()
            if character_format.hasProperty(QTextCharFormat.ForegroundBrush)
            else self.defaultTextColor()
        )
        alignment = cursor.blockFormat().alignment()
        if alignment & Qt.AlignHCenter:
            alignment_name = "center"
        elif alignment & Qt.AlignRight:
            alignment_name = "right"
        else:
            alignment_name = "left"

        return {
            "alignment": alignment_name,
            "font_size": max(1.0, point_size),
            "color": color,
            "background_color": QColor(self.background_color),
            "bold": font.bold(),
            "italic": font.italic(),
            "underline": font.underline(),
        }

    def set_alignment(self, alignment_name: str) -> None:
        alignments = {
            "left": Qt.AlignLeft,
            "center": Qt.AlignHCenter,
            "right": Qt.AlignRight,
        }
        alignment = alignments.get(alignment_name)
        if alignment is None:
            return
        cursor = self.textCursor()
        block_format = QTextBlockFormat(cursor.blockFormat())
        block_format.setAlignment(alignment)
        cursor.mergeBlockFormat(block_format)
        self.setTextCursor(cursor)
        self._format_applied()

    def set_font_size(self, point_size: float) -> None:
        if point_size <= 0:
            return
        character_format = QTextCharFormat()
        character_format.setFontPointSize(point_size)
        self._merge_character_format(character_format)

    def set_text_color(self, color: QColor) -> None:
        if not color.isValid():
            return
        character_format = QTextCharFormat()
        character_format.setForeground(color)
        self._merge_character_format(character_format)

    def set_background_color(self, color: QColor) -> None:
        if not color.isValid():
            return
        self.background_color = QColor(color)
        self.update()
        self._format_applied()

    def set_bold(self, enabled: bool) -> None:
        character_format = QTextCharFormat()
        character_format.setFontWeight(
            QFont.Bold if enabled else QFont.Normal
        )
        self._merge_character_format(character_format)

    def set_italic(self, enabled: bool) -> None:
        character_format = QTextCharFormat()
        character_format.setFontItalic(enabled)
        self._merge_character_format(character_format)

    def set_underline(self, enabled: bool) -> None:
        character_format = QTextCharFormat()
        character_format.setFontUnderline(enabled)
        self._merge_character_format(character_format)

    def _merge_character_format(self, character_format: QTextCharFormat) -> None:
        cursor = self.textCursor()
        cursor.mergeCharFormat(character_format)
        self.setTextCursor(cursor)
        self._format_applied()

    def _format_applied(self) -> None:
        self.setFocus(Qt.OtherFocusReason)
        self.cursor_format_changed.emit()
        self.geometry_changed.emit()
        if self._changed:
            self._changed()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        result = super().itemChange(change, value)
        if change in {
            QGraphicsItem.ItemPositionHasChanged,
            QGraphicsItem.ItemTransformHasChanged,
            QGraphicsItem.ItemRotationHasChanged,
        }:
            self.geometry_changed.emit()
            if self._changed:
                self._changed()
        return result

    def _contents_changed(self) -> None:
        self.geometry_changed.emit()
        if self.is_editing:
            self.cursor_format_changed.emit()
        if self._changed:
            self._changed()
