from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import math

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QMouseEvent,
    QNativeGestureEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from .constants import DEFAULT_SCENE_RECT, FRAME_MIME_TYPE, SUPPORTED_IMAGE_SUFFIXES
from .theme import COLORS


class BoardScene(QGraphicsScene):
    def __init__(self) -> None:
        super().__init__()
        self.setSceneRect(QRectF(*DEFAULT_SCENE_RECT))
        self.setItemIndexMethod(QGraphicsScene.BspTreeIndex)


class CanvasView(QGraphicsView):
    files_dropped = Signal(list, QPointF)
    frames_dropped = Signal(QPointF)
    zoom_changed = Signal(float)

    def __init__(self, scene: BoardScene) -> None:
        super().__init__(scene)
        self.setAcceptDrops(True)
        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setBackgroundBrush(QColor(COLORS["background"]))
        self.setFrameShape(QGraphicsView.NoFrame)
        self._zoom = 1.0
        self._panning = False
        self._last_pan_point = QPoint()

    @property
    def zoom_level(self) -> float:
        return self._zoom

    def set_zoom_level(
        self,
        zoom: float,
        anchor: Optional[QPointF] = None,
    ) -> None:
        zoom = min(8.0, max(0.05, zoom))
        if math.isclose(zoom, self._zoom, rel_tol=1e-6):
            return
        anchor = anchor or QPointF(self.viewport().rect().center())
        scene_before = self.mapToScene(anchor.toPoint())
        self.resetTransform()
        self.scale(zoom, zoom)
        self._zoom = zoom
        scene_after = self.mapToScene(anchor.toPoint())
        delta = scene_after - scene_before
        self.translate(delta.x(), delta.y())
        self.zoom_changed.emit(self._zoom)

    def zoom_in(self) -> None:
        self.set_zoom_level(self._zoom * 1.2)

    def zoom_out(self) -> None:
        self.set_zoom_level(self._zoom / 1.2)

    def reset_view(self) -> None:
        self.resetTransform()
        self._zoom = 1.0
        self.centerOn(0, 0)
        self.zoom_changed.emit(self._zoom)

    def fit_items(self) -> None:
        items_rect = self.scene().itemsBoundingRect()
        if items_rect.isNull() or items_rect.isEmpty():
            self.reset_view()
            return
        padded = items_rect.adjusted(-80, -80, 80, 80)
        self.fitInView(padded, Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoom_changed.emit(self._zoom)

    def viewportEvent(self, event) -> bool:  # type: ignore[no-untyped-def]
        if event.type() == QEvent.NativeGesture:
            gesture = event
            if (
                isinstance(gesture, QNativeGestureEvent)
                and gesture.gestureType() == Qt.ZoomNativeGesture
            ):
                factor = max(0.5, min(1.5, 1.0 + gesture.value()))
                self.set_zoom_level(self._zoom * factor, gesture.position())
                return True
        return super().viewportEvent(event)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(COLORS["background"]))
        minor_grid = 20
        major_grid = 100

        left = int(rect.left()) - (int(rect.left()) % minor_grid)
        top = int(rect.top()) - (int(rect.top()) % minor_grid)

        minor_lines = []
        major_lines = []
        x = left
        while x < rect.right():
            target = major_lines if x % major_grid == 0 else minor_lines
            target.append((QPointF(x, rect.top()), QPointF(x, rect.bottom())))
            x += minor_grid
        y = top
        while y < rect.bottom():
            target = major_lines if y % major_grid == 0 else minor_lines
            target.append((QPointF(rect.left(), y), QPointF(rect.right(), y)))
            y += minor_grid

        minor_pen = QPen(QColor(COLORS["grid_minor"]), 0)
        major_pen = QPen(QColor(COLORS["grid_major"]), 0)
        painter.setPen(minor_pen)
        for start, end in minor_lines:
            painter.drawLine(start, end)
        painter.setPen(major_pen)
        for start, end in major_lines:
            painter.drawLine(start, end)

    def wheelEvent(self, event: QWheelEvent) -> None:
        modifiers = event.modifiers()
        zoom_modifier = modifiers & (Qt.ControlModifier | Qt.MetaModifier)
        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()

        if zoom_modifier:
            amount = pixel_delta.y() if not pixel_delta.isNull() else angle_delta.y() / 8
            if amount:
                factor = math.exp(amount * 0.006)
                self.set_zoom_level(self._zoom * factor, event.position())
            event.accept()
            return

        if not pixel_delta.isNull():
            horizontal = pixel_delta.x()
            vertical = pixel_delta.y()
        else:
            horizontal = angle_delta.x() / 2
            vertical = angle_delta.y() / 2
            if modifiers & Qt.ShiftModifier:
                horizontal, vertical = vertical, horizontal

        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - int(horizontal)
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - int(vertical)
        )
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        left_on_empty = (
            event.button() == Qt.LeftButton
            and self.itemAt(event.position().toPoint()) is None
            and not event.modifiers() & Qt.ShiftModifier
        )
        should_pan = event.button() == Qt.MiddleButton or left_on_empty
        if should_pan:
            if left_on_empty:
                focus_item = self.scene().focusItem()
                finish_editing = getattr(focus_item, "finish_editing", None)
                if callable(finish_editing):
                    finish_editing()
                self.scene().clearFocus()
                self.scene().clearSelection()
            self._panning = True
            self._last_pan_point = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            current = event.position().toPoint()
            delta = current - self._last_pan_point
            self._last_pan_point = current
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and event.button() in {Qt.MiddleButton, Qt.LeftButton}:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(FRAME_MIME_TYPE):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        if self._accepted_files(event.mimeData().urls()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasFormat(FRAME_MIME_TYPE):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        if self._accepted_files(event.mimeData().urls()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasFormat(FRAME_MIME_TYPE):
            self.frames_dropped.emit(
                self.mapToScene(event.position().toPoint())
            )
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        files = self._accepted_files(event.mimeData().urls())
        if files:
            self.files_dropped.emit(files, self.mapToScene(event.position().toPoint()))
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    @staticmethod
    def _accepted_files(urls: Iterable) -> list:
        result = []
        for url in urls:
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
                result.append(str(path))
        return result
