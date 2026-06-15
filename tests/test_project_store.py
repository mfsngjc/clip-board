import tempfile
import unittest
from pathlib import Path

from PIL import Image

from clip_board.media import (
    AnimationFrame,
    AssetLibrary,
    export_animation_gif,
    read_animation_frames,
    save_animation_frames,
)
from clip_board.models import BoardItemModel, ProjectModel, new_id
from clip_board.project_store import ProjectStore


class ProjectStoreTests(unittest.TestCase):
    def test_portable_project_round_trip_includes_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (160, 90), "#24B7A4").save(source)

            store = ProjectStore(root / "data")
            library = AssetLibrary(store.workspace.assets_dir)
            asset = library.import_file(source)
            project = ProjectModel.create("Portable")
            project.assets.append(asset)
            project.board.items.append(
                BoardItemModel(
                    id=new_id("item"),
                    kind="media",
                    asset_id=asset.id,
                    width=160,
                    height=90,
                )
            )
            destination = root / "portable.clipboard"

            store.save(project, destination)
            store.workspace.reset()
            loaded = store.load(destination)

            self.assertEqual(loaded.name, "Portable")
            self.assertEqual(len(loaded.assets), 1)
            restored = store.workspace.asset_path(loaded.assets[0].relative_path)
            self.assertTrue(restored.exists())
            self.assertEqual(restored.read_bytes(), source.read_bytes())

    def test_asset_library_deduplicates_the_stored_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (20, 20), "#F07C46").save(source)
            library = AssetLibrary(root / "assets")

            first = library.import_file(source)
            second = library.import_file(source)

            self.assertEqual(first.sha256, second.sha256)
            self.assertEqual(first.relative_path, second.relative_path)
            self.assertEqual(len(list((root / "assets").iterdir())), 1)

    def test_create_gif_preserves_frame_order_and_duration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = AssetLibrary(root / "assets")
            frames = [
                AnimationFrame(Image.new("RGBA", (32, 20), color), duration)
                for color, duration in (
                    ("#E53E3E", 80),
                    ("#38A169", 120),
                    ("#3182CE", 160),
                )
            ]

            asset = library.create_gif(
                [frames[2], frames[0], frames[1]],
                "Reordered.gif",
            )
            stored = root / asset.relative_path
            loaded = read_animation_frames(stored)

            self.assertEqual(asset.name, "Reordered.gif")
            self.assertEqual(asset.frame_count, 3)
            self.assertEqual([frame.duration_ms for frame in loaded], [160, 80, 120])
            self.assertEqual(
                [frame.image.getpixel((0, 0))[:3] for frame in loaded],
                [(49, 130, 206), (229, 62, 62), (56, 161, 105)],
            )

    def test_export_animation_gif_resizes_all_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.gif"
            destination = root / "clipboard" / "scaled.gif"
            frames = [
                AnimationFrame(Image.new("RGBA", (80, 40), color), duration)
                for color, duration in (
                    ("#E53E3E", 90),
                    ("#3182CE", 150),
                )
            ]
            save_animation_frames(frames, source)
            export_animation_gif(source, destination, (40, 20))
            loaded = read_animation_frames(destination)

            self.assertEqual([frame.image.size for frame in loaded], [(40, 20)] * 2)
            self.assertEqual([frame.duration_ms for frame in loaded], [90, 150])


if __name__ == "__main__":
    unittest.main()
