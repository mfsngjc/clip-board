from pathlib import Path

APP_NAME = "Clip Board"
PROJECT_SUFFIX = ".clipboard"
FRAME_MIME_TYPE = "application/x-clip-board-frames"
SCHEMA_VERSION = 2

SUPPORTED_IMAGE_SUFFIXES = {
    ".gif",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".apng",
}

DEFAULT_SCENE_RECT = (-50000.0, -50000.0, 100000.0, 100000.0)
DEFAULT_COMPOSITION_WIDTH = 1920
DEFAULT_COMPOSITION_HEIGHT = 1080
DEFAULT_COMPOSITION_FPS = 30
DEFAULT_COMPOSITION_DURATION_MS = 10000

AUTOSAVE_FILENAME = "autosave.clipboard"


def file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".gif", ".apng", ".webp"}:
        return "animation"
    return "image"
