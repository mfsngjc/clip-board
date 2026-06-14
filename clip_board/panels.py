from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QItemSelection,
    QItemSelectionModel,
    QPoint,
    QSignalBlocker,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QDrag,
    QDropEvent,
    QFontMetrics,
    QIcon,
    QMouseEvent,
    QMovie,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .constants import FRAME_MIME_TYPE
from .models import AssetModel, CompositionModel
from .theme import COLORS


class AssetPanel(QWidget):
    asset_activated = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.empty_label = QLabel("Drop images or GIFs onto the board")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; padding: 24px 16px;"
        )
        layout.addWidget(self.empty_label)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListView.IconMode)
        self.list_widget.setResizeMode(QListView.Adjust)
        self.list_widget.setMovement(QListView.Static)
        self.list_widget.setIconSize(QSize(96, 72))
        self.list_widget.setGridSize(QSize(120, 108))
        self.list_widget.setWordWrap(True)
        self.list_widget.itemDoubleClicked.connect(self._activate_item)
        layout.addWidget(self.list_widget, 1)
        self._sync_empty_state()

    def clear(self) -> None:
        self.list_widget.clear()
        self._sync_empty_state()

    def add_asset(self, asset: AssetModel, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.list_widget.iconSize(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        item = QListWidgetItem(QIcon(pixmap), asset.name)
        item.setData(Qt.UserRole, asset.id)
        item.setToolTip(
            f"{asset.name}\n{asset.width} x {asset.height}\n"
            f"{asset.frame_count} frame{'s' if asset.frame_count != 1 else ''}"
        )
        self.list_widget.addItem(item)
        self._sync_empty_state()

    def selected_asset_id(self) -> Optional[str]:
        items = self.list_widget.selectedItems()
        return str(items[0].data(Qt.UserRole)) if items else None

    def select_asset(self, asset_id: str) -> None:
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.data(Qt.UserRole) == asset_id:
                self.list_widget.setCurrentItem(item)
                return

    def _activate_item(self, item: QListWidgetItem) -> None:
        self.asset_activated.emit(str(item.data(Qt.UserRole)))

    def _sync_empty_state(self) -> None:
        is_empty = self.list_widget.count() == 0
        self.empty_label.setVisible(is_empty)
        self.list_widget.setVisible(not is_empty)


class FrameListWidget(QListWidget):
    frames_drag_started = Signal(object)
    frames_reordered = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._selection_anchor_item: Optional[QListWidgetItem] = None
        self._range_selecting = False
        self._pointer_selecting = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        if event.button() != Qt.LeftButton or not index.isValid():
            self._range_selecting = False
            self._pointer_selecting = False
            super().mousePressEvent(event)
            return

        self._pointer_selecting = True
        row = index.row()
        anchor_row = self._anchor_row()
        if event.modifiers() & Qt.ShiftModifier and anchor_row is not None:
            start = self.model().index(min(anchor_row, row), 0)
            end = self.model().index(max(anchor_row, row), 0)
            self.selectionModel().select(
                QItemSelection(start, end),
                QItemSelectionModel.ClearAndSelect,
            )
            self.selectionModel().setCurrentIndex(
                index,
                QItemSelectionModel.NoUpdate,
            )
            self._range_selecting = True
            event.accept()
            return

        self._range_selecting = False
        super().mousePressEvent(event)
        self._selection_anchor_item = self.item(row)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._range_selecting:
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._range_selecting and event.button() == Qt.LeftButton:
            self._range_selecting = False
            self._pointer_selecting = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self._pointer_selecting = False

    def reset_selection_anchor(self) -> None:
        self._selection_anchor_item = None
        self._range_selecting = False
        self._pointer_selecting = False

    @property
    def pointer_selecting(self) -> bool:
        return self._pointer_selecting

    def reveal_item_outside_guard(self, item: QListWidgetItem) -> None:
        rect = self.visualItemRect(item)
        viewport_width = self.viewport().width()
        if not rect.isValid() or viewport_width <= 0:
            return

        margin = min(
            self.gridSize().width(),
            max(24, (viewport_width - rect.width()) // 2),
        )
        guard_left = margin
        guard_right = viewport_width - margin
        delta = 0
        if rect.left() < guard_left:
            delta = rect.left() - guard_left
        elif rect.right() > guard_right:
            delta = rect.right() - guard_right
        if delta:
            scrollbar = self.horizontalScrollBar()
            scrollbar.setValue(scrollbar.value() + delta)

    def _anchor_row(self) -> Optional[int]:
        if self._selection_anchor_item is None:
            return None
        try:
            row = self.row(self._selection_anchor_item)
        except RuntimeError:
            self.reset_selection_anchor()
            return None
        if row < 0:
            self.reset_selection_anchor()
            return None
        return row

    def startDrag(self, supported_actions) -> None:  # type: ignore[no-untyped-def]
        selected_rows = sorted(
            index.row() for index in self.selectedIndexes()
        )
        if not selected_rows:
            return
        selected = [self.item(row) for row in selected_rows]
        frame_indices = [int(item.data(Qt.UserRole)) for item in selected]
        self.frames_drag_started.emit(frame_indices)

        mime = self.model().mimeData(self.selectedIndexes())
        mime.setData(FRAME_MIME_TYPE, str(len(frame_indices)).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        icon = selected[0].icon()
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(self.iconSize()))
        drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.MoveAction)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.source() is not self:
            super().dropEvent(event)
            return
        drop_row = self._drop_row(event.position().toPoint())
        if not self.move_selected_rows(drop_row):
            event.ignore()
            return
        event.setDropAction(Qt.MoveAction)
        event.accept()

    def move_selected_rows(self, drop_row: int) -> bool:
        selected_rows = sorted(
            index.row() for index in self.selectedIndexes()
        )
        if not selected_rows:
            return False

        before = [
            int(self.item(row).data(Qt.UserRole))
            for row in range(self.count())
        ]
        drop_row = max(0, min(drop_row, self.count()))
        insertion_row = drop_row - sum(
            row < drop_row for row in selected_rows
        )

        blocker = QSignalBlocker(self)
        moving_items = [
            self.takeItem(row)
            for row in reversed(selected_rows)
        ]
        moving_items.reverse()
        insertion_row = max(0, min(insertion_row, self.count()))
        for offset, item in enumerate(moving_items):
            self.insertItem(insertion_row + offset, item)
            item.setSelected(True)
        if moving_items:
            self.setCurrentItem(
                moving_items[0],
                QItemSelectionModel.NoUpdate,
            )
            self._selection_anchor_item = moving_items[0]
        del blocker

        after = [
            int(self.item(row).data(Qt.UserRole))
            for row in range(self.count())
        ]
        if after == before:
            return False
        self.frames_reordered.emit(after)
        return True

    def _drop_row(self, point: QPoint) -> int:
        for row in range(self.count()):
            rect = self.visualItemRect(self.item(row))
            if point.x() < rect.center().x():
                return row
        return self.count()


class FrameStrip(QWidget):
    frame_selected = Signal(int)
    selection_changed = Signal(object)
    frames_drag_started = Signal(object)
    frames_reordered = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._asset_id: Optional[str] = None
        self._frame_durations: list[int] = []
        self._cache: dict[tuple[str, int], list[tuple[QPixmap, int]]] = {}
        self._summary_text = ""
        self._loading = False
        self._syncing_current = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.summary = QLabel("Select a GIF to inspect its frames")
        self.summary.setStyleSheet(
            f"color: {COLORS['text_muted']}; padding: 8px 12px;"
        )
        layout.addWidget(self.summary)

        self.list_widget = FrameListWidget()
        self.list_widget.setViewMode(QListView.IconMode)
        self.list_widget.setFlow(QListView.LeftToRight)
        self.list_widget.setWrapping(False)
        self.list_widget.setResizeMode(QListView.Fixed)
        self.list_widget.setMovement(QListView.Snap)
        self.list_widget.setIconSize(QSize(120, 78))
        self.list_widget.setGridSize(QSize(138, 118))
        self.list_widget.setSpacing(4)
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.MoveAction)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setDropIndicatorShown(True)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setToolTip(
            "Command-click to select multiple frames; Shift-click for a range; drag to reorder."
        )
        self.list_widget.currentItemChanged.connect(self._current_item_changed)
        self.list_widget.itemSelectionChanged.connect(self._selection_changed)
        self.list_widget.frames_drag_started.connect(self.frames_drag_started)
        self.list_widget.frames_reordered.connect(self.frames_reordered)
        self.list_widget.model().rowsMoved.connect(self._rows_moved)
        layout.addWidget(self.list_widget, 1)

    @property
    def frame_count(self) -> int:
        return self.list_widget.count()

    @property
    def asset_id(self) -> Optional[str]:
        return self._asset_id

    def selected_indices(self) -> list[int]:
        return [
            int(self.list_widget.item(row).data(Qt.UserRole))
            for row in range(self.list_widget.count())
            if self.list_widget.item(row).isSelected()
        ]

    def has_focus(self) -> bool:
        focused = QApplication.focusWidget()
        return focused is not None and (
            focused is self.list_widget or self.list_widget.isAncestorOf(focused)
        )

    def show_asset(
        self,
        asset: AssetModel,
        path: Path,
        current_frame: int = 0,
    ) -> None:
        cache_key = (asset.sha256 or str(path), int(path.stat().st_mtime_ns))
        if self._asset_id != asset.id:
            self._loading = True
            self.list_widget.reset_selection_anchor()
            self.list_widget.clear()
            frames = self._cache.get(cache_key)
            if frames is None:
                frames = self._read_frames(path, asset.frame_count)
                self._cache[cache_key] = frames
            self._asset_id = asset.id
            self._frame_durations = [duration for _, duration in frames]
            elapsed = 0
            for index, (pixmap, duration) in enumerate(frames):
                item = QListWidgetItem(
                    QIcon(pixmap),
                    f"#{index + 1:03d}  {duration} ms",
                )
                item.setData(Qt.UserRole, index)
                item.setTextAlignment(Qt.AlignHCenter)
                item.setSizeHint(QSize(138, 118))
                item.setToolTip(
                    f"Frame {index + 1} of {len(frames)}\n"
                    f"Starts at {elapsed / 1000:.3f}s · Duration {duration}ms"
                )
                self.list_widget.addItem(item)
                elapsed += duration
            total_duration = sum(self._frame_durations)
            self._summary_text = (
                f"{asset.name} · {len(frames)} frames · {total_duration / 1000:.3f}s"
            )
            self.summary.setText(self._summary_text)
            self._loading = False
        self.set_current_frame(current_frame)
        if not self.selected_indices() and self.list_widget.currentItem() is not None:
            self.list_widget.currentItem().setSelected(True)

    def set_current_frame(self, frame_number: int) -> None:
        if not self.list_widget.count():
            return
        frame_number = max(0, min(frame_number, self.list_widget.count() - 1))
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if int(item.data(Qt.UserRole)) == frame_number:
                if self.list_widget.currentItem() is item:
                    return
                self._syncing_current = True
                self.list_widget.setCurrentItem(
                    item,
                    QItemSelectionModel.NoUpdate,
                )
                self._syncing_current = False
                if not self.list_widget.pointer_selecting:
                    self.list_widget.reveal_item_outside_guard(item)
                return

    def _current_item_changed(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ) -> None:
        del previous
        if self._loading or self._syncing_current or current is None:
            return
        self.frame_selected.emit(int(current.data(Qt.UserRole)))

    def _selection_changed(self) -> None:
        if self._loading:
            return
        selected = self.selected_indices()
        suffix = f" · {len(selected)} selected" if len(selected) > 1 else ""
        self.summary.setText(f"{self._summary_text}{suffix}")
        self.selection_changed.emit(selected)

    def _rows_moved(self, *args) -> None:  # type: ignore[no-untyped-def]
        del args
        if self._loading:
            return
        order = [
            int(self.list_widget.item(row).data(Qt.UserRole))
            for row in range(self.list_widget.count())
        ]
        QTimer.singleShot(
            0,
            lambda frame_order=order: self.frames_reordered.emit(frame_order),
        )

    @staticmethod
    def _read_frames(path: Path, expected_count: int) -> list[tuple[QPixmap, int]]:
        movie = QMovie(str(path))
        movie.setCacheMode(QMovie.CacheAll)
        frames: list[tuple[QPixmap, int]] = []
        frame_count = max(1, movie.frameCount(), expected_count)
        for index in range(frame_count):
            if not movie.jumpToFrame(index):
                break
            pixmap = movie.currentPixmap()
            if pixmap.isNull():
                continue
            preview = pixmap.scaled(
                QSize(120, 78),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            frames.append((preview, max(10, movie.nextFrameDelay())))
        return frames


class TimelineCanvas(QWidget):
    playhead_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.composition: Optional[CompositionModel] = None
        self.playhead_ms = 0
        self.pixels_per_second = 100
        self.header_height = 30
        self.track_height = 44
        self.gutter_width = 112
        self.setMinimumHeight(124)

    def set_composition(self, composition: CompositionModel) -> None:
        self.composition = composition
        duration = max(composition.duration_ms, 10000)
        width = self.gutter_width + int(duration / 1000 * self.pixels_per_second) + 100
        height = self.header_height + max(2, len(composition.tracks)) * self.track_height
        self.setMinimumSize(width, height)
        self.update()

    def set_playhead(self, milliseconds: int) -> None:
        self.playhead_ms = max(0, milliseconds)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COLORS["surface"]))
        painter.fillRect(
            0, 0, self.gutter_width, self.height(), QColor(COLORS["surface_raised"])
        )
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.drawLine(self.gutter_width, 0, self.gutter_width, self.height())
        painter.drawLine(0, self.header_height, self.width(), self.header_height)

        composition = self.composition
        if composition is None:
            return

        seconds = max(10, int(composition.duration_ms / 1000) + 1)
        painter.setPen(QColor(COLORS["text_muted"]))
        for second in range(seconds + 1):
            x = self.gutter_width + second * self.pixels_per_second
            tick_height = 10 if second % 5 == 0 else 6
            painter.drawLine(x, self.header_height - tick_height, x, self.header_height)
            if second % 5 == 0:
                painter.drawText(x + 4, 18, f"{second}s")

        metrics = QFontMetrics(painter.font())
        for track_index, track in enumerate(composition.tracks):
            y = self.header_height + track_index * self.track_height
            if track_index % 2:
                painter.fillRect(
                    self.gutter_width,
                    y,
                    self.width() - self.gutter_width,
                    self.track_height,
                    QColor("#F8FAFB"),
                )
            painter.setPen(QColor(COLORS["border"]))
            painter.drawLine(0, y + self.track_height, self.width(), y + self.track_height)
            painter.setPen(QColor(COLORS["text"]))
            painter.drawText(10, y, self.gutter_width - 20, self.track_height, Qt.AlignVCenter, track.name)

            for clip in track.clips:
                clip_x = self.gutter_width + int(
                    clip.timeline_start_ms / 1000 * self.pixels_per_second
                )
                clip_width = max(
                    36, int(clip.duration_ms / 1000 * self.pixels_per_second)
                )
                clip_rect = (
                    clip_x,
                    y + 5,
                    clip_width,
                    self.track_height - 10,
                )
                painter.setPen(QPen(QColor(COLORS["primary"]), 1))
                painter.setBrush(QColor(COLORS["primary_soft"]))
                painter.drawRoundedRect(*clip_rect, 4, 4)
                available = max(0, clip_width - 12)
                text = metrics.elidedText(clip.name, Qt.ElideRight, available)
                painter.setPen(QColor(COLORS["text"]))
                painter.drawText(
                    clip_x + 6,
                    y + 5,
                    available,
                    self.track_height - 10,
                    Qt.AlignVCenter,
                    text,
                )

        playhead_x = self.gutter_width + int(
            self.playhead_ms / 1000 * self.pixels_per_second
        )
        painter.setPen(QPen(QColor(COLORS["accent"]), 2))
        painter.drawLine(playhead_x, 0, playhead_x, self.height())
        painter.setBrush(QColor(COLORS["accent"]))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(
            [
                QPoint(playhead_x - 5, 0),
                QPoint(playhead_x + 5, 0),
                QPoint(playhead_x, 7),
            ]
        )

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.position().x() < self.gutter_width:
            return
        milliseconds = int(
            (event.position().x() - self.gutter_width)
            / self.pixels_per_second
            * 1000
        )
        self.set_playhead(milliseconds)
        self.playhead_changed.emit(milliseconds)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.buttons() & Qt.LeftButton:
            self.mousePressEvent(event)


class NoteTextToolbar(QFrame):
    alignment_changed = Signal(str)
    font_size_changed = Signal(float)
    color_requested = Signal()
    background_color_requested = Signal()
    bold_toggled = Signal(bool)
    italic_toggled = Signal(bool)
    underline_toggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("NoteTextToolbar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(
            f"""
            QFrame#NoteTextToolbar {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
            QFrame#NoteTextToolbar QFrame[separator="true"] {{
                background: {COLORS['border']};
                border: 0;
            }}
            """
        )

        controls_layout = QHBoxLayout(self)
        controls_layout.setContentsMargins(6, 5, 6, 5)
        controls_layout.setSpacing(4)

        self.size_button = self._tool_button("16", "Font size")
        self.size_button.setObjectName("NoteFontSize")
        self.size_button.setMinimumWidth(48)
        self.size_menu = QMenu(self.size_button)
        for point_size in (10, 12, 14, 16, 18, 20, 24, 28, 32, 40, 48, 64):
            action = self.size_menu.addAction(str(point_size))
            action.triggered.connect(
                lambda checked=False, value=point_size: self._request_font_size(value)
            )
        self.size_button.setMenu(self.size_menu)
        controls_layout.addWidget(self.size_button)

        self.color_button = self._tool_button("", "Text color")
        self.color_button.setObjectName("NoteTextColor")
        self.color_button.setFixedWidth(36)
        self.color_button.clicked.connect(self.color_requested)
        controls_layout.addWidget(self.color_button)

        self.background_color_button = self._tool_button("", "Note background color")
        self.background_color_button.setObjectName("NoteBackgroundColor")
        self.background_color_button.setFixedWidth(36)
        self.background_color_button.clicked.connect(
            self.background_color_requested
        )
        controls_layout.addWidget(self.background_color_button)

        controls_layout.addWidget(self._separator())

        self.bold_button = self._tool_button("B", "Bold", checkable=True)
        self.bold_button.setObjectName("NoteBold")
        bold_font = self.bold_button.font()
        bold_font.setBold(True)
        self.bold_button.setFont(bold_font)
        self.bold_button.clicked.connect(self.bold_toggled)
        controls_layout.addWidget(self.bold_button)

        self.italic_button = self._tool_button("I", "Italic", checkable=True)
        self.italic_button.setObjectName("NoteItalic")
        italic_font = self.italic_button.font()
        italic_font.setItalic(True)
        self.italic_button.setFont(italic_font)
        self.italic_button.clicked.connect(self.italic_toggled)
        controls_layout.addWidget(self.italic_button)

        self.underline_button = self._tool_button(
            "U",
            "Underline",
            checkable=True,
        )
        self.underline_button.setObjectName("NoteUnderline")
        underline_font = self.underline_button.font()
        underline_font.setUnderline(True)
        self.underline_button.setFont(underline_font)
        self.underline_button.clicked.connect(self.underline_toggled)
        controls_layout.addWidget(self.underline_button)

        controls_layout.addWidget(self._separator())

        self.alignment_group = QButtonGroup(self)
        self.alignment_group.setExclusive(True)
        self.alignment_buttons: dict[str, QPushButton] = {}
        alignment_icons = {
            "left": ("align-left.svg", "Align left"),
            "center": ("align-center.svg", "Align center"),
            "right": ("align-right.svg", "Align right"),
        }
        icon_root = Path(__file__).resolve().parent / "assets" / "icons"
        for name, (filename, tooltip) in alignment_icons.items():
            button = self._tool_button("", tooltip, checkable=True)
            button.setObjectName(f"NoteAlign{name.title()}")
            button.setIcon(QIcon(str(icon_root / filename)))
            button.setIconSize(QSize(20, 20))
            button.setFixedWidth(34)
            button.clicked.connect(
                lambda checked=False, value=name: (
                    self.alignment_changed.emit(value) if checked else None
                )
            )
            self.alignment_group.addButton(button)
            self.alignment_buttons[name] = button
            controls_layout.addWidget(button)

        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def _tool_button(
        self,
        text: str,
        tooltip: str,
        checkable: bool = False,
    ) -> QPushButton:
        button = QPushButton(text, self)
        button.setCheckable(checkable)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFocusPolicy(Qt.NoFocus)
        button.setFixedHeight(34)
        button.setMinimumWidth(34)
        return button

    def _separator(self) -> QFrame:
        separator = QFrame(self)
        separator.setProperty("separator", True)
        separator.setFixedSize(1, 22)
        return separator

    def _request_font_size(self, point_size: float) -> None:
        self.size_button.setText(f"{point_size:g}")
        self.font_size_changed.emit(point_size)

    def set_format_state(self, state: dict[str, object]) -> None:
        alignment = str(state.get("alignment", "left"))
        for name, button in self.alignment_buttons.items():
            blocker = QSignalBlocker(button)
            button.setChecked(name == alignment)
            del blocker

        point_size = float(state.get("font_size", 16.0))
        self.size_button.setText(f"{point_size:g}")

        color = state.get("color")
        if isinstance(color, QColor) and color.isValid():
            self.set_text_color(color)

        background_color = state.get("background_color")
        if isinstance(background_color, QColor) and background_color.isValid():
            self.set_background_color(background_color)

        toggle_states = (
            (self.bold_button, bool(state.get("bold", False))),
            (self.italic_button, bool(state.get("italic", False))),
            (self.underline_button, bool(state.get("underline", False))),
        )
        for button, checked in toggle_states:
            blocker = QSignalBlocker(button)
            button.setChecked(checked)
            del blocker

    def set_text_color(self, color: QColor) -> None:
        self.color_button.setIcon(self._text_color_icon(color))
        self.color_button.setIconSize(QSize(22, 22))

    def set_background_color(self, color: QColor) -> None:
        self.background_color_button.setIcon(self._background_color_icon(color))
        self.background_color_button.setIconSize(QSize(22, 22))
        self.background_color_button.setToolTip(
            f"Note background color ({color.alpha()} / 255 opacity)"
        )

    @staticmethod
    def _text_color_icon(color: QColor) -> QIcon:
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(11)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(pixmap.rect().adjusted(0, -2, 0, -2), Qt.AlignCenter, "A")
        painter.fillRect(3, 18, 16, 3, color)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _background_color_icon(color: QColor) -> QIcon:
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        cell = 4
        for y in range(3, 19, cell):
            for x in range(3, 19, cell):
                checker = QColor("#D9DEE3") if (x // cell + y // cell) % 2 else QColor("#FFFFFF")
                painter.fillRect(x, y, cell, cell, checker)
        painter.fillRect(3, 3, 16, 16, color)
        painter.setPen(QPen(QColor(COLORS["text_muted"]), 1))
        painter.drawRect(3, 3, 16, 16)
        painter.end()
        return QIcon(pixmap)


class GifControlBar(QFrame):
    playback_toggled = Signal()
    playback_rate_changed = Signal(float)
    previous_frame_requested = Signal()
    next_frame_requested = Signal()
    frames_toggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._playback_rate = 1.0
        self.setObjectName("GifFloatingControls")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"""
            QFrame#GifFloatingControls {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
            """
        )
        controls_layout = QHBoxLayout(self)
        controls_layout.setContentsMargins(6, 5, 6, 5)
        controls_layout.setSpacing(6)

        self.previous_button = QPushButton()
        self.previous_button.setIcon(
            self.style().standardIcon(QStyle.SP_MediaSkipBackward)
        )
        self.previous_button.setToolTip("Previous frame (Left Arrow)")
        self.previous_button.setAccessibleName("Previous frame")
        self.previous_button.setFixedSize(38, 34)
        self.previous_button.clicked.connect(self.previous_frame_requested)
        controls_layout.addWidget(self.previous_button)

        self.play_button = QPushButton()
        self.play_button.setIcon(
            self.style().standardIcon(QStyle.SP_MediaPlay)
        )
        self.play_button.setToolTip("Play or pause selected GIF (Space)")
        self.play_button.setAccessibleName("Play selected GIF")
        self.play_button.setFixedSize(38, 34)
        self.play_button.clicked.connect(self.playback_toggled)
        controls_layout.addWidget(self.play_button)

        self.next_button = QPushButton()
        self.next_button.setIcon(
            self.style().standardIcon(QStyle.SP_MediaSkipForward)
        )
        self.next_button.setToolTip("Next frame (Right Arrow)")
        self.next_button.setAccessibleName("Next frame")
        self.next_button.setFixedSize(38, 34)
        self.next_button.clicked.connect(self.next_frame_requested)
        controls_layout.addWidget(self.next_button)

        self.speed_button = QPushButton("1×")
        self.speed_button.setToolTip("GIF playback speed")
        self.speed_button.setAccessibleName("GIF playback speed")
        self.speed_button.setMinimumWidth(68)
        self.speed_button.setFixedHeight(34)
        self.speed_menu = QMenu(self.speed_button)
        self.speed_action_group = QActionGroup(self.speed_menu)
        self.speed_action_group.setExclusive(True)
        self.speed_actions: dict[float, QAction] = {}
        for rate in (0.25, 0.5, 1.0, 2.0, 4.0):
            action = self.speed_menu.addAction(f"{rate:g}×")
            action.setCheckable(True)
            action.setData(rate)
            action.triggered.connect(
                lambda checked=False, value=rate: self._request_playback_rate(value)
            )
            self.speed_action_group.addAction(action)
            self.speed_actions[rate] = action
        self.speed_button.setMenu(self.speed_menu)
        controls_layout.addWidget(self.speed_button)

        self.frame_count_button = QPushButton("1 / 1")
        self.frame_count_button.setCheckable(True)
        self.frame_count_button.setToolTip("Show all GIF frames")
        self.frame_count_button.setAccessibleName("Show GIF frames")
        self.frame_count_button.setMinimumWidth(92)
        self.frame_count_button.setFixedHeight(34)
        self.frame_count_button.clicked.connect(self.frames_toggled)
        controls_layout.addWidget(self.frame_count_button)

        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def set_frame(self, frame_number: int, frame_count: int) -> None:
        frame_count = max(1, frame_count)
        current = max(0, min(frame_number, frame_count - 1))
        self.frame_count_button.setText(f"{current + 1} / {frame_count}")

    def set_playing(self, playing: bool) -> None:
        icon = QStyle.SP_MediaPause if playing else QStyle.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))
        self.play_button.setAccessibleName(
            "Pause selected GIF" if playing else "Play selected GIF"
        )

    def set_playback_rate(self, rate: float) -> None:
        self._playback_rate = rate
        self.speed_button.setText(f"{rate:g}×")
        self.speed_button.setToolTip(f"GIF playback speed: {rate:g}×")
        action = self.speed_actions.get(rate)
        if action is not None:
            action.setChecked(True)

    def set_frames_expanded(self, expanded: bool) -> None:
        self.frame_count_button.setChecked(expanded)
        self.frame_count_button.setToolTip(
            "Hide GIF frames" if expanded else "Show all GIF frames"
        )

    def _request_playback_rate(self, rate: float) -> None:
        self.set_playback_rate(rate)
        self.playback_rate_changed.emit(rate)


class TimelinePanel(QWidget):
    frame_selected = Signal(int)
    frames_drag_started = Signal(object)
    frames_reordered = Signal(object)
    expanded_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._asset: Optional[AssetModel] = None
        self._path: Optional[Path] = None
        self._current_frame = 0
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.frame_strip = FrameStrip()
        self.frame_strip.frame_selected.connect(self.frame_selected)
        self.frame_strip.frames_drag_started.connect(self.frames_drag_started)
        self.frame_strip.frames_reordered.connect(self.frames_reordered)
        self.frame_strip.setVisible(False)
        outer.addWidget(self.frame_strip, 1)

    def set_composition(self, composition: CompositionModel) -> None:
        del composition

    def show_frames(
        self,
        asset: AssetModel,
        path: Path,
        current_frame: int = 0,
        expanded: bool = False,
    ) -> None:
        self._asset = asset
        self._path = path
        self._current_frame = current_frame
        self.set_expanded(expanded)
        self.set_frame(current_frame)

    def set_frame(self, frame_number: int) -> None:
        if self._asset is None:
            return
        self._current_frame = max(0, min(frame_number, self._asset.frame_count - 1))
        if self.frame_strip.asset_id == self._asset.id:
            self.frame_strip.set_current_frame(self._current_frame)

    def selected_frame_indices(self) -> list[int]:
        return self.frame_strip.selected_indices()

    def frames_have_focus(self) -> bool:
        return self.frame_strip.has_focus()

    def set_expanded(self, expanded: bool) -> None:
        if self._asset is None or self._path is None:
            expanded = False
        if expanded and self.frame_strip.asset_id != self._asset.id:
            self.frame_strip.summary.setText(
                f"Loading {self._asset.name} frames..."
            )
            asset_id = self._asset.id
            QTimer.singleShot(
                50,
                lambda selected_asset_id=asset_id: self._load_frames(
                    selected_asset_id
                ),
            )
        self._expanded = expanded
        self.frame_strip.setVisible(expanded)
        self.expanded_changed.emit(expanded)

    def _load_frames(self, asset_id: str) -> None:
        if (
            not self._expanded
            or self._asset is None
            or self._path is None
            or self._asset.id != asset_id
            or self.frame_strip.asset_id == asset_id
        ):
            return
        self.frame_strip.show_asset(
            self._asset,
            self._path,
            self._current_frame,
        )
