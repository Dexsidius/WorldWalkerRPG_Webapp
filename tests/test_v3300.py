import copy
import unittest

from worlds import APP_VERSION, BASE_STATE
from state_guard import APP_OWNED, migrate_state
from simulation import refresh_npc_intentions, advance_npc_intentions
from simulation_core import (refresh_simulation_core, companion_support_for_combat,
                             normalize_encounter_state, record_resolution_transaction)
from evaluations import run_local_simulation_evaluation
from game import GameSession


class WorldwalkerV3300SimulationCoreTests(unittest.TestCase):
    def test_release_and_owned_core_records(self):
        self.assertEqual(APP_VERSION, "3.30.0")
        for field in ("capability_profile", "ability_registry", "progression_calibration", "npc_continuity",
                      "encounter_state", "story_threads", "resolution_ledger", "simulation_core_version"):
            self.assertIn(field, BASE_STATE)
            self.assertIn(field, APP_OWNED)

    def test_core_unifies_capability_ability_progression_npcs_and_threads(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", location="Amegakure",
                     stats={"Taijutsu": 80, "Ninjutsu": 120, "Genjutsu": 30, "Chakra Control": 90, "Willpower": 70, "Intellect": 55},
                     skills={"Storm Needle": {"effect": "Pins an enemy with lightning chakra.", "limitation": "Needs line of sight.", "combat_usable": True, "effect_type": "control"}},
                     companions=[{"name": "Konan", "role": "Ranged support", "combat_support": True, "support_bonus": 8}],
                     npc_memories={"Konan": {"goal": "Protect Amegakure", "last_known_location": "Amegakure"},
                                   "Hanzō": {"goal": "Destroy the Akatsuki", "nemesis": True, "recurring": True}},
                     quests=[{"name": "Secure Amegakure", "status": "Active", "next_hint": "Win local support"}])
        refresh_simulation_core(state, ["Train Storm Needle through daily chakra drills"], 43200)
        self.assertEqual(state["capability_profile"]["power"]["peak"]["score"], 120)
        self.assertTrue(state["ability_registry"]["Storm Needle"]["mechanics"]["counterplay"])
        self.assertGreater(state["progression_calibration"]["expected_primary_gain"]["typical"], 0)
        self.assertTrue(state["npc_continuity"]["Hanzō"]["nemesis"])
        self.assertEqual(companion_support_for_combat(state)[0]["bonus"], 8)
        self.assertIn("quest:secure amegakure", state["story_threads"])

    def test_encounter_lifecycle_and_resolution_transaction(self):
        state = copy.deepcopy(BASE_STATE)
        before = copy.deepcopy(state)
        state["combat"] = {"active": True, "enemy": {"name": "Bandit"}}
        self.assertEqual(normalize_encounter_state(state)["phase"], "active_combat")
        state["combat"].update(active=False, outcome="victory")
        self.assertEqual(normalize_encounter_state(state)["phase"], "aftermath")
        state["stats"]["Strength"] += 3
        tx = record_resolution_transaction(state, before, ["Train with weighted drills"], 1440, "The training works.")
        self.assertEqual(tx["phases"]["mechanics"]["stat_changes"]["Strength"], 3)

    def test_nemesis_flag_survives_intention_system_and_advances_slowly(self):
        state = copy.deepcopy(BASE_STATE)
        state["npc_memories"] = {"Nemesis": {"goal": "A long scheme", "nemesis": True, "recurring": True}}
        row = refresh_npc_intentions(state)["Nemesis"]
        self.assertTrue(row["nemesis"])
        advance_npc_intentions(state, 14400)
        self.assertLess(state["npc_intentions"]["Nemesis"]["progress"], 10)

    def test_existing_nemesis_and_combat_support_flags_reach_gm_and_combat(self):
        game = GameSession()
        game.state.update(world="Naruto", location="Amegakure",
                          companions=[{"name": "Konan", "combat_support": True, "support_bonus": 9}],
                          npc_memories={"Konan": {"goal": "Protect Yahiko"},
                                        "Hanzō": {"nemesis": True, "goal": "Break the Akatsuki"}},
                          combat={"active": True, "enemy": {"name": "Hanzō's guard", "power": 60,
                                                              "hp": 100, "hp_max": 100}})
        prompt_state = game.task_state_for_ai("moment")
        role_flags = {row["name"]: row for row in prompt_state["npc_role_flags"]}
        self.assertTrue(role_flags["Hanzō"]["nemesis"])
        self.assertTrue(role_flags["Konan"]["combat_support"])
        game.ensure_combat_numbers()
        self.assertEqual(game.state["combat"]["ally_support"], 9)
        self.assertEqual(game.state["combat"]["supporting_companions"][0]["name"], "Konan")

    def test_migration_backfills_core_and_local_evaluator_is_free(self):
        migrated = migrate_state({"world": "Bleach", "schema_version": 19}, "3.29.0")
        self.assertTrue(migrated["capability_profile"])
        report = run_local_simulation_evaluation()
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["ai_calls"], 0)
        self.assertEqual(report["estimated_cost_usd"], 0.0)


if __name__ == "__main__":
    unittest.main()
