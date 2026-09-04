import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from systems import map_snapshot
from worlds import BASE_STATE, WORLD_DATA


class MapWorkspaceTests(unittest.TestCase):
    def test_every_map_is_zoom_ready(self):
        from PIL import Image

        for path in (ROOT / "assets" / "generated_maps").glob("*.webp"):
            with self.subTest(path=path.name), Image.open(path) as image:
                self.assertGreaterEqual(image.width, 3840)
                self.assertGreaterEqual(image.height, 2160)

    def test_naruto_canon_polities_use_stable_country_geometry(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", location="Konohagakure")
        regions = map_snapshot(state, WORLD_DATA["Naruto"]["map"], "Naruto")["regions"]
        by_name = {row["name"]: row for row in regions}
        for name in ("Konohagakure", "Sunagakure", "Kirigakure", "Kumogakure", "Iwagakure", "Amegakure", "Iron Country"):
            self.assertEqual(by_name[name]["geometry"], "canon")
            self.assertGreaterEqual(len(by_name[name]["polygon"]), 4)

    def test_naruto_major_and_minor_canon_places_are_plotted(self):
        names = {row[0] for row in WORLD_DATA["Naruto"]["map"]}
        for name in ("Kusagakure", "Takigakure", "Yugakure", "Otogakure", "Uzushiogakure Ruins", "Five Kage Summit"):
            self.assertIn(name, names)

    def test_journal_promotes_map_to_viewport_workspace(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn('classList.toggle("map-workspace", tab === "map")', js)
        self.assertIn("#modal-journal.map-workspace>.modal", css)
        self.assertIn("height:calc(100dvh", css)
        self.assertIn('data-mobile-view="world" aria-selected="false"><span>⌖</span>Map', html)


if __name__ == "__main__":
    unittest.main()
