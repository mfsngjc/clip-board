from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

from PIL import Image, ImageOps

from .constants import SUPPORTED_IMAGE_SUFFIXES, file_kind
from .models import AssetModel, new_id


@dataclass
class AnimationFrame:
    image: Image.Image
    duration_ms: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_image(path: Path) -> Dict[str, int]:
    result = {"width": 0, "height": 0, "duration_ms": 0, "frame_count": 1}
    with Image.open(path) as image:
        result["width"], result["height"] = image.size
        frame_count = int(getattr(image, "n_frames", 1))
        result["frame_count"] = frame_count
        if frame_count > 1:
            duration = 0
            for frame_index in range(frame_count):
                image.seek(frame_index)
                duration += int(image.info.get("duration", 100))
            result["duration_ms"] = max(duration, 1)
        else:
            result["duration_ms"] = 3000
    return result


def read_animation_frames(
    path: Path,
    indices: Optional[Sequence[int]] = None,
) -> list[AnimationFrame]:
    with Image.open(path) as image:
        frame_count = int(getattr(image, "n_frames", 1))
        requested = list(range(frame_count)) if indices is None else list(indices)
        frames = []
        for frame_index in requested:
            if frame_index < 0 or frame_index >= frame_count:
                raise IndexError(f"Frame {frame_index} is outside the animation.")
            image.seek(frame_index)
            frames.append(
                AnimationFrame(
                    image=image.convert("RGBA").copy(),
                    duration_ms=max(10, int(image.info.get("duration", 100))),
                )
            )
    return frames


def normalize_animation_frames(
    frames: Iterable[AnimationFrame],
    target_size: Optional[tuple[int, int]] = None,
) -> list[AnimationFrame]:
    source = list(frames)
    if not source:
        raise ValueError("An animation needs at least one frame.")
    if target_size is None:
        target_size = (
            max(frame.image.width for frame in source),
            max(frame.image.height for frame in source),
        )

    normalized = []
    for frame in source:
        image = ImageOps.contain(
            frame.image.convert("RGBA"),
            target_size,
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
        canvas.alpha_composite(
            image,
            (
                (target_size[0] - image.width) // 2,
                (target_size[1] - image.height) // 2,
            ),
        )
        normalized.append(AnimationFrame(canvas, frame.duration_ms))
    return normalized


def save_animation_frames(
    frames: Iterable[AnimationFrame],
    destination: Path,
    target_size: Optional[tuple[int, int]] = None,
) -> None:
    normalized = normalize_animation_frames(frames, target_size)
    destination.parent.mkdir(parents=True, exist_ok=True)
    durations = [frame.duration_ms for frame in normalized]
    first, *remaining = [frame.image for frame in normalized]
    first.save(
        destination,
        format="GIF",
        save_all=True,
        append_images=remaining,
        duration=durations,
        loop=0,
        disposal=2,
        optimize=False,
    )


def export_animation_gif(
    source: Path,
    destination: Path,
    target_size: Optional[tuple[int, int]] = None,
) -> None:
    source = source.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if target_size is None and source.suffix.lower() == ".gif":
        shutil.copy2(source, destination)
        return
    if target_size is not None and (target_size[0] < 1 or target_size[1] < 1):
        raise ValueError("GIF export dimensions must be positive.")
    save_animation_frames(
        read_animation_frames(source),
        destination,
        target_size,
    )


class AssetLibrary:
    def __init__(self, assets_dir: Path) -> None:
        self.assets_dir = assets_dir
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def import_file(self, source_path: Path) -> AssetModel:
        source_path = source_path.expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        if source_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported image format: {source_path.suffix}")

        digest = sha256_file(source_path)
        destination_name = f"{digest[:20]}{source_path.suffix.lower()}"
        destination = self.assets_dir / destination_name
        if not destination.exists():
            shutil.copy2(source_path, destination)

        metadata = probe_image(destination)
        return AssetModel(
            id=new_id("asset"),
            name=source_path.name,
            kind=file_kind(source_path),
            relative_path=f"assets/{destination_name}",
            source_path=str(source_path),
            sha256=digest,
            **metadata,
        )

    def create_gif(
        self,
        frames: Iterable[AnimationFrame],
        name: str = "Frame selection.gif",
        target_size: Optional[tuple[int, int]] = None,
    ) -> AssetModel:
        handle, temp_name = tempfile.mkstemp(
            prefix=".clip-board-frames-",
            suffix=".gif",
            dir=str(self.assets_dir),
        )
        os.close(handle)
        Path(temp_name).unlink(missing_ok=True)
        try:
            save_animation_frames(frames, Path(temp_name), target_size)
            asset = self.import_file(Path(temp_name))
        finally:
            Path(temp_name).unlink(missing_ok=True)
        asset.name = f"{Path(name).stem}.gif"
        asset.source_path = ""
        return asset
