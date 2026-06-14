from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .constants import (
    DEFAULT_COMPOSITION_DURATION_MS,
    DEFAULT_COMPOSITION_FPS,
    DEFAULT_COMPOSITION_HEIGHT,
    DEFAULT_COMPOSITION_WIDTH,
    SCHEMA_VERSION,
)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass
class AssetModel:
    id: str
    name: str
    kind: str
    relative_path: str
    source_path: str = ""
    sha256: str = ""
    width: int = 0
    height: int = 0
    duration_ms: int = 0
    frame_count: int = 1


@dataclass
class BoardItemModel:
    id: str
    kind: str
    asset_id: Optional[str] = None
    x: float = 0.0
    y: float = 0.0
    width: float = 320.0
    height: float = 180.0
    scale: float = 1.0
    rotation: float = 0.0
    z: float = 0.0
    playback_rate: float = 1.0
    text: str = ""
    rich_text: str = ""
    text_color: str = "#17212B"
    background_color: str = "#FFF2B8"
    font_size: int = 16


@dataclass
class BoardModel:
    items: List[BoardItemModel] = field(default_factory=list)
    view_center_x: float = 0.0
    view_center_y: float = 0.0
    view_scale: float = 1.0


@dataclass
class ClipModel:
    id: str
    asset_id: str
    name: str
    timeline_start_ms: int
    source_in_ms: int = 0
    source_out_ms: int = 3000
    playback_rate: float = 1.0
    loop: bool = False
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0
    opacity: float = 1.0

    @property
    def duration_ms(self) -> int:
        return max(1, int((self.source_out_ms - self.source_in_ms) / self.playback_rate))


@dataclass
class TrackModel:
    id: str
    name: str
    kind: str = "visual"
    muted: bool = False
    locked: bool = False
    clips: List[ClipModel] = field(default_factory=list)


@dataclass
class CompositionModel:
    id: str
    name: str
    width: int = DEFAULT_COMPOSITION_WIDTH
    height: int = DEFAULT_COMPOSITION_HEIGHT
    fps: int = DEFAULT_COMPOSITION_FPS
    duration_ms: int = DEFAULT_COMPOSITION_DURATION_MS
    tracks: List[TrackModel] = field(default_factory=list)


@dataclass
class ProjectModel:
    schema_version: int = SCHEMA_VERSION
    name: str = "Untitled Board"
    assets: List[AssetModel] = field(default_factory=list)
    board: BoardModel = field(default_factory=BoardModel)
    compositions: List[CompositionModel] = field(default_factory=list)
    active_composition_id: Optional[str] = None

    @classmethod
    def create(cls, name: str = "Untitled Board") -> "ProjectModel":
        track = TrackModel(id=new_id("track"), name="Visual 1")
        composition = CompositionModel(
            id=new_id("comp"),
            name="Main Composition",
            tracks=[track],
        )
        return cls(
            name=name,
            compositions=[composition],
            active_composition_id=composition.id,
        )

    def active_composition(self) -> CompositionModel:
        for composition in self.compositions:
            if composition.id == self.active_composition_id:
                return composition
        if not self.compositions:
            replacement = ProjectModel.create(self.name)
            self.compositions = replacement.compositions
            self.active_composition_id = replacement.active_composition_id
        return self.compositions[0]

    def asset_by_id(self, asset_id: Optional[str]) -> Optional[AssetModel]:
        if not asset_id:
            return None
        return next((asset for asset in self.assets if asset.id == asset_id), None)

    def board_item_by_id(self, item_id: str) -> Optional[BoardItemModel]:
        return next((item for item in self.board.items if item.id == item_id), None)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectModel":
        schema_version = int(data.get("schema_version", 1))
        if schema_version > SCHEMA_VERSION:
            raise ValueError(
                f"Project schema {schema_version} is newer than supported schema {SCHEMA_VERSION}."
            )

        board_data = data.get("board", {})
        board = BoardModel(
            items=[BoardItemModel(**item) for item in board_data.get("items", [])],
            view_center_x=board_data.get("view_center_x", 0.0),
            view_center_y=board_data.get("view_center_y", 0.0),
            view_scale=board_data.get("view_scale", 1.0),
        )

        compositions: List[CompositionModel] = []
        for composition_data in data.get("compositions", []):
            tracks: List[TrackModel] = []
            for track_data in composition_data.get("tracks", []):
                clips = [ClipModel(**clip) for clip in track_data.get("clips", [])]
                tracks.append(
                    TrackModel(
                        id=track_data["id"],
                        name=track_data["name"],
                        kind=track_data.get("kind", "visual"),
                        muted=track_data.get("muted", False),
                        locked=track_data.get("locked", False),
                        clips=clips,
                    )
                )
            composition_values = {
                key: value
                for key, value in composition_data.items()
                if key != "tracks"
            }
            compositions.append(CompositionModel(tracks=tracks, **composition_values))

        project = cls(
            schema_version=SCHEMA_VERSION,
            name=data.get("name", "Untitled Board"),
            assets=[AssetModel(**asset) for asset in data.get("assets", [])],
            board=board,
            compositions=compositions,
            active_composition_id=data.get("active_composition_id"),
        )
        project.active_composition()
        return project
