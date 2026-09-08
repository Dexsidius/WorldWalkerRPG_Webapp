"""No-network adapter for creation, combat summaries and shared engine hooks.

Offline turns are resolved by offline_choices, not by a free-text narrator.
Unknown generation tasks return {} to select existing local fallbacks.
"""
from ai_client import AI

OPENINGS = {
    "Naruto": "The village is already moving: couriers cross the street and a training ground rings with practice strikes.",
    "One Piece": "A sea breeze carries voices from the docks. Crews need capable hands, and a new voyage begins with the people you choose to trust.",
    "Hunter x Hunter": "Travelers trade practical information nearby. A reliable contact is worth more than an untested rumor.",
    "Bleach": "Daily duties continue around you. Your blade, your training and the people you work with will shape your next steps.",
    "Jujutsu Kaisen": "You take stock of your current abilities and contacts. Nothing here calls for a fight until a real threat is established.",
    "Overgeared": "Satisfy's streets are busy with players and residents making their own plans. You can find companions, practice, or take on local work.",
    "Solo Max-Level Newbie": "You check your equipment and the time remaining. Reliable allies and preparation both matter inside the Tower.",
    "Reincarnated as a Slime": "People are finding their place in a changing world. Your next step can be a new connection or time spent strengthening yourself.",
}

class OfflineSimulationClient(AI):
    def __init__(self, state_getter=lambda: {}, model="Worldwalker Offline Engine"):
        super().__init__(model=model, provider="offline")
        self.state_getter = state_getter
        self.last_endpoint = "offline://choices"

    def list_models(self, timeout=8):
        return [self.model]

    def estimate_request_cost(self, instructions, payload, max_output_tokens=700):
        return 0.0

    def request(self, instructions, payload, timeout=240, max_output_tokens=700):
        payload = payload if isinstance(payload, dict) else {}
        task = str(payload.get("task") or "").lower()
        state = self.state_getter() or {}
        if task in {"assess_action", "assess_time_skip", "narrator_and_resolution", "event_turn", "resolve_time_skip", "side_chat_reply"}:
            raise ValueError("Offline typing has been removed. Select a structured choice instead.")
        if task == "opening":
            opening = OPENINGS.get(state.get("world"), "Your journey begins with the people, resources and abilities already recorded for this character.")
            return {"narrative": f"{state.get('name', 'Traveler')} — {state.get('location', 'Starting Region')}. {opening}",
                    "state_patch": {}, "events": [], "suggested_actions": []}
        if task == "narrate_combat":
            outcome = payload.get("combat_outcome") or "resolved"
            return {"narrative": f"The encounter at {state.get('location', 'your location')} is {outcome}. Injuries and effects are recorded in the combat panel."}
        if task == "incoming_chat_check":
            return {"incoming_chats": []}
        if task == "background_world_tick":
            return {"updates": [], "state_patch": {}}
        if task == "reentry_recap":
            return {"narrative": f"Welcome back to {state.get('location', 'your campaign')}. Your saved choices are ready to continue."}
        if task == "memory_manager":
            return {"summary": "Campaign facts are stored in the local save."}
        if task == "continuity_correction":
            return {"narrative": "", "state_patch": {}}
        return {}
