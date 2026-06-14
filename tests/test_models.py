import unittest

from clip_board.constants import SCHEMA_VERSION
from clip_board.models import BoardItemModel, ClipModel, ProjectModel, new_id


class ProjectModelTests(unittest.TestCase):
    def test_round_trip_preserves_composition_and_clip(self) -> None:
        project = ProjectModel.create("Round Trip")
        track = project.active_composition().tracks[0]
        track.clips.append(
            ClipModel(
                id=new_id("clip"),
                asset_id="asset_test",
                name="Test Clip",
                timeline_start_ms=500,
                source_in_ms=100,
                source_out_ms=2100,
                playback_rate=2.0,
            )
        )

        loaded = ProjectModel.from_dict(project.to_dict())

        self.assertEqual(loaded.name, "Round Trip")
        self.assertEqual(len(loaded.active_composition().tracks), 1)
        clip = loaded.active_composition().tracks[0].clips[0]
        self.assertEqual(clip.duration_ms, 1000)
        self.assertEqual(clip.timeline_start_ms, 500)

    def test_new_project_has_an_editable_track(self) -> None:
        project = ProjectModel.create()
        self.assertEqual(len(project.compositions), 1)
        self.assertEqual(len(project.active_composition().tracks), 1)

    def test_rich_text_round_trip_and_schema_upgrade(self) -> None:
        project = ProjectModel.create("Rich Notes")
        project.schema_version = 1
        project.board.items.append(
            BoardItemModel(
                id=new_id("note"),
                kind="note",
                text="Mixed styles",
                rich_text="<p><b>Mixed</b> styles</p>",
            )
        )

        loaded = ProjectModel.from_dict(project.to_dict())

        self.assertEqual(loaded.schema_version, SCHEMA_VERSION)
        self.assertEqual(
            loaded.board.items[0].rich_text,
            "<p><b>Mixed</b> styles</p>",
        )


if __name__ == "__main__":
    unittest.main()
