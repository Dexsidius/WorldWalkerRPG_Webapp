import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from systems import (
    campaign_health, map_snapshot, normalize_quest_state_machine,
    normalize_tuning, relationship_snapshot, tick_world_clocks, update_chapter_memory,
)
from continuity import update_continuity
from state_guard import migrate_state
from worlds import BASE_STATE, WORLD_DATA, abilities_for, format_calendar_date, timeline_for, expansion_for, start_options_for, starting_era_by_id, power_tier_reference


class PlanningAI:
    def request(self, rules, payload, max_output_tokens=0):
        if payload["task"] == "assess_time_skip":
            return {
                "checks": [{"id": "hard", "reason": "Overcome the veteran", "ability": "Taijutsu", "skill": None,
                            "difficulty_min": 82, "difficulty_max": 88, "relevant_average_stat": 35,
                            "situational_bonus": 0, "time_difficulty_modifier": 0, "major_event": False,
                            "lethal_risk": "moderate"}],
                "reachable_actions": payload["planned_actions"], "deferred_actions": [],
            }
        return {
            "narrative": "The world moves through several grounded developments until the next major pressure arrives.",
            "updates": [{"sequence": 1, "type": "world_event", "title": "Rumors spread", "narrative": "A courier brings delayed news.",
                         "why_it_matters": "A nearby faction is mobilizing.", "player_knowledge": "The courier is credible but did not witness the cause.",
                         "next_pressure": "The road may close soon."}],
            "state_patch": {}, "events": [], "timeline_events": [], "elapsed": {"amount": 2, "unit": "days"},
            "interrupted": False, "completed_actions": payload.get("planned_actions", []), "deferred_actions": [],
            "major_event_reached": True, "major_event_kind": "personal", "major_event_title": "A Rival Arrives",
            "suggested_actions": ["Question the courier about the closed road", "Train Taijutsu before meeting the rival", "Visit the gate to inspect the mobilization"],
        }


class WorldwalkerV260Tests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        game = GameSession()
        game.state = copy.deepcopy(BASE_STATE)
        game.state.update(name="Ari", world=world, location=WORLD_DATA[world]["map"][0][0],
                          stats={name: 35 for name in abilities_for(world)},
                          special={"Archetype": "Adventurer"})
        return game

    def test_difficult_check_preview_warns_before_resolution(self):
        game = self.fresh()
        game.ai = PlanningAI()
        result = game.assess_time_skip(1, "days", "Challenge the veteran", "normal")
        self.assertTrue(result["assessment"]["requires_difficulty_confirmation"])
        self.assertEqual(result["assessment"]["difficult_checks"][0]["id"], "hard")
        self.assertGreaterEqual(result["assessment"]["difficult_checks"][0]["expected_raw_needed"], 65)

    def test_next_event_mode_has_no_quantity_and_natural_stop(self):
        game = self.fresh()
        game.ai = PlanningAI()
        assessed = game.assess_time_skip(77, "next_event", "Continue training", "normal")
        self.assertEqual(assessed["amount"], 1)
        self.assertTrue(assessed["time_budget"]["event_driven_major"])
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal",
                                    {**assessed["assessment"], "checks": []})
        self.assertTrue(result["major_event_reached"])
        self.assertFalse(result["interrupted"])
        self.assertEqual(result["intervention_prompt"], "")

    def test_time_skip_beats_carry_chip_map_change_and_quote_detail(self):
        # Pax Historia-style dense feed: a multi-day skip's dated beats
        # should carry enough structured extra to render as a rich card
        # (entity chips, a rare map-control change, a rare pull-quote)
        # instead of a plain paragraph — but only when the AI actually
        # supplied them, and derived from the same **bolded** convention
        # already used for Codex linking, not a separate AI field, so it
        # can never drift out of sync with what the prose actually bolds.
        class RichBeatAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload["task"] == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}
                return {
                    "narrative": "The week unfolds.",
                    "updates": [
                        {"sequence": 1, "type": "faction_reaction", "title": "Dawn of the Shadow Multiverse",
                         "canon_day": 3, "narrative": "**Shizuno** stands with the **Empire of the End** as the **Spire of Infinity** stabilizes a bridge to **Reality-701**.",
                         "why_it_matters": "", "player_knowledge": "", "next_pressure": "",
                         "map_changes": ["The Empire of the End gains a foothold in Reality-701", "  "],
                         "quote": {"text": "The first bridge is stable.", "speaker": "Solomon"}},
                        {"sequence": 2, "type": "world_event", "title": "Quiet Day", "canon_day": 4,
                         "narrative": "Little of note happens.", "why_it_matters": "", "player_knowledge": "", "next_pressure": ""},
                    ],
                    "state_patch": {}, "events": [], "timeline_events": [], "elapsed": {"amount": 7, "unit": "days"},
                    "interrupted": False, "completed_actions": [], "deferred_actions": [],
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "suggested_actions": ["Continue", "Rest", "Investigate"],
                }

        game = self.fresh("Reincarnated as a Slime")
        game.ai = RichBeatAI()
        assessed = game.assess_time_skip(7, "days", "Let the week play out", "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        story = result["story"]

        rich = next(e for e in story if "DAWN OF THE SHADOW MULTIVERSE" in e["text"])
        self.assertEqual(rich["canon_day"], 3)
        self.assertEqual(set(rich["detail"]["entities"]), {"Shizuno", "Empire of the End", "Spire of Infinity", "Reality-701"})
        # A blank/whitespace-only entry is dropped rather than showing up as
        # an empty line in the map-changes list.
        self.assertEqual(rich["detail"]["map_changes"], ["The Empire of the End gains a foothold in Reality-701"])
        self.assertEqual(rich["detail"]["quote"], {"text": "The first bridge is stable.", "speaker": "Solomon"})

        # A beat with no bolded names, no map change, and no quote carries
        # no detail at all — the plain-paragraph rendering it already had.
        quiet = next(e for e in story if "QUIET DAY" in e["text"])
        self.assertIsNone(quiet.get("detail"))

    def test_minigame_roll_can_replace_a_regular_check(self):
        game = self.fresh()
        game.ai = PlanningAI()
        result = game.run_time_skip(1, "days", ["Challenge the veteran"], "normal",
                                    {"checks": [{"id": "hard", "reason": "Veteran", "ability": "Taijutsu",
                                                 "difficulty_min": 70, "difficulty_max": 70, "situational_bonus": 0,
                                                 "time_difficulty_modifier": 0, "major_event": False, "lethal_risk": "none"}]},
                                    manual_rolls={"hard": 91}, challenge_modes={"hard": "timing"})
        self.assertEqual(result["status"], "resolved")
        self.assertTrue(any("Timing 91" in entry["text"] for entry in result["story"]))

    def test_moment_keeps_later_queued_actions_for_next_advance(self):
        game = self.fresh()
        game.ai = PlanningAI()
        game.state["queued_actions"] = ["Inspect the signal post", "Question the border patrol"]
        assessed = game.assess_time_skip(9, "moment", [], "normal")
        self.assertEqual(assessed["orders"], ["Inspect the signal post"])
        self.assertEqual(assessed["assessment"]["deferred_actions"], ["Question the border patrol"])
        assessed["assessment"]["checks"] = []
        result = game.run_time_skip(1, "moment", assessed["orders"], "normal", assessed["assessment"])
        self.assertEqual(result["state"]["queued_actions"], ["Question the border patrol"])

    def test_chapter_memory_consolidates_every_game_quarter(self):
        """Chapters track in-game time (roughly a season/quarter), not a
        fixed action count — a few busy turns spanning only a day or two
        should not already close out a chapter."""
        state = copy.deepcopy(BASE_STATE)
        state.update(name="Ari", world="Naruto", location="Konohagakure", canon_day=-7)
        before = copy.deepcopy(state)
        chapter = None
        for index in range(6):
            state["turn"] = index + 1
            state["canon_day"] = -7 + index
            chapter = update_chapter_memory(before, state, f"Decision {index + 1}", f"Beat {index + 1} changes the situation.")
            before = copy.deepcopy(state)
        self.assertIsNone(chapter)
        self.assertEqual(state.get("chapter_summaries", []), [])

        for index in range(6, 100):
            state["turn"] = index + 1
            state["canon_day"] = -7 + index
            chapter = update_chapter_memory(before, state, f"Decision {index + 1}", f"Beat {index + 1} changes the situation.")
            before = copy.deepcopy(state)
            if chapter:
                break
        self.assertIsNotNone(chapter)
        self.assertEqual(len(state["chapter_summaries"]), 1)
        self.assertEqual(state["chapter_buffer"], [])

    def test_chapter_memory_backstop_fires_without_much_date_movement(self):
        """A long dialogue-heavy stretch that barely advances canon_day
        should still eventually close a chapter, via the beat-count
        backstop, rather than never consolidating at all."""
        state = copy.deepcopy(BASE_STATE)
        state.update(name="Ari", world="Naruto", location="Konohagakure", canon_day=-7)
        before = copy.deepcopy(state)
        chapter = None
        for index in range(24):
            state["turn"] = index + 1
            chapter = update_chapter_memory(before, state, f"Decision {index + 1}", f"Beat {index + 1} changes the situation.")
            before = copy.deepcopy(state)
        self.assertIsNotNone(chapter)
        self.assertEqual(len(state["chapter_summaries"]), 1)

    def test_quests_clocks_map_tuning_and_health_are_structured(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", location="Konohagakure", discovered_locations=["Konohagakure"],
                     quests=[{"name": "Find the Scout", "clear_conditions": ["Locate the scout"]}],
                     factions={"Akatsuki": {"status": "hidden"}},
                     npc_memories={"Rin": {"goal": "Find the lost archive", "importance": "major"}})
        normalize_quest_state_machine(state)
        self.assertEqual(state["quests"][0]["objectives"][0]["status"], "active")
        tick_world_clocks(state, 1440)
        self.assertGreater(state["faction_clocks"]["Akatsuki"]["progress"], 0)
        self.assertGreater(state["npc_clocks"]["Rin"]["progress"], 0)
        tuning = normalize_tuning(state)
        self.assertIn("training_rate", tuning)
        atlas = map_snapshot(state, WORLD_DATA["Naruto"]["map"], "Naruto")
        self.assertTrue(any(node["current"] for node in atlas["nodes"]))
        self.assertIn("score", campaign_health(state))

    def test_new_ui_surfaces_and_chronicle_nonshrinking_css_exist(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        for marker in ('value="next_event"', 'id="modal-difficult-check"', 'id="modal-timing-challenge"',
                       'id="modal-tactical-challenge"', 'data-tab="chapters"', 'data-tab="health"'):
            self.assertIn(marker, html)
        self.assertIn('event.target.id === "lore-import-form"', js)
        self.assertIn('.story-beat{ flex:0 0 auto; width:100%; min-width:0; min-height:max-content;', css)
        self.assertIn('.story-entry{ flex:0 0 auto; width:100%; min-width:0;', css)

    def test_starting_era_and_canon_character_anchor_their_own_calendar(self):
        """A campaign that begins somewhere other than the world's default
        start_day (a chosen starting era, or a canon character born/starting
        far from that default) must read Year 1 on its own opening day, not
        some nonsense negative year computed against a start_day it never
        actually used."""
        stats = {name: 30 for name in abilities_for("Naruto")}
        era_game = GameSession()
        era_game.new_campaign("Kagome", "Naruto", "Adventurer", "", "", "", "Academy Student",
                               "Ninjutsu Student", stats, starting_era_id="third_shinobi_war")
        self.assertEqual(era_game.state["canon_day"], -4900)
        self.assertEqual(era_game.state["calendar_anchor_day"], -4900)
        self.assertIn("Year 1", era_game.state["world_time"])

        canon_game = GameSession()
        canon_game.new_campaign("unused", "Naruto", "Adventurer", "", "", "", "Academy Student",
                                 "Ninjutsu Student", stats, canon_character_id="naruto_birth")
        self.assertEqual(canon_game.state["calendar_anchor_day"], -4380)
        self.assertIn("Year 1", canon_game.state["world_time"])

        default_game = GameSession()
        default_game.new_campaign("Ari", "Naruto", "Adventurer", "", "", "", "Academy Student",
                                   "Ninjutsu Student", stats)
        self.assertEqual(default_game.state["calendar_anchor_day"], -7)
        self.assertIn("Year 1", default_game.state["world_time"])

    def test_old_save_without_calendar_anchor_falls_back_to_world_default(self):
        state = copy.deepcopy(BASE_STATE)
        state.update(world="Naruto", canon_day=-7)
        del state["calendar_anchor_day"]
        migrated = migrate_state(state)
        self.assertIsNone(migrated["calendar_anchor_day"])
        self.assertEqual(format_calendar_date("Naruto", -7, None, migrated["calendar_anchor_day"]), "January 1, Year 1")

    def test_calendar_and_starting_era_smoke_markers(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        for marker in ('id="nc-era-row"', 'id="nc-starting-era"', 'id="nc-era-note"'):
            self.assertIn(marker, html)
        for marker in ("function formatCalendarDate", "function refreshEraRow", "WORLD_CALENDAR_MONTHS",
                       "hasOwnTitle", "isContinuation", "calendar_anchor_day"):
            self.assertIn(marker, js)
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".story-entry.continuation", css)

    def test_dict_shaped_title_from_a_weaker_model_does_not_crash(self):
        """titles gets diffed with set() in two hot paths (continuity ledger,
        per-turn notify messages) on every single turn. A weaker/local model
        that returns a title as {"title": "...", "reason": "..."} instead of
        a plain string used to raise TypeError: unhashable type: 'dict' and
        crash the turn outright."""
        game = self.fresh()
        before = copy.deepcopy(game.state)
        before["titles"] = ["Academy Graduate"]
        after = copy.deepcopy(game.state)
        after["titles"] = ["Academy Graduate", {"title": "Bridge Survivor"}]
        update_continuity(before, after, "Cross the bridge", "The bridge holds.")
        title_facts = [f["text"] for f in after["continuity_ledger"]["facts"] if f["type"] == "title"]
        self.assertTrue(any("Bridge Survivor" in t for t in title_facts))
        self.assertNotIn("{'title'", " ".join(title_facts))
        msgs = [m["message"] for m in game.notify(before, after, [])]
        self.assertTrue(any("Bridge Survivor" in m for m in msgs))
        self.assertNotIn("{'title'", " ".join(msgs))

    def test_next_event_mode_floor_reaches_a_nearby_canon_event(self):
        """A weak/local model that keeps calling a trivial beat a "major
        personal event" only a sliver into the available window used to make
        'next major event' mode crawl forward by a shrinking fraction of the
        remaining time each click — asymptotically approaching a nearby fixed
        canon event (e.g. the Nine-Tails attack, 7 days into a campaign that
        starts a week before it) without ever actually reaching it, even
        across many clicks. The elapsed time is now floored so real forward
        progress happens on every call regardless of how eager the model is."""
        class OverEagerAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                budget = payload.get("next_major_event_mode", {}).get("max_elapsed_minutes", 1440)
                claimed = max(1, int(budget * 0.1))
                return {
                    "narrative": "A minor thing happens.",
                    "updates": [{"sequence": 1, "type": "consequence", "title": "Ran into an old acquaintance",
                                 "narrative": "Small talk.", "why_it_matters": "", "player_knowledge": "", "next_pressure": ""}],
                    "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": claimed, "unit": "minutes"},
                    "interrupted": False, "major_event_reached": True, "major_event_kind": "personal",
                    "major_event_title": "Ran into an old acquaintance",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Kushina Watcher", "Naruto", "Adventurer", "", "", "", "Academy Student",
                           "Ninjutsu Student", {n: 30 for n in abilities_for("Naruto")}, starting_era_id="before_naruto_birth")
        game.ai = OverEagerAI()
        for _ in range(3):
            assessed = game.assess_time_skip(1, "next_event", [], "normal")
            game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
            if game.state.get("canon_events_fired"):
                break
        self.assertIn("day:-4380:Naruto's birth and the Nine-Tails attack", game.state.get("canon_events_fired", []))

    def test_gm_rules_separate_past_canon_events_from_upcoming(self):
        """A campaign that starts after a canon event (e.g. the default
        Academy Graduation start, well after the Nine-Tails attack) must be
        told that event is settled history, not left to its own background
        knowledge — otherwise it can narrate an already-past event as if it
        were still approaching. A campaign that starts before that same
        event must see it under upcoming pressures instead."""
        after_game = self.fresh()
        after_rules = after_game.gm_rules()
        history_line = next(line for line in after_rules.splitlines() if line.startswith("CANON HISTORY"))
        upcoming_line = next(line for line in after_rules.splitlines() if line.startswith("UPCOMING CANON PRESSURES"))
        self.assertIn("Naruto's birth and the Nine-Tails attack", history_line)
        self.assertNotIn("Naruto's birth and the Nine-Tails attack", upcoming_line)

        before_game = GameSession()
        before_game.new_campaign("B", "Naruto", "Adventurer", "", "", "", "Academy Student",
                                  "Ninjutsu Student", {n: 30 for n in abilities_for("Naruto")}, starting_era_id="before_naruto_birth")
        before_rules = before_game.gm_rules()
        before_history = next(line for line in before_rules.splitlines() if line.startswith("CANON HISTORY"))
        before_upcoming = next(line for line in before_rules.splitlines() if line.startswith("UPCOMING CANON PRESSURES"))
        self.assertNotIn("Naruto's birth and the Nine-Tails attack", before_history)
        self.assertIn("Naruto's birth and the Nine-Tails attack", before_upcoming)

    def test_canon_boundary_only_interrupts_when_narrator_says_player_is_present(self):
        """Reaching a fixed canon event used to always force interrupted=True
        and a 'will you intervene' prompt, even for a player nowhere near it.
        The narrator now judges plausible presence itself (per gm_rules); the
        engine should trust that call instead of overriding it, while still
        always advancing canon_day and marking the event fired correctly."""
        class ScriptedAI:
            def __init__(self, interrupted):
                self.interrupted = interrupted

            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                return {
                    "narrative": "Time passes.",
                    "updates": [{"sequence": 1, "type": "canon_event", "title": "Event", "narrative": "Something happens.",
                                 "why_it_matters": "", "player_knowledge": "", "next_pressure": ""}],
                    "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 10080, "unit": "minutes"},
                    "interrupted": self.interrupted,
                    "interruption_kind": "canon_event" if self.interrupted else "",
                    "interruption_reason": "" if not self.interrupted else "On the scene.",
                    "interruption_context": "", "intervention_prompt": "" if not self.interrupted else "Will you act?",
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        for interrupted_flag in (False, True):
            with self.subTest(interrupted=interrupted_flag):
                game = GameSession()
                game.new_campaign("Traveler", "Naruto", "Adventurer", "", "", "", "Academy Student",
                                   "Ninjutsu Student", {n: 30 for n in abilities_for("Naruto")}, starting_era_id="before_naruto_birth")
                # The player's tracked location starts matching the event's
                # location (Konohagakure) by default, which now hardcodes
                # interrupted=True regardless of what the model says — move
                # the player elsewhere for the "far away, trust the model's
                # own False" half of this test.
                if not interrupted_flag:
                    game.state["location"] = "Sunagakure"
                game.ai = ScriptedAI(interrupted_flag)
                assessed = game.assess_time_skip(30, "days", ["Continue"], "normal")
                result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
                self.assertEqual(result["interrupted"], interrupted_flag)
                self.assertEqual(bool(result.get("intervention_prompt")), interrupted_flag)
                self.assertEqual(game.state["canon_day"], -4380)
                self.assertIn("day:-4380:Naruto's birth and the Nine-Tails attack", game.state["canon_events_fired"])

    def test_canon_boundary_defaults_to_absence_when_model_omits_interrupted(self):
        """If the model leaves `interrupted` out entirely for a player who
        isn't at the event's location, the safe default is absence (a report
        the player reads, not a forced live scene with canon figures they
        were never established as being near) — the previous default of
        presence made every player forgetting to omit this into a forced
        cameo, exactly what the plausibility rule exists to prevent."""
        class OmittingAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                return {
                    "narrative": "Time passes.",
                    "updates": [{"sequence": 1, "type": "canon_event", "title": "Event", "narrative": "Something happens elsewhere.",
                                 "why_it_matters": "", "player_knowledge": "", "next_pressure": ""}],
                    "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 10080, "unit": "minutes"},
                    # `interrupted` deliberately omitted — simulates a model
                    # that didn't comply with the schema for this field.
                    "interruption_kind": "", "interruption_reason": "",
                    "interruption_context": "", "intervention_prompt": "",
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Traveler", "Naruto", "Adventurer", "", "", "", "Academy Student",
                           "Ninjutsu Student", {n: 30 for n in abilities_for("Naruto")}, starting_era_id="before_naruto_birth")
        game.state["location"] = "Sunagakure"  # far from Konohagakure, where the event fires
        game.ai = OmittingAI()
        assessed = game.assess_time_skip(30, "days", ["Continue"], "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertFalse(result["interrupted"])
        self.assertFalse(result.get("intervention_prompt"))

    def test_personal_scope_event_is_not_forced_by_shared_village_location(self):
        """A real report: the Mizuki/scroll-theft incident forced the player
        into a live scene just because their tracked location was also
        Konohagakure — being in the same enormous village a small, secretive
        incident happens in is not the same as being in the room for it.
        Only a 'wide' scope event (the whole village genuinely affected)
        should let shared location alone force presence; a 'personal' scope
        event (the default) must fall through to the model's own judgment,
        which an oblivious model still gets wrong here without an
        established tie to Naruto — proving the location-only hardcode is
        actually gone for this class of event."""
        mizuki_event = next(e for e in timeline_for("Naruto")["events"] if "Mizuki" in e.get("title", ""))
        self.assertEqual(mizuki_event.get("scope", "personal"), "personal")

        class ObliviousAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                return {
                    "narrative": "Time passes.", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 14400, "unit": "minutes"},
                    "interrupted": False, "interruption_kind": "", "interruption_reason": "",
                    "interruption_context": "", "intervention_prompt": "",
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Traveler", "Naruto", "Adventurer", "", "", "", "Academy Student",
                           "Ninjutsu Student", {n: 30 for n in abilities_for("Naruto")})
        self.assertEqual(game.state["location"], "Konohagakure")  # same village as the Mizuki incident
        game.ai = ObliviousAI()
        assessed = game.assess_time_skip(10, "days", ["Continue"], "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertFalse(result["interrupted"])
        self.assertFalse(result.get("intervention_prompt"))

    def test_wide_scope_event_still_forces_interruption_on_shared_location(self):
        # The opposite side of the same fix: a genuinely village-wide event
        # (everyone here is affected) still hardcodes presence on shared
        # location, exactly as before — only personal-scope events lost
        # that hardcode.
        nine_tails = next(e for e in timeline_for("Naruto")["events"] if "Nine-Tails attack" in e.get("title", ""))
        self.assertEqual(nine_tails.get("scope"), "wide")

    def test_power_goal_chance_hits_the_two_stated_checkpoints(self):
        # 80% at a month of committed effort, guaranteed after one further
        # week — the two concrete numbers actually asked for.
        self.assertEqual(GameSession._power_goal_chance(0), 0.0)
        self.assertAlmostEqual(GameSession._power_goal_chance(30), 0.8)
        self.assertAlmostEqual(GameSession._power_goal_chance(37), 1.0)
        self.assertEqual(GameSession._power_goal_chance(50), 1.0)
        self.assertGreater(GameSession._power_goal_chance(15), 0.0)
        self.assertLess(GameSession._power_goal_chance(15), 0.8)

    def test_power_goal_progress_accumulates_on_the_same_goal_and_resets_on_a_new_one(self):
        game = GameSession()
        game.new_campaign("Traveler", "One Piece", "Adventurer", "", "", "", "Cabin Boy",
                           "Swordsman", {n: 30 for n in abilities_for("One Piece")})
        first = game._check_power_goal_progress(["Train relentlessly to learn Haki"], 20)
        self.assertEqual(first["days_invested"], 20)
        second = game._check_power_goal_progress(["Train relentlessly to learn Haki"], 15)
        self.assertEqual(second["days_invested"], 35)  # same goal text — accumulates
        different = game._check_power_goal_progress(["Master swordsmanship fundamentals"], 10)
        self.assertEqual(different["days_invested"], 10)  # different goal — starts over
        no_goal = game._check_power_goal_progress(["Buy supplies at the market"], 10)
        self.assertIsNone(no_goal)  # no power-goal keyword present at all

    def test_run_time_skip_gates_on_power_jump_warning_until_confirmed(self):
        class ScriptedAI:
            def __init__(self):
                self.resolve_calls = 0

            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": [],
                            "power_jump_warning": "The old master's warning echoes: power like this always demands its price."}
                self.resolve_calls += 1
                self.last_payload = payload
                power_goal = payload.get("power_goal_progress") or {}
                achieved = bool(power_goal.get("mechanical_success"))
                return {
                    "narrative": "Time passes.", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 43200, "unit": "minutes"},
                    "interrupted": False, "interruption_kind": "", "interruption_reason": "",
                    "interruption_context": "", "intervention_prompt": "",
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {"action": "learn Haki", "achieved": achieved, "elapsed": {"amount": 43200, "unit": "minutes"}, "explanation": "", "next_hint": ""},
                    "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Traveler", "One Piece", "Adventurer", "", "", "", "Cabin Boy",
                           "Swordsman", {n: 30 for n in abilities_for("One Piece")})
        ai = ScriptedAI()
        game.ai = ai
        assessed = game.assess_time_skip(30, "days", ["Train relentlessly to learn Haki"], "normal")
        gated = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertEqual(gated["status"], "power_goal_confirm_required")
        self.assertIn("price", gated["warning"])
        self.assertEqual(ai.resolve_calls, 0)  # gated before the expensive resolve call
        confirmed = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"],
                                        confirmed_power_goal=True)
        self.assertEqual(confirmed["status"], "resolved")
        self.assertEqual(ai.resolve_calls, 1)

    def test_power_goal_mechanically_forces_success_once_days_cross_the_threshold(self):
        class ScriptedAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                power_goal = payload.get("power_goal_progress") or {}
                # A deliberately pessimistic model — it would say "not yet"
                # on its own. The mechanical push must override that.
                achieved = bool(power_goal.get("mechanical_success"))
                return {
                    "narrative": "Time passes.", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 43200, "unit": "minutes"},
                    "interrupted": False, "interruption_kind": "", "interruption_reason": "",
                    "interruption_context": "", "intervention_prompt": "",
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {"action": "learn Haki", "achieved": achieved, "elapsed": {"amount": 43200, "unit": "minutes"}, "explanation": "", "next_hint": ""},
                    "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Traveler", "One Piece", "Adventurer", "", "", "", "Cabin Boy",
                           "Swordsman", {n: 30 for n in abilities_for("One Piece")})
        # Already past the guaranteed threshold from prior committed days.
        game.state["power_goal_tracker"] = {"key": "train relentlessly to learn haki", "days_invested": 40.0}
        game.ai = ScriptedAI()
        assessed = game.assess_time_skip(1, "days", ["Train relentlessly to learn Haki"], "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"],
                                     confirmed_power_goal=True)
        self.assertTrue(result["goal_status"]["achieved"])

    def test_canon_boundary_forces_interruption_when_location_obviously_matches(self):
        """A model saying interrupted=false for an event happening in the
        player's own current location must not be trusted — this exact
        moment (present for the Nine-Tails attack) is important enough that
        it needs to be hardcoded to actually be played out, not left to the
        model reliably noticing the match on its own."""
        class ObliviousAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                return {
                    "narrative": "Time passes.", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 10080, "unit": "minutes"},
                    "interrupted": False, "interruption_kind": "", "interruption_reason": "",
                    "interruption_context": "", "intervention_prompt": "",
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Traveler", "Naruto", "Adventurer", "", "", "", "Academy Student",
                           "Ninjutsu Student", {n: 30 for n in abilities_for("Naruto")}, starting_era_id="before_naruto_birth")
        self.assertEqual(game.state["location"], "Konohagakure")
        game.ai = ObliviousAI()
        assessed = game.assess_time_skip(30, "days", ["Continue"], "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["interruption_kind"], "canon_event")
        self.assertTrue(result.get("intervention_prompt"))

    def test_canon_boundary_instruction_gives_concrete_scale_examples(self):
        # A bare "judge plausibility" instruction proved unreliable in
        # practice — a model kept forcing players into scenes with named
        # canon figures (Minato, Kushina) or offering intervention choices
        # for beats (Naruto stealing the scroll) they had no established way
        # to actually be near. Concrete worked examples anchor the judgment
        # call far more reliably than an abstract rule alone.
        source = (ROOT / "backend" / "engine_time.py").read_text(encoding="utf-8")
        self.assertIn("event's own scale is never itself a reason to force presence", source)
        self.assertIn("Nine-Tails attacks Konoha", source)
        self.assertIn("Naruto steals the forbidden scroll", source)

    def test_canon_event_catches_up_if_a_prior_turn_missed_it(self):
        """fire_canon_events used to only catch an event whose day fell
        exactly inside one specific turn's [before, after] window — if some
        earlier turn ever slipped past that window without firing it (a
        save carried over from a build with the since-fixed 'next major
        event' crawl bug, for instance), the event was stuck as permanently
        unfired no matter how much further time passed. It must now catch up
        the moment we notice we're already past its day."""
        class QuietAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                return {
                    "narrative": "A day passes.", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 1, "unit": "days"}, "interrupted": False,
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Stuck Save", "Naruto", "Adventurer", "", "", "", "Academy Student",
                           "Ninjutsu Student", {n: 30 for n in abilities_for("Naruto")}, starting_era_id="before_naruto_birth")
        game.state["canon_day"] = -4300
        game.state["canon_time_minutes"] = -4300 * 1440 + 480
        game.ai = QuietAI()
        self.assertEqual(game.state.get("canon_events_fired"), [])
        assessed = game.assess_time_skip(1, "days", ["Continue"], "normal")
        game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertIn("day:-4380:Naruto's birth and the Nine-Tails attack", game.state["canon_events_fired"])

    def test_legacy_save_missing_calendar_anchor_day_still_fires_upcoming_events(self):
        """A real regression: saves created before calendar_anchor_day
        existed have it as None. The pre-campaign-history filter used to
        fall back to the WORLD's generic default start_day (-7) whenever
        anchor_day was None — for a campaign that actually began earlier
        than that default (e.g. a week before Naruto's birth, day -4387),
        this wrongly reclassified the Nine-Tails attack (day -4380) as
        already-historical and permanently suppressed it, no matter how much
        further time passed. When we don't actually know the true start,
        the filter must not apply at all."""
        class QuietAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                return {
                    "narrative": "A day passes.", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 1, "unit": "days"}, "interrupted": False,
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Legacy Save", "Naruto", "Adventurer", "", "", "", "Academy Student",
                           "Ninjutsu Student", {n: 30 for n in abilities_for("Naruto")}, starting_era_id="before_naruto_birth")
        game.state["calendar_anchor_day"] = None  # simulate a save from before this field existed
        game.ai = QuietAI()
        target = "day:-4380:Naruto's birth and the Nine-Tails attack"
        for _ in range(10):
            assessed = game.assess_time_skip(1, "days", ["Continue"], "normal")
            game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
            if target in game.state.get("canon_events_fired", []):
                break
        self.assertIn(target, game.state.get("canon_events_fired", []))

    def test_pre_campaign_canon_events_never_auto_fire_as_live_events(self):
        """A campaign starting at the default day (well after Naruto's
        birth) must never have that event fire as a live '[CANON TIMELINE]'
        system beat — it's settled history (see CANON HISTORY in gm_rules),
        not something the catch-up guarantee should resurrect."""
        game = self.fresh()
        # calendar_anchor_day is what actually distinguishes "starts after
        # this event" from "we don't know, don't filter" (see fire_canon_events)
        # — fresh() builds state directly from BASE_STATE rather than through
        # new_campaign(), so it must be set explicitly to represent a real
        # default-start campaign here.
        game.state["calendar_anchor_day"] = -7

        class QuietAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                return {
                    "narrative": "A day passes.", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 5, "unit": "days"}, "interrupted": False,
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game.ai = QuietAI()
        assessed = game.assess_time_skip(5, "days", ["Continue"], "normal")
        game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertEqual(game.state.get("canon_events_fired"), [])

    def test_canon_event_note_interleaves_by_day_not_appended_first(self):
        """The [CANON TIMELINE] note used to always land at the very start of
        a multi-day skip's Chronicle entries regardless of its actual day —
        so an event on day -4380 would appear ABOVE a narrator update dated
        -4386 (six days earlier) and BELOW one dated -4379, reading as
        nonsense out-of-order history. It must interleave by canon_day like
        any other entry."""
        class MixedDayAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                return {
                    "narrative": "Days pass.",
                    "updates": [
                        {"sequence": 1, "type": "world_event", "title": "Early routine day", "canon_day": -4386,
                         "narrative": "Quiet training.", "why_it_matters": "", "player_knowledge": "", "next_pressure": ""},
                        {"sequence": 1, "type": "world_event", "title": "Later routine day", "canon_day": -4379,
                         "narrative": "More quiet training.", "why_it_matters": "", "player_knowledge": "", "next_pressure": ""},
                    ],
                    "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 8, "unit": "days"}, "interrupted": False,
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Ari", "Naruto", "Adventurer", "", "", "", "Academy Student",
                           "Ninjutsu Student", {n: 30 for n in abilities_for("Naruto")}, starting_era_id="before_naruto_birth")
        game.ai = MixedDayAI()
        assessed = game.assess_time_skip(8, "days", ["Continue"], "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        dated = [e for e in result["story"] if e.get("canon_day") is not None]
        days = [e["canon_day"] for e in dated]
        self.assertEqual(days, sorted(days))
        self.assertEqual(days, [-4386, -4380, -4379])
        self.assertIn("Nine-Tails", dated[1]["text"])
        self.assertEqual(result["state"].get("active_canon_event"), "Naruto's birth and the Nine-Tails attack")

    def test_one_piece_timeline_fires_in_order_and_skips_pre_departure_history(self):
        """The One Piece timeline was rebuilt from a real source chronology
        (The Library of Ohara), converting real Kaienreki dates into
        day-offsets from Luffy's departure. Pre-departure history (Roger's
        execution, Luffy's own birth, etc.) is centuries before day 0 and
        must never auto-fire as a live event; the actual voyage's beats must
        fire in their correct chronological order as canon_day advances."""
        events = timeline_for("One Piece")["events"]
        self.assertGreater(len(events), 30)
        self.assertTrue(all(e.get("historical_only") for e in events if e["day"] < 0))
        days = [e["day"] for e in events]
        self.assertEqual(days, sorted(days))

        class QuietAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload.get("task") == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload.get("planned_actions", []), "deferred_actions": []}
                return {
                    "narrative": "Days pass.", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 3, "unit": "days"}, "interrupted": False,
                    "major_event_reached": False, "major_event_kind": "", "major_event_title": "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": [], "deferred_actions": [],
                    "suggested_actions": ["a", "b", "c"],
                }

        game = GameSession()
        game.new_campaign("Ari", "One Piece", "Adventurer", "", "", "", "East Blue Civilian",
                           "Brawler", {n: 30 for n in abilities_for("One Piece")})
        game.ai = QuietAI()
        for _ in range(8):
            assessed = game.assess_time_skip(3, "days", ["Continue"], "normal")
            game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        fired = game.state.get("canon_events_fired", [])
        self.assertFalse(any("Roger's execution" in f or "Luffy is born" in f for f in fired))
        self.assertIn("day:0:Luffy leaves Foosha Village", fired)
        self.assertIn("day:13:Baratie conflict", fired)
        self.assertLess(fired.index("day:0:Luffy leaves Foosha Village"), fired.index("day:13:Baratie conflict"))

    def test_phone_host_and_responsive_shell_are_present(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")
        service_worker = (ROOT / "frontend" / "sw.js").read_text(encoding="utf-8")
        self.assertIn('rel="manifest"', html)
        self.assertIn('id="phone-host-banner"', html)
        self.assertIn('navigator.serviceWorker.register', js)
        # col-right (Action Chat/Time Control — what a phone player actually
        # needs to act) is ordered ahead of col-center (scene art + the
        # Chronicle) on mobile, so those controls sit right after the topbar
        # instead of requiring a scroll past the whole story feed on every
        # single turn.
        self.assertIn('.col-right{ order:1;', css)
        self.assertIn('.col-center{ order:2;', css)
        self.assertIn('LAN_MODE = "--lan" in sys.argv', launcher)
        self.assertIn('url.pathname.startsWith("/api/")', service_worker)
        # webview.start(debug=True) was only ever meant to be temporary, for
        # diagnosing the Godot black-square bug with real console access —
        # that bug is fixed and confirmed (v2.6.29+), so DevTools access
        # should not still be exposed in a shipped build.
        self.assertIn("webview.start()", launcher)
        self.assertNotIn("debug=True", launcher)

    def test_sidebar_time_row_wraps_instead_of_clipping_the_advance_button(self):
        # A real report: selecting days/weeks/months reveals the amount
        # input alongside the unit dropdown and ADVANCE button in the same
        # narrow sidebar row — three items' combined min-content width
        # exceeds the column's width at plenty of ordinary desktop sizes
        # (not just the small-screen breakpoint), and flex items refuse to
        # shrink past their own min-content by default, so the row silently
        # overflowed and clipped the button instead of ever squeezing it.
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".time-row{ display:flex; flex-wrap:wrap;", css)

    def test_service_worker_clones_the_response_before_any_async_gap(self):
        # Cloning a Response inside a `caches.open(...).then(...)` callback
        # is a real race: that promise settles a tick later, and by then the
        # page may have already started reading the same response's body,
        # which locks it and makes clone() throw "Response body is already
        # used". That failure was silently swallowed, leaving the fetch
        # handler's `.catch()` to serve whatever stale copy was already in
        # the cache — so a shipped CSS/JS change could appear to never take
        # effect for a player with an existing service-worker installation.
        # The fix clones synchronously, in the same tick the response
        # arrives, before handing it off to any async continuation.
        service_worker = (ROOT / "frontend" / "sw.js").read_text(encoding="utf-8")
        self.assertNotIn("cache.put(event.request, response.clone())", service_worker)
        clone_pos = service_worker.index("response.clone()")
        cache_open_pos = service_worker.index("caches.open(CACHE).then((cache) => cache.put(")
        self.assertLess(clone_pos, cache_open_pos)

    def test_service_worker_does_not_intercept_godot_build_assets(self):
        # A real report: loading a world logged an uncaught
        # "Failed to execute 'put' on 'Cache': Partial response (status code
        # 206) is unsupported". Godot's Web export loader issues ranged
        # fetches for its large .wasm/.pck files, which return 206 Partial
        # Content — the Cache API rejects caching those outright, and the
        # fetch handler's fire-and-forget cache.put() had no .catch(), so it
        # surfaced as an unhandled rejection on every world load. Those build
        # files don't need service-worker caching in the first place, so
        # they're excluded the same way /music/ and /portrait-cache/ are.
        service_worker = (ROOT / "frontend" / "sw.js").read_text(encoding="utf-8")
        self.assertIn('url.pathname.startsWith("/godot/")', service_worker)

    def test_desktop_shell_never_registers_a_service_worker(self):
        # A pywebview window only ever talks to its own same-machine Flask
        # server — there is no offline case for a cache layer to cover, and
        # a stale one can silently keep serving an old style.css/app.js
        # snapshot indefinitely. The desktop path must actively tear down
        # any worker a previous build left registered, not just skip
        # registering a new one (skipping alone leaves an old active worker
        # in permanent control with no code path left to replace it).
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        pywebview_pos = js.index("window.pywebview")
        unregister_pos = js.index("getRegistrations().then((regs) => regs.forEach((r) => r.unregister())")
        register_pos = js.index('navigator.serviceWorker.register("/sw.js")')
        self.assertLess(pywebview_pos, unregister_pos)
        self.assertLess(unregister_pos, register_pos)

    def test_event_window_does_not_duplicate_narrative_into_the_chronicle_live(self):
        # Every turn's narrative, and every combat round, used to be
        # unconditionally mirrored into the main Chronicle even while the
        # event window was open on top of it — the same text updating in
        # two places at once, one of them hidden behind the modal. Both
        # call sites must route through the event window's own buffer
        # instead while a scene is active.
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("APP.eventWindow = { storyBuffer: [] };", js)
        self.assertIn("if (APP.eventWindow) APP.eventWindow.storyBuffer.push(...(result.story || []));", js)
        combat_mirror = js.index("const chronicleLines = (entries || []).map")
        event_window_check = js.index("if (APP.eventWindow) APP.eventWindow.storyBuffer.push(entry);")
        self.assertLess(combat_mirror, event_window_check)

    def test_event_window_close_posts_only_a_summary_not_the_full_log(self):
        # A real report: the full beat-by-beat buffer (every prompt, every
        # combat round) was landing in the Chronicle verbatim once the event
        # window closed — a wall of text where a paragraph would do.
        # respond_to_event already writes a single "[EVENT CONCLUDED]"
        # summary entry when the scene ends; closeEventWindow must surface
        # only that, not the whole buffer.
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        close_fn = js[js.index("function closeEventWindow()"):]
        close_fn = close_fn[:close_fn.index("\n}\n")]
        self.assertIn('startsWith("[EVENT CONCLUDED]")', close_fn)
        self.assertIn("appendStoryEntries([summary", close_fn)
        self.assertNotIn("appendStoryEntries(APP.eventWindow.storyBuffer)", close_fn)
        self.assertNotIn("appendStoryEntries(buffer)", close_fn)

    def test_event_conclusion_summary_is_capped_to_one_paragraph(self):
        import inspect
        game = self.fresh("Naruto")
        source = inspect.getsource(game.respond_to_event)
        self.assertIn("ONE paragraph", source)
        self.assertIn("not a beat-by-beat recap", source)

    def test_godot_portrait_ambient_export_and_embed_wiring_are_present(self):
        # The Godot-rendered ambient effect ships as a static HTML5/WebGL
        # export sitting under frontend/godot/, served by the same
        # catch-all static route as everything else in frontend/ — no
        # dedicated Flask route needed. This locks in that the exported
        # build and the iframe-embedding JS both actually exist together,
        # since a build without wiring (or wiring without a build) is a
        # silent no-op with no console error to notice.
        export_dir = ROOT / "frontend" / "godot" / "portrait_ambient"
        for filename in ("index.html", "index.js", "index.wasm", "index.pck"):
            self.assertTrue((export_dir / filename).exists(), f"missing {filename} in the exported Godot build")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="portrait-godot-ambient"', (ROOT / "frontend" / "index.html").read_text(encoding="utf-8"))
        self.assertIn("GODOT_AMBIENT_WORLDS", js)
        self.assertIn("/godot/portrait_ambient/index.html?world=", js)
        self.assertIn("applyGodotAmbient(s.world", js)
        # One export, six worlds — the scene reads ?world= at runtime and
        # re-themes its own particle material rather than needing a
        # separate ~40MB WASM build shipped per world.
        for world in ("Naruto", "One Piece", "Hunter x Hunter", "Solo Max-Level Newbie", "Overgeared", "Reincarnated as a Slime"):
            self.assertIn(f'"{world}"', js[js.index("GODOT_AMBIENT_WORLDS"):js.index("GODOT_AMBIENT_WORLDS") + 300])
        theme_script = (ROOT / "godot" / "portrait_ambient" / "ambient_theme.gd").read_text(encoding="utf-8")
        for world in ("Naruto", "One Piece", "Hunter x Hunter", "Solo Max-Level Newbie", "Overgeared", "Reincarnated as a Slime"):
            self.assertIn(f'"{world}"', theme_script)
        self.assertIn("_world_from_query", theme_script)
        self.assertIn("GradientTexture1D", theme_script)  # color_ramp needs a texture, not a raw Gradient

    def test_godot_scene_ambient_export_and_embed_wiring_are_present(self):
        # The scene banner's old canvas particle/glow system (#scene-fx,
        # seedParticles/seedSceneGlows/tickSceneFx) and CSS weather overlay
        # (.scene-weather) are fully replaced by one Godot layer, not
        # layered underneath it — this locks in both that the replacement
        # is actually wired up AND that the old dead code is gone, not
        # just unreachable.
        export_dir = ROOT / "frontend" / "godot" / "scene_ambient"
        for filename in ("index.html", "index.js", "index.wasm", "index.pck"):
            self.assertTrue((export_dir / filename).exists(), f"missing {filename} in the exported Godot build")
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn('id="scene-godot-fx"', html)
        self.assertNotIn('id="scene-fx"', html)
        self.assertNotIn('id="scene-weather"', html)
        self.assertIn(".scene-godot-fx{", css)
        self.assertNotIn(".scene-weather{", css)
        self.assertIn("applyGodotSceneFx", js)
        self.assertIn("/godot/scene_ambient/index.html?", js)
        for dead in ("function startSceneFx", "function seedParticles", "function seedSceneGlows",
                     "function tickSceneFx", "function resizeSceneFx", "sceneFx.canvas"):
            self.assertNotIn(dead, js)
        # Live re-theming, not a reload: the scene category/weather can
        # change nearly every turn, so a second call must talk to the
        # already-running instance instead of reloading the ~40MB WASM
        # runtime. JavaScriptBridge.create_callback()/get_interface() to
        # expose a Godot-side function to JS proved unreliable in testing
        # (calls landed nowhere, no error raised) — the page instead sets a
        # plain JS global that scene_theme.gd polls a few times a second via
        # eval(), the same primitive its own initial query-string read
        # already uses successfully.
        self.assertIn("frame.contentWindow.sceneThemeParams = key", js)
        theme_script = (ROOT / "godot" / "scene_ambient" / "scene_theme.gd").read_text(encoding="utf-8")
        self.assertIn("func set_theme(category: String, weather: String)", theme_script)
        self.assertIn("window.sceneThemeParams", theme_script)
        self.assertIn("GradientTexture1D", theme_script)
        # Every category actually used elsewhere in the app maps to a
        # real family, not silently falling back to the default for most
        # of them.
        for category in ("town_square", "kingdom", "indoor_grandhall", "harbor_port", "forest_path",
                          "mountain_castle", "battlefield_dusk", "monster_battlefield", "monster_lair",
                          "dungeon_cave", "starry_sky", "night_wilderness", "tower_hub", "duel",
                          "merchant_shop", "tavern_inn", "academy_classroom", "arena_floor", "ship_deck"):
            self.assertIn(f'"{category}"', theme_script, f"{category} has no family mapping in scene_theme.gd")
        for weather in ("rain", "storm", "snow", "fog"):
            self.assertIn(f'"{weather}"', theme_script)

    def test_godot_projects_are_configured_for_a_transparent_embedded_background(self):
        # A real report: the banner rendered as an opaque black rectangle
        # with particles floating on it instead of a transparent overlay
        # over the actual scene art. window/size/transparent (a desktop
        # window-compositing flag) does nothing for a Web export — the
        # viewport itself needs transparent_background, or every pixel the
        # scene doesn't explicitly draw over composites as opaque black
        # regardless of clear-color alpha. canvas_resize_policy=2 (Adaptive)
        # is required too: with the default (0/None) the browser stretches
        # a fixed-resolution canvas to fill the responsive iframe box via
        # GPU bilinear scaling, which left a visible opaque band along the
        # top/bottom edges even after the viewport fix. Even with both of
        # those fixed and verified via direct canvas pixel-alpha sampling,
        # the packaged app still showed a solid black square: Godot's
        # generated HTML export shell hardcodes `body { background-color:
        # black; }`, which sits directly behind the (correctly transparent)
        # canvas in the SAME document and shows through once the browser
        # composites the canvas's real per-pixel alpha onto the page — a
        # layer no canvas-level pixel sampling or iframe/canvas CSS check
        # can detect, since neither inspects the child document's own body.
        # html/head_include injects a later, !important override so this
        # survives every future re-export instead of hand-patching the
        # generated index.html files.
        for project in ("scene_ambient", "portrait_ambient", "map_ambient"):
            cfg = (ROOT / "godot" / project / "project.godot").read_text(encoding="utf-8")
            self.assertIn("viewport/transparent_background=true", cfg, f"{project}/project.godot")
            preset = (ROOT / "godot" / project / "export_presets.cfg").read_text(encoding="utf-8")
            self.assertIn("html/canvas_resize_policy=2", preset, f"{project}/export_presets.cfg")
            self.assertIn("background:transparent!important", preset, f"{project}/export_presets.cfg")
            exported_html = (ROOT / "frontend" / "godot" / project / "index.html").read_text(encoding="utf-8")
            self.assertIn("background:transparent!important", exported_html, f"frontend/godot/{project}/index.html")

    def test_godot_ambient_layers_fill_their_container_instead_of_letterboxing(self):
        # A real report, after the black-square bug above was fixed: the
        # banner picture only occupied a centered strip with black bars on
        # either side. Godot's window/stretch/aspect defaults to "keep",
        # which pillarboxes/letterboxes to preserve each project's fixed
        # design resolution (640x260 / 280x200 / 960x600) instead of filling
        # whatever shape its actual embedding container is — invisible
        # before, because the whole canvas rendered opaque black anyway, so
        # the letterbox bars blended into the same black square. Fixing the
        # black-square bug made the previously-hidden pillarboxing visible.
        # "expand" fills the container with no letterboxing, but the
        # emitters were hand-placed in each .tscn assuming the fixed design
        # size, so each script must also rescale them off the live
        # get_viewport_rect().size or they'd stay pinned to their original
        # small patch instead of covering the actual, larger visible area.
        for project in ("scene_ambient", "portrait_ambient", "map_ambient"):
            cfg = (ROOT / "godot" / project / "project.godot").read_text(encoding="utf-8")
            self.assertIn('window/stretch/aspect="expand"', cfg, f"{project}/project.godot")
        scene_script = (ROOT / "godot" / "scene_ambient" / "scene_theme.gd").read_text(encoding="utf-8")
        self.assertIn("get_viewport_rect().size", scene_script)
        self.assertIn("get_viewport().size_changed.connect(_fit_to_viewport)", scene_script)
        portrait_script = (ROOT / "godot" / "portrait_ambient" / "ambient_theme.gd").read_text(encoding="utf-8")
        self.assertIn("get_viewport_rect().size", portrait_script)
        self.assertIn("get_viewport().size_changed.connect(_fit_to_viewport)", portrait_script)
        map_script = (ROOT / "godot" / "map_ambient" / "map_theme.gd").read_text(encoding="utf-8")
        self.assertIn("get_viewport().size_changed.connect(_fit_to_viewport)", map_script)

    def test_godot_map_ambient_export_and_embed_wiring_are_present(self):
        # The map's real interactive parts (pan/zoom, territory Voronoi
        # coloring, clickable pins) are untouched — this is purely an
        # additive glow/atmosphere layer. Unlike the scene banner, #map-wrap
        # is a fresh DOM element every time the Map tab renders, so danger
        # nodes travel as a query-string param read once at startup rather
        # than a live-update mechanism — a JavaScriptBridge.create_callback
        # attempt for the banner proved unreliable in testing (see the
        # scene_theme.gd note), and the map doesn't need that complexity
        # anyway since a fresh load already happens on every tab-open.
        export_dir = ROOT / "frontend" / "godot" / "map_ambient"
        for filename in ("index.html", "index.js", "index.wasm", "index.pck"):
            self.assertTrue((export_dir / filename).exists(), f"missing {filename} in the exported Godot build")
        html_text = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        # map-godot-fx isn't in index.html's static markup — the map panel
        # (like the rest of the Journal) is built from a JS template string
        # at render time, not present in the page's initial HTML.
        self.assertIn('id="map-godot-fx"', js)
        self.assertIn(".map-godot-fx{", css)
        self.assertIn("applyGodotMapFx", js)
        self.assertIn("/godot/map_ambient/index.html?", js)
        self.assertIn('danger_level || "").toLowerCase() === "critical"', js)
        theme_script = (ROOT / "godot" / "map_ambient" / "map_theme.gd").read_text(encoding="utf-8")
        self.assertIn('kv[0] == "danger"', theme_script)

    def test_index_html_is_served_with_cache_busting_asset_versions(self):
        # A desktop build's no-store headers only stop the plain HTTP
        # cache — they don't touch a browser engine's own Cache Storage,
        # which can keep answering with a snapshot from a much older
        # version indefinitely. Stamping the CSS/JS URLs with the current
        # APP_VERSION makes every release a brand new resource to every
        # cache layer at once, regardless of which one was misbehaving.
        sys.path.insert(0, str(ROOT / "backend"))
        from app import app as flask_app
        from worlds import APP_VERSION
        client = flask_app.test_client()
        html = client.get("/").get_data(as_text=True)
        self.assertIn(f'href="/css/style.css?v={APP_VERSION}"', html)
        self.assertIn(f'src="/js/app.js?v={APP_VERSION}"', html)

    def test_same_place_recognizes_common_hidden_village_aliases(self):
        # Canon-timeline data always uses the Japanese village name
        # ("Konohagakure"), but players and the narrator routinely use the
        # common English alias ("Leaf Village") — a real save hit this
        # exactly: the player was in Konoha for the Nine-Tails attack but
        # the plain substring match missed it, so the interactive scene
        # never triggered and it silently narrated as a summary instead.
        self.assertTrue(GameSession._same_place("Leaf Village", "Konohagakure"))
        self.assertTrue(GameSession._same_place("the Hidden Leaf", "Konohagakure"))
        self.assertTrue(GameSession._same_place("Konoha", "Konohagakure"))
        self.assertTrue(GameSession._same_place("Hidden Sand", "Sunagakure"))
        self.assertFalse(GameSession._same_place("Sand Village", "Konohagakure"))
        self.assertFalse(GameSession._same_place("", "Konohagakure"))

    def test_active_canon_event_guarantees_a_difficulty_gate(self):
        # A real save hit this: the player clicked "TAKE PART — EXPERIENCE
        # IT" on the Nine-Tails attack, typed a response, and nothing
        # happened — the AI's assessment returned no checks at all for that
        # moment, so the difficulty gate (and its roll/Timing Clash/Tactical
        # Approach choice) never appeared and engaging did nothing.
        class NoCheckAI:
            def request(self, rules, payload, max_output_tokens=0):
                return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}

        game = self.fresh()
        game.state["active_canon_event"] = "Naruto's birth and the Nine-Tails attack"
        game.ai = NoCheckAI()
        result = game.assess_time_skip(1, "moment", ["Rush to help defend the village"], "normal")
        self.assertTrue(result["assessment"]["requires_difficulty_confirmation"])
        self.assertEqual(len(result["assessment"]["difficult_checks"]), 1)

        # Outside an active canon event, an empty check list is left alone.
        game2 = self.fresh()
        game2.ai = NoCheckAI()
        result2 = game2.assess_time_skip(1, "moment", ["Take a quiet walk"], "normal")
        self.assertFalse(result2["assessment"]["requires_difficulty_confirmation"])
        self.assertEqual(result2["assessment"]["difficult_checks"], [])

    def test_update_context_fields_combine_into_one_plain_sentence(self):
        class NarrateAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload["task"] == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}
                return {"narrative": "fallback", "updates": [{
                    "sequence": 1, "type": "action", "title": "Into the Fray",
                    "narrative": "You charge toward the fighting.",
                    "why_it_matters": "This is the moment your training either holds or breaks.",
                    "player_knowledge": "You can see the beast towering over the village walls.",
                    "next_pressure": "It is turning toward you.",
                }], "state_patch": {}, "events": [], "timeline_events": [],
                    "elapsed": {"amount": 5, "unit": "minutes"}, "interrupted": False,
                    "completed_actions": [], "deferred_actions": [], "active_major_event": ""}

        game = self.fresh()
        game.state["calendar_anchor_day"] = game.state["canon_day"]
        game.ai = NarrateAI()
        assessed = game.assess_time_skip(1, "moment", ["Charge in"], "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        entry = next(e for e in result["story"] if "INTO THE FRAY" in e.get("text", ""))
        self.assertNotIn("Why it matters:", entry["text"])
        self.assertNotIn("What you know:", entry["text"])
        self.assertNotIn("Pressure:", entry["text"])
        self.assertIn("This is the moment your training either holds or breaks.", entry["text"])
        self.assertIn("It is turning toward you.", entry["text"])

    def test_non_lethal_combat_floors_hp_at_one_for_both_sides(self):
        # A spar/rank-test/supervised duel (combat.non_lethal) must never be
        # able to actually kill either combatant — it's won or lost on
        # points, HP floored at 1 instead of 0.
        game = self.fresh()
        game.state.update(hp=100, hp_max=100)
        game.state["combat"] = {"active": True, "non_lethal": True,
            "enemy": {"name": "Sparring Partner", "hp": 1000, "hp_max": 1000, "power": 500,
                      "difficulty_min": 1, "difficulty_max": 1, "attack_min": 100, "attack_max": 100}}
        for _ in range(20):
            game.resolve_combat_round("attack")
            if not game.state["combat"].get("active"):
                break
        self.assertEqual(game.state["hp"], 1)
        self.assertEqual(game.state["combat"]["outcome"], "yielded")
        self.assertTrue(game.state["alive"])

        game2 = self.fresh()
        game2.state.update(hp=100, hp_max=100)
        for name in game2.state["stats"]:
            game2.state["stats"][name] = 200
        game2.state["combat"] = {"active": True, "non_lethal": True,
            "enemy": {"name": "Trainee", "hp": 20, "hp_max": 20, "power": 5,
                      "difficulty_min": 1, "difficulty_max": 1, "attack_min": 1, "attack_max": 1}}
        for _ in range(10):
            game2.resolve_combat_round("attack")
            if not game2.state["combat"].get("active"):
                break
        self.assertEqual(game2.state["combat"]["enemy"]["hp"], 1)
        self.assertEqual(game2.state["combat"]["outcome"], "victory")

    def test_spare_enemy_toggle_only_protects_the_enemy_not_the_player(self):
        # combat.spare_enemy is the player's own choice to knock an opponent
        # out instead of killing them on a win — it must NOT make the fight
        # safe for the player. Losing a fight the player chose to show mercy
        # in still kills them exactly like any other real fight.
        game = self.fresh()
        game.state.update(hp=100, hp_max=100)
        game.state["combat"] = {"active": True, "spare_enemy": True,
            "enemy": {"name": "Rival", "hp": 20, "hp_max": 20, "power": 500,
                      "difficulty_min": 1, "difficulty_max": 1, "attack_min": 100, "attack_max": 100}}
        for _ in range(20):
            game.resolve_combat_round("attack")
            if not game.state["combat"].get("active"):
                break
        self.assertEqual(game.state["combat"]["outcome"], "defeat")
        self.assertEqual(game.state["hp"], 0)
        self.assertFalse(game.state["alive"])

        # But a WIN with spare_enemy floors the enemy at 1 instead of 0.
        game2 = self.fresh()
        game2.state.update(hp=100, hp_max=100)
        for name in game2.state["stats"]:
            game2.state["stats"][name] = 200
        game2.state["combat"] = {"active": True, "spare_enemy": True,
            "enemy": {"name": "Bandit", "hp": 20, "hp_max": 20, "power": 5,
                      "difficulty_min": 1, "difficulty_max": 1, "attack_min": 1, "attack_max": 1}}
        for _ in range(10):
            game2.resolve_combat_round("attack")
            if not game2.state["combat"].get("active"):
                break
        self.assertEqual(game2.state["combat"]["outcome"], "victory")
        self.assertEqual(game2.state["combat"]["enemy"]["hp"], 1)

    def test_next_major_event_mode_still_gives_a_live_scene_for_a_present_canon_event(self):
        # A real save hit this: using "Skip to next major event" to reach the
        # Nine-Tails attack while standing in Konohagakure produced only a
        # flat "Major Event Reached" report — event_mode unconditionally
        # cleared interrupted/interruption_kind regardless of whether the
        # boundary was a personal development or a canon event the player
        # was actually standing in. It must get the same live "take part /
        # let it play out" scene a normal multi-day skip would give it.
        class QuietAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload["task"] == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}
                return {"narrative": "Time passes quietly.", "updates": [], "state_patch": {}, "events": [],
                        "timeline_events": [], "interrupted": False, "completed_actions": [], "deferred_actions": [],
                        "major_event_reached": False, "suggested_actions": ["a", "b", "c"]}

        game = self.fresh()
        game.state.update(location="Konohagakure", canon_day=-4387,
                           canon_time_minutes=-4387 * 1440 + 480, calendar_anchor_day=-4387)
        game.ai = QuietAI()
        assessed = game.assess_time_skip(1, "next_event", [], "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["interruption_kind"], "canon_event")
        self.assertIn("Nine-Tails", result["intervention_prompt"])
        self.assertEqual(result["major_event_kind"], "canon")
        # Not duplicated: exactly one "MAJOR CANON EVENT" chronicle entry,
        # not also a separate flat "Major Event Reached" note for the same beat.
        major_entries = [s for s in result["story"] if "MAJOR" in s.get("text", "")]
        self.assertEqual(len(major_entries), 1)
        self.assertIn("MAJOR CANON EVENT", major_entries[0]["text"])

        # A personal (non-canon) major event reached the same way is
        # unaffected — still never interactive, per this mode's own contract.
        class PersonalAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload["task"] == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}
                return {"narrative": "A breakthrough occurs.", "updates": [], "state_patch": {}, "events": [],
                        "timeline_events": [], "elapsed": {"amount": 3, "unit": "days"}, "interrupted": False,
                        "completed_actions": [], "deferred_actions": [], "major_event_reached": True,
                        "major_event_kind": "personal", "major_event_title": "A Rival Arrives",
                        "suggested_actions": ["a", "b", "c"]}

        game2 = self.fresh()
        game2.state.update(location="Land of Waves", canon_day=100,
                            canon_time_minutes=100 * 1440 + 480, calendar_anchor_day=0)
        game2.ai = PersonalAI()
        assessed2 = game2.assess_time_skip(1, "next_event", [], "normal")
        result2 = game2.run_time_skip(assessed2["amount"], assessed2["unit"], assessed2["orders"], "normal", assessed2["assessment"])
        self.assertFalse(result2["interrupted"])
        self.assertEqual(result2["interruption_kind"], "")

    def test_manual_roll_gate_does_not_duplicate_the_action_echo(self):
        # A real playthrough hit this: a major-event check requires a manual
        # roll, which re-enters run_time_skip a second time on the SAME
        # queued action once the player supplies the roll. The action's own
        # "> ..." Chronicle line was being appended on both the first call
        # (which just bails out asking for the roll) and the second — the
        # same single action showing up twice in the Chronicle.
        class MajorCheckAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload["task"] == "assess_time_skip":
                    return {"checks": [{"id": "m1", "reason": "Engage the threat", "ability": "Taijutsu", "skill": None,
                             "difficulty_min": 50, "difficulty_max": 60, "relevant_average_stat": 30,
                             "situational_bonus": 0, "time_difficulty_modifier": 0, "major_event": True,
                             "lethal_risk": "moderate"}],
                            "reachable_actions": payload["planned_actions"], "deferred_actions": []}
                return {"narrative": "fallback", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                        "elapsed": {"amount": 5, "unit": "minutes"}, "interrupted": False, "completed_actions": [],
                        "deferred_actions": [], "active_major_event": ""}

        game = self.fresh()
        game.ai = MajorCheckAI()
        assessed = game.assess_time_skip(1, "moment", ["Engage the threat"], "normal")
        first = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertEqual(first["status"], "manual_roll_required")
        second = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal",
                                     assessed["assessment"], manual_rolls={"m1": 70})
        echoes = [e for e in second.get("story", []) if e.get("text") == "> Engage the threat"]
        self.assertEqual(len(echoes), 1)

    def test_custom_locations_appear_on_the_map_without_duplicating_canon_ones(self):
        # The AI can now introduce an original place mid-story (state_patch.
        # custom_locations) and have it actually show up as a real node on
        # the interactive map, not just live in prose.
        game = self.fresh()
        game.state["location"] = "Hidden Camp of the Wandering Sparrows"
        game.state["custom_locations"] = [
            {"name": "Hidden Camp of the Wandering Sparrows", "x": 60, "y": 45, "kind": "camp", "tier": 2},
            {"name": "Konohagakure", "x": 1, "y": 1, "kind": "village", "tier": 1},  # collides with canon — must be skipped
        ]
        snap = map_snapshot(game.state, WORLD_DATA["Naruto"]["map"], "Naruto")
        names = [n["name"] for n in snap["nodes"]]
        self.assertIn("Hidden Camp of the Wandering Sparrows", names)
        self.assertEqual(names.count("Konohagakure"), 1)
        custom_node = next(n for n in snap["nodes"] if n["name"] == "Hidden Camp of the Wandering Sparrows")
        self.assertTrue(custom_node["current"])
        self.assertEqual((custom_node["x"], custom_node["y"]), (60.0, 45.0))

    def test_tower_floor_deadline_resets_on_advance_and_forces_death_at_zero(self):
        class NoOpAI:
            def __init__(self, patch=None, elapsed_days=3):
                self.patch = patch or {}
                self.elapsed_days = elapsed_days

            def request(self, rules, payload, max_output_tokens=0):
                if payload["task"] == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}
                return {"narrative": "Time passes in the tower.", "updates": [], "state_patch": self.patch,
                        "events": [], "timeline_events": [], "elapsed": {"amount": self.elapsed_days, "unit": "days"},
                        "interrupted": False, "completed_actions": [], "deferred_actions": [], "active_major_event": ""}

        game = self.fresh(world="Solo Max-Level Newbie")
        game.state.update(tower_floor=1, tower_floor_deadline_day=game.state["canon_day"] + 10)
        game.ai = NoOpAI(patch={"tower_floor": 2, "location": "Floor 2"}, elapsed_days=1)
        assessed = game.assess_time_skip(1, "days", [], "normal")
        game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        # Clearing to a new floor resets the deadline to canon_day + 90 from here.
        self.assertEqual(game.state["tower_floor"], 2)
        self.assertEqual(game.state["tower_floor_deadline_day"], game.state["canon_day"] + 90)

        # Now let the (new) deadline actually run out.
        game.state["tower_floor_deadline_day"] = game.state["canon_day"] + 2
        game.ai = NoOpAI(patch={}, elapsed_days=3)
        assessed2 = game.assess_time_skip(3, "days", [], "normal")
        result = game.run_time_skip(assessed2["amount"], assessed2["unit"], assessed2["orders"], "normal", assessed2["assessment"])
        self.assertTrue(result["died"])
        self.assertFalse(game.state["alive"])
        self.assertTrue(game.state["tower_over"])

    def test_time_skip_death_is_reported_like_any_other_death(self):
        # apply_time_skip previously had no "died" signal at all — a killed-
        # off character during an ordinary Advance (not combat, not a single
        # action) never triggered the death modal on the frontend.
        class LethalAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload["task"] == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}
                return {"narrative": "It goes badly.", "updates": [], "state_patch": {"alive": False, "hp": 0},
                        "events": [], "timeline_events": [], "elapsed": {"amount": 1, "unit": "days"},
                        "interrupted": False, "completed_actions": [], "deferred_actions": []}

        game = self.fresh()
        game.ai = LethalAI()
        assessed = game.assess_time_skip(1, "days", [], "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertTrue(result["died"])
        self.assertFalse(game.state["alive"])

    def test_forced_canon_event_check_only_fires_on_the_first_beat(self):
        # Forcing a check on the FIRST beat of engaging a canon event solves
        # "playing through does nothing" — but applying that same force to
        # every later beat inside the same event turned the intended
        # choose-your-own-adventure scene into constant minigame popups.
        class NoCheckAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload["task"] == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}
                return {"narrative": "beat", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                        "elapsed": {"amount": 5, "unit": "minutes"}, "interrupted": False, "completed_actions": [],
                        "deferred_actions": [], "active_major_event": "The Big Event"}

        def resolve_fully(game, assessed):
            result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
            if result.get("status") == "manual_roll_required":
                result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal",
                                             assessed["assessment"], manual_rolls={result["check_id"]: 70})
            return result

        game = self.fresh()
        game.state["calendar_anchor_day"] = game.state["canon_day"]  # avoid unrelated legacy catch-up firing
        game.state["active_canon_event"] = "The Big Event"
        game.ai = NoCheckAI()

        first = game.assess_time_skip(1, "moment", ["engage"], "normal")
        self.assertTrue(first["assessment"]["difficult_checks"])
        resolve_fully(game, first)
        self.assertEqual(game.state["canon_event_engagement_count"], 1)

        second = game.assess_time_skip(1, "moment", ["keep going"], "normal")
        self.assertFalse(second["assessment"]["difficult_checks"])

    def test_background_world_feed_mirrors_independent_world_movement(self):
        # The World Feed split (Your Story vs. The Wider World) relies on
        # background_world_feed carrying the exact same text as the specific
        # world_events/timeline entries that were delivered as background
        # texture rather than lived through — canon catch-up notes and
        # NPC/faction clock turning points, nothing the player did.
        class NoOpAI:
            def request(self, rules, payload, max_output_tokens=0):
                if payload["task"] == "assess_time_skip":
                    return {"checks": [], "reachable_actions": payload["planned_actions"], "deferred_actions": []}
                return {"narrative": "A quiet day.", "updates": [], "state_patch": {}, "events": [], "timeline_events": [],
                        "elapsed": {"amount": 1, "unit": "days"}, "interrupted": False, "completed_actions": [],
                        "deferred_actions": []}

        game = self.fresh()
        game.state["calendar_anchor_day"] = game.state["canon_day"]  # avoid unrelated legacy catch-up firing
        game.state["npc_clocks"] = {"Rival": {"name": "Rival", "goal": "Grow stronger", "progress": 99,
                                                "threshold": 100, "status": "active", "last_update": ""}}
        game.ai = NoOpAI()
        assessed = game.assess_time_skip(1, "days", [], "normal")
        game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        feed = game.state.get("background_world_feed", [])
        self.assertEqual(len(feed), 1)
        self.assertIn("Rival's agenda reached a turning point", feed[0])
        self.assertIn(feed[0], game.state.get("world_events", []))

    def test_clock_turning_point_names_fall_back_to_dict_key(self):
        # _clock() always sets "name", but the GM can also author npc_clocks
        # directly via state_patch without it — the turning-point message
        # must still name the right agent instead of "None's agenda...".
        from systems import tick_world_clocks
        state = {"factions": {}, "npc_clocks": {"Rival": {"goal": "Grow stronger", "progress": 99,
                                                            "threshold": 100, "status": "active"}},
                 "npc_memories": {}, "world_time": "Day 1"}
        events = tick_world_clocks(state, 1440)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["message"].startswith("Rival's agenda"))

    def test_tension_level_reads_hp_combat_and_deadlines(self):
        from systems import tension_level

        calm = tension_level({"hp": 100, "hp_max": 100, "combat": {}, "scheduled_events": [], "canon_day": 0})
        self.assertEqual(calm["label"], "Calm")
        self.assertEqual(calm["score"], 0)

        critical = tension_level({"hp": 5, "hp_max": 100, "combat": {"active": True}, "scheduled_events": [], "canon_day": 0})
        self.assertEqual(critical["label"], "Critical")
        self.assertIn("critically low HP", critical["reasons"])
        self.assertIn("in active combat", critical["reasons"])

        imminent = tension_level({"hp": 100, "hp_max": 100, "combat": {}, "canon_day": 10,
            "scheduled_events": [{"due_canon_day": 11, "resolved": False, "visibility": "confirmed"}]})
        self.assertGreater(imminent["score"], 0)

        # A hidden or already-resolved scheduled event must not add tension.
        hidden = tension_level({"hp": 100, "hp_max": 100, "combat": {}, "canon_day": 10,
            "scheduled_events": [{"due_canon_day": 11, "resolved": False, "visibility": "hidden"}]})
        self.assertEqual(hidden["score"], 0)

    def test_nemesis_clock_runs_longer_than_a_normal_npc_clock_and_bumps_tension(self):
        from systems import tick_world_clocks, active_nemesis_threats, tension_level, NEMESIS_CLOCK_THRESHOLD

        state = {"factions": {}, "npc_clocks": {}, "world_time": "Day 1",
                 "npc_memories": {"Orochimaru": {"goal": "Destroy the Leaf from within", "nemesis": True, "recurring": True}}}
        tick_world_clocks(state, 1440)
        clock = state["npc_clocks"]["Orochimaru"]
        self.assertEqual(clock["threshold"], NEMESIS_CLOCK_THRESHOLD)
        self.assertTrue(clock["nemesis"])
        self.assertEqual(active_nemesis_threats(state), [])  # not at a turning point yet

        clock["progress"] = NEMESIS_CLOCK_THRESHOLD - 1
        events = tick_world_clocks(state, 1440)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["nemesis"])
        self.assertIn("Orochimaru", events[0]["message"])
        self.assertIn("breaking point", events[0]["message"])

        threats = active_nemesis_threats(state)
        self.assertEqual(len(threats), 1)
        self.assertEqual(threats[0]["name"], "Orochimaru")

        bumped = tension_level({**state, "hp": 100, "hp_max": 100, "combat": {}, "scheduled_events": [], "canon_day": 0})
        self.assertIn("a nemesis threat has reached a breaking point", bumped["reasons"])

    def test_pacing_guidance_flags_dry_spell_and_event_pileup(self):
        from systems import pacing_guidance

        # No chapters yet — too early in the campaign to say anything.
        self.assertEqual(pacing_guidance({"chapter_summaries": [], "canon_day": 20, "last_major_beat_day": 0}), "")

        # No major beat has ever landed — nothing to compare against.
        self.assertEqual(pacing_guidance({"chapter_summaries": [{}], "canon_day": 20, "last_major_beat_day": None,
                                            "hp": 100, "hp_max": 100}), "")

        dry_spell = pacing_guidance({"chapter_summaries": [{}], "canon_day": 20, "last_major_beat_day": 5,
                                       "hp": 100, "hp_max": 100, "combat": {}, "scheduled_events": []})
        self.assertIn("PACING", dry_spell)
        self.assertIn("15 in-story days", dry_spell)

        pileup = pacing_guidance({"chapter_summaries": [{}], "canon_day": 20, "last_major_beat_day": 20,
                                    "hp": 5, "hp_max": 100, "combat": {"active": True}, "scheduled_events": []})
        self.assertIn("PACING", pileup)
        self.assertIn("Ease off", pileup)

        steady = pacing_guidance({"chapter_summaries": [{}], "canon_day": 20, "last_major_beat_day": 17,
                                    "hp": 100, "hp_max": 100, "combat": {}, "scheduled_events": []})
        self.assertEqual(steady, "")

    def test_time_skip_records_last_major_beat_day_when_a_major_event_lands(self):
        game = self.fresh()
        game.ai = PlanningAI()  # always reports major_event_reached=True
        self.assertIsNone(game.state.get("last_major_beat_day"))
        assessed = game.assess_time_skip(2, "days", [], "normal")
        game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], "normal", assessed["assessment"])
        self.assertEqual(game.state.get("last_major_beat_day"), game.state.get("canon_day"))

    def test_director_notes_are_read_by_the_gm_and_cannot_be_authored_by_it(self):
        game = self.fresh()
        game.state["director_notes"] = "Lean into faction politics, ease off on combat."
        rules = game.gm_rules()
        self.assertIn("DIRECTOR'S NOTES", rules)
        self.assertIn("Lean into faction politics", rules)

        from state_guard import apply_guarded_patch
        report = apply_guarded_patch(game.state, {"director_notes": "overwritten by the model", "last_major_beat_day": 999})
        self.assertNotIn("director_notes", report["accepted"])
        self.assertNotIn("last_major_beat_day", report["accepted"])
        self.assertEqual(game.state["director_notes"], "Lean into faction politics, ease off on combat.")

    def test_faction_conflict_resolves_a_turning_point_and_can_destroy_the_loser(self):
        from unittest.mock import patch

        state = {"factions": {}, "world_time": "Day 1", "location_details": {}, "npc_memories": {},
                 "faction_clocks": {
                     "Leaf": {"name": "Leaf", "goal": "Retake the border fort", "progress": 99, "threshold": 100,
                              "status": "active", "power": 80, "opponent": "Sand", "contested_location": "Border Fort"},
                     "Sand": {"name": "Sand", "goal": "Hold the border", "progress": 0, "threshold": 100,
                              "status": "active", "power": 10},
                 },
                 "npc_clocks": {}}
        with patch("systems.random.random", return_value=0.0):  # guarantees the actor (Leaf) wins
            events = tick_world_clocks(state, 1440)
        messages = [e["message"] for e in events]
        self.assertTrue(any("Leaf has triumphed over Sand" in m for m in messages))
        self.assertTrue(any(m.startswith("[FACTION DESTROYED] Sand") for m in messages))
        self.assertEqual(state["location_details"]["Border Fort"]["controlling_faction"], "Leaf")
        self.assertEqual(state["faction_clocks"]["Sand"]["status"], "destroyed")
        self.assertEqual(state["faction_clocks"]["Leaf"]["status"], "active")
        self.assertEqual(state["faction_clocks"]["Leaf"]["opponent"], "")

    def test_off_screen_conflict_can_get_an_npc_killed(self):
        from unittest.mock import patch

        state = {"factions": {}, "world_time": "Day 1", "location_details": {},
                 "npc_memories": {"Rogue Ninja": {"goal": "Overthrow the village council", "recurring": True}},
                 "npc_clocks": {"Rogue Ninja": {"name": "Rogue Ninja", "goal": "Overthrow the village council",
                                                 "progress": 99, "threshold": 100, "status": "active",
                                                 "power": 10, "opponent": "Village Guard"}},
                 "faction_clocks": {}}
        with patch("systems.random.random", return_value=1.0):  # guarantees the actor loses
            events = tick_world_clocks(state, 1440)
        messages = [e["message"] for e in events]
        self.assertTrue(any(m.startswith("[NPC LOST] Rogue Ninja") for m in messages))
        self.assertEqual(state["npc_clocks"]["Rogue Ninja"]["status"], "defeated")
        self.assertEqual(state["npc_memories"]["Rogue Ninja"]["status"], "deceased")

    def test_mutual_opponents_resolve_only_once_per_tick(self):
        from unittest.mock import patch

        state = {"factions": {}, "world_time": "Day 1", "location_details": {}, "npc_memories": {},
                 "faction_clocks": {
                     "Alpha": {"name": "Alpha", "goal": "Crush Beta", "progress": 99, "threshold": 100,
                               "status": "active", "power": 60, "opponent": "Beta"},
                     "Beta": {"name": "Beta", "goal": "Crush Alpha", "progress": 99, "threshold": 100,
                              "status": "active", "power": 60, "opponent": "Alpha"},
                 },
                 "npc_clocks": {}}
        with patch("systems.random.random", return_value=0.0):
            events = tick_world_clocks(state, 1440)
        conflict_events = [e for e in events if e.get("conflict")]
        self.assertEqual(len(conflict_events), 1)

    def test_ally_reinforcement_can_swing_an_otherwise_losing_matchup(self):
        from unittest.mock import patch
        from systems import resolve_clock_conflicts

        # Leaf alone (30) is weaker than Sand (60), so an unpatched random
        # roll should usually favor Sand — but Leaf's ally Mist (50) adds
        # half its power (25) to Leaf's side, tipping the effective balance
        # to 55 vs 60. Pin the roll right between "Leaf alone would lose"
        # and "Leaf-plus-ally wins" to prove the ally's contribution is
        # actually being counted, not just decorative.
        state = {"location_details": {}, "npc_memories": {},
                 "faction_clocks": {
                     "Leaf": {"name": "Leaf", "goal": "Push the border", "progress": 100, "threshold": 100,
                              "status": "turning_point", "power": 30, "opponent": "Sand", "ally": "Mist"},
                     "Sand": {"name": "Sand", "goal": "Hold the line", "progress": 0, "threshold": 100,
                              "status": "active", "power": 60},
                     "Mist": {"name": "Mist", "goal": "Support Leaf", "progress": 0, "threshold": 100,
                              "status": "active", "power": 50},
                 },
                 "npc_clocks": {}}
        # Effective power: Leaf 30+25=55, Sand 60. Total 115. A roll just
        # under 55/115 wins for Leaf — impossible without the ally (30/90).
        with patch("systems.random.random", return_value=0.4):
            events = resolve_clock_conflicts(state)
        self.assertTrue(any("Leaf has triumphed over Sand" in e["message"] for e in events))
        self.assertGreater(state["faction_clocks"]["Mist"]["power"], 50)  # ally shared in the win

    def test_sim_proposed_conflict_always_ends_in_a_stalemate(self):
        from unittest.mock import patch
        from systems import resolve_clock_conflicts

        # A hugely lopsided matchup that would obviously destroy the weaker
        # side in a real (GM-declared) conflict — but this one is marked
        # proposed by the deterministic sim, not the GM, so it must never
        # actually resolve to a winner/loser no matter how the dice land.
        state = {"location_details": {"Border Fort": {"controlling_faction": "Sand"}}, "npc_memories": {},
                 "faction_clocks": {
                     "Leaf": {"name": "Leaf", "goal": "Advance", "progress": 100, "threshold": 100,
                              "status": "turning_point", "power": 95, "opponent": "Sand",
                              "contested_location": "Border Fort", "proposed": True},
                     "Sand": {"name": "Sand", "goal": "Hold", "progress": 0, "threshold": 100,
                              "status": "active", "power": 5},
                 },
                 "npc_clocks": {}}
        with patch("systems.random.random", return_value=0.0):  # would guarantee Leaf a win if not proposed
            events = resolve_clock_conflicts(state)
        self.assertTrue(any("neither gains lasting advantage" in e["message"] for e in events))
        self.assertEqual(state["location_details"]["Border Fort"]["controlling_faction"], "Sand")  # unchanged
        self.assertNotEqual(state["faction_clocks"]["Sand"]["status"], "destroyed")
        self.assertFalse(state["faction_clocks"]["Leaf"]["proposed"])

    def test_player_involved_lets_a_proposed_conflict_resolve_for_real(self):
        from unittest.mock import patch
        from systems import resolve_clock_conflicts

        state = {"location_details": {}, "npc_memories": {},
                 "faction_clocks": {
                     "Leaf": {"name": "Leaf", "goal": "Advance", "progress": 100, "threshold": 100,
                              "status": "turning_point", "power": 95, "opponent": "Sand",
                              "proposed": True, "player_involved": True},
                     "Sand": {"name": "Sand", "goal": "Hold", "progress": 0, "threshold": 100,
                              "status": "active", "power": 5},
                 },
                 "npc_clocks": {}}
        with patch("systems.random.random", return_value=0.0):
            events = resolve_clock_conflicts(state)
        self.assertTrue(any("Leaf has triumphed over Sand" in e["message"] for e in events))

    def test_faction_destruction_vacates_other_territory_and_costs_its_leader(self):
        from unittest.mock import patch
        from systems import resolve_clock_conflicts

        state = {"npc_memories": {"Kage": {"goal": "Lead Sand", "leads_faction": "Sand"}},
                 "location_details": {
                     "Border Fort": {"controlling_faction": "Sand"},
                     "Sand Capital": {"controlling_faction": "Sand"},
                     "Oasis Camp": {"controlling_faction": "Sand"},
                 },
                 "faction_clocks": {
                     "Leaf": {"name": "Leaf", "goal": "Advance", "progress": 100, "threshold": 100,
                              "status": "turning_point", "power": 90, "opponent": "Sand", "contested_location": "Border Fort"},
                     "Sand": {"name": "Sand", "goal": "Hold", "progress": 0, "threshold": 100, "status": "active", "power": 5},
                 },
                 "npc_clocks": {}}
        with patch("systems.random.random", return_value=0.0):
            events = resolve_clock_conflicts(state)
        # The contested fort transfers; the OTHER two locations Sand held
        # are not touched by the contest itself but must still end up
        # vacated once Sand is destroyed — a real power vacuum, not a
        # frozen status quo.
        self.assertEqual(state["location_details"]["Border Fort"]["controlling_faction"], "Leaf")
        self.assertEqual(state["location_details"]["Sand Capital"]["controlling_faction"], "")
        self.assertEqual(state["location_details"]["Oasis Camp"]["controlling_faction"], "")
        self.assertIn(state["npc_memories"]["Kage"]["status"], ("deceased", "captured", "exiled"))
        self.assertTrue(any("unclaimed" in e["message"] for e in events))
        self.assertTrue(any("Kage" in e["message"] and "collapse" in e["message"] for e in events))

    def test_propose_faction_conflicts_creates_an_eligible_matchup(self):
        from unittest.mock import patch
        from systems import propose_faction_conflicts

        state = {"location_details": {"A Fort": {"controlling_faction": "Leaf"}, "B Fort": {"controlling_faction": "Sand"}},
                 "faction_clocks": {
                     "Leaf": {"name": "Leaf", "goal": "Advance", "progress": 0, "threshold": 100, "status": "active", "power": 50},
                     "Sand": {"name": "Sand", "goal": "Hold", "progress": 0, "threshold": 100, "status": "active", "power": 50},
                 }}
        with patch("systems.random.random", return_value=0.0), patch("systems.random.sample", return_value=["Leaf", "Sand"]):
            propose_faction_conflicts(state, elapsed_days=2)
        clock = state["faction_clocks"]["Leaf"]
        self.assertEqual(clock["opponent"], "Sand")
        self.assertTrue(clock["proposed"])
        self.assertEqual(clock["contested_location"], "B Fort")

    def test_event_window_turn_does_not_advance_time_and_can_conclude_on_flee(self):
        # The Event Window used to route every exchange through the full
        # time-skip pipeline (beginTimeSkip), which meant clicking through a
        # major event silently simulated the wider world forward on every
        # single beat. respond_to_event must resolve like an ordinary
        # action instead — no calendar/world-clock movement at all — and
        # must end the event when the player's own action disengages.
        class EventAI:
            def __init__(self):
                self.calls = 0

            def request(self, rules, payload, max_output_tokens=0):
                self.calls += 1
                if self.calls == 1:
                    return {"narrative": "The masked figure lunges as you weigh your options.",
                            "state_patch": {}, "events": [], "suggested_actions": ["Fight back", "Call for help", "Flee the scene"],
                            "event_concluded": False, "event_conclusion_summary": ""}
                return {"narrative": "You bolt down the alley, leaving the confrontation behind.",
                        "state_patch": {}, "events": [], "suggested_actions": ["Catch your breath", "Head home", "Watch from a distance"],
                        "event_concluded": True, "event_conclusion_summary": "The player fled before it resolved and does not know what happened next."}

        game = self.fresh()
        game.state["active_canon_event"] = "Ambush in the Market"
        game.state["interruption_context"] = "A masked figure ambushes the player in the crowded market."
        game.ai = EventAI()
        before_day, before_minutes = game.state["canon_day"], game.state["world_clock_minutes"]

        result1 = game.respond_to_event("Draw my weapon and size up the attacker.")
        self.assertFalse(result1["event_concluded"])
        self.assertEqual(game.state["canon_day"], before_day)
        self.assertEqual(game.state["world_clock_minutes"], before_minutes)
        self.assertEqual(game.state["active_canon_event"], "Ambush in the Market")

        result2 = game.respond_to_event("Actually, I run away and leave the area.")
        self.assertTrue(result2["event_concluded"])
        self.assertEqual(game.state["active_canon_event"], "")
        self.assertEqual(game.state["canon_event_engagement_count"], 0)
        self.assertEqual(game.state["canon_day"], before_day)
        self.assertEqual(game.state["world_clock_minutes"], before_minutes)
        self.assertIn("fled before it resolved", "".join(e["text"] for e in result2["story"]))

    def test_respond_to_event_requires_an_active_event(self):
        game = self.fresh()
        with self.assertRaises(RuntimeError):
            game.respond_to_event("Look around.")

    def test_gm_rules_faction_conflict_reflects_canon_vs_beyond_canon(self):
        # self.fresh() skips the real campaign-creation step that seeds
        # state["factions"] from the world's roster (engine_campaign.py) —
        # reproduce that seeding here since the FACTION CONFLICT rule only
        # appears once the campaign actually knows this world's factions.
        game = self.fresh()
        game.state["factions"] = dict(WORLD_DATA["Naruto"]["factions"])
        rules = game.gm_rules()
        self.assertIn("FACTION CONFLICT", rules)
        self.assertIn("REAL canon-established relationships", rules)

        game.state["canon_day"] = 7000  # past Naruto's last scripted canon event
        beyond_rules = game.gm_rules()
        self.assertIn("beyond this world's last established", beyond_rules)

    def test_tower_band_covers_every_floor_without_crashing(self):
        from worlds import tower_band, TOWER_FLOOR_COUNT
        for floor in range(1, TOWER_FLOOR_COUNT + 1):
            name, ecology = tower_band(floor)
            self.assertTrue(name)
            self.assertTrue(ecology)
        # Escalation should actually escalate — floor 1's band must differ
        # from floor 50's (the true top of THIS Tower), not flatten out.
        self.assertNotEqual(tower_band(1)[0], tower_band(TOWER_FLOOR_COUNT)[0])

    def test_tower_gm_rules_hard_locks_individual_scale_by_default(self):
        game = self.fresh("Solo Max-Level Newbie")
        game.state["tower_floor"] = 1
        rules = game.gm_rules()
        self.assertIn("SCALE LOCK", rules)
        self.assertIn("current scale: Individual", rules)
        self.assertIn("never owns or governs a country", rules)
        self.assertIn("ecological band", rules)

        game.state["simulation_scale"] = "Nation"
        upgraded_rules = game.gm_rules()
        self.assertIn("current scale: Nation", upgraded_rules)
        self.assertNotIn("never owns or governs a country", upgraded_rules)

    def test_scale_lock_applies_to_every_world_not_just_the_tower(self):
        game = self.fresh("Naruto")
        rules = game.gm_rules()
        self.assertIn("SCALE LOCK", rules)
        self.assertIn("current scale: Individual", rules)
        self.assertIn("never owns or governs a country", rules)
        self.assertNotIn("ecological band", rules)  # Tower-only content stays Tower-only

    def test_espionage_rule_covers_standing_assignments_and_multiple_updates(self):
        game = self.fresh("Naruto")
        game.state["factions"] = dict(WORLD_DATA["Naruto"]["factions"])
        rules = game.gm_rules()
        self.assertIn("ESPIONAGE", rules)
        self.assertIn("recurring=true", rules)
        self.assertIn("MULTIPLE distinct updates", rules)
        self.assertIn("player_knowledge", rules)
        self.assertIn("'captured', 'exiled', or 'deceased'", rules)

        game.state["factions"] = {}
        no_factions_rules = game.gm_rules()
        self.assertNotIn("ESPIONAGE", no_factions_rules)

    def test_core_rules_is_much_lighter_than_gm_rules_but_keeps_scale_lock(self):
        # Background/side tasks (chat replies, the incoming-message check,
        # the world tick, memory maintenance) don't need combat, quests, the
        # Tower, or faction conflict rules to do their job — but they DO
        # still need the scale-lock/identity/information-fog block, since a
        # side chat reply could just as easily leak an unearned government
        # contact as a full turn could.
        game = self.fresh("Naruto")
        game.state["factions"] = dict(WORLD_DATA["Naruto"]["factions"])
        heavy = game.gm_rules()
        light = game.core_rules(extra="Test extra instruction.")
        self.assertLess(len(light), len(heavy) * 0.2)
        self.assertIn("SCALE LOCK", light)
        self.assertIn("never owns or governs a country", light)
        self.assertIn("Test extra instruction.", light)
        self.assertNotIn("NON-NEGOTIABLE RULES", light)
        self.assertNotIn("FACTION CONFLICT", light)
        self.assertNotIn("ESPIONAGE", light)

    def test_background_social_tasks_use_the_lighter_core_rules(self):
        class RecordingAI:
            def __init__(self):
                self.seen_rules = []

            def request(self, rules, payload, max_output_tokens=0):
                self.seen_rules.append(rules)
                task = payload.get("task")
                if task == "side_chat_reply":
                    return {"reply": "", "state_patch": {}, "events": []}
                if task == "incoming_chat_check":
                    return {"send": False}
                if task == "background_world_tick":
                    return {"state_patch": {}, "heard_event": ""}
                if task == "memory_manager":
                    return {"state_patch": {}, "memory_note": ""}
                return {}

        game = self.fresh("Naruto")
        game.settings["model"] = "test-model"
        game.ai = RecordingAI()
        game.ai_bg = RecordingAI()
        game.state["contacts"] = {"Iruka": {"name": "Iruka", "can_contact": True}}

        game.resolve_side_chat("Iruka", "hey, you free?")
        game.maybe_generate_incoming_chat()
        game.state["last_protagonist_tick_day"] = int(game.state["canon_day"]) - 31
        game.create_world_event_if_due()
        game.run_memory_manager()

        for rules in game.ai.seen_rules + game.ai_bg.seen_rules:
            self.assertLess(len(rules), 6000, "a background/side task is using the full gm_rules() instead of core_rules()")
            self.assertNotIn("NON-NEGOTIABLE RULES", rules)

    def test_side_chat_scales_token_budget_to_message_length(self):
        class RecordingAI:
            def __init__(self):
                self.calls = []

            def request(self, rules, payload, max_output_tokens=0):
                self.calls.append(max_output_tokens)
                return {"reply": "", "state_patch": {}, "events": []}

        game = self.fresh("Naruto")
        game.settings["model"] = "test-model"
        game.ai = RecordingAI()
        game.state["contacts"] = {"Iruka": {"name": "Iruka", "can_contact": True}}

        game.resolve_side_chat("Iruka", "hey, you free?")
        self.assertEqual(game.ai.calls[-1], 150)

        game.resolve_side_chat("Iruka", "Can you meet me at the training grounds tonight to go over the mission briefing before we leave?")
        self.assertEqual(game.ai.calls[-1], 500)

    def test_advisor_uses_concise_mode_for_short_questions_only(self):
        class RecordingAdvisorAI:
            def __init__(self):
                self.calls = []

            def request(self, rules, payload, max_output_tokens=0):
                self.calls.append({"rules": rules, "schema": payload["schema"], "max_output_tokens": max_output_tokens})
                return {"summary": "Short answer.", "points": [], "follow_ups": []}

        game = self.fresh("Naruto")
        game.settings["model"] = "test-model"
        game.ai = RecordingAdvisorAI()

        game.ask_advisor("how strong am I?")
        short_call = game.ai.calls[-1]
        self.assertIn("SHORT/LOW-EFFORT", short_call["rules"])
        self.assertEqual(short_call["max_output_tokens"], 200)
        self.assertEqual(short_call["schema"]["points"], [])
        self.assertEqual(short_call["schema"]["follow_ups"], [])

        game.ask_advisor("What should I actually do about the Akatsuki threat and my standing with the Hokage?")
        long_call = game.ai.calls[-1]
        self.assertNotIn("SHORT/LOW-EFFORT", long_call["rules"])
        self.assertEqual(long_call["max_output_tokens"], 1000)
        self.assertNotEqual(long_call["schema"]["points"], [])

    def test_advisor_speaks_like_a_dm_and_resolves_untracked_questions_from_canon(self):
        # The Advisor used to default to a dry "Pax-Historia-style briefing"
        # report voice for anything but rules questions, and hedged on
        # anything not explicitly in tracked state instead of reasoning from
        # this world's canon at the current timeline point — a real
        # complaint, since most interesting questions ("what's Itachi up to
        # right now?") are about things the player hasn't personally tracked.
        class RecordingAdvisorAI:
            def __init__(self):
                self.payload = None
                self.rules = None

            def request(self, rules, payload, max_output_tokens=0):
                self.rules = rules
                self.payload = payload
                return {"summary": "Test.", "points": [], "follow_ups": []}

        game = self.fresh("Naruto")
        game.settings["model"] = "test-model"
        game.ai = RecordingAdvisorAI()
        game.state["canon_divergences"] = [{"turn": 3, "text": "Mizuki was arrested before he could steal the scroll."}]

        game.ask_advisor("What's Itachi been doing lately, and is that still true given how my campaign has gone?")

        self.assertIn("like a DM answering a question at the table", game.ai.rules)
        self.assertIn("don't deflect", game.ai.rules)
        self.assertIn("canon_divergences", game.ai.rules)
        self.assertEqual(game.ai.payload["canon_divergences"], game.state["canon_divergences"])

    def test_advisor_chart_is_sanitized_and_capped(self):
        class ChartAI:
            def request(self, rules, payload, max_output_tokens=0):
                return {
                    "summary": "Here's how you compare.",
                    "points": [], "follow_ups": [],
                    "chart": {
                        "title": "Power Levels", "unit": "DBZ Power Level",
                        "items": [
                            {"label": "You", "value": 9001},
                            {"label": "Rival", "value": "not a number"},
                            {"label": "", "value": 500},
                            {"label": "Bystander", "value": 12},
                        ] + [{"label": f"Extra {i}", "value": i} for i in range(10)],
                    },
                }

        game = self.fresh("Naruto")
        game.settings["model"] = "test-model"
        game.ai = ChartAI()
        result = game.ask_advisor("Graph my power level against the others in DBZ terms.")
        chart = result["entry"]["chart"]
        self.assertEqual(chart["title"], "Power Levels")
        self.assertEqual(chart["unit"], "DBZ Power Level")
        # The non-numeric and empty-label entries are dropped, and the list
        # is capped at 8 even though the model sent more.
        self.assertLessEqual(len(chart["items"]), 8)
        self.assertIn({"label": "You", "value": 9001.0}, chart["items"])
        self.assertNotIn("Rival", [it["label"] for it in chart["items"]])

    def test_advisor_chart_absent_when_ai_returns_nothing_or_garbage(self):
        class NoChartAI:
            def request(self, rules, payload, max_output_tokens=0):
                return {"summary": "Plain answer, no chart.", "points": [], "follow_ups": []}

        game = self.fresh("Naruto")
        game.settings["model"] = "test-model"
        game.ai = NoChartAI()
        result = game.ask_advisor("How strong am I?")
        self.assertIsNone(result["entry"]["chart"])

    def test_advisor_wording_requesting_a_graph_flags_the_ai_call(self):
        class RecordingAdvisorAI:
            def __init__(self):
                self.rules = None

            def request(self, rules, payload, max_output_tokens=0):
                self.rules = rules
                return {"summary": "Test.", "points": [], "follow_ups": []}

        game = self.fresh("Naruto")
        game.settings["model"] = "test-model"
        game.ai = RecordingAdvisorAI()
        game.ask_advisor("Can you chart my power level versus the others?")
        self.assertIn("WORDING SUGGESTS THEY WANT A VISUAL", game.ai.rules)

    def test_gm_rules_stays_cache_friendly_across_a_canon_day_change(self):
        # gm_rules() is resent in full on every single AI call. canon_day
        # changes on nearly every time skip, so if anything volatile sits
        # near the FRONT of the prompt, it breaks the request's cacheable
        # prefix (what OpenAI's and local llama.cpp-style servers' automatic
        # prompt caching key off of) on every skip — even though the ~300
        # lines of NON-NEGOTIABLE RULES below it haven't actually changed.
        # canon_day-dependent content was moved to the very end specifically
        # so the bulk of the prompt stays a stable, cacheable prefix instead.
        game = self.fresh("Naruto")
        game.state["factions"] = dict(WORLD_DATA["Naruto"]["factions"])
        before = game.gm_rules()
        game.state["canon_day"] = 15  # simulates a time skip moving the clock
        after = game.gm_rules()
        shared = 0
        for a, b in zip(before, after):
            if a != b: break
            shared += 1
        self.assertGreater(shared / len(before), 0.9,
                            "canon_day-dependent content leaked into the stable prefix — keep it at the tail of gm_rules()")

    def test_gm_rules_has_not_silently_ballooned(self):
        # Not a hard ceiling on writing new rules — a tripwire so a future
        # addition that meaningfully bloats every single AI call (this
        # session alone added several thousand characters across a handful
        # of features) gets a deliberate look before it ships, not a silent
        # creep someone only notices later as "the game feels laggy."
        game = self.fresh("Naruto")
        game.state["factions"] = dict(WORLD_DATA["Naruto"]["factions"])
        self.assertLess(len(game.gm_rules()), 60000)

    def test_starting_currency_scales_with_world_and_background(self):
        # Every campaign used to start with a flat 250 regardless of world
        # or background - meaningless in a Berries economy and identical
        # for a street orphan and a runaway noble alike. Wealth and this
        # world's own economic scale should both actually matter now.
        game = GameSession()
        rich = game.infer_starting_wealth("One Piece", "Runaway Noble", "Navigator", "the pampered heir to a trading fortune", 0)
        poor = game.infer_starting_wealth("One Piece", "Orphan Trainee", "Navigator", "a street orphan who grew up with nothing", 0)
        self.assertGreater(rich, poor * 3)  # comfortably outside the +/-15% jitter band

        naruto_amount = game.infer_starting_wealth("Naruto", "Academy Graduate", "Scout", "an ordinary academy graduate", 0)
        one_piece_amount = game.infer_starting_wealth("One Piece", "Runaway Noble", "Navigator", "born into a wealthy merchant family", 0)
        self.assertGreater(one_piece_amount, naruto_amount)  # Berries economy dwarfs Ryo, even wealthy-vs-ordinary

        stats = {name: 30 for name in abilities_for("One Piece")}
        game.new_campaign("Ari", "One Piece", "Adventurer", "a runaway noble born into a wealthy merchant family",
                           "", "", "Runaway Noble", "Navigator", stats)
        self.assertEqual(game.state["currency"]["name"], "Berries")
        self.assertNotEqual(game.state["currency"]["amount"], 250)
        self.assertGreater(game.state["currency"]["amount"], 1000)

    def test_naruto_offers_new_origins_archetype_and_start_location(self):
        ex = expansion_for("Naruto")
        for origin in ("Uchiha Clan Child", "Iron Country Samurai-in-Training", "Rogue Ninja (Missing-nin)",
                       "Anbu Root Recruit", "Chunin on Active Duty", "Jonin Squad Leader"):
            self.assertIn(origin, ex["origins"])
        self.assertIn("Samurai", ex["archetypes"])
        self.assertIn("Iron Country", [o["location"] for o in start_options_for("Naruto")])

    def test_rank_tier_origins_added_across_worlds_exclude_singular_leader_titles(self):
        # "Should be able to start as a Chunin or Jonin, but not the
        # Hokage" — mid/high individual rank is fair game as a selectable
        # origin everywhere, but the one singular seat at the top of each
        # world's hierarchy (Hokage, Yonko/Pirate King, Hunter Association
        # Chairman, the Tower's 1st Ranker, a world's one Demon Lord tier)
        # is never offered as a structured choice.
        never_offered = {
            "Naruto": ["Hokage"], "One Piece": ["Yonko", "Pirate King", "Fleet Admiral"],
            "Hunter x Hunter": ["Chairman", "Zodiac"], "Solo Max-Level Newbie": ["1st Ranker"],
            "Overgeared": ["Emperor"], "Reincarnated as a Slime": ["Demon Lord"],
        }
        for world, forbidden in never_offered.items():
            origins = expansion_for(world)["origins"]
            for title in forbidden:
                self.assertFalse(any(title.lower() in o.lower() for o in origins),
                                  f"{title} should never be a selectable origin in {world}")
        # And the higher-rank additions actually exist as real choices.
        self.assertIn("Veteran Crew Member", expansion_for("One Piece")["origins"])
        self.assertIn("Notorious Bounty-Head", expansion_for("One Piece")["origins"])
        self.assertIn("Licensed Hunter", expansion_for("Hunter x Hunter")["origins"])
        self.assertIn("Veteran Hunter", expansion_for("Hunter x Hunter")["origins"])
        self.assertIn("Elite Ranker", expansion_for("Solo Max-Level Newbie")["origins"])
        self.assertIn("Veteran Adventurer", expansion_for("Overgeared")["origins"])
        self.assertIn("Renowned Craftsman", expansion_for("Overgeared")["origins"])
        self.assertIn("Veteran Tempest Officer", expansion_for("Reincarnated as a Slime")["origins"])

    def test_rank_tier_origins_actually_grant_a_power_boost(self):
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Naruto")}
        beginner = game.infer_starting_profile("Naruto", "Civilian Academy Hopeful", "Scout", "an ordinary hopeful", dict(stats))
        chunin = game.infer_starting_profile("Naruto", "Chunin on Active Duty", "Scout", "", dict(stats))
        jonin = game.infer_starting_profile("Naruto", "Jonin Squad Leader", "Scout", "", dict(stats))
        self.assertEqual(beginner["power_band"], "Average beginner")
        self.assertEqual(chunin["power_band"], "Trained starter")
        self.assertEqual(jonin["power_band"], "Exceptional starter")

    def test_naruto_title_reflects_rank_and_affiliation_not_archetype(self):
        # Outside character creation, "Ninjutsu Student" never mattered as
        # an ongoing identity — what reads to another shinobi is rank and
        # affiliation: "Leaf - Chunin", "Sand - Genin", "Akatsuki - Member".
        game = GameSession()
        self.assertEqual(game.naruto_identity_title("Chunin on Active Duty", "Konohagakure"), "Leaf - Chunin")
        self.assertEqual(game.naruto_identity_title("Jonin Squad Leader", "Sunagakure"), "Sand - Jonin")
        self.assertEqual(game.naruto_identity_title("Academy Graduate", "Kirigakure"), "Mist - Genin")
        self.assertEqual(game.naruto_identity_title("Civilian Academy Hopeful", "Kumogakure"), "Cloud - Academy Student")
        self.assertEqual(game.naruto_identity_title("Anbu Root Recruit", "Konohagakure"), "Leaf - Anbu")
        self.assertEqual(game.naruto_identity_title("Rogue Ninja (Missing-nin)", "Konohagakure"), "Rogue - Missing-nin")
        self.assertEqual(game.naruto_identity_title("Iron Country Samurai-in-Training", "Iron Country"), "Iron Country - Samurai")
        self.assertEqual(game.naruto_identity_title("Academy Graduate", "Amegakure"), "Akatsuki - Member")

        stats = {name: 30 for name in abilities_for("Naruto")}
        game.new_campaign("Ari", "Naruto", "Adventurer", "", "", "", "Chunin on Active Duty", "Ninjutsu Student",
                           stats, start_location="Konohagakure")
        self.assertEqual(game.state["titles"], ["Leaf - Chunin"])
        # Every other world keeps the existing origin+archetype title —
        # this is a Naruto-specific change, not a universal one.
        one_piece = GameSession()
        one_piece_stats = {name: 30 for name in abilities_for("One Piece")}
        one_piece.new_campaign("Ari", "One Piece", "Adventurer", "", "", "", "Aspiring Pirate", "Swordsman", one_piece_stats)
        self.assertEqual(one_piece.state["titles"], ["Aspiring Pirate Swordsman"])

    def test_calendars_use_real_month_names_everywhere(self):
        for world in ("One Piece", "Naruto", "Hunter x Hunter", "Overgeared", "Reincarnated as a Slime"):
            self.assertEqual(format_calendar_date(world, 0, None, 0), "January 1, Year 1")

    def test_one_piece_offers_a_year_before_departure_starting_era(self):
        era = starting_era_by_id("One Piece", "year_before_departure")
        self.assertIsNotNone(era)
        self.assertEqual(era["start_day"], -367)

    def test_explicit_age_is_respected_verbatim_including_odd_combinations(self):
        # The point of a manual age field is that an unusual combination
        # (a 70-year-old fresh academy graduate) is a deliberate choice,
        # not a mistake for the game to quietly correct.
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Naruto")}
        game.new_campaign("Ari", "Naruto", "Adventurer", "a late bloomer", "", "", "Academy Graduate",
                           "Scout", stats, age="70")
        self.assertEqual(game.state["age"], "70")

    def test_blank_age_defers_to_the_opening_ai_inference(self):
        game = GameSession()
        stats = {name: 30 for name in abilities_for("Naruto")}
        game.new_campaign("Ari", "Naruto", "Adventurer", "an academy graduate", "", "", "Academy Graduate",
                           "Scout", stats, age="")
        self.assertEqual(game.state["age"], "")

    def test_new_campaign_age_field_exists_in_ui_and_is_sent_to_the_backend(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="nc-age"', html)
        self.assertIn('age: $("#nc-age").value.trim()', js)

    def test_webview2_no_longer_forces_software_rendering(self):
        # A real report: the portrait/scene/map Godot layers rendered as
        # opaque black squares instead of a transparent overlay in the
        # actual packaged app, despite verified-correct transparency when
        # tested in a normal browser (WebGL context alpha:true, all CSS
        # backgrounds transparent). Traced to --disable-gpu forcing WebView2
        # into software rendering, which doesn't correctly composite canvas
        # alpha onto the page. That flag existed to defend against an
        # unrelated "solid white window" bug on some hardware, but silently
        # broke a real, shipped feature for everyone — so it's no longer
        # forced on by default.
        launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")
        self.assertNotIn('os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"', launcher)

    def test_gm_rules_requires_committing_to_stated_actions(self):
        # A real player report: saying "I grab her and take her to safety"
        # got narrated as merely preparing to — the action was never
        # actually resolved. Lock in the instruction that closes that gap.
        game = self.fresh("Naruto")
        rules = game.gm_rules()
        self.assertIn("is something they DO, not merely intend", rules)
        self.assertIn("never a suspended non-answer", rules)

    def test_event_window_rules_reinforces_committing_to_actions(self):
        game = self.fresh("Naruto")
        game.state["active_canon_event"] = "The Nine-Tails Attacks"
        rules = game.event_window_rules()
        self.assertIn("actually happens this beat, not something merely attempted", rules)

    def test_event_window_frontend_has_a_continue_watching_option(self):
        # Not every beat asks for a decision — some are just showing the
        # player something. A generic "continue watching" affordance lets
        # them move past those without typing or picking a suggested action,
        # and a background job still in flight from before the event window
        # opened must not inject unrelated Chronicle noise behind the modal
        # while it's up.
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="btn-event-window-wait"', html)
        self.assertIn('$("#btn-event-window-wait").addEventListener("click"', js)
        self.assertIn("if (APP.eventWindow) return;", js)

    def test_event_window_rules_honors_a_stated_continue_to_resolution_intent(self):
        # A real report: saying "I help people until the attack is over"
        # kept getting more intermediate prompts instead of the scene
        # actually advancing to its conclusion — the player's own stated
        # endpoint was never being honored.
        game = self.fresh("Naruto")
        game.state["active_canon_event"] = "The Nine-Tails Attacks"
        rules = game.event_window_rules()
        self.assertIn("authorization to advance straight through the scene's remaining beats", rules)
        self.assertIn("Never repeat or lightly reword a beat", rules)

    def test_wants_event_resolution_detects_common_phrasings(self):
        game = GameSession()
        positive = [
            "I help people until the attack is over",
            "I keep fighting until things settle",
            "I hold this position for the rest of the fight",
            "I stay and help until it's done",
            "I keep going till the danger passes",
        ]
        for text in positive:
            with self.subTest(text=text):
                self.assertTrue(game._wants_event_resolution(text))
        negative = [
            "I attack the nearest enemy",
            "I wait until nightfall to sneak in",  # "until" present but no endpoint-of-THIS-event word
            "I ask what happened until now",
            "",
        ]
        for text in negative:
            with self.subTest(text=text):
                self.assertFalse(game._wants_event_resolution(text))

    def test_respond_to_event_overrides_a_noncompliant_model_that_still_wont_conclude(self):
        # This is the real report: the stronger per-turn directive alone
        # was not enough — a model can still return event_concluded=false
        # even after being told, explicitly, in this exact call, that the
        # player just ordered the scene to be seen through. The server must
        # not just ask more politely a second time; it has to take the
        # outcome as given, the same way _same_place and the power-goal
        # mechanic override an unreliable model elsewhere in this codebase.
        class StubbornAI:
            def request(self, rules, payload, max_output_tokens=0):
                self.last_payload = payload
                return {
                    "narrative": "You keep helping.", "state_patch": {}, "events": [],
                    "suggested_actions": ["a", "b", "c"],
                    "event_concluded": False,  # non-compliant, even with resolve_to_conclusion=True
                    "event_conclusion_summary": "",
                }

        game = self.fresh("Naruto")
        game.state["active_canon_event"] = "The Nine-Tails Attacks"
        ai = StubbornAI()
        game.ai = ai
        result = game.respond_to_event("I help people until the attack is over")
        self.assertTrue(ai.last_payload["resolve_to_conclusion"])
        self.assertIn("resolve_to_conclusion is true", ai.last_payload["requirements"][0])
        self.assertTrue(result["event_concluded"])
        self.assertEqual(game.state["active_canon_event"], "")

    def test_respond_to_event_does_not_force_conclusion_mid_combat(self):
        # Forcing an exit while a fight is still active would be a worse
        # bug than the one this override fixes — combat and a pending
        # intervention question both take priority over the override.
        class StubbornAI:
            def request(self, rules, payload, max_output_tokens=0):
                return {
                    "narrative": "The fight continues.", "state_patch": {"combat": {"active": True}}, "events": [],
                    "suggested_actions": ["a", "b", "c"],
                    "event_concluded": False, "event_conclusion_summary": "",
                }

        game = self.fresh("Naruto")
        game.state["active_canon_event"] = "The Nine-Tails Attacks"
        game.ai = StubbornAI()
        result = game.respond_to_event("I fight until the attack is over")
        self.assertFalse(result["event_concluded"])
        self.assertEqual(game.state["active_canon_event"], "The Nine-Tails Attacks")

    def test_continue_watching_repeats_the_players_last_action_not_a_static_wait(self):
        # The button used to always send the exact same static string,
        # which both misrepresented "continue" as passive watching when the
        # player was actively doing something, and produced near-identical
        # repeated output on consecutive clicks since the model kept
        # receiving literally the same input with nothing new to react to.
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("APP.eventWindow.lastAction = text;", js)
        wait_handler = js[js.index('$("#btn-event-window-wait").addEventListener("click"'):]
        wait_handler = wait_handler[:wait_handler.index("\n});") + 4]
        self.assertIn("APP.eventWindow && APP.eventWindow.lastAction", wait_handler)
        self.assertIn("Continue doing what I was already doing", wait_handler)
        # Must NOT overwrite lastAction with its own synthetic continuation
        # text, or a second click would start referencing the first click's
        # generated text instead of the real last action.
        self.assertNotIn("lastAction = text", wait_handler)
        self.assertNotIn("lastAction =", wait_handler)

    def test_administrative_notices_are_tagged_meta_not_system(self):
        # A real complaint: the Chronicle mixed real story prose with
        # bracket-labeled bookkeeping (stat deltas, undo confirmations,
        # "quest complete" notices) that reads as pure UI chrome, not
        # narration. Those specific notices now use a distinct "meta" tag
        # so the frontend can collapse them into a separate strip instead
        # of interrupting the story — while genuinely narrative content
        # that merely happens to carry a "system"-styled label (a dated
        # time-skip beat, a canon-timeline note, a quest briefing) is
        # untouched and stays tagged "system", not swept up by mistake.
        game = self.fresh("Naruto")

        # Stat growth: a real story delta but a purely mechanical readout.
        before = copy.deepcopy(game.state)
        game.state["stats"]["Taijutsu"] += 2
        game.append_growth_deltas(before)
        self.assertEqual(game.story_log[-1]["tag"], "meta")
        self.assertTrue(game.story_log[-1]["text"].startswith("[GROWTH]"))

        # notify(): a non-death mechanical readout goes to meta, but a
        # death-related one keeps its "danger" tag — that one is a real,
        # urgent story beat, not administrative noise.
        b, a = copy.deepcopy(game.state), copy.deepcopy(game.state)
        a["xp"] = b.get("xp", 0) + 1
        game.notify(b, a, [])
        self.assertEqual(game.story_log[-1]["tag"], "meta")
        game.notify(b, a, [{"message": "A quiet death passes unnoticed nearby."}])
        self.assertEqual(game.story_log[-1]["tag"], "danger")

        # These next three flush story_log as part of their own return
        # value (the same mechanism the API layer relies on), so the tag
        # has to be checked on what they returned, not on story_log after
        # the call — it's already been drained back to empty by then.
        result = game.take_turn("Fly to the moon barehanded", cached_assessment={"impossible": True, "reason": "No known ability grants flight."})
        self.assertEqual(result["story"][-1]["tag"], "meta")
        self.assertTrue(result["story"][-1]["text"].startswith("[ACTION NOT POSSIBLE]"))

        game.checkpoints.append(copy.deepcopy(game.state))
        result = game.undo()
        self.assertEqual(result["story"][-1]["tag"], "meta")
        self.assertTrue(result["story"][-1]["text"].startswith("[TURN REVERTED]"))

        game.checkpoints.append(copy.deepcopy(game.state))
        result = game.rewind_death()
        self.assertEqual(result["story"][-1]["tag"], "meta")
        self.assertTrue(result["story"][-1]["text"].startswith("[TIMELINE REWOUND]"))

    def test_quest_briefing_and_canon_notes_keep_their_system_tag(self):
        # These carry real, actionable narrative content (a quest's actual
        # objective/first step, a canon-timeline event's description) —
        # unlike the bookkeeping notices above, hiding these in a collapsed
        # strip would risk the player missing something they need, so they
        # must NOT have been swept into the "meta" retagging.
        source = (ROOT / "backend" / "engine_time.py").read_text(encoding="utf-8")
        self.assertIn('"tag": "canon_event" if major else "system"', source)
        self.assertIn('pending_appends.append({"text": "[SCHEDULED EVENT]\\n" + detail, "tag": "system"', source)
        turns_source = (ROOT / "backend" / "engine_turns.py").read_text(encoding="utf-8")
        start = turns_source.index("[QUEST STARTED")
        self.assertIn('"system"', turns_source[start:start + 500])

    def test_chronicle_collapses_meta_entries_into_a_system_strip(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('if (part.tag === "meta") {', js)
        self.assertIn("metaEntries.push(part)", js)
        self.assertIn('strip.className = "story-beat-system"', js)
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".story-beat-system{", css)

    def test_advisor_anchors_power_comparisons_to_a_stable_tier_reference(self):
        # Without a fixed reference, the Advisor previously improvised a
        # different power scale every time it was asked — fine for a single
        # answer, but inconsistent across a conversation (a rival placed at
        # "elite" one question could read as "legendary" the next with
        # nothing in the world having changed). The ladder is baked into
        # every advisor call so its own sense of "how strong is strong"
        # stays fixed for a given campaign.
        class RecordingAdvisorAI:
            def request(self, rules, payload, max_output_tokens=0):
                self.rules = rules
                return {"summary": "Test.", "points": [], "follow_ups": []}

        game = self.fresh("Naruto")
        game.settings["model"] = "test-model"
        ai = RecordingAdvisorAI()
        game.ai = ai
        game.ask_advisor("How strong am I compared to the Akatsuki?")
        self.assertIn("Mundane", ai.rules)
        self.assertIn("Reality-Bending", ai.rules)
        self.assertIn("stay consistent with that placement", ai.rules)

    def test_npc_goal_layers_feed_clocks_and_relationship_view(self):
        # Optional depth beyond the single .goal line every tracked NPC
        # already gets: immediate/mid-term/core-ambition. The clock
        # mechanism should prefer the concrete immediate_goal over the
        # older single-field goal when both are present (it's the more
        # specific, more actionable one), and the relationship view should
        # surface all three layers so the player can actually see them.
        game = self.fresh("Naruto")
        game.state["npc_memories"]["Itachi"] = {
            "goal": "Watch over the village from the shadows",
            "immediate_goal": "Recover a stolen scroll before it reaches Orochimaru",
            "mid_term_goal": "Dismantle the Akatsuki from within",
            "core_ambition": "Protect Sasuke without him ever knowing",
            "recurring": True,
        }
        tick_world_clocks(game.state, 1440)
        self.assertIn("Recover a stolen scroll before it reaches Orochimaru", game.state["npc_clocks"]["Itachi"]["goal"])

        view = relationship_snapshot(game.state)
        itachi = next(p for p in view["people"] if p["name"] == "Itachi")
        self.assertEqual(itachi["goal"], "Recover a stolen scroll before it reaches Orochimaru")
        self.assertEqual(itachi["mid_term_goal"], "Dismantle the Akatsuki from within")
        self.assertEqual(itachi["core_ambition"], "Protect Sasuke without him ever knowing")

        # An NPC with only the legacy single goal field still works exactly
        # as before — the new layers are additive, not required.
        game.state["npc_memories"]["Iruka"] = {"goal": "Keep the Academy running smoothly", "recurring": True}
        view2 = relationship_snapshot(game.state)
        iruka = next(p for p in view2["people"] if p["name"] == "Iruka")
        self.assertEqual(iruka["goal"], "Keep the Academy running smoothly")
        self.assertEqual(iruka["mid_term_goal"], "")
        self.assertEqual(iruka["core_ambition"], "")

    def test_gm_rules_document_the_optional_goal_layers(self):
        game = self.fresh("Naruto")
        rules = game.gm_rules()
        self.assertIn("immediate_goal", rules)
        self.assertIn("mid_term_goal", rules)
        self.assertIn("core_ambition", rules)

    def test_relationship_card_shows_goal_layers_when_present(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("person.mid_term_goal", js)
        self.assertIn("person.core_ambition", js)
        self.assertIn("Building toward:", js)
        self.assertIn("Deep down wants:", js)


if __name__ == "__main__":
    unittest.main()
