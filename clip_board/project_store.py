from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from .constants import AUTOSAVE_FILENAME
from .models import ProjectModel


class ProjectWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.assets_dir = root / "assets"
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def reset(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def asset_path(self, relative_path: str) -> Path:
        normalized = relative_path.replace("\\", "/")
        if normalized.startswith("assets/"):
            normalized = normalized[len("assets/") :]
        return self.assets_dir / normalized


class ProjectStore:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.workspace = ProjectWorkspace(data_root / "workspace")
        self.autosave_path = data_root / AUTOSAVE_FILENAME
        self.data_root.mkdir(parents=True, exist_ok=True)

    def save(self, project: ProjectModel, destination: Path) -> None:
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=str(destination.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            with zipfile.ZipFile(
                temp_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                manifest = json.dumps(
                    project.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                )
                archive.writestr("project.json", manifest)
                for asset in project.assets:
                    source = self.workspace.asset_path(asset.relative_path)
                    if source.exists():
                        archive.write(source, asset.relative_path)
            os.replace(temp_path, destination)
        finally:
            temp_path.unlink(missing_ok=True)

    def load(self, source: Path) -> ProjectModel:
        source = source.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        self.workspace.reset()
        with zipfile.ZipFile(source, "r") as archive:
            members = archive.namelist()
            if "project.json" not in members:
                raise ValueError("This file does not contain a Clip Board project.")
            for member in members:
                target = (self.workspace.root / member).resolve()
                if self.workspace.root.resolve() not in target.parents and target != self.workspace.root.resolve():
                    raise ValueError("Project contains an unsafe path.")
            archive.extractall(self.workspace.root)
        manifest_path = self.workspace.root / "project.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ProjectModel.from_dict(data)

    def autosave(self, project: ProjectModel) -> None:
        self.save(project, self.autosave_path)

    def restore_autosave(self) -> Optional[ProjectModel]:
        if not self.autosave_path.exists():
            return None
        try:
            return self.load(self.autosave_path)
        except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
            return None

