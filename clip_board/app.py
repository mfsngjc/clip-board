from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QCoreApplication, QEvent, Qt, Signal
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QApplication

from .constants import APP_NAME
from .main_window import MainWindow


class ClipBoardApplication(QApplication):
    file_open_requested = Signal(str)

    def __init__(self, arguments: list[str]) -> None:
        super().__init__(arguments)
        self._pending_files: list[Path] = []

    def event(self, event) -> bool:  # type: ignore[no-untyped-def]
        if event.type() == QEvent.FileOpen and isinstance(event, QFileOpenEvent):
            filename = event.file()
            if filename:
                path = Path(filename).expanduser().resolve()
                self._pending_files.append(path)
                self.file_open_requested.emit(str(path))
                return True
        return super().event(event)

    def take_pending_files(self) -> list[Path]:
        pending = list(self._pending_files)
        self._pending_files.clear()
        return pending


def main(argv: Optional[list[str]] = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    QCoreApplication.setOrganizationName("Clip Board")
    QCoreApplication.setApplicationName(APP_NAME)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = ClipBoardApplication(arguments)
    app.setApplicationDisplayName(APP_NAME)
    app.setStyle("Fusion")

    initial_project = None
    if len(arguments) > 1:
        candidate = Path(arguments[1])
        if candidate.exists():
            initial_project = candidate.expanduser().resolve()
    if initial_project is None:
        pending = app.take_pending_files()
        initial_project = pending[-1] if pending else None

    window = MainWindow(initial_project)
    app.file_open_requested.connect(
        lambda filename: window.load_project(Path(filename))
    )
    window.show()
    return app.exec()
