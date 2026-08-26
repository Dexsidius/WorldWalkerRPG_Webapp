import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from simulation import deterministic_assessment
from worlds import APP_VERSION, BASE_STATE, abilities_for


class WorldwalkerV3121ProgressionAndQATests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(APP_VERSION, "3.12.1")

    def make_system_game(self, world):
        game = GameSession()
        game.settings["autosave"] = False
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "name": "QA Traveler", "world": world, "difficulty": "Adventurer",
            "stats": {name: 20 for name in abilities_for(world)},
            "special": {"Archetype": "Blacksmith" if world == "Overgeared" else "All-Rounder"},
            "titles": ["Early Adopter"], "opening_complete": True,
            "campaign_id": f"qa-{world}", "xp": 0, "xp_next": 100, "level": 1,
        })
        game.campaign_active = True
        return game

    def test_ordinary_numbered_kido_practice_is_not_a_power_leap(self):
        state = copy.deepcopy(BASE_STATE)
        state.update({"world": "Bleach", "stats": {name: 25 for name in abilities_for("Bleach")}})
        action = "Practice Bakudo #1 and Hado #4 for an hour"
        assessment = deterministic_assessment(
            state, [action], {"reachable_actions": [action], "deferred_actions": [], "time_dc_modifier": 0}
        )
        self.assertFalse(assessment.get("power_jump_warning"))
        self.assertEqual(assessment["checks"], [])

    def test_named_sensor_skill_trains_chakra_control_not_taijutsu(self):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "world": "Naruto", "difficulty": "Adventurer",
            "stats": {name: 30 for name in abilities_for("Naruto")},
            "skills": {"Echo Thread Technique": {
                "description": "Forms fine chakra threads for precise attacks, traps, sensing, or utility.",
                "growth_path": "Improve chakra control and learn matching nature transformation.",
            }},
        })
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("engine_time.random.random", return_value=1.0):
            game.enforce_training_progress(data, [], 7, "days", ["Train Echo Thread Technique"], "normal")
        self.assertGreater(data["state_patch"]["stats"]["Chakra Control"],
                           data["state_patch"]["stats"]["Taijutsu"])
        self.assertEqual(data["state_patch"]["progression_log"][-1]["ability"], "Chakra Control")

    def test_successful_opening_check_changes_combat_state_once(self):
        game = self.make_system_game("Overgeared")
        game.state["combat"] = {
            "active": True, "round": 1,
            "enemy": {"name": "Elite Guardian", "hp": 200, "hp_max": 200, "power": 45},
            "opening_check": {"success": True, "total": 92, "difficulty": 80,
                              "margin": 12, "ability": "Strength", "breakthrough": False},
        }
        game.ensure_combat_numbers()
        first_hp = game.state["combat"]["enemy"]["hp"]
        self.assertLess(first_hp, 200)
        self.assertEqual(game.state["combat"]["opening_advantage"]["remaining_hp"], first_hp)
        game.ensure_combat_numbers()
        self.assertEqual(game.state["combat"]["enemy"]["hp"], first_hp)

    def test_overgeared_skip_tracks_training_xp_and_persistent_earned_title(self):
        game = self.make_system_game("Overgeared")
        before = copy.deepcopy(game.state)
        award = game.calculate_xp_award(["Train blacksmithing every day"], [], 7 * 1440, "normal", [])[0]
        game.apply_system_xp(before, ["Train blacksmithing every day"], [], 7 * 1440, "normal", [])
        game.reconcile_title_events([{"type": "title", "title": "Patient Artisan",
                                      "message": "Title acquired: Patient Artisan"}])
        self.assertEqual(game.state["progression_log"][-1]["xp_awarded"], award)
        self.assertEqual(game.state["xp"], award)
        self.assertIn("Early Adopter", game.state["titles"])
        self.assertIn("Patient Artisan", game.state["titles"])
        notices = game.notify(before, game.state, [])
        self.assertTrue(any(f"XP +{award}" in row["message"] for row in notices))
        self.assertTrue(any("TITLE ACQUIRED: Patient Artisan" in row["message"] for row in notices))

    def test_solo_level_up_reports_xp_even_when_bar_returns_to_same_value(self):
        game = self.make_system_game("Solo Max-Level Newbie")
        award = game.calculate_xp_award(["Defeat the floor guardian"], [], 60, "normal", [])[0]
        game.state["xp_next"] = award
        before = copy.deepcopy(game.state)
        game.apply_system_xp(before, ["Defeat the floor guardian"], [], 60, "normal", [])
        game.reconcile_title_events([{"type": "world", "message": "Earned the title: Gate Breaker"}])
        self.assertEqual(game.state["xp"], 0)
        self.assertEqual(game.state["level"], 2)
        self.assertEqual(game.state["progression_log"][-1]["xp_awarded"], award)
        self.assertIn("Gate Breaker", game.state["titles"])
        notices = game.notify(before, game.state, [])
        self.assertTrue(any(f"XP +{award}" in row["message"] for row in notices))
        self.assertTrue(any("LEVEL UP" in row["message"] for row in notices))

    def test_xp_notice_survives_a_capped_progression_ledger(self):
        game = self.make_system_game("Overgeared")
        game.state["turn"] = 400
        game.state["progression_log"] = [
            {"type": "xp", "turn": turn, "xp_awarded": 1} for turn in range(101, 401)
        ]
        before = copy.deepcopy(game.state)
        game.apply_system_xp(before, ["Study a new production method"], [], 60, "normal", [])
        self.assertEqual(len(game.state["progression_log"]), 300)
        notices = game.notify(before, game.state, [])
        self.assertTrue(any("XP +" in row["message"] for row in notices))

    def test_title_patch_cannot_erase_older_titles(self):
        game = self.make_system_game("Overgeared")
        from state_guard import apply_guarded_patch
        apply_guarded_patch(game.state, {"titles": ["Commission Finisher"]}, source="test")
        self.assertEqual(game.state["titles"], ["Early Adopter", "Commission Finisher"])

    def test_missing_goal_status_gets_a_deterministic_incomplete_explanation(self):
        class GoalOmittingNarrator:
            model = "goal-omitting-test"

            def request(self, rules, payload, max_output_tokens=0):
                return {
                    "narrative": "The training period ends with the technique still unstable.",
                    "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 3, "unit": "days"}, "interrupted": False,
                    "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["Seek a chakra-control instructor"],
                }

        game = GameSession()
        game.settings["autosave"] = False
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update({
            "world": "Naruto", "difficulty": "Adventurer", "canon_day": 5000,
            "calendar_anchor_day": 5000,
            "stats": {name: 30 for name in abilities_for("Naruto")},
            "opening_complete": True,
        })
        game.ai = GoalOmittingNarrator()
        action = "Train until I master the Echo Thread Technique"
        result = game.run_time_skip(
            3, "days", [action], "normal",
            {"checks": [], "reachable_actions": [action], "deferred_actions": []},
        )
        self.assertFalse(result["goal_status"]["achieved"])
        self.assertIn("without confirming", result["goal_status"]["explanation"])
        self.assertTrue(result["goal_status"]["next_hint"])
        self.assertTrue(any("GOAL NOT YET COMPLETE" in row["text"] for row in result["story"]))

    def test_frontend_exposes_world_clock_progress_and_grouped_one_piece_starts(self):
        source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("entry.world_time", source)
        self.assertIn("CURRENT SCENE", source)
        self.assertIn("% to next point", source)
        self.assertIn("Selected skip: next major event", source)
        self.assertIn("<optgroup", source)
        self.assertIn('debuff: "⛓ "', source)


if __name__ == "__main__":
    unittest.main()
