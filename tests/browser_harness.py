"""Deterministic narrator used only for manual multi-world browser QA."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app as app_module


class BrowserNarrator:
    model = "browser-qa"
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "uncached_input_tokens": 0,
             "output_tokens": 0, "calls": 0, "cost_usd": 0.0, "cost_unknown": False,
             "cost_is_conservative": False}

    def request(self, rules, payload, max_output_tokens=0):
        task = payload.get("task")
        state = payload.get("state") or payload.get("state_before") or {}
        world = state.get("world", "the world")
        name = state.get("name", "the traveler")
        if task == "opening":
            if world == "Naruto":
                narrative = (f"Morning mist hangs between Konohagakure's tiled roofs as {name} reaches the mission board. "
                             "A breathless courier reports that a border scout missed two check-ins, while a veteran instructor offers one hour of focused chakra practice before the search party leaves. "
                             "Neither lead waits forever, but both are within reach.")
            else:
                narrative = (f"Salt wind crosses the harbor as {name} watches a damaged courier boat drift toward the quay. "
                             "Its lone deckhand carries a sealed Marine route ledger, and a local navigator quietly offers a safer path before patrols arrive. "
                             "The harbor continues around them; no one assumes which side they will choose.")
            suggestions = (["Question the courier about the missing scout", "Train with the veteran before the search party leaves", "Inspect the departure route for signs of an ambush"]
                           if world == "Naruto" else
                           ["Question the deckhand about the damaged boat", "Ask the navigator to chart the safer route", "Inspect the Marine ledger before patrols arrive"])
            return {"narrative": narrative, "state_patch": {"appearance_desc": state.get("appearance_desc") or "A capable young traveler in practical local clothing."},
                    "events": [], "timeline_event": "", "suggested_actions": suggestions}
        if task == "assess_time_skip":
            actions = payload.get("planned_actions", [])
            hard = any("guardian" in str(action).lower() or "elite" in str(action).lower() for action in actions)
            checks = []
            if hard:
                ability = "Taijutsu" if world == "Naruto" else "Strength"
                checks.append({"id": "elite-check", "reason": "Overcome the elite guardian", "ability": ability, "skill": None,
                               "difficulty_min": 84, "difficulty_max": 88, "relevant_average_stat": 35,
                               "situational_bonus": 0, "time_difficulty_modifier": 0, "major_event": False,
                               "major_reason": "", "lethal_risk": "moderate", "lethal_warning": "The guardian can inflict a serious wound."})
            return {"checks": checks, "fixed_facts": "The listed actions remain in order.",
                    "simulation_notes": "World actors continue independently.", "reachable_actions": actions, "deferred_actions": []}
        if task == "resolve_time_skip":
            actions = payload.get("planned_actions", [])
            event_mode = payload.get("next_major_event_mode", {}).get("enabled")
            shinobi = world == "Naruto"
            route_name = "eastern road" if shinobi else "outer harbor channel"
            updates = []
            for index, action in enumerate(actions or ["Continue the prior course"]):
                updates.append({"sequence": index + 1, "type": "action", "title": "Plan advances", "related_action": action,
                                "narrative": f"{name} works through: {action}. The result follows the time available and the supplied check rather than assuming instant completion.",
                                "why_it_matters": "The action changes what nearby people can reasonably observe and respond to.",
                                "player_knowledge": "The immediate result is directly witnessed; distant motives remain uncertain.",
                                "next_pressure": "A competing group is moving toward the same objective."})
            updates.append({"sequence": 20, "type": "faction_reaction", "title": "A rival group moves", "related_action": "",
                            "narrative": f"Several hours later, a reliable witness reports that another team left by the {route_name}. The witness saw their departure but does not know their orders.",
                            "why_it_matters": "The route may become contested.", "player_knowledge": "The departure is confirmed; its purpose is only an inference.",
                            "next_pressure": "Reaching the next landmark first now has value."})
            if shinobi:
                quest = {"name": "The Missing Scout", "status": "Active", "category": "main",
                         "explanation": "A border scout missed two scheduled reports after investigating damaged signal posts.",
                         "giver": "Village courier", "first_step": "Inspect the eastern signal post",
                         "current_knowledge": ["The scout was last seen taking the eastern road", "Two signal posts stopped responding"],
                         "clear_conditions": ["Locate the scout", "Determine what disabled the signal posts"],
                         "objectives": [{"id": "find", "text": "Locate the missing scout", "status": "active", "optional": False, "progress": 20},
                                        {"id": "cause", "text": "Identify who damaged the signal posts", "status": "locked", "optional": False, "progress": 0}],
                         "branch_state": {"current": "search", "available": ["Follow the road", "Question nearby patrols"], "locked": ["Confront the saboteur"]},
                         "locations": [state.get("location", "Starting Region")], "risks": ["Unknown hostile presence"]}
            else:
                quest = {"name": "The Damaged Courier Boat", "status": "Active", "category": "main",
                         "explanation": "A courier boat limped into port with a stolen route page and signs of a deliberate attack.",
                         "giver": "Harbor watch", "first_step": "Inspect the hull and question the deckhand",
                         "current_knowledge": ["The damage happened outside the harbor", "One Marine route page is missing"],
                         "clear_conditions": ["Identify who attacked the courier", "Recover or account for the missing page"],
                         "objectives": [{"id": "attack", "text": "Identify the attackers", "status": "active", "optional": False, "progress": 20},
                                        {"id": "ledger", "text": "Account for the missing route page", "status": "locked", "optional": False, "progress": 0}],
                         "branch_state": {"current": "investigate", "available": ["Inspect the boat", "Question harbor witnesses"], "locked": ["Confront the attackers"]},
                         "locations": [state.get("location", "Starting Region")], "risks": ["Unknown vessel offshore"]}
            return {"narrative": "The ordered plan produces several distinct developments and ends at a clear decision point.",
                    "updates": updates, "state_patch": {"quests": [quest], "factions": {"Eastern Rivals": {"status": "active"}},
                                                       "npc_memories": {"Village Courier": {"goal": "Find the missing scout", "importance": "major", "attitude": "Concerned"}}},
                    "events": [], "timeline_events": [], "elapsed": {"amount": 2 if event_mode else 4, "unit": "hours"},
                    "interrupted": False, "interruption_reason": "", "intervention_prompt": "",
                    "major_event_reached": bool(event_mode), "major_event_kind": "personal" if event_mode else "",
                    "major_event_title": "The Scout's Signal Returns" if event_mode else "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": actions,
                    "deferred_actions": [],
                    "suggested_actions": (["Follow the eastern road before the rival team gains distance", "Ask the veteran to identify the signal damage", "Question the courier about the scout's usual contacts"] if shinobi else
                                          ["Inspect the courier boat before the tide changes", "Ask the navigator to chart the attack route", "Question harbor witnesses about the rival vessel"])}
        return {"narrative": "The situation remains stable.", "state_patch": {}, "events": [],
                "suggested_actions": ["Follow the strongest visible lead", "Prepare for the next obstacle", "Ask a local witness for details"]}


game = app_module.game
game.settings.update({"provider": "local", "model": "browser-qa", "secondary_model": ""})
game.ai = BrowserNarrator()
game.ai_bg = BrowserNarrator()

if __name__ == "__main__":
    app_module.app.run(host="127.0.0.1", port=int(os.environ.get("WW_QA_PORT", "8765")), debug=False, use_reloader=False)
