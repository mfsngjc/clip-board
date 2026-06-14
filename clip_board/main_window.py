from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, QStandardPaths, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QImage,
    QKeySequence,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .canvas import BoardScene, CanvasView
from .constants import (
    APP_NAME,
    FRAME_MIME_TYPE,
    PROJECT_SUFFIX,
    SUPPORTED_IMAGE_SUFFIXES,
)
from .media import AnimationFrame, AssetLibrary, read_animation_frames
from .models import BoardItemModel, ClipModel, ProjectModel, new_id
from .panels import AssetPanel, GifControlBar, NoteTextToolbar, TimelinePanel
from .project_store import ProjectStore
from .scene_items import MediaItem, NoteItem
from .theme import APP_STYLESHEET, COLORS


class AddBoardItemCommand(QUndoCommand):
    def __init__(self, window: "MainWindow", model: BoardItemModel, label: str) -> None:
        super().__init__(label)
        self.window = window
        self.model = model

    def redo(self) -> None:
        self.window.insert_board_item(self.model)

    def undo(self) -> None:
        self.window.remove_board_item(self.model.id)


class DeleteBoardItemsCommand(QUndoCommand):
    def __init__(self, window: "MainWindow", models: list[BoardItemModel]) -> None:
        super().__init__("Delete selection")
        self.window = window
        self.models = models

    def redo(self) -> None:
        for model in self.models:
            self.window.remove_board_item(model.id)

    def undo(self) -> None:
        for model in self.models:
            self.window.insert_board_item(model)


class ReplaceMediaAssetCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        item_id: str,
        old_asset_id: str,
        new_asset_id: str,
        old_frame: int,
        new_frame: int,
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.item_id = item_id
        self.old_asset_id = old_asset_id
        self.new_asset_id = new_asset_id
        self.old_frame = old_frame
        self.new_frame = new_frame

    def redo(self) -> None:
        self.window._apply_media_asset(
            self.item_id,
            self.new_asset_id,
            self.new_frame,
        )

    def undo(self) -> None:
        self.window._apply_media_asset(
            self.item_id,
            self.old_asset_id,
            self.old_frame,
        )


class MainWindow(QMainWindow):
    def __init__(self, initial_project: Optional[Path] = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)
        self.setMinimumSize(900, 620)
        self.setStyleSheet(APP_STYLESHEET)
        self.setDockNestingEnabled(True)

        data_root = Path(
            QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        )
        self.store = ProjectStore(data_root)
        self.asset_library = AssetLibrary(self.store.workspace.assets_dir)
        self.project = ProjectModel.create()
        self.project_path: Optional[Path] = None
        self.scene_items: dict[str, object] = {}
        self._copied_frames: list[AnimationFrame] = []
        self._editing_note_id: Optional[str] = None
        self.dirty = False
        self._closing = False

        self.scene = BoardScene()
        self.canvas = CanvasView(self.scene)
        self.undo_stack = QUndoStack(self)

        self.asset_panel = AssetPanel()
        self.timeline_panel = TimelinePanel()
        self.gif_controls = GifControlBar(self.canvas.viewport())
        self.gif_controls.hide()
        self.note_controls = NoteTextToolbar(self.canvas.viewport())
        self.note_controls.hide()
        self._build_workspace()
        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._connect_signals()

        self.playing = False

        self._frame_step_direction = 0
        self.frame_repeat_delay_timer = QTimer(self)
        self.frame_repeat_delay_timer.setSingleShot(True)
        self.frame_repeat_delay_timer.setInterval(260)
        self.frame_repeat_delay_timer.timeout.connect(self.frame_repeat_timer_start)
        self.frame_repeat_timer = QTimer(self)
        self.frame_repeat_timer.setInterval(70)
        self.frame_repeat_timer.timeout.connect(self._repeat_frame_step)

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()

        self.statusBar().showMessage("Ready")

        if initial_project:
            self.load_project(initial_project)
        else:
            restored = self.store.restore_autosave()
            if restored:
                self._adopt_project(restored)
                self.statusBar().showMessage("Restored autosaved board", 4000)
            else:
                self._adopt_project(self.project)

    def _build_workspace(self) -> None:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.canvas, 1)

        self.timeline_panel.setObjectName("GifFrames")
        self.timeline_panel.setFixedHeight(196)
        self.timeline_panel.hide()
        layout.addWidget(self.timeline_panel)
        self.timeline_dock = self.timeline_panel
        self.setCentralWidget(workspace)

    def _build_docks(self) -> None:
        assets_dock = QDockWidget("Assets", self)
        assets_dock.setObjectName("AssetsDock")
        assets_dock.setWidget(self.asset_panel)
        assets_dock.setMinimumWidth(240)
        self.addDockWidget(Qt.LeftDockWidgetArea, assets_dock)

    def _make_action(
        self,
        text: str,
        callback,
        shortcut=None,
        standard_icon: Optional[QStyle.StandardPixmap] = None,
        tooltip: Optional[str] = None,
    ) -> QAction:
        action = QAction(text, self)
        if standard_icon is not None:
            action.setIcon(self.style().standardIcon(standard_icon))
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.setToolTip(tooltip or text)
        action.setStatusTip(tooltip or text)
        action.triggered.connect(callback)
        return action

    def _build_actions(self) -> None:
        self.new_action = self._make_action(
            "New",
            self.new_project,
            QKeySequence.New,
            QStyle.SP_FileIcon,
            "Create a new board",
        )
        self.open_action = self._make_action(
            "Open Project",
            self.choose_project,
            QKeySequence.Open,
            QStyle.SP_DialogOpenButton,
            "Open a .clipboard project",
        )
        self.import_action = self._make_action(
            "Import Media",
            self.choose_media,
            "Ctrl+I",
            QStyle.SP_DialogOpenButton,
            "Import images or GIFs",
        )
        self.save_action = self._make_action(
            "Save",
            self.save_project,
            QKeySequence.Save,
            QStyle.SP_DialogSaveButton,
            "Save the current project",
        )
        self.save_as_action = self._make_action(
            "Save As",
            self.save_project_as,
            QKeySequence.SaveAs,
            QStyle.SP_DialogSaveButton,
            "Save a portable copy",
        )
        self.quit_action = self._make_action("Quit", self.close, QKeySequence.Quit)

        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.delete_action = self._make_action(
            "Delete",
            self.delete_selection,
            None,
            QStyle.SP_TrashIcon,
            "Delete selected frames or board objects (Backspace)",
        )
        self.delete_action.setShortcuts(
            [QKeySequence("Backspace"), QKeySequence.Delete]
        )
        self.note_action = self._make_action(
            "Add Note",
            self.add_note_at_center,
            None,
            QStyle.SP_FileDialogDetailedView,
            "Add a text note (N)",
        )
        self.copy_action = self._make_action(
            "Copy",
            self.copy_selection,
            QKeySequence.Copy,
            QStyle.SP_DialogSaveButton,
            "Copy selected GIF frames",
        )
        self.paste_action = self._make_action(
            "Paste",
            self.paste_from_clipboard,
            QKeySequence.Paste,
            QStyle.SP_DialogOpenButton,
            "Paste image files or a clipboard image",
        )

        self.play_action = self._make_action(
            "Play / Pause",
            self.toggle_playback,
            None,
            QStyle.SP_MediaPlay,
            "Play or pause animation (Space)",
        )
        self.previous_frame_action = self._make_action(
            "Previous Frame", lambda: self.step_selected(-1), None, QStyle.SP_MediaSkipBackward
        )
        self.next_frame_action = self._make_action(
            "Next Frame", lambda: self.step_selected(1), None, QStyle.SP_MediaSkipForward
        )
        self.fit_action = self._make_action(
            "Fit Board",
            self.canvas.fit_items,
            None,
            QStyle.SP_DesktopIcon,
            "Fit all board objects in view (F)",
        )
        self.reset_view_action = self._make_action(
            "Reset View",
            self.canvas.reset_view,
            "Ctrl+0",
            QStyle.SP_BrowserReload,
            "Reset zoom and center",
        )
        self.zoom_in_action = self._make_action(
            "Zoom In",
            self.canvas.zoom_in,
            QKeySequence.ZoomIn,
            None,
            "Zoom in around the center",
        )
        self.zoom_out_action = self._make_action(
            "Zoom Out",
            self.canvas.zoom_out,
            QKeySequence.ZoomOut,
            None,
            "Zoom out around the center",
        )

        self.speed_actions = []
        for rate in (0.25, 0.5, 1.0, 2.0, 4.0):
            action = self._make_action(
                f"{rate:g}x",
                lambda checked=False, value=rate: self.set_selected_speed(value),
                None,
            )
            self.speed_actions.append(action)

        for action in (
            self.paste_action,
            self.reset_view_action,
            self.zoom_in_action,
            self.zoom_out_action,
        ):
            self.addAction(action)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions(
            [
                self.new_action,
                self.open_action,
                self.import_action,
                self.save_action,
                self.save_as_action,
            ]
        )
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions(
            [
                self.undo_action,
                self.redo_action,
                self.copy_action,
                self.paste_action,
                self.delete_action,
                self.note_action,
            ]
        )

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addActions(
            [
                self.zoom_in_action,
                self.zoom_out_action,
                self.fit_action,
                self.reset_view_action,
            ]
        )

        playback_menu = self.menuBar().addMenu("&Playback")
        playback_menu.addActions(
            [self.play_action, self.previous_frame_action, self.next_frame_action]
        )
        speed_menu = playback_menu.addMenu("Speed")
        speed_menu.addActions(self.speed_actions)

    def _connect_signals(self) -> None:
        self.canvas.files_dropped.connect(self.import_files)
        self.canvas.frames_dropped.connect(self.drop_copied_frames)
        self.canvas.zoom_changed.connect(self._zoom_changed)
        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._show_canvas_menu)
        self.scene.selectionChanged.connect(self._selection_changed)
        self.asset_panel.asset_activated.connect(self.add_asset_to_board)
        self.note_controls.alignment_changed.connect(
            self._set_note_alignment
        )
        self.note_controls.font_size_changed.connect(
            self._set_note_font_size
        )
        self.note_controls.color_requested.connect(
            self._choose_note_text_color
        )
        self.note_controls.background_color_requested.connect(
            self._choose_note_background_color
        )
        self.note_controls.bold_toggled.connect(self._set_note_bold)
        self.note_controls.italic_toggled.connect(self._set_note_italic)
        self.note_controls.underline_toggled.connect(
            self._set_note_underline
        )
        self.gif_controls.playback_toggled.connect(self.toggle_playback)
        self.gif_controls.playback_rate_changed.connect(
            self.set_selected_speed
        )
        self.gif_controls.previous_frame_requested.connect(
            lambda: self.step_selected(-1)
        )
        self.gif_controls.next_frame_requested.connect(
            lambda: self.step_selected(1)
        )
        self.gif_controls.frames_toggled.connect(
            self.timeline_panel.set_expanded
        )
        self.timeline_panel.frame_selected.connect(self.select_gif_frame)
        self.timeline_panel.frames_drag_started.connect(self.prepare_frame_drag)
        self.timeline_panel.frames_reordered.connect(
            self.reorder_selected_gif_frames
        )
        self.timeline_panel.expanded_changed.connect(self._set_frame_panel_expanded)
        self.canvas.horizontalScrollBar().valueChanged.connect(
            self._position_gif_controls
        )
        self.canvas.horizontalScrollBar().valueChanged.connect(
            self._position_note_controls
        )
        self.canvas.verticalScrollBar().valueChanged.connect(
            self._position_gif_controls
        )
        self.canvas.verticalScrollBar().valueChanged.connect(
            self._position_note_controls
        )
        self.canvas.zoom_changed.connect(self._position_gif_controls)
        self.canvas.zoom_changed.connect(self._position_note_controls)

    def new_project(self) -> None:
        self.sync_project_from_scene()
        self.autosave()
        self.store.workspace.reset()
        self.asset_library = AssetLibrary(self.store.workspace.assets_dir)
        self.project_path = None
        self.undo_stack.clear()
        self._adopt_project(ProjectModel.create())
        self.mark_dirty()
        self.statusBar().showMessage("New board created", 3000)

    def choose_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Clip Board Project",
            "",
            f"Clip Board Project (*{PROJECT_SUFFIX})",
        )
        if filename:
            self.load_project(Path(filename))

    def load_project(self, path: Path) -> None:
        try:
            project = self.store.load(path)
        except Exception as exc:
            self._show_error("Could not open project", str(exc))
            return
        self.project_path = path.resolve()
        self.asset_library = AssetLibrary(self.store.workspace.assets_dir)
        self.undo_stack.clear()
        self._adopt_project(project)
        self.dirty = False
        self.statusBar().showMessage(f"Opened {path.name}", 4000)

    def save_project(self) -> bool:
        if self.project_path is None:
            return self.save_project_as()
        return self._save_to(self.project_path)

    def save_project_as(self) -> bool:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Clip Board Project",
            f"{self.project.name}{PROJECT_SUFFIX}",
            f"Clip Board Project (*{PROJECT_SUFFIX})",
        )
        if not filename:
            return False
        destination = Path(filename)
        if destination.suffix.lower() != PROJECT_SUFFIX:
            destination = destination.with_suffix(PROJECT_SUFFIX)
        return self._save_to(destination)

    def _save_to(self, destination: Path) -> bool:
        destination = destination.expanduser().resolve()
        self.sync_project_from_scene()
        try:
            self.store.save(self.project, destination)
        except Exception as exc:
            self._show_error("Could not save project", str(exc))
            return False
        self.project_path = destination
        self.dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Saved {destination.name}", 4000)
        return True

    def autosave(self) -> None:
        if not self.dirty:
            return
        self.sync_project_from_scene()
        try:
            self.store.autosave(self.project)
        except OSError:
            return
        self.statusBar().showMessage("Autosaved", 1500)

    def choose_media(self) -> None:
        patterns = " ".join(f"*{suffix}" for suffix in sorted(SUPPORTED_IMAGE_SUFFIXES))
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Media",
            "",
            f"Images and GIFs ({patterns})",
        )
        if filenames:
            self.import_files(filenames, self.canvas.mapToScene(self.canvas.viewport().rect().center()))

    def import_files(self, filenames: Iterable[str], scene_position: QPointF) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        errors = []
        imported = 0
        try:
            for index, filename in enumerate(filenames):
                try:
                    imported_asset = self.asset_library.import_file(Path(filename))
                    asset = self._register_asset(imported_asset)
                    position = scene_position + QPointF((index % 4) * 36, (index // 4) * 36)
                    model = self._media_model(asset.id, position)
                    self.undo_stack.push(AddBoardItemCommand(self, model, "Import media"))
                    imported += 1
                except Exception as exc:
                    errors.append(f"{Path(filename).name}: {exc}")
        finally:
            QApplication.restoreOverrideCursor()

        if imported:
            self.statusBar().showMessage(
                f"Imported {imported} asset{'s' if imported != 1 else ''}", 3500
            )
        if errors:
            self._show_error("Some files could not be imported", "\n".join(errors))

    def _register_asset(self, asset):  # type: ignore[no-untyped-def]
        existing = next(
            (
                candidate
                for candidate in self.project.assets
                if candidate.sha256 == asset.sha256
            ),
            None,
        )
        if existing is not None:
            return existing
        self.project.assets.append(asset)
        self.asset_panel.add_asset(
            asset,
            self.store.workspace.asset_path(asset.relative_path),
        )
        return asset

    def _create_derived_gif(
        self,
        frames: Iterable[AnimationFrame],
        name: str,
        target_size: Optional[tuple[int, int]] = None,
    ):  # type: ignore[no-untyped-def]
        asset = self.asset_library.create_gif(frames, name, target_size)
        return self._register_asset(asset)

    def _media_model(self, asset_id: str, position: QPointF) -> BoardItemModel:
        asset = self.project.asset_by_id(asset_id)
        if asset is None:
            raise ValueError("Unknown asset")
        width = float(asset.width or 320)
        height = float(asset.height or 180)
        factor = min(480 / width, 360 / height, 1.0)
        return BoardItemModel(
            id=new_id("item"),
            kind="media",
            asset_id=asset.id,
            x=position.x(),
            y=position.y(),
            width=max(80.0, width * factor),
            height=max(60.0, height * factor),
            z=float(len(self.project.board.items)),
        )

    def add_asset_to_board(self, asset_id: str) -> None:
        center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        self.undo_stack.push(
            AddBoardItemCommand(
                self,
                self._media_model(asset_id, center),
                "Add asset to board",
            )
        )

    def add_note_at_center(self) -> None:
        self.add_note(self.canvas.mapToScene(self.canvas.viewport().rect().center()))

    def add_note(self, scene_position: QPointF) -> None:
        model = BoardItemModel(
            id=new_id("note"),
            kind="note",
            x=scene_position.x(),
            y=scene_position.y(),
            width=280,
            height=120,
            z=float(len(self.project.board.items)),
            text="New note",
        )
        self.undo_stack.push(AddBoardItemCommand(self, model, "Add note"))
        item = self.scene_items.get(model.id)
        if isinstance(item, NoteItem):
            self.scene.clearSelection()
            item.setSelected(True)
            item.start_editing(select_all=True)

    def insert_board_item(self, model: BoardItemModel) -> None:
        if self.project.board_item_by_id(model.id) is None:
            self.project.board.items.append(model)
        if model.id in self.scene_items:
            return

        if model.kind == "media":
            asset = self.project.asset_by_id(model.asset_id)
            if asset is None:
                return
            item = MediaItem(
                model,
                asset,
                self.store.workspace.asset_path(asset.relative_path),
                self.mark_dirty,
            )
            item.frame_changed.connect(
                lambda frame, item_id=model.id: self._media_frame_changed(
                    item_id, frame
                )
            )
            item.geometry_changed.connect(self._position_gif_controls)
        elif model.kind == "note":
            item = NoteItem(model, self.mark_dirty)
            item.geometry_changed.connect(self._position_gif_controls)
            item.geometry_changed.connect(self._position_note_controls)
            item.editing_started.connect(
                lambda item_id=model.id: self._note_editing_started(item_id)
            )
            item.editing_finished.connect(
                lambda item_id=model.id: self._note_editing_finished(item_id)
            )
            item.cursor_format_changed.connect(
                lambda item_id=model.id: self._note_cursor_format_changed(item_id)
            )
        else:
            return
        self.scene.addItem(item)
        self.scene_items[model.id] = item
        self.mark_dirty()

    def remove_board_item(self, item_id: str) -> None:
        model = self.project.board_item_by_id(item_id)
        if model:
            self.project.board.items.remove(model)
        item = self.scene_items.pop(item_id, None)
        if item is not None:
            if item_id == self._editing_note_id:
                self._editing_note_id = None
                self.note_controls.hide()
            self.scene.removeItem(item)
        self.mark_dirty()

    def _apply_media_asset(
        self,
        item_id: str,
        asset_id: str,
        frame_number: int,
    ) -> None:
        model = self.project.board_item_by_id(item_id)
        asset = self.project.asset_by_id(asset_id)
        if model is None or asset is None:
            return
        frames_were_visible = self.timeline_panel.frame_strip.isVisible()

        previous = self.scene_items.pop(item_id, None)
        if isinstance(previous, MediaItem):
            previous.pause()
            model.x = previous.pos().x()
            model.y = previous.pos().y()
            model.scale = previous.scale()
            model.rotation = previous.rotation()
            model.z = previous.zValue()
            previous.dispose()
            self.scene.removeItem(previous)
            previous.deleteLater()

        model.asset_id = asset.id
        self.insert_board_item(model)
        replacement = self.scene_items.get(item_id)
        if isinstance(replacement, MediaItem):
            self.scene.clearSelection()
            replacement.setSelected(True)
            replacement.jump_to_frame(frame_number)
            if replacement.is_animated and frames_were_visible:
                self.timeline_panel.set_expanded(True)
        self.mark_dirty()

    def delete_selection(self) -> None:
        if self._delete_selected_frames():
            return
        selected_ids = [
            str(item.data(0))
            for item in self.scene.selectedItems()
            if item.data(0)
        ]
        models = [
            model
            for item_id in selected_ids
            if (model := self.project.board_item_by_id(item_id)) is not None
        ]
        if models:
            self.undo_stack.push(DeleteBoardItemsCommand(self, models))

    def copy_selection(self) -> None:
        item = self.selected_media_item()
        if (
            item is None
            or not item.is_animated
            or not self.timeline_panel.frame_strip.isVisible()
        ):
            self.statusBar().showMessage("Select one or more GIF frames first", 2500)
            return

        indices = self.timeline_panel.selected_frame_indices()
        if not indices:
            indices = [item.current_frame()]
        try:
            frames = read_animation_frames(item.source_path, indices)
        except Exception as exc:
            self._show_error("Could not copy frames", str(exc))
            return

        self._copied_frames = [
            AnimationFrame(frame.image.copy(), frame.duration_ms) for frame in frames
        ]
        encoded = io.BytesIO()
        self._copied_frames[0].image.save(encoded, format="PNG")
        mime = QMimeData()
        mime.setData(FRAME_MIME_TYPE, str(len(frames)).encode("ascii"))
        mime.setImageData(QImage.fromData(encoded.getvalue(), "PNG"))
        QApplication.clipboard().setMimeData(mime)
        self.statusBar().showMessage(
            f"Copied {len(frames)} frame{'s' if len(frames) != 1 else ''}",
            2500,
        )

    def prepare_frame_drag(self, indices: object) -> None:
        item = self.selected_media_item()
        if item is None or not item.is_animated:
            self._copied_frames = []
            return
        try:
            frames = read_animation_frames(
                item.source_path,
                [int(index) for index in indices],  # type: ignore[arg-type]
            )
        except Exception:
            self._copied_frames = []
            return
        self._copied_frames = [
            AnimationFrame(frame.image.copy(), frame.duration_ms) for frame in frames
        ]

    def drop_copied_frames(self, scene_position: QPointF) -> None:
        if not self._copied_frames:
            return
        target = next(
            (
                candidate
                for candidate in self.scene.items(scene_position)
                if isinstance(candidate, MediaItem) and candidate.is_animated
            ),
            None,
        )
        self._paste_copied_frames(scene_position, target)

    def paste_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime.hasFormat(FRAME_MIME_TYPE) and self._copied_frames:
            self._paste_copied_frames()
            return
        urls = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
        if urls:
            self.import_files(
                urls,
                self.canvas.mapToScene(self.canvas.viewport().rect().center()),
            )
            return
        image = clipboard.image()
        if image.isNull():
            self.statusBar().showMessage("Clipboard does not contain an image", 3000)
            return
        paste_dir = self.store.data_root / "paste"
        paste_dir.mkdir(parents=True, exist_ok=True)
        handle, filename = tempfile.mkstemp(suffix=".png", dir=str(paste_dir))
        os.close(handle)
        Path(filename).unlink(missing_ok=True)
        image.save(filename, "PNG")
        self.import_files(
            [filename],
            self.canvas.mapToScene(self.canvas.viewport().rect().center()),
        )
        try:
            Path(filename).unlink()
        except OSError:
            pass

    def _paste_copied_frames(
        self,
        scene_position: Optional[QPointF] = None,
        target: Optional[MediaItem] = None,
    ) -> None:
        if target is None and scene_position is None:
            target = self.selected_media_item()
        if target is not None and target.is_animated:
            try:
                existing = read_animation_frames(target.source_path)
                insertion = target.current_frame() + 1
                combined = (
                    existing[:insertion]
                    + [
                        AnimationFrame(frame.image.copy(), frame.duration_ms)
                        for frame in self._copied_frames
                    ]
                    + existing[insertion:]
                )
                asset = self._create_derived_gif(
                    combined,
                    f"{Path(target.asset.name).stem} edited.gif",
                    (target.asset.width, target.asset.height),
                )
            except Exception as exc:
                self._show_error("Could not insert frames", str(exc))
                return
            self.undo_stack.push(
                ReplaceMediaAssetCommand(
                    self,
                    target.model_id,
                    target.asset_id,
                    asset.id,
                    target.current_frame(),
                    insertion,
                    "Insert GIF frames",
                )
            )
            self.statusBar().showMessage(
                f"Inserted {len(self._copied_frames)} frame"
                f"{'s' if len(self._copied_frames) != 1 else ''}",
                3000,
            )
            return

        try:
            asset = self._create_derived_gif(
                [
                    AnimationFrame(frame.image.copy(), frame.duration_ms)
                    for frame in self._copied_frames
                ],
                "Frame selection.gif",
            )
        except Exception as exc:
            self._show_error("Could not create GIF", str(exc))
            return
        position = scene_position or self.canvas.mapToScene(
            self.canvas.viewport().rect().center()
        )
        model = self._media_model(asset.id, position)
        self.undo_stack.push(AddBoardItemCommand(self, model, "Paste frames as GIF"))
        pasted = self.scene_items.get(model.id)
        if isinstance(pasted, MediaItem):
            self.scene.clearSelection()
            pasted.setSelected(True)
        self.statusBar().showMessage(
            f"Created GIF from {len(self._copied_frames)} frame"
            f"{'s' if len(self._copied_frames) != 1 else ''}",
            3000,
        )

    def _delete_selected_frames(self) -> bool:
        if (
            not self.timeline_panel.frame_strip.isVisible()
            or not self.timeline_panel.frames_have_focus()
        ):
            return False
        item = self.selected_media_item()
        if item is None or not item.is_animated:
            return False

        selected = set(self.timeline_panel.selected_frame_indices())
        if not selected:
            selected = {item.current_frame()}
        if len(selected) >= item.asset.frame_count:
            self.statusBar().showMessage(
                "A GIF must keep at least one frame",
                3000,
            )
            return True

        remaining = [
            index
            for index in range(item.asset.frame_count)
            if index not in selected
        ]
        old_frame = item.current_frame()
        new_frame = min(
            max(0, old_frame - sum(index < old_frame for index in selected)),
            len(remaining) - 1,
        )
        try:
            frames = read_animation_frames(item.source_path, remaining)
            asset = self._create_derived_gif(
                frames,
                f"{Path(item.asset.name).stem} edited.gif",
                (item.asset.width, item.asset.height),
            )
        except Exception as exc:
            self._show_error("Could not delete frames", str(exc))
            return True

        self.undo_stack.push(
            ReplaceMediaAssetCommand(
                self,
                item.model_id,
                item.asset_id,
                asset.id,
                old_frame,
                new_frame,
                "Delete GIF frames",
            )
        )
        self.statusBar().showMessage(
            f"Deleted {len(selected)} frame"
            f"{'s' if len(selected) != 1 else ''}",
            2500,
        )
        return True

    def reorder_selected_gif_frames(self, order: object) -> None:
        item = self.selected_media_item()
        if item is None or not item.is_animated:
            return
        frame_order = [int(index) for index in order]  # type: ignore[arg-type]
        if frame_order == list(range(item.asset.frame_count)):
            return
        if sorted(frame_order) != list(range(item.asset.frame_count)):
            self.statusBar().showMessage("Could not reorder these frames", 2500)
            return

        old_frame = item.current_frame()
        new_frame = frame_order.index(old_frame)
        try:
            frames = read_animation_frames(item.source_path, frame_order)
            asset = self._create_derived_gif(
                frames,
                f"{Path(item.asset.name).stem} reordered.gif",
                (item.asset.width, item.asset.height),
            )
        except Exception as exc:
            self._show_error("Could not reorder frames", str(exc))
            return
        self.undo_stack.push(
            ReplaceMediaAssetCommand(
                self,
                item.model_id,
                item.asset_id,
                asset.id,
                old_frame,
                new_frame,
                "Reorder GIF frames",
            )
        )
        self.statusBar().showMessage("Reordered GIF frames", 2500)

    def add_selected_to_timeline(self) -> None:
        asset_id = None
        selected = self.scene.selectedItems()
        if selected and isinstance(selected[0], MediaItem):
            asset_id = selected[0].asset_id
        if asset_id is None:
            asset_id = self.asset_panel.selected_asset_id()
        asset = self.project.asset_by_id(asset_id)
        if asset is None:
            self.statusBar().showMessage("Select a media item or asset first", 3000)
            return

        composition = self.project.active_composition()
        if not composition.tracks:
            return
        track = composition.tracks[0]
        next_start = max(
            (
                clip.timeline_start_ms + clip.duration_ms
                for clip in track.clips
            ),
            default=0,
        )
        duration = max(1, asset.duration_ms or 3000)
        clip = ClipModel(
            id=new_id("clip"),
            asset_id=asset.id,
            name=asset.name,
            timeline_start_ms=next_start,
            source_out_ms=duration,
            loop=asset.frame_count > 1,
        )
        track.clips.append(clip)
        composition.duration_ms = max(
            composition.duration_ms,
            clip.timeline_start_ms + clip.duration_ms + 1000,
        )
        self.timeline_panel.set_composition(composition)
        self.mark_dirty()
        self.statusBar().showMessage(f"Added {asset.name} to timeline", 3000)

    def toggle_playback(self) -> None:
        selected = self.selected_media_item()
        if selected is None or not selected.is_animated:
            return
        self.playing = not selected.is_playing
        if self.playing:
            selected.play()
        else:
            selected.pause()
        self._sync_playback_controls()

    def selected_media_item(self) -> Optional[MediaItem]:
        selected = self.scene.selectedItems()
        if selected and isinstance(selected[0], MediaItem):
            return selected[0]
        return None

    def step_selected(self, delta: int) -> None:
        item = self.selected_media_item()
        if item and item.is_animated:
            item.step_frame(delta)
            self.playing = False
            self._sync_playback_controls()

    def select_gif_frame(self, frame_number: int) -> None:
        item = self.selected_media_item()
        if item is None or not item.is_animated:
            return
        item.jump_to_frame(frame_number)
        self.playing = False
        self._sync_playback_controls()

    def set_selected_speed(self, rate: float) -> None:
        item = self.selected_media_item()
        if item:
            item.set_playback_rate(rate)
            model = self.project.board_item_by_id(item.model_id)
            if model is not None:
                model.playback_rate = item.playback_rate
            self.gif_controls.set_playback_rate(item.playback_rate)
            self.mark_dirty()
            self.statusBar().showMessage(f"Playback speed {rate:g}x", 2000)

    def sync_project_from_scene(self) -> None:
        for model in self.project.board.items:
            item = self.scene_items.get(model.id)
            if item is None:
                continue
            model.x = item.pos().x()
            model.y = item.pos().y()
            model.scale = item.scale()
            model.rotation = item.rotation()
            model.z = item.zValue()
            if isinstance(item, NoteItem):
                model.text = item.toPlainText()
                model.rich_text = item.toHtml()
                model.width = item.textWidth()
                model.font_size = item.document().defaultFont().pointSize()
                model.background_color = item.background_color.name(
                    QColor.HexArgb
                )

        center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        self.project.board.view_center_x = center.x()
        self.project.board.view_center_y = center.y()
        self.project.board.view_scale = self.canvas.zoom_level

    def _adopt_project(self, project: ProjectModel) -> None:
        self.project = project
        self.scene.clear()
        self.scene_items.clear()
        self.asset_panel.clear()
        for asset in self.project.assets:
            self.asset_panel.add_asset(
                asset, self.store.workspace.asset_path(asset.relative_path)
            )
        for model in list(self.project.board.items):
            self.insert_board_item(model)
        self.canvas.resetTransform()
        self.canvas._zoom = 1.0
        self.canvas.set_zoom_level(max(0.1, self.project.board.view_scale))
        self.canvas.centerOn(
            self.project.board.view_center_x,
            self.project.board.view_center_y,
        )
        self.timeline_panel.set_composition(self.project.active_composition())
        self.timeline_dock.hide()
        self.gif_controls.hide()
        self._editing_note_id = None
        self.note_controls.hide()
        self.dirty = False
        self._update_title()

    def mark_dirty(self) -> None:
        self.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        marker = " *" if self.dirty else ""
        filename = self.project_path.name if self.project_path else self.project.name
        self.setWindowTitle(f"{filename}{marker} - {APP_NAME}")

    def _selection_changed(self) -> None:
        if self._closing:
            return
        try:
            selected = self.scene.selectedItems()
        except RuntimeError:
            return
        item = selected[0] if len(selected) == 1 else None
        for candidate in self.scene_items.values():
            if (
                isinstance(candidate, MediaItem)
                and candidate is not item
                and candidate.is_playing
            ):
                candidate.pause()
            if (
                isinstance(candidate, NoteItem)
                and candidate is not item
                and candidate.is_editing
            ):
                candidate.finish_editing()
        if isinstance(item, NoteItem):
            self.playing = False
            self.timeline_dock.hide()
            self.gif_controls.hide()
            if item.is_editing:
                self._editing_note_id = item.model_id
                self._sync_note_controls()
                QTimer.singleShot(0, self._position_note_controls)
            else:
                self._editing_note_id = None
                self.note_controls.hide()
            return
        if isinstance(item, MediaItem):
            self.asset_panel.select_asset(item.asset_id)
            if item.is_animated:
                self.playing = item.is_playing
                self.timeline_panel.show_frames(
                    item.asset,
                    item.source_path,
                    item.current_frame(),
                    expanded=True,
                )
                self.gif_controls.set_frame(
                    item.current_frame(),
                    item.asset.frame_count,
                )
                self.gif_controls.set_playing(item.is_playing)
                self.gif_controls.set_playback_rate(item.playback_rate)
                self.gif_controls.set_frames_expanded(True)
                QTimer.singleShot(0, self._position_gif_controls)
                return
        self.playing = False
        self.timeline_dock.hide()
        self.gif_controls.hide()
        self._editing_note_id = None
        self.note_controls.hide()

    def _media_frame_changed(self, item_id: str, frame_number: int) -> None:
        selected = self.selected_media_item()
        if selected is not None and selected.model_id == item_id:
            self.timeline_panel.set_frame(frame_number)
            self.gif_controls.set_frame(
                frame_number,
                selected.asset.frame_count,
            )

    def _sync_playback_controls(self) -> None:
        self.gif_controls.set_playing(self.playing)
        self.play_action.setIcon(
            self.style().standardIcon(
                QStyle.SP_MediaPause if self.playing else QStyle.SP_MediaPlay
            )
        )

    def _active_note_item(self) -> Optional[NoteItem]:
        if self._editing_note_id is None:
            return None
        item = self.scene_items.get(self._editing_note_id)
        if isinstance(item, NoteItem) and item.is_editing:
            return item
        return None

    def _note_editing_started(self, item_id: str) -> None:
        item = self.scene_items.get(item_id)
        if not isinstance(item, NoteItem):
            return
        for candidate in self.scene_items.values():
            if (
                isinstance(candidate, NoteItem)
                and candidate is not item
                and candidate.is_editing
            ):
                candidate.finish_editing()
        if not item.isSelected():
            self.scene.clearSelection()
            item.setSelected(True)
        self._editing_note_id = item_id
        self.timeline_dock.hide()
        self.gif_controls.hide()
        self._sync_note_controls()
        QTimer.singleShot(0, self._position_note_controls)

    def _note_editing_finished(self, item_id: str) -> None:
        if self._editing_note_id != item_id:
            return
        self._editing_note_id = None
        self.note_controls.hide()

    def _note_cursor_format_changed(self, item_id: str) -> None:
        if item_id != self._editing_note_id:
            return
        self._sync_note_controls()
        QTimer.singleShot(0, self._position_note_controls)

    def _sync_note_controls(self) -> None:
        item = self._active_note_item()
        if item is None:
            self.note_controls.hide()
            return
        self.note_controls.set_format_state(item.current_format_state())

    def _set_note_alignment(self, alignment: str) -> None:
        item = self._active_note_item()
        if item is not None:
            item.set_alignment(alignment)

    def _set_note_font_size(self, point_size: float) -> None:
        item = self._active_note_item()
        if item is not None:
            item.set_font_size(point_size)

    def _choose_note_text_color(self) -> None:
        item = self._active_note_item()
        if item is None:
            return
        state = item.current_format_state()
        current = state.get("color")
        initial = current if isinstance(current, QColor) else QColor(COLORS["text"])
        color = QColorDialog.getColor(initial, self, "Text Color")
        if color.isValid():
            item.set_text_color(color)
            self.note_controls.set_text_color(color)

    def _choose_note_background_color(self) -> None:
        item = self._active_note_item()
        if item is None:
            return
        color = QColorDialog.getColor(
            item.background_color,
            self,
            "Note Background Color",
            QColorDialog.ShowAlphaChannel | QColorDialog.DontUseNativeDialog,
        )
        if color.isValid():
            item.set_background_color(color)
            self.note_controls.set_background_color(color)

    def _set_note_bold(self, enabled: bool) -> None:
        item = self._active_note_item()
        if item is not None:
            item.set_bold(enabled)

    def _set_note_italic(self, enabled: bool) -> None:
        item = self._active_note_item()
        if item is not None:
            item.set_italic(enabled)

    def _set_note_underline(self, enabled: bool) -> None:
        item = self._active_note_item()
        if item is not None:
            item.set_underline(enabled)

    def _zoom_changed(self, zoom: float) -> None:
        percentage = f"{zoom * 100:.0f}%"
        self.statusBar().showMessage(f"Zoom {percentage}", 1200)

    def _show_canvas_menu(self, viewport_position) -> None:  # type: ignore[no-untyped-def]
        item = self.canvas.itemAt(viewport_position)
        if item is not None and not item.isSelected():
            self.scene.clearSelection()
            item.setSelected(True)
        menu = QMenu(self)
        menu.addAction(self.import_action)
        menu.addAction(self.note_action)
        if self.scene.selectedItems():
            menu.addAction(self.delete_action)
        menu.exec(self.canvas.viewport().mapToGlobal(viewport_position))

    def _set_frame_panel_expanded(self, expanded: bool) -> None:
        self.gif_controls.set_frames_expanded(expanded)
        if expanded:
            self.timeline_panel.setFixedHeight(196)
            self.timeline_panel.show()
        else:
            self.timeline_panel.hide()
        self.timeline_panel.updateGeometry()
        QTimer.singleShot(0, self._position_gif_controls)

    def _position_note_controls(self, *args) -> None:  # type: ignore[no-untyped-def]
        del args
        if self._closing:
            return
        item = self._active_note_item()
        if item is None:
            self.note_controls.hide()
            return

        viewport_rect = self.canvas.viewport().rect().adjusted(6, 6, -6, -6)
        item_scene_rect = item.sceneBoundingRect()
        item_rect = QRect(
            self.canvas.mapFromScene(item_scene_rect.topLeft()),
            self.canvas.mapFromScene(item_scene_rect.bottomRight()),
        ).normalized()
        if not item_rect.intersects(viewport_rect):
            self.note_controls.hide()
            return

        toolbar_size = self.note_controls.size()
        centered_x = item_rect.center().x() - toolbar_size.width() // 2
        centered_y = item_rect.center().y() - toolbar_size.height() // 2
        placements = [
            QPoint(centered_x, item_rect.bottom() + 8),
            QPoint(centered_x, item_rect.top() - toolbar_size.height() - 8),
            QPoint(item_rect.right() + 8, centered_y),
            QPoint(item_rect.left() - toolbar_size.width() - 8, centered_y),
        ]
        blocked = item_rect.adjusted(-5, -5, 5, 5)
        placement = None
        for candidate in placements:
            rect = QRect(candidate, toolbar_size)
            if viewport_rect.contains(rect) and not rect.intersects(blocked):
                placement = candidate
                break
        if placement is None:
            self.note_controls.hide()
            return

        self.note_controls.move(placement)
        self.note_controls.raise_()
        self.note_controls.show()

    def _position_gif_controls(self, *args) -> None:  # type: ignore[no-untyped-def]
        del args
        if self._closing:
            return
        try:
            item = self.selected_media_item()
        except RuntimeError:
            return
        if item is None or not item.is_animated:
            self.gif_controls.hide()
            return

        viewport_rect = self.canvas.viewport().rect().adjusted(6, 6, -6, -6)
        item_scene_rect = item.sceneBoundingRect()
        item_top_left = self.canvas.mapFromScene(item_scene_rect.topLeft())
        item_bottom_right = self.canvas.mapFromScene(item_scene_rect.bottomRight())
        item_rect = QRect(item_top_left, item_bottom_right).normalized()
        if not item_rect.intersects(viewport_rect):
            self.gif_controls.hide()
            return

        toolbar_size = self.gif_controls.size()
        preferred_x = item_rect.center().x() - toolbar_size.width() // 2
        preferred_y = item_rect.bottom() + 8
        x_candidates = [
            preferred_x,
            item_rect.left(),
            item_rect.right() - toolbar_size.width(),
        ]
        note_rects = []
        for candidate in self.scene_items.values():
            if not isinstance(candidate, NoteItem):
                continue
            note_scene_rect = candidate.sceneBoundingRect()
            note_rect = QRect(
                self.canvas.mapFromScene(note_scene_rect.topLeft()),
                self.canvas.mapFromScene(note_scene_rect.bottomRight()),
            ).normalized().adjusted(-6, -6, 6, 6)
            if note_rect.intersects(viewport_rect):
                note_rects.append(note_rect)

        y_candidates = [preferred_y]
        y_candidates.extend(
            sorted(
                {
                    note_rect.bottom() + 8
                    for note_rect in note_rects
                    if note_rect.bottom() >= preferred_y
                }
            )
        )
        placement = self._free_toolbar_position(
            x_candidates,
            y_candidates,
            toolbar_size.width(),
            toolbar_size.height(),
            viewport_rect,
            note_rects,
        )
        if placement is None:
            placement = self._free_toolbar_position(
                x_candidates,
                [item_rect.top() - toolbar_size.height() - 8],
                toolbar_size.width(),
                toolbar_size.height(),
                viewport_rect,
                note_rects,
            )
        if placement is None:
            self.gif_controls.hide()
            return
        self.gif_controls.move(placement)
        self.gif_controls.raise_()
        self.gif_controls.show()

    @staticmethod
    def _free_toolbar_position(
        x_candidates: list[int],
        y_candidates: list[int],
        width: int,
        height: int,
        viewport_rect: QRect,
        blocked_rects: list[QRect],
    ) -> Optional[QPoint]:
        for y in y_candidates:
            for x in x_candidates:
                bounded_x = max(
                    viewport_rect.left(),
                    min(x, viewport_rect.right() - width + 1),
                )
                candidate = QRect(bounded_x, y, width, height)
                if not viewport_rect.contains(candidate):
                    continue
                if any(candidate.intersects(blocked) for blocked in blocked_rects):
                    continue
                return candidate.topLeft()
        return None

    def frame_repeat_timer_start(self) -> None:
        if self._frame_step_direction:
            self.frame_repeat_timer.start()

    def _repeat_frame_step(self) -> None:
        if self._frame_step_direction:
            self.step_selected(self._frame_step_direction)

    def _show_error(self, title: str, detail: str) -> None:
        QMessageBox.critical(self, title, detail)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if not self._closing:
            QTimer.singleShot(0, self._position_gif_controls)
            QTimer.singleShot(0, self._position_note_controls)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        focus_item = self.scene.focusItem()
        editing_note = (
            isinstance(focus_item, NoteItem)
            and focus_item.textInteractionFlags() & Qt.TextEditorInteraction
        )
        if editing_note:
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()
        if modifiers == Qt.NoModifier:
            if key == Qt.Key_Space and not event.isAutoRepeat():
                self.toggle_playback()
                event.accept()
                return
            if key in {Qt.Key_Backspace, Qt.Key_Delete}:
                self.delete_selection()
                event.accept()
                return
            if key == Qt.Key_Left:
                if not event.isAutoRepeat():
                    self._frame_step_direction = -1
                    self.step_selected(-1)
                    self.frame_repeat_delay_timer.start()
                event.accept()
                return
            if key == Qt.Key_Right:
                if not event.isAutoRepeat():
                    self._frame_step_direction = 1
                    self.step_selected(1)
                    self.frame_repeat_delay_timer.start()
                event.accept()
                return
            if key == Qt.Key_F and not event.isAutoRepeat():
                self.canvas.fit_items()
                event.accept()
                return
            rates_by_key = {
                Qt.Key_1: 0.25,
                Qt.Key_2: 0.5,
                Qt.Key_3: 1.0,
                Qt.Key_4: 2.0,
                Qt.Key_5: 4.0,
            }
            if key in rates_by_key:
                self.set_selected_speed(rates_by_key[key])
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.isAutoRepeat():
            event.accept()
            return
        key = event.key()
        releasing_active_direction = (
            key == Qt.Key_Left and self._frame_step_direction == -1
        ) or (
            key == Qt.Key_Right and self._frame_step_direction == 1
        )
        if releasing_active_direction:
            self._frame_step_direction = 0
            self.frame_repeat_delay_timer.stop()
            self.frame_repeat_timer.stop()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing = True
        self.autosave()
        self.frame_repeat_delay_timer.stop()
        self.frame_repeat_timer.stop()
        for item in self.scene_items.values():
            if isinstance(item, MediaItem):
                item.dispose()
        try:
            self.scene.selectionChanged.disconnect(self._selection_changed)
        except (RuntimeError, TypeError):
            pass
        event.accept()
