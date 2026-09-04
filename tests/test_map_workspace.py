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

    def test_approved_living_map_replaces_the_journal_renderer(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        living_js = (ROOT / "frontend" / "js" / "living-map.js").read_text(encoding="utf-8")
        living_css = (ROOT / "frontend" / "css" / "living-map.css").read_text(encoding="utf-8")
        self.assertIn('window.WorldwalkerLivingMap.open()', js)
        self.assertIn('/js/living-map.js?v=3.57.1-map2', html)
        self.assertIn('grid-template-columns:clamp(205px,17vw,290px) minmax(0,1fr)', living_css)
        self.assertIn('mode: "political"', living_js)
        self.assertNotIn('paintMapTerritories', living_js)
        self.assertIn('data-mobile-view="world" aria-selected="false"><span>⌖</span>Map', html)

    def test_living_map_preserves_tracking_and_world_layer_rules(self):
        js = (ROOT / "frontend" / "js" / "living-map.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "living-map.css").read_text(encoding="utf-8")
        self.assertIn('Math.abs(scoreOf(row)) >= 20', js)
        self.assertIn('/companion|mentor|nemesis/i', js)
        self.assertIn('organization_roster', js)
        self.assertIn('Political', js)
        self.assertIn('Danger', js)
        self.assertIn('Relationships', js)
        self.assertIn('Events', js)
        self.assertIn('radialGradient', js)
        self.assertIn('.lm-marker.is-moving', css)


if __name__ == "__main__":
    unittest.main()
