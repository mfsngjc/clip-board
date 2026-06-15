from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw
from PySide6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QPoint,
    QPointF,
    QRect,
    QStandardPaths,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QFileOpenEvent,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QTextCursor,
)
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDockWidget,
    QListWidgetItem,
    QToolBar,
)

from clip_board.app import ClipBoardApplication
from clip_board.main_window import MainWindow
from clip_board.models import BoardItemModel, ProjectModel, new_id
from clip_board.panels import FrameStrip
from clip_board.scene_items import MediaItem, NoteItem


def create_media(root: Path) -> tuple[Path, Path]:
    still = root / "still.png"
    animation = root / "motion.gif"
    Image.new("RGB", (420, 260), "#E7F6F2").save(still)

    frames = []
    for index, color in enumerate(("#24B7A4", "#F07C46", "#56C7F2")):
        image = Image.new("RGB", (320, 180), "#172129")
        painter = ImageDraw.Draw(image)
        painter.rounded_rectangle(
            (30 + index * 28, 45, 150 + index * 28, 135),
            radius=16,
            fill=color,
        )
        frames.append(image)
    frames[0].save(
        animation,
        save_all=True,
        append_images=frames[1:],
        duration=[120, 180, 240],
        loop=0,
    )
    return still, animation


def main() -> int:
    QStandardPaths.setTestModeEnabled(True)
    app = ClipBoardApplication([])

    file_open_requests = []
    app.file_open_requested.connect(file_open_requests.append)
    test_open_path = Path(tempfile.gettempdir()) / "double-click.clipboard"
    QApplication.sendEvent(app, QFileOpenEvent(str(test_open_path)))
    assert file_open_requests == [str(test_open_path.resolve())]
    assert app.take_pending_files() == [test_open_path.resolve()]

    scroll_strip = FrameStrip()
    scroll_strip.resize(520, 170)
    for index in range(14):
        item = QListWidgetItem(f"Frame {index + 1}")
        item.setData(Qt.UserRole, index)
        scroll_strip.list_widget.addItem(item)
    scroll_strip.show()
    app.processEvents()
    scroll_bar = scroll_strip.list_widget.horizontalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum() // 2)
    app.processEvents()
    visible_rows = [
        row
        for row in range(scroll_strip.list_widget.count())
        if scroll_strip.list_widget.visualItemRect(
            scroll_strip.list_widget.item(row)
        ).intersects(scroll_strip.list_widget.viewport().rect())
    ]
    clicked_row = visible_rows[len(visible_rows) // 2]
    clicked_item = scroll_strip.list_widget.item(clicked_row)
    scroll_before_click = scroll_bar.value()
    QTest.mouseClick(
        scroll_strip.list_widget.viewport(),
        Qt.LeftButton,
        pos=scroll_strip.list_widget.visualItemRect(clicked_item).center(),
    )
    scroll_strip.set_current_frame(clicked_row)
    app.processEvents()
    assert scroll_bar.value() == scroll_before_click
    scroll_strip.set_current_frame(0)
    app.processEvents()
    assert scroll_bar.value() < scroll_before_click
    scroll_strip.close()

    source_root = Path(tempfile.mkdtemp(prefix="clip-board-smoke-"))
    still, animation = create_media(source_root)
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    project_path = output / "smoke-project.clipboard"

    window = MainWindow()
    window.store.autosave_path.unlink(missing_ok=True)
    window.store.workspace.reset()
    window.asset_library.assets_dir.mkdir(parents=True, exist_ok=True)
    window._adopt_project(ProjectModel.create("Smoke Test"))
    window.show()
    app.processEvents()

    first_save_path = source_root / "first-save.clipboard"
    with patch(
        "clip_board.main_window.QFileDialog.getSaveFileName",
        return_value=(str(first_save_path), "Clip Board Project"),
    ) as save_dialog:
        window.save_project()
        save_dialog.assert_called_once()
    assert window.project_path == first_save_path.resolve()
    assert first_save_path.exists()
    with patch(
        "clip_board.main_window.QFileDialog.getSaveFileName"
    ) as save_dialog:
        window.mark_dirty()
        window.save_project()
        save_dialog.assert_not_called()
    assert first_save_path.exists()
    window.project_path = None

    zoom_anchor = QPointF(180, 140)
    scene_before = window.canvas.mapToScene(zoom_anchor.toPoint())
    window.canvas.set_zoom_level(2.0, zoom_anchor)
    scene_after = window.canvas.mapToScene(zoom_anchor.toPoint())
    assert abs(scene_before.x() - scene_after.x()) < 0.01
    assert abs(scene_before.y() - scene_after.y()) < 0.01
    window.canvas.reset_view()

    initial_item_count = len(window.project.board.items)
    QTest.mouseDClick(
        window.canvas.viewport(),
        Qt.LeftButton,
        pos=QPoint(700, 420),
    )
    app.processEvents()
    assert len(window.project.board.items) == initial_item_count

    window.add_note(QPointF(260, 180))
    app.processEvents()
    note = next(
        item for item in window.scene.items() if isinstance(item, NoteItem)
    )
    assert note.textInteractionFlags() & Qt.TextEditorInteraction
    assert note.textCursor().hasSelection()
    assert window.note_controls.isVisible()
    toolbar_order = [
        widget.objectName()
        for index in range(window.note_controls.layout().count())
        if (
            (widget := window.note_controls.layout().itemAt(index).widget())
            is not None
            and widget.objectName()
        )
    ]
    assert toolbar_order == [
        "NoteFontSize",
        "NoteTextColor",
        "NoteBackgroundColor",
        "NoteBold",
        "NoteItalic",
        "NoteUnderline",
        "NoteAlignLeft",
        "NoteAlignCenter",
        "NoteAlignRight",
    ]
    assert all(
        not button.icon().isNull()
        for button in window.note_controls.alignment_buttons.values()
    )

    cursor = note.textCursor()
    cursor.insertText("Bold line\nItalic line\nUnder line")
    note.setTextCursor(cursor)
    text = note.toPlainText()

    def select_note_text(fragment: str) -> None:
        start = text.index(fragment)
        selection = QTextCursor(note.document())
        selection.setPosition(start)
        selection.setPosition(start + len(fragment), QTextCursor.KeepAnchor)
        note.setTextCursor(selection)
        note.cursor_format_changed.emit()
        app.processEvents()

    select_note_text("Bold")
    window.note_controls.bold_button.click()
    window.note_controls._request_font_size(24)
    note.set_text_color(QColor("#C93636"))
    window.note_controls.alignment_buttons["left"].click()

    select_note_text("Italic")
    window.note_controls.italic_button.click()
    window.note_controls._request_font_size(18)
    note.set_text_color(QColor("#0F766E"))
    window.note_controls.alignment_buttons["center"].click()

    select_note_text("Under")
    window.note_controls.underline_button.click()
    window.note_controls._request_font_size(14)
    note.set_text_color(QColor("#0878C9"))
    window.note_controls.alignment_buttons["right"].click()
    app.processEvents()

    def format_for(fragment: str):
        probe = QTextCursor(note.document())
        probe.setPosition(text.index(fragment) + 1)
        return probe.charFormat(), probe.blockFormat()

    bold_format, bold_block = format_for("Bold")
    italic_format, italic_block = format_for("Italic")
    under_format, under_block = format_for("Under")
    assert bold_format.fontWeight() >= QFont.Bold
    assert bold_format.fontPointSize() == 24
    assert bold_format.foreground().color().name() == "#c93636"
    assert bold_block.alignment() & Qt.AlignLeft
    assert italic_format.fontItalic()
    assert italic_format.fontPointSize() == 18
    assert italic_format.foreground().color().name() == "#0f766e"
    assert italic_block.alignment() & Qt.AlignHCenter
    assert under_format.fontUnderline()
    assert under_format.fontPointSize() == 14
    assert under_format.foreground().color().name() == "#0878c9"
    assert under_block.alignment() & Qt.AlignRight

    transparent_background = QColor(255, 196, 48, 96)
    with patch(
        "clip_board.main_window.QColorDialog.getColor",
        return_value=transparent_background,
    ) as background_dialog:
        window._choose_note_background_color()
        options = background_dialog.call_args.args[3]
        assert options & QColorDialog.ShowAlphaChannel
        assert options & QColorDialog.DontUseNativeDialog
    assert note.background_color == transparent_background
    assert not window.note_controls.background_color_button.icon().isNull()
    assert window.grab().save(str(output / "note-rich-toolbar.png"))

    window.sync_project_from_scene()
    note_model = window.project.board_item_by_id(note.model_id)
    assert note_model is not None
    assert note_model.rich_text
    assert note_model.background_color == "#60ffc430"
    restored_project = ProjectModel.from_dict(window.project.to_dict())
    restored_model = restored_project.board_item_by_id(note.model_id)
    assert restored_model is not None
    restored_note = NoteItem(restored_model)
    assert restored_note.background_color.alpha() == 96
    restored_text = restored_note.toPlainText()
    assert restored_text == text
    restored_probe = QTextCursor(restored_note.document())
    restored_probe.setPosition(restored_text.index("Italic") + 1)
    assert restored_probe.charFormat().fontItalic()
    assert restored_probe.blockFormat().alignment() & Qt.AlignHCenter

    note_rect = QRect(
        window.canvas.mapFromScene(note.sceneBoundingRect().topLeft()),
        window.canvas.mapFromScene(note.sceneBoundingRect().bottomRight()),
    ).normalized()
    assert not window.note_controls.geometry().intersects(note_rect)
    QTest.mouseClick(
        window.canvas.viewport(),
        Qt.LeftButton,
        pos=QPoint(900, 520),
    )
    app.processEvents()
    assert note.textInteractionFlags() == Qt.NoTextInteraction
    assert not note.hasFocus()
    assert not note.isSelected()
    assert not note.textCursor().hasSelection()
    assert not window.note_controls.isVisible()
    window.undo_stack.undo()
    app.processEvents()

    window.import_files([str(still), str(animation)], QPointF(-180, -100))
    app.processEvents()
    media_items = [
        item for item in window.scene.items() if isinstance(item, MediaItem)
    ]
    assert len(media_items) == 2

    animated = next(item for item in media_items if item.is_animated)
    animated_rect = animated.sceneBoundingRect()
    blocking_note_model = BoardItemModel(
        id=new_id("note"),
        kind="note",
        x=animated_rect.left(),
        y=animated_rect.bottom() + 4,
        width=280,
        height=120,
        z=10,
        text="Toolbar collision test",
    )
    window.insert_board_item(blocking_note_model)
    blocking_note = window.scene_items[blocking_note_model.id]
    assert isinstance(blocking_note, NoteItem)

    view_origin_before = window.canvas.mapToScene(QPoint(0, 0))
    animated_position_before = QPointF(animated.pos())
    window.scene.clearSelection()
    animated.setSelected(True)
    app.processEvents()
    QTest.qWait(80)
    app.processEvents()
    view_origin_after = window.canvas.mapToScene(QPoint(0, 0))
    assert window.gif_controls.isVisible()
    assert window.timeline_dock.isVisible()
    assert window.timeline_panel.frame_strip.isVisible()
    assert window.timeline_panel.frame_strip.frame_count == 3
    assert window.timeline_dock.height() >= 190
    assert window.timeline_panel.frame_strip.height() >= 150
    assert abs(view_origin_before.x() - view_origin_after.x()) < 0.01
    assert abs(view_origin_before.y() - view_origin_after.y()) < 0.01
    assert animated.pos() == animated_position_before
    blocking_note_rect = QRect(
        window.canvas.mapFromScene(blocking_note.sceneBoundingRect().topLeft()),
        window.canvas.mapFromScene(blocking_note.sceneBoundingRect().bottomRight()),
    ).normalized()
    assert not window.gif_controls.geometry().intersects(blocking_note_rect)
    assert not window.findChildren(QToolBar)
    assert window.findChild(QDockWidget, "InspectorDock") is None

    QTest.mouseClick(
        window.canvas.viewport(),
        Qt.LeftButton,
        pos=QPoint(900, 420),
    )
    app.processEvents()
    assert not window.gif_controls.isVisible()
    assert not window.timeline_dock.isVisible()
    animated.setSelected(True)
    app.processEvents()
    QTest.qWait(80)
    app.processEvents()
    assert window.gif_controls.isVisible()
    assert window.timeline_dock.isVisible()
    window.remove_board_item(blocking_note_model.id)
    app.processEvents()

    item_center = window.canvas.mapFromScene(
        animated.mapToScene(animated.boundingRect().center())
    )
    moved_point = item_center + QPoint(2, 2)
    QApplication.sendEvent(
        window.canvas.viewport(),
        QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(item_center),
            QPointF(window.canvas.viewport().mapToGlobal(item_center)),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        ),
    )
    QApplication.sendEvent(
        window.canvas.viewport(),
        QMouseEvent(
            QEvent.MouseMove,
            QPointF(moved_point),
            QPointF(window.canvas.viewport().mapToGlobal(moved_point)),
            Qt.NoButton,
            Qt.LeftButton,
            Qt.NoModifier,
        ),
    )
    QApplication.sendEvent(
        window.canvas.viewport(),
        QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(moved_point),
            QPointF(window.canvas.viewport().mapToGlobal(moved_point)),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        ),
    )
    app.processEvents()
    assert animated.pos() == animated_position_before

    observed_frames = []
    animated.frame_changed.connect(observed_frames.append)
    window.keyPressEvent(
        QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
    )
    QTest.qWait(650)
    window.keyReleaseEvent(
        QKeyEvent(QEvent.KeyRelease, Qt.Key_Right, Qt.NoModifier)
    )
    assert len(observed_frames) >= 3
    window.keyPressEvent(
        QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier)
    )
    assert animated.is_playing
    window.keyPressEvent(
        QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier)
    )
    assert not animated.is_playing

    window.gif_controls._request_playback_rate(2.0)
    assert animated.playback_rate == 2.0
    assert (
        window.project.board_item_by_id(animated.model_id).playback_rate
        == 2.0
    )
    assert window.gif_controls.speed_button.text() == "2×"
    window.set_selected_speed(0.5)
    assert animated.playback_rate == 0.5
    assert window.gif_controls.speed_button.text() == "0.5×"
    window.set_selected_speed(1.0)

    gif_position = window.canvas.mapFromScene(
        animated.mapToScene(animated.boundingRect().center())
    )
    window.canvas.context_menu_requested.disconnect(window._show_canvas_menu)
    context_menu_spy = QSignalSpy(window.canvas.context_menu_requested)
    QTest.mousePress(
        window.canvas.viewport(),
        Qt.RightButton,
        pos=gif_position,
    )
    app.processEvents()
    assert context_menu_spy.count() == 1
    assert context_menu_spy.at(0)[0] == gif_position
    window.canvas.context_menu_requested.connect(window._show_canvas_menu)

    gif_menu = window._build_canvas_menu(gif_position)
    copy_menu_action = next(
        action
        for action in gif_menu.actions()
        if action.text() == "Copy GIF to Clipboard"
    )
    copy_menu = copy_menu_action.menu()
    assert copy_menu is not None
    assert [action.text() for action in copy_menu.actions()] == [
        "Original (320 × 180)",
        "75% (240 × 135)",
        "50% (160 × 90)",
        "25% (80 × 45)",
    ]
    copy_menu.actions()[2].trigger()
    app.processEvents()
    clipboard_mime = app.clipboard().mimeData()
    assert clipboard_mime.hasFormat("image/gif")
    clipboard_urls = clipboard_mime.urls()
    assert len(clipboard_urls) == 1
    clipboard_gif = Path(clipboard_urls[0].toLocalFile())
    assert clipboard_gif.exists()
    with Image.open(clipboard_gif) as copied_image:
        assert copied_image.size == (160, 90)
        assert copied_image.n_frames == 3

    assert window.grab().save(str(output / "gif-frames-expanded.png"))

    frame_list = window.timeline_panel.frame_strip.list_widget
    first_rect = frame_list.visualItemRect(frame_list.item(0))
    third_rect = frame_list.visualItemRect(frame_list.item(2))
    QTest.mouseClick(
        frame_list.viewport(),
        Qt.LeftButton,
        Qt.NoModifier,
        first_rect.center(),
    )
    QTest.mouseClick(
        frame_list.viewport(),
        Qt.LeftButton,
        Qt.ShiftModifier,
        third_rect.center(),
    )
    assert [
        row
        for row in range(frame_list.count())
        if frame_list.item(row).isSelected()
    ] == [0, 1, 2]

    third_rect = frame_list.visualItemRect(frame_list.item(2))
    second_rect = frame_list.visualItemRect(frame_list.item(1))
    QTest.mouseClick(
        frame_list.viewport(),
        Qt.LeftButton,
        Qt.NoModifier,
        third_rect.center(),
    )
    frame_list.setCurrentItem(
        frame_list.item(0),
        QItemSelectionModel.NoUpdate,
    )
    QTest.mouseClick(
        frame_list.viewport(),
        Qt.LeftButton,
        Qt.ShiftModifier,
        second_rect.center(),
    )
    assert [
        row
        for row in range(frame_list.count())
        if frame_list.item(row).isSelected()
    ] == [1, 2]

    frame_list.clearSelection()
    frame_list.item(0).setSelected(True)
    frame_list.item(2).setSelected(True)
    window.copy_selection()
    assert len(window._copied_frames) == 2
    window.scene.clearSelection()
    window.paste_from_clipboard()
    app.processEvents()
    pasted = window.selected_media_item()
    assert pasted is not None
    assert pasted.asset.frame_count == 2
    pasted_item_id = pasted.model_id

    window.scene.clearSelection()
    animated.setSelected(True)
    app.processEvents()
    window.timeline_panel.set_expanded(True)
    app.processEvents()
    frame_list = window.timeline_panel.frame_strip.list_widget
    frame_list.clearSelection()
    frame_list.item(1).setSelected(True)
    frame_list.setCurrentItem(frame_list.item(1))
    window.copy_selection()
    assert len(window._copied_frames) == 1

    pasted = window.scene_items[pasted_item_id]
    assert isinstance(pasted, MediaItem)
    window.scene.clearSelection()
    pasted.setSelected(True)
    window.paste_from_clipboard()
    app.processEvents()
    pasted = window.scene_items[pasted_item_id]
    assert isinstance(pasted, MediaItem)
    assert pasted.asset.frame_count == 3

    window.timeline_panel.set_expanded(True)
    app.processEvents()
    frame_list = window.timeline_panel.frame_strip.list_widget
    frame_list.clearSelection()
    frame_list.item(0).setSelected(True)
    frame_list.setCurrentItem(frame_list.item(0))
    assert frame_list.move_selected_rows(3)
    QTest.qWait(100)
    app.processEvents()
    pasted = window.scene_items[pasted_item_id]
    assert isinstance(pasted, MediaItem)
    assert pasted.asset.frame_count == 3

    window.timeline_panel.set_expanded(True)
    app.processEvents()
    frame_list = window.timeline_panel.frame_strip.list_widget
    frame_list.clearSelection()
    frame_list.item(0).setSelected(True)
    frame_list.setCurrentItem(frame_list.item(0))
    frame_list.setFocus()
    window.delete_selection()
    app.processEvents()
    pasted = window.scene_items[pasted_item_id]
    assert isinstance(pasted, MediaItem)
    assert pasted.asset.frame_count == 2
    window.undo_stack.undo()
    app.processEvents()
    pasted = window.scene_items[pasted_item_id]
    assert isinstance(pasted, MediaItem)
    assert pasted.asset.frame_count == 3

    window.timeline_panel.frame_selected.emit(1)
    app.processEvents()
    assert pasted.current_frame() == 1
    window.gif_controls.frame_count_button.click()
    app.processEvents()
    assert not window.timeline_panel.frame_strip.isVisible()
    assert not window.timeline_dock.isVisible()

    still_item = next(
        item
        for item in window.scene.items()
        if isinstance(item, MediaItem) and not item.is_animated
    )
    window.scene.clearSelection()
    still_item.setSelected(True)
    item_count_before_delete = len(window.project.board.items)
    window.keyPressEvent(
        QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier)
    )
    app.processEvents()
    assert len(window.project.board.items) == item_count_before_delete - 1
    window.undo_stack.undo()
    app.processEvents()
    assert len(window.project.board.items) == item_count_before_delete

    pasted = window.scene_items[pasted_item_id]
    assert isinstance(pasted, MediaItem)
    window.scene.clearSelection()
    pasted.setSelected(True)
    window.add_selected_to_timeline()
    window.toggle_playback()
    for _ in range(8):
        app.processEvents()
    window.toggle_playback()

    assert len(window.project.assets) >= 5
    assert len(window.project.board.items) == 3
    assert len(window.project.active_composition().tracks[0].clips) == 1
    window._save_to(project_path)
    window.canvas.fit_items()
    app.processEvents()
    assert window.grab().save(str(output / "v0-workflow.png"))
    window.dirty = False
    window.close()

    loaded = MainWindow(project_path)
    loaded.show()
    app.processEvents()
    assert len(loaded.project.assets) >= 5
    assert len(loaded.project.board.items) == 3
    assert len(loaded.project.active_composition().tracks[0].clips) == 1
    assert len(loaded.scene_items) == 3
    loaded.dirty = False
    loaded.close()
    app.processEvents()
    app.clipboard().clear()
    app.processEvents()
    print(f"SMOKE_OK {project_path} ({project_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
