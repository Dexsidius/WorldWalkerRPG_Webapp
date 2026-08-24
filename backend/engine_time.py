"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, json, random, re, secrets, threading
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, format_calendar_date
from ai_client import AI
from lore import format_lore_context
from portrait_generator import portrait_view
from state_guard import apply_guarded_patch, migrate_state
from continuity import update_continuity
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url, ai_text
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks)


# The minimum in-game time a single "next major event" click is allowed to
# consume before its claimed stop is honored — see run_time_skip's event_mode
# branch.
EVENT_STEP_FLOOR_MINUTES = 1440

DEFAULT_SETTINGS = {
    "provider": "local",
    "local_base_url": "http://localhost:1234/v1",
    "local_token": "",
    "api_key": "",
    "model": "",
    "secondary_model": "",
    "narration": "Concise",
    "autosave": True,
    "sound_enabled": True,
    "music_enabled": True,
    "music_volume": 0.35,
    "animations_enabled": True,
    "portrait_generation_enabled": True,
    "image_model": "gpt-image-2",
    "local_image_model": "",
    "portrait_quality": "low",
    "developer_mode": False,
}


WORLD_STARTER_GEAR = {
    "One Piece": "Travel-worn weapon and island supplies",
    "Hunter x Hunter": "Practical travel gear and training wraps",
    "Naruto": "Kunai pouch, shuriken and field supplies",
    "Solo Max-Level Newbie": "Beginner weapon and emergency potion",
    "Overgeared": "Beginner equipment set and trade tools",
    "Reincarnated as a Slime": "Species-appropriate natural weapon or focus",
    "Custom World": "Setting-appropriate weapon and travel kit",
}

WORLD_STARTER_SKILL = {
    "One Piece": "Foundation Combat Style", "Hunter x Hunter": "Conditioned Fundamentals",
    "Naruto": "Academy Fundamentals", "Solo Max-Level Newbie": "System Adaptation",
    "Overgeared": "Class Fundamentals", "Reincarnated as a Slime": "Intrinsic Species Trait",
    "Bleach": "Shinigami Fundamentals", "Custom World": "Background Expertise",
}

POOL_STATS = {
    "One Piece": (("Endurance", "Willpower"), ("Willpower", "Instinct")),
    "Hunter x Hunter": (("Strength", "Willpower"), ("Aura Control", "Willpower")),
    "Naruto": (("Taijutsu", "Willpower"), ("Chakra Control", "Ninjutsu")),
    "Solo Max-Level Newbie": (("Constitution", "Strength"), ("Intelligence", "Wisdom")),
    "Overgeared": (("Constitution", "Strength"), ("Intelligence", "Wisdom")),
    "Reincarnated as a Slime": (("Instinct", "Willpower"), ("Magicule Control", "Skill Mastery")),
    "Custom World": (("Constitution", "Strength"), ("Wisdom", "Intelligence")),
}

ABILITY_ASPECTS = {
    "fire": "Ember", "flame": "Ember", "heat": "Ember", "water": "Tide",
    "wind": "Gale", "air": "Gale", "lightning": "Storm", "electric": "Storm",
    "earth": "Stone", "ice": "Frost", "shadow": "Shadow", "dark": "Shadow",
    "light": "Radiance", "heal": "Renewal", "medical": "Renewal", "sense": "Echo",
    "sensor": "Echo", "speed": "Flash", "strong": "Titan", "strength": "Titan",
}

WORLD_ABILITY_FORMS = {
    "Naruto": [
        ("{aspect} Thread Technique", "a personal chakra transformation discovered during uneven early training",
         "forms fine {aspect_lower}-natured chakra threads for precise attacks, traps, sensing, or utility",
         "complex shapes quickly exhaust chakra and collapse when concentration breaks",
         "improve chakra control, learn the matching nature transformation, and develop larger stable patterns"),
        ("{aspect} Pulse", "an unusual chakra response first triggered during a formative moment",
         "releases a short pulse of {aspect_lower}-aligned chakra whose exact use adapts to the user's intent",
         "has short range and becomes unreliable when emotionally or physically exhausted",
         "practice controlled pulses, study sealing principles, and learn to sustain the effect"),
    ],
    "One Piece": [
        ("{aspect} Imprint Style", "an improvised island fighting art shaped by the character's environment",
         "imprints {aspect_lower}-themed force or motion into strikes, tools, and movement without ignoring physical limits",
         "requires preparation and stamina; stronger effects expose the user to retaliation",
         "condition the body, refine timing, and eventually combine the style with Haki if it is learned"),
        ("{aspect} Instinct", "a rare natural sensitivity that has not yet matured into formal Haki",
         "notices subtle {aspect_lower}-like patterns in danger, movement, and intent a moment earlier than normal",
         "provides impressions rather than certainty and fails amid overwhelming chaos",
         "survive demanding encounters, train awareness, and seek instruction in Observation Haki"),
    ],
    "Hunter x Hunter": [
        ("{aspect} Resonance", "a dormant Nen inclination expressed before the character understands aura",
         "causes aura to resonate with {aspect_lower}-themed conditions and hints at a future personal Hatsu",
         "remains inconsistent until the character properly opens and controls their aura nodes",
         "learn Ten, Ren, Zetsu and Hatsu, then define restrictions that strengthen the effect"),
        ("{aspect} Tell", "an exceptional learned instinct that may later become a Nen technique",
         "reads small bodily and environmental cues through a {aspect_lower}-themed mental association",
         "can be deceived and becomes noisy under stress or unfamiliar conditions",
         "test the instinct, study opponents, and later reinforce it with a suitable Nen category"),
    ],
    "Solo Max-Level Newbie": [
        ("Adaptive Skill: {aspect} Script", "a background-derived trait recognized when the System evaluates the player",
         "builds proficiency when the player repeats successful {aspect_lower}-aligned solutions",
         "starts at low rank and loses efficiency when the same trick is forced into unsuitable situations",
         "meet hidden conditions, diversify applications, and earn System achievements"),
    ],
    "Overgeared": [
        ("Rare Skill: {aspect} Craft", "a personal knack translated into a Satisfy-compatible skill",
         "adds {aspect_lower}-themed properties to appropriate crafted items or class techniques",
         "success depends on materials, production skill, design quality, and class compatibility",
         "raise production mastery, acquire better materials, and complete a related class quest"),
    ],
    "Reincarnated as a Slime": [
        ("Extra Skill: {aspect} Weave", "a desire and prior-life inclination crystallized into a world-valid skill",
         "shapes magicules into controlled {aspect_lower}-themed effects suited to the user's species",
         "output is limited by magicule capacity, analysis, resistances, and control",
         "increase magicule capacity, analyze related phenomena, and combine compatible skills"),
    ],
    "Custom World": [
        ("{aspect} Gift", "a setting-consistent talent produced from the player's requested parameters",
         "creates a flexible {aspect_lower}-themed effect within the established rules of the custom world",
         "begins narrow in scope and cannot bypass costs, counters, or prerequisites established by the setting",
         "practice its core use, discover its source, and earn broader applications through play"),
    ],
}

WORLD_BACKGROUND_COLOR = {
    "Naruto": ("a retired local shinobi", "a mission-era accident exposed the cost of acting without preparation"),
    "One Piece": ("a weathered island veteran", "a pirate raid forced the community to rely on anyone willing to stand up"),
    "Hunter x Hunter": ("a traveling specialist", "an encounter with a far stronger stranger revealed how large the world really was"),
    "Solo Max-Level Newbie": ("an obsessive strategy partner", "years spent mastering impossible game scenarios turned obscure knowledge into instinct"),
    "Overgeared": ("a demanding workshop senior", "a costly failure made persistence more important than easy talent"),
    "Reincarnated as a Slime": ("an elder familiar with local monsters", "a territorial crisis revealed both the value and danger of unusual abilities"),
    "Custom World": ("a locally respected mentor", "a dangerous incident revealed that talent without understanding creates consequences"),
}

WORLD_BACKGROUND_NAMES = {
    "Naruto": ("Mika Sato", "Daichi Mori", "Ren Aburame"),
    "One Piece": ("Mara Venn", "Old Corin", "Tessa Flint"),
    "Hunter x Hunter": ("Ilya Rook", "Mina Vale", "Toren Ash"),
    "Solo Max-Level Newbie": ("Seo Min-jae", "Han Yu-ri", "Park Do-jin"),
    "Overgeared": ("Elian Voss", "Mira Anvil", "Garron Pell"),
    "Reincarnated as a Slime": ("Rilsa", "Gelm", "Nemu"),
    "Custom World": ("Ari Vale", "Mara Stone", "Toren Reed"),
}

BACKGROUND_HOMES = (
    "A practical household taught them to contribute early, even when its members did not fully understand their ambitions.",
    "They were raised by a small circle of relatives and neighbors whose support came with duties they still feel responsible for.",
    "Their home life was modest and sometimes unstable, making preparation, loyalty, and self-reliance learned habits rather than slogans.",
)



# Canon-timeline data always uses each hidden village's Japanese name
# ("Konohagakure"), but the narrator and the player routinely use the
# common English alias instead ("Leaf Village", "the Hidden Leaf") — the two
# share no substring, so a plain fuzzy match misses what is obviously the
# same place. Grouped so _same_place can treat any alias in a group as
# equivalent to any other.
_LOCATION_ALIAS_GROUPS = [
    {"konohagakure", "leaf village", "hidden leaf", "the leaf", "konoha"},
    {"sunagakure", "sand village", "hidden sand", "suna"},
    {"kirigakure", "mist village", "hidden mist", "kiri"},
    {"kumogakure", "cloud village", "hidden cloud", "kumo"},
    {"iwagakure", "stone village", "hidden stone", "iwa"},
    {"amegakure", "rain village", "hidden rain", "ame"},
    {"otogakure", "sound village", "hidden sound", "oto"},
    {"land of fire", "fire country"},
    {"land of wind", "wind country"},
    {"land of water", "water country"},
    {"land of lightning", "lightning country"},
    {"land of earth", "earth country"},
]


# Words that mark an order as reaching for a genuinely new capability
# ("learn Haki", "master the technique", "unlock my bloodline") rather than
# routine practice of something the character already has — see
# _check_power_goal_progress.
_POWER_GOAL_KEYWORDS = ("learn", "master", "unlock", "awaken", "achieve", "obtain", "attain")


class TimeSkipMixin:
    @staticmethod
    def _same_place(player_location, event_location):
        """Fuzzy same-place check used to force a canon-event interruption
        when the player is obviously right where it's happening, rather than
        leaving that obvious case to model compliance alone (see canon_stop
        handling in run_time_skip)."""
        a, b = str(player_location or "").strip().lower(), str(event_location or "").strip().lower()
        if not a or not b:
            return False
        a_core = re.split(r"[—,-]", a)[0].strip()
        b_core = re.split(r"[—,-]", b)[0].strip()
        if not a_core or not b_core:
            return False
        if a_core == b_core or a_core in b_core or b_core in a_core:
            return True
        for group in _LOCATION_ALIAS_GROUPS:
            if (any(alias in a_core or a_core in alias for alias in group)
                    and any(alias in b_core or b_core in alias for alias in group)):
                return True
        return False

    @staticmethod
    def _power_goal_chance(days_invested):
        """Two checkpoints, matching what sustained commitment should
        realistically buy: ~80% after a month (30 days) of continuous
        focused effort toward the SAME stated goal, guaranteed after one
        further week (37 days). Ramps linearly toward each rather than
        jumping, so a shorter but still real attempt has a real, smaller
        shot instead of an all-or-nothing cliff at exactly day 30."""
        if days_invested <= 0:
            return 0.0
        if days_invested <= 30:
            return 0.8 * (days_invested / 30)
        if days_invested <= 37:
            return 0.8 + 0.2 * ((days_invested - 30) / 7)
        return 1.0

    def _check_power_goal_progress(self, orders, requested_days):
        """Mechanically pushes an explicitly-stated power/ability goal
        toward success the longer the player stays committed to that exact
        goal, rather than leaving a full month of stated focused effort
        entirely to a model that tends to under-reward it as unrealistic.
        Tracked by the goal's own text (not the model's own judgment of
        whether it's "the same goal"), so accumulation survives even if a
        turn's response never mentions continuity explicitly. Only ever
        pushes toward success — see the resolve_time_skip requirement that
        reads this — never away from it."""
        keyword_order = next((o for o in orders if any(k in str(o).lower() for k in _POWER_GOAL_KEYWORDS)), None)
        if not keyword_order or requested_days <= 0:
            return None
        key = re.sub(r"\s+", " ", str(keyword_order).strip().lower())
        tracker = self.state.get("power_goal_tracker")
        if not isinstance(tracker, dict) or tracker.get("key") != key:
            tracker = {"key": key, "days_invested": 0.0}
        tracker["days_invested"] = float(tracker.get("days_invested", 0) or 0) + requested_days
        self.state["power_goal_tracker"] = tracker
        chance = self._power_goal_chance(tracker["days_invested"])
        return {"order": keyword_order, "days_invested": round(tracker["days_invested"], 1), "chance": round(chance, 3),
                "mechanical_success": random.random() < chance}

    @staticmethod
    def estimate_action_minutes(action):
        text = str(action).lower()
        if any(k in text for k in ("sleep", "overnight", "full rest")): return 480
        if any(k in text for k in ("train", "practice", "study", "research", "craft", "forge")): return 60
        if any(k in text for k in ("travel", "journey", "sail", "cross the", "climb")): return 90
        if any(k in text for k in ("fight", "duel", "battle", "hunt")): return 30
        if any(k in text for k in ("buy", "sell", "shop", "ask around", "interview")): return 15
        if any(k in text for k in ("talk", "speak", "question", "eat")): return 10
        if any(k in text for k in ("look", "inspect", "check", "read")): return 5
        return 15

    def time_budget(self, amount, unit, orders):
        available = max(1, self.duration_minutes(amount, unit))
        estimates = [{"action": action, "estimated_minutes": self.estimate_action_minutes(action)} for action in orders]
        used, reachable, deferred = 0, [], []
        for item in estimates:
            if used + item["estimated_minutes"] <= available:
                reachable.append(item["action"]); used += item["estimated_minutes"]
            else:
                deferred.append(item["action"])
        total = sum(x["estimated_minutes"] for x in estimates)
        ratio = available / max(1, total)
        modifier = 0 if ratio >= 1 else 2 if ratio >= .75 else 3 if ratio >= .5 else 5 if ratio >= .25 else 8
        return {"available_minutes": available, "estimated_minutes": total, "estimated_actions": estimates,
                "time_ratio": round(ratio, 3), "time_dc_modifier": modifier,
                "reachable_actions": reachable, "deferred_actions": deferred}

    def assess_time_skip(self, amount, unit, orders_text, intensity):
        event_mode = unit == "next_event"
        if unit in {"moment", "next_event"}:
            amount = 1
        if isinstance(orders_text, list):
            clean_orders = [str(x).strip(" •\t") for x in orders_text if str(x).strip(" •\t")]
        else:
            clean_orders = [x.strip(" •\t") for x in str(orders_text or "").splitlines() if x.strip(" •\t")]
        queued = list(self.state.get("queued_actions", []))
        clean_orders = queued + [x for x in clean_orders if x not in queued]
        continuing_previous_orders = False
        if not clean_orders:
            clean_orders = [str(x).strip() for x in self.state.get("standing_orders", []) if str(x).strip()]
            continuing_previous_orders = bool(clean_orders)
        standing_orders = list(clean_orders)
        moment_deferred = []
        if unit == "moment" and len(clean_orders) > 1:
            moment_deferred = clean_orders[1:]
            clean_orders = clean_orders[:1]
        if event_mode:
            horizon_minutes = 180 * 1440
            canon_stop = self.next_canon_stop(horizon_minutes, "minutes")
            available_minutes = canon_stop["minutes_until"] if canon_stop else horizon_minutes
            budget = self.time_budget(available_minutes, "minutes", clean_orders)
            budget.update({"event_driven_major": True, "max_elapsed_minutes": available_minutes,
                           "safety_horizon_days": 180})
        else:
            canon_stop = None
            budget = self.time_budget(24, "hours", clean_orders) if unit == "moment" else self.time_budget(amount, unit, clean_orders)
        if unit == "moment":
            budget.update({"event_driven_moment": True, "max_elapsed_minutes": 1440,
                           "deferred_actions": moment_deferred + [x for x in budget.get("deferred_actions", []) if x not in moment_deferred]})
        if not event_mode:
            canon_stop = self.next_canon_stop(24, "hours") if unit == "moment" else self.next_canon_stop(amount, unit)
        if canon_stop:
            budget["requested_minutes"] = budget["available_minutes"]
            budget["available_minutes"] = canon_stop["minutes_until"]
            budget["canon_stop"] = canon_stop
        with self.lock:
            self.state["standing_orders"] = standing_orders
            self.state["time_mode"] = unit
            self.checkpoints.append(copy.deepcopy(self.state))
            self.checkpoints = self.checkpoints[-40:]
        payload = {
            "task": "assess_time_skip", "duration": {"amount": amount, "unit": unit},
            "planned_actions": clean_orders, "intensity": intensity, "state": self.trimmed_state_for_ai(),
            "time_budget": budget, "continuing_previous_orders": continuing_previous_orders,
            "requirements": [
                "Identify every activity/project during this period whose outcome materially varies with skill, danger, endurance, learning rate, chance, opposition, or world conditions.",
                "Create a compact set of contextual d100 checks for those uncertain outcomes.",
                "Do not roll any dice yourself.",
                "Long repetitive training should usually require a small number of representative milestone checks, not hundreds of rolls.",
                "Treat planned_actions as an ordered itinerary. Carry them out in listed order across the available duration; do not flatten them into one repeated activity.",
                "Compare the concrete time_budget against the itinerary. Insufficient time makes rushed attempts harder and leaves later actions deferred rather than magically completed.",
                "Apply time_difficulty_modifier to checks affected by rushing. If an action cannot even begin in sequence, list it in deferred_actions and create no roll for it.",
                "If continuing_previous_orders is true, treat these as ongoing standing instructions and continue them naturally rather than restarting them from zero.",
                "If the list is truly empty, advance the world naturally without forcing a character action; NPCs, factions, travel, rumors, markets and scheduled pressures still move.",
                "When time_budget.event_driven_moment is true, assess only the single next immediate meaningful story beat. That beat may plausibly consume minutes or several hours, but never more than 24 hours. Do not resolve later queued actions in the same moment.",
                "When time_budget.event_driven_major is true, assess the standing plan across the horizon until the earliest major personal development or major canon event — a genuine tier-of-power change, transformation, or class/form change, a real battle, a world-changing event, or a major canon event, and nothing smaller. An ordinary stat or skill increase is NOT enough by itself, no matter how large the number — only stop for a stat/power change when it actually pushes the character into a different tier of power altogether. Routine beats (conversations, small skirmishes, incremental gains, rumors, errands) are updates, not stopping points, no matter how many of them occur across the horizon. The eventual major event ends naturally without asking whether to intervene. EXCEPTION: if planned_actions itself names an explicit wait condition (\"wait until the attack,\" \"hold until she returns,\" \"watch until someone comes\"), that named condition IS the stopping point for this skip, overriding the generic taxonomy above even if it wouldn't otherwise qualify as major — the player was explicit about what they're waiting for, so honor exactly that instead of substituting a different, bigger event. If the named condition doesn't plausibly occur within the available horizon, say so explicitly in the resulting narrative rather than silently stopping for something else.",
                "Difficulty ranges follow world lore and what is realistic for an average relevant character at this time; never scale them to the player.",
                "Mark major_event for every evolution, transformation, climactic confrontation or irreversible major turning point so the player rolls manually.",
                "Extreme schedules can cause injury, burnout, resource depletion, or death if genuinely plausible; flag lethal checks.",
                "If any planned_action explicitly aims to acquire, unlock, or master a significant new power, ability, technique, or tier of strength for this world (not routine stat/skill practice — a genuine capability the character does not have yet), set power_jump_warning to one short in-character sentence, spoken the way a mentor, elder, or the world's own lore would frame it — never a system/meta voice, never mention percentages, mechanics, or 'this game'. It should read as real in-world foreshadowing (a warning about the cost or weight of such power, or a promise that sustained dedication can genuinely get them there), not a UI disclaimer wearing a costume."
            ],
            "schema": {
                "checks": [{"id": "short id", "reason": "under 10 words", "ability": self.ability_enum(), "skill": "name or null", "difficulty_min": "1-100 contextual lower edge", "difficulty_max": "1-100 contextual upper edge", "relevant_average_stat": "average relevant world-relative stat", "situational_bonus": "-20 to 20", "time_difficulty_modifier": "0-25 from time pressure", "major_event": "bool", "major_reason": "short reason or empty", "lethal_risk": "none|low|moderate|high|extreme", "lethal_warning": "warning or empty, under 20 words"}],
                "fixed_facts": "under 30 words",
                "simulation_notes": "under 30 words", "reachable_actions": "ordered list",
                "deferred_actions": "ordered actions that cannot be reached in the allotted time",
                "power_jump_warning": "one in-character sentence per the requirement above, or empty if nothing planned reaches for a new power/ability"
            }
        }
        rules = self.gm_context(" ".join(clean_orders)) + " Keep every field extremely terse — this is a mechanical planning pass, not prose."
        assessment = self.ai.request(rules, payload, max_output_tokens=700)
        assessment.setdefault("time_budget", budget)
        if canon_stop:
            assessment["canon_stop"] = canon_stop
        assessment.setdefault("reachable_actions", budget["reachable_actions"])
        assessment.setdefault("deferred_actions", budget["deferred_actions"])
        if moment_deferred:
            authored_deferred = assessment.get("deferred_actions") if isinstance(assessment.get("deferred_actions"), list) else []
            assessment["deferred_actions"] = moment_deferred + [x for x in authored_deferred if x not in moment_deferred]
        checks = assessment.get("checks", []) if isinstance(assessment.get("checks"), list) else []
        previews = [self.preview_check(check, assessment, clean_orders[index] if index < len(clean_orders) else "")
                    for index, check in enumerate(checks) if isinstance(check, dict)]
        assessment["check_previews"] = previews
        assessment["difficult_checks"] = [preview for preview in previews if preview.get("difficult")]
        # A live major canon event ("TAKE PART — EXPERIENCE IT" or "LET IT
        # PLAY OUT — DECIDE BY ROLL") already promises the player a real
        # stake in what happens — but only ONCE, on the very first beat of
        # actually engaging it. Forcing a check is exactly the kind of
        # compliance gap this hardcodes around elsewhere (see _same_place):
        # without it, engaging could silently be a no-op the first time. But
        # applying that same force to EVERY later beat inside the same event
        # turns what's supposed to be a flowing choose-your-own-adventure
        # scene into a minigame after minigame after minigame — the model's
        # own judgment is trusted for every beat after the first, same as it
        # is anywhere else in normal play.
        if (unit == "moment" and self.state.get("active_canon_event")
                and not int(self.state.get("canon_event_engagement_count", 0) or 0)
                and not assessment["difficult_checks"]):
            if previews:
                previews[0]["difficult"] = True
                assessment["difficult_checks"] = [previews[0]]
            else:
                synthetic = {"id": "canon_event_response", "reason": f"Engage directly in {self.state['active_canon_event']}",
                             "ability": abilities_for(self.state.get("world", "Custom World"))[0], "skill": None,
                             "difficulty_min": 55, "difficulty_max": 70, "relevant_average_stat": 30,
                             "situational_bonus": 0, "time_difficulty_modifier": 0, "major_event": True,
                             "lethal_risk": "moderate"}
                preview = self.preview_check(synthetic, assessment, clean_orders[0] if clean_orders else "")
                preview["difficult"] = True
                assessment["checks"] = checks + [synthetic]
                assessment["check_previews"] = previews + [preview]
                assessment["difficult_checks"] = [preview]
        assessment["requires_difficulty_confirmation"] = bool(assessment["difficult_checks"])
        return {"assessment": assessment, "amount": amount, "unit": unit, "orders": clean_orders, "intensity": intensity,
                "time_budget": budget}

    def run_time_skip(self, amount, unit, orders, intensity, assessment, confirmed_lethal=False, confirmed_power_goal=False, manual_rolls=None, challenge_modes=None):
        event_mode = unit == "next_event"
        if unit in {"moment", "next_event"}:
            amount = 1
        checks = assessment.get("checks", [])
        canon_stop = assessment.get("canon_stop") if isinstance(assessment.get("canon_stop"), dict) else None
        moment_mode = unit == "moment"
        event_horizon = int(assessment.get("time_budget", {}).get("max_elapsed_minutes", 180 * 1440) or 180 * 1440)
        simulation_amount = canon_stop.get("minutes_until", 0) if canon_stop else (event_horizon if event_mode else 1440 if moment_mode else amount)
        simulation_unit = "minutes" if canon_stop or moment_mode or event_mode else unit
        for check_index, chk in enumerate(checks):
            if chk.get("lethal_risk") in ("high", "extreme") and not confirmed_lethal:
                return {"status": "lethal_confirm_required", "check": chk}
        if assessment.get("power_jump_warning") and not confirmed_power_goal:
            return {"status": "power_goal_confirm_required", "warning": assessment["power_jump_warning"]}
        manual_rolls = manual_rolls if isinstance(manual_rolls, dict) else {}
        challenge_modes = challenge_modes if isinstance(challenge_modes, dict) else {}
        for chk in checks:
            check_id = str(chk.get("id") or chk.get("reason") or "major")
            if chk.get("major_event") and check_id not in manual_rolls:
                return {"status": "manual_roll_required", "check": chk, "check_id": check_id,
                        "theme": self.state.get("world", "Custom World")}
        # A "moment" is exactly one action (see assess_time_skip's truncation)
        # — this is the live path every single normal turn actually resolves
        # through, so the action's own Chronicle line belongs here, with any
        # roll for it attaching right underneath (see appendStoryEntries).
        # Deliberately placed AFTER both early-return gates above: a lethal
        # or major-event check re-enters this same function on the SAME
        # orders once the player confirms/rolls, and appending here first
        # would otherwise write the player's action line to the Chronicle
        # once per gate hit — twice over, for the exact same single action.
        if moment_mode and orders:
            self.append("> " + str(orders[0]), "player")
        results = []
        for chk in checks:
            normalized = copy.deepcopy(chk)
            time_modifier = int(chk.get("time_difficulty_modifier", 0) or 0)
            if not time_modifier:
                time_modifier = int(chk.get("time_dc_modifier", assessment.get("time_budget", {}).get("time_dc_modifier", 0)) or 0) * 3
            if normalized.get("difficulty_min") is not None: normalized["difficulty_min"] = int(normalized["difficulty_min"]) + time_modifier
            if normalized.get("difficulty_max") is not None: normalized["difficulty_max"] = int(normalized["difficulty_max"]) + time_modifier
            check_id = str(chk.get("id") or chk.get("reason") or "major")
            res = self.roll(normalized, manual_rolls.get(check_id) if check_id in manual_rolls else None)
            res.update({"id": chk.get("id"), "reason": chk.get("reason"), "major_event": bool(chk.get("major_event")),
                        "time_difficulty_modifier": time_modifier, "challenge_mode": challenge_modes.get(check_id, "")})
            results.append(res)
            action_label = orders[check_index] if check_index < len(orders) else chk.get("reason", "Time-skip milestone")
            self.append(self.format_roll_summary(action_label, res), "roll", detail=self.format_bonus_breakdown(res.get("bonus_breakdown")))

        # A month of genuinely stated, sustained commitment to one explicit
        # power/ability goal ("train until I learn Haki") kept reading as a
        # near-miss or partial result far more often than not — a model
        # left entirely to its own judgment tends to under-reward "realism"
        # over the player actually getting the power fantasy they asked
        # for. This mechanically pushes toward success as accumulated,
        # continuous days on the SAME stated goal cross real thresholds,
        # rather than leaving it purely to narrative taste — but only ever
        # pushes toward success, never away from it, and only for plain
        # explicit-duration skips (not moment/event/canon-interrupted ones,
        # where "how many days was this" isn't a clean question).
        power_goal = None
        if not moment_mode and not event_mode and not canon_stop:
            power_goal = self._check_power_goal_progress(orders, self.duration_minutes(amount, unit) / 1440.0)

        payload = {
            "task": "resolve_time_skip", "duration": {"amount": simulation_amount, "unit": simulation_unit},
            "original_requested_duration": {"amount": amount, "unit": unit}, "planned_actions": orders,
            "intensity": intensity, "assessment": assessment, "dice_results": results, "state_before": self.trimmed_state_for_ai(),
            "moment_mode": {"enabled": moment_mode, "max_elapsed_minutes": 1440, "instruction": "Resolve only the next immediate meaningful beat"},
            "live_event_scene": bool(moment_mode and self.state.get("active_canon_event")),
            "next_major_event_mode": {"enabled": event_mode, "max_elapsed_minutes": event_horizon,
                "canon_boundary": canon_stop or {},
                "instruction": "Continue through routine beats and stop ONLY at the earliest genuinely major personal development or the canon boundary — see the requirements below for exactly what qualifies. End naturally; never ask whether the player intervenes."},
            "power_goal_progress": power_goal or {},
            "requirements": [
                "Simulate the ENTIRE skipped period, not just its ending scene.",
                "Any period longer than a single moment should cover several distinct notable beats/events spread across the timespan (e.g. across a day: morning training, an afternoon encounter, an evening development), not one flattened event. Only moment-to-moment turns focus on a single thing at a time.",
                "When moment_mode.enabled is true, resolve exactly one immediate meaningful story beat based on current context and the first player action/standing order. Let that beat consume a believable amount of time—even several hours—but never more than 24 hours. Defer every later action and stop at the next decision point.",
                "When live_event_scene is true, the player is personally living through a major canon event inside its own dedicated scene, one beat at a time, like a choose-your-own-adventure page — the narrative should read as immediate, present, moment-to-moment sensory experience (what they see/hear/feel RIGHT NOW, who's near them, what's changing second to second), not a summary or a report of what happened. Directly react to and build on whatever the player just chose or typed — their exact stated action should visibly move the scene forward, not be politely acknowledged and sidestepped. End every beat at a genuine fork the player must actually choose from next (via suggested_actions and/or the open narrative itself), actively pushing them toward the event's real climax rather than stalling in place. Do not force a difficult check on every single beat of this scene — most beats should just be narrative choice and consequence; reserve real risk/checks for the moments that actually warrant them, exactly as you would for any other action.",
                "When next_major_event_mode.enabled is true, keep simulating through routine decisions and include clear chronological updates, but do not stop for ordinary prompts. The bar for stopping is deliberately high — this mode exists to skip PAST the small stuff and run until the intended goal is reached or the available time fully elapses, not pause partway through for anything less. Stop ONLY when something on this scale actually happens: the character moving into a genuinely different tier of power (not just a stat/skill increase — an actual breakthrough, transformation, or class/form change), a real battle or life-threatening confrontation, a world-changing event (a war, disaster, regime change, a faction destroyed or founded), or a major canon timeline event. A defining goal being fully completed also qualifies. None of the following are ever, by themselves, a reason to stop — narrate them as an ordinary update and keep going: a routine conversation or social call, a minor non-lethal scuffle or scare, an ordinary stat tick or incremental skill/level gain (even a large one, as long as it's the same tier of power as before), a passing rumor or piece of news, a small transaction or errand, meeting or running into someone without real stakes, or anything that would read as one line in a history feed rather than a headline. If you are genuinely unsure whether something clears this bar, it does not — keep simulating past it, all the way to the requested goal or the end of the available time, whichever comes first. Return no intervention_prompt and do not ask Yes/No.",
                "Present world updates with information fog: distinguish what objectively changed, why it matters, and what the character can actually know through witnesses, messages, evidence, travel time, or rumor. The world is not omniscient and information never teleports.",
                "Treat the player as one actor inside an independently moving world, not as its automatic protagonist. Keep the current simulation scale grounded in the character's actual reach while still advancing distant NPC and faction agendas.",
                "The player's planned actions are an ordered itinerary: attempt each in sequence and distribute the available time sensibly.",
                "Never complete a deferred action. If time expires during an action, describe partial progress and keep the unfinished or unstarted action in deferred_actions.",
                "Training intensity must affect gains, fatigue, injury risk, resources, and sustainability.",
                "Respect travel times, sleep, recovery, money, food, healing, social obligations, faction responses, lore, and world chronology.",
                "Use supplied dice results exactly for uncertain milestones.",
                "If an action begins or accepts a quest/mission/job/contract, give a complete readable briefing and add a structured active quest: name, giver/cause, objective, known location, known risks, first actionable step, current knowledge, and clear completion conditions.",
                "Write skills in plain language with effect, use/activation, limitation or cost, and growth path; never expose raw arrays, internal identifiers, or calculation traces as descriptions.",
                "Advance NPCs, factions, canon events, quests, relationships, markets, wars, organizations, and rumors independently.",
                "Generate meaningful world movement on EVERY Advance, including turns with no new player action or turns that merely continue standing orders. If an event genuinely requires the player's decision, stop at that moment and return a concrete intervention_prompt.",
                "Prior player actions and promises continue affecting outcomes.",
                "If power_goal_progress.order is present and power_goal_progress.mechanical_success is true, this time skip's narrative MUST conclude with the character genuinely succeeding at that stated power/ability goal — sustained, focused commitment (power_goal_progress.days_invested cumulative days on this exact goal) has crossed the threshold for a real breakthrough. Write a concrete, lore-consistent explanation for why it clicked now (not a coincidence, not a shortcut — the payoff of that sustained effort), set goal_status.achieved=true, and reflect the new capability in state_patch (a new skill/technique entry, or whatever this world's own mechanism for a new power is). If mechanical_success is false or power_goal_progress is empty, judge the outcome normally on its own narrative merits — this field only ever pushes toward success, never toward failure.",
                "If an interruption is important enough that the player would reasonably stop and choose what to do, end the skip EARLY and return interrupted=true with the amount of time actually elapsed.",
                "Treat action wording such as 'until', 'master', 'learn', 'find', 'reach', 'finish', 'complete', or another clear result as a goal condition. If that goal is achieved before the requested duration ends, stop immediately on the day/minute of completion, set goal_status.achieved=true, and return only the actual elapsed time.",
                "If a stated goal is not achieved by the end of the requested duration, set goal_status.achieved=false and explain the concrete in-world cause: insufficient insight, teacher/resources, injury, interruption, failed milestone, difficulty, or another setting-valid reason. Include a useful next_hint grounded in what the character learned.",
                "If assessment.canon_stop exists, simulate only through that stop boundary and do not grant progress, travel, recovery or consequences from time after it.",
                "When stopping at canon_boundary/assessment.canon_stop specifically, decide plausible involvement in exactly two steps, in order. STEP 1 — check the player's own current status: location, travel time from the event, rank/standing, and any established affiliation with its participants. STEP 2 — check the event's own scale: canon_stop.scope is 'wide' when the event affects an entire location/population (a village under attack, a war, a public ceremony) and 'personal' when it's a small-cast incident that merely happens to be tagged with a village-level location for convenience (most of them). Only a wide-scope event lets simply being in the same broad location justify presence; for a personal-scope event, sharing that location proves nothing — most of that village's population never even learns a small-cast incident like this happened at all, let alone happens to be standing in the right room, so the default chance of genuine involvement is very low unless the player's own status from Step 1 specifically puts them there or with its participants. If both steps support it, set interrupted=true and phrase intervention_prompt as a genuine choice to personally engage. Otherwise set interrupted=false, leave intervention_prompt empty, and instead deliver the event as a detailed, concrete report within updates (via news, a messenger, rumor, or documentation appropriate to how fast word could reach them — for a personal-scope event this is often nothing at all, not even a rumor, unless something would plausibly surface it), then continue narrating from where the player actually is. Never ask an intervention question of a player who could not possibly be there. The event's own scale is never itself a reason to force presence — a world-shaking (wide-scope) event still only interrupts someone who was actually positioned for it: if the Nine-Tails attacks Konoha and the player is an ordinary genin elsewhere in the village with no established tie to the Hokage's family or its guard, they experience village-wide chaos and read about the rest, they do not end up in the room with Minato and Kushina; if the player had instead been established earlier as assigned to guard them or traveling with them, presence follows naturally from that standing. This same split applies WITHIN a wide-scope event, not just to whether it opens a scene at all: a wide scope justifies the player being caught up in the event's genuinely public component (the village-wide fighting, evacuation, fires, damage), never in a specific named-character confrontation buried inside it that nobody actually witnessed — Obito's attack on Minato and Kushina during the Nine-Tails' release happened in near-total isolation, so an ungoverned genin swept up in the wide village chaos experiences exactly that chaos and nothing more; only Step 1 (an established tie to Minato, Kushina, or their guard) can put them in that private confrontation, wide scope alone never does. A personal-scope beat needs Step 1 to justify it on its own — if Naruto steals the forbidden scroll after graduation and the player was never with Naruto or otherwise tied into that thread, it is not even background news to them, let alone a scene, with no roll and no intervention choice offered, because they were never in a position to affect it either way. Default to the report (or nothing at all), not the scene, whenever presence is not clearly established.",
                "For uninterrupted training, treat every training day/session as real accumulated practice; a month is roughly 30 daily sessions, never one generic reward.",
                "In non-System worlds do not award XP or levels. Show progress through open-ended stats, knowledge, techniques, ranks and titles. Use XP only if state._uses_xp is true.",
                "Every breakthrough result requires a concrete lore-based cause and a substantially larger but world-valid gain.",
                "Record all meaningful changes mechanically."
                ,"Return separate chronological updates for every queued action that begins, every major reaction by an NPC/faction/world system, every interruption, and every major consequence. Do not combine unrelated reactions into one paragraph.",
                "Each update should be decently detailed: normally 2-5 sentences with cause, immediate reaction, consequence, and any unresolved pressure.",
                "Give every update its own canon_day so multi-day skips read as a dated sequence of beats, not one undated blob — like a history feed, not a single diary entry. A single day may reasonably contain more than one update when multiple things happen.",
                "Bold the proper names of every character, faction, and named location the first time each appears within an update's narrative (e.g. **Kaito Moriyama**, **Hueco Mundo**), the way a wiki or timeline entry would — this is for readability, not emphasis of importance.",
                "Fill in each update's map_changes only on the rare beat that actually shifts who controls a territory/settlement/map node, and quote only on the rare beat with a real, attributable spoken line worth surfacing on its own — both are empty on most updates, and forcing either in when nothing warrants it is worse than leaving them empty.",
                "If simulating this period would put the player character in real physical danger — a fight, ambush, hazard, or confrontation with a real chance of injury or worse — always stop the skip immediately BEFORE that danger resolves, even if standing orders said to keep going; danger is never auto-resolved silently. Set interrupted=true, interruption_kind='danger', and phrase intervention_prompt as a choice between taking personal control of it now (dropping out of the skip to handle it turn by turn) or letting it be decided by a roll so the simulation can continue."
                ,"End at a clear decision point. Preserve or reveal at least one actionable journey lead and return exactly 3 optional suggested actions grounded in current knowledge."
            ],
            "schema": {
                "narrative": "brief overall summary used only as fallback", "updates": [{"sequence":"number", "type":"action|npc_reaction|faction_reaction|world_event|canon_event|interruption|consequence", "title":"specific short heading", "canon_day":"integer canon day this beat occurred on", "related_action":"queued action or empty", "narrative":"2-5 substantive sentences, proper nouns bolded with **double asterisks** on first mention", "why_it_matters":"one short plain sentence on the stakes, phrased the way a narrator would actually say it out loud, not a labeled report line", "player_knowledge":"one short plain sentence on what the character can verify, infer, or only heard as rumor, phrased the same natural way, or empty if nothing new", "next_pressure":"one short plain sentence naming the unresolved pressure, phrased the same natural way, or empty", "map_changes": "empty list unless this SPECIFIC beat changed who controls/holds a territory, settlement, or map node — then a short list of what changed, e.g. 'The Empire of the End gains control of the Rift Node'. Most beats have none.", "quote": "empty unless this beat naturally includes one short, genuinely quotable spoken line — then {\"text\": the line, \"speaker\": who said it}. Use sparingly, only when a line actually lands; never invent dialogue just to fill this in."}], "state_patch": "ALL persistent changes",
                "events": "system notifications", "timeline_events": "list of major events",
                "elapsed": {"amount": "number", "unit": "same or sensible normalized unit"},
                "interrupted": "boolean", "interruption_kind": "canon_event|goal_complete|world_event|danger|other or empty", "interruption_reason": "string or empty",
                "interruption_context": "full context the player needs before deciding", "intervention_prompt": "specific final question phrased as Will <player name> ...? or empty",
                "goal_status": {"action": "goal-bearing action or empty", "achieved": "boolean", "elapsed": {"amount": "number", "unit": "unit"}, "explanation": "in-world result or obstacle", "next_hint": "actionable hint when incomplete"},
                "major_event_reached": "boolean; required in next major event mode", "major_event_kind": "personal|canon|empty", "major_event_title": "specific title or empty",
                "active_major_event": "the EXACT title of a major canon event (matching one listed under UPCOMING CANON PRESSURES/CANON HISTORY) if this update is still directly part of that event's unfolding scene, or empty once it has concluded and the story has moved past it — this drives which banner art the player sees, so keep it set for as long as the scene is genuinely still that event and clear it the moment it resolves.",
                "new_contacts": "EVERY named character or group the player had a real, individual interaction with this update — talked to, fought, helped, was helped by, was noticed by, negotiated with, or was introduced to. Not just plot-important figures — a shopkeeper who remembers the player, a rival genin, a rank-and-file guard who let something slip. If they're worth naming in the update at all, they belong here with {name, kind: person|group}.",
                "incoming_chats": [{"thread": "contact/group", "sender": "sender", "message": "message"}]
                ,"completed_actions": "ordered actions completed or meaningfully attempted",
                "deferred_actions": "unfinished/unstarted actions retained for the next Advance",
                "suggested_actions": ["exactly 3 concrete optional actions written as verb + target + purpose: strongest lead, growth/preparation, alternate hook. Each must name a SPECIFIC person, place, faction, item, or thread that actually exists in this campaign right now — never generic filler like 'look for rumors' or 'train' with no real target. Vary the scale honestly: one can be a single moment, another can openly span several days or a longer project ('spend the next few days...', 'seek out ... over the coming weeks') when that's genuinely what the lead calls for — don't force everything into an instant."]
            }
        }
        data = self.request_with_narrative(self.gm_context(" ".join(str(x) for x in orders or [])), payload, 2800)
        if canon_stop and not event_mode:
            data["elapsed"] = {"amount": canon_stop.get("minutes_until", 0), "unit": "minutes"}
            # Whether reaching this boundary becomes a real "will you personally
            # engage" moment or just a narrated report the player reads about
            # depends on whether they could plausibly be there. When the
            # player's own tracked location obviously matches the event's
            # location, that's hardcoded rather than left to model compliance
            # — a model has repeatedly proven unreliable at reliably noticing
            # this on its own, and this is exactly the kind of moment that
            # must actually be played out live, not silently summarized.
            # BUT: location alone only justifies that hardcode for a "wide"
            # scope event (a village under attack, a war, a public event) —
            # for anything else (the default, "personal": a small-cast
            # incident that happens to be tagged with a village-level
            # location for convenience) sharing that broad location proves
            # nothing. "Same village as Mizuki and Naruto that night" is not
            # "in the room when he steals the scroll." Check status/location
            # against the event's own scale first; only a wide-scope match
            # skips straight to forced presence.
            # Otherwise (a real judgment call — different location, travel
            # time, standing, or a personal-scope event regardless of
            # location) trust the narrator's own interrupted call, per the
            # gm_rules instruction. Defaulting to ABSENCE, not presence,
            # when the model leaves the field genuinely unset: a player who
            # was never established as being anywhere near a canon event has
            # no plausible way to attend it, and silently forcing them into
            # a live scene with named canon figures they were never actually
            # near is a worse failure than the reverse — a missed live scene
            # just reads as a report instead, which is what should happen by
            # default anyway for anyone not already involved.
            if canon_stop.get("scope") == "wide" and self._same_place(self.state.get("location"), canon_stop.get("location")):
                player_present = True
            else:
                player_present = bool(data.get("interrupted")) if isinstance(data.get("interrupted"), bool) else False
            data["interrupted"] = player_present
            if player_present:
                data["interruption_kind"] = "canon_event"
                data["interruption_reason"] = data.get("interruption_reason") or f"Major canon event reached: {canon_stop.get('title', 'Timeline event')}."
                data["interruption_context"] = (data.get("interruption_context") or
                    f"{canon_stop.get('title', 'Timeline event')} is unfolding at {canon_stop.get('location', 'an unknown location')}. "
                    f"{canon_stop.get('summary', 'The situation has reached a point where the player may intervene.')}")
                data["intervention_prompt"] = (data.get("intervention_prompt") or
                    f"Will {self.state.get('name', 'the player')} intervene in {canon_stop.get('title', 'this event')}?")
                # Hardcoded, not left to model compliance: the banner art for
                # a major event the player is actually present for must show
                # while it's unfolding, matching interrupted=True exactly.
                data["active_major_event"] = canon_stop.get("title", "")
            else:
                data["interruption_kind"] = ""
                data["interruption_reason"] = ""
                data["interruption_context"] = ""
                data["intervention_prompt"] = ""
        elif event_mode:
            elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
            elapsed_minutes = self.duration_minutes(elapsed.get("amount", 0), elapsed.get("unit", "minutes"))
            # A model that reports a suspiciously tiny elapsed time for a claimed
            # "major personal event" turns this mode into pausing every few
            # minutes of simulated time instead of skipping ahead meaningfully —
            # which also silently starves any real canon event further out from
            # ever being reached, since each click only closes a sliver of the
            # remaining distance. Floor the accepted elapsed time to at least a
            # day (or the exact canon boundary, if that's actually closer) so
            # real forward progress happens on every single call regardless of
            # how eager the model is to call something major.
            min_event_step = min(EVENT_STEP_FLOOR_MINUTES, canon_stop["minutes_until"]) if canon_stop else EVENT_STEP_FLOOR_MINUTES
            personal_stop = bool(data.get("major_event_reached")) and data.get("major_event_kind") == "personal" and min_event_step <= elapsed_minutes < simulation_amount
            if personal_stop:
                data["elapsed"] = {"amount": elapsed_minutes, "unit": "minutes"}
                stop_title = str(data.get("major_event_title") or "Major personal development")
                stop_kind = "personal"
            elif canon_stop:
                data["elapsed"] = {"amount": canon_stop.get("minutes_until", simulation_amount), "unit": "minutes"}
                stop_title = canon_stop.get("title", "Major canon event")
                stop_kind = "canon"
            else:
                safe_elapsed = elapsed_minutes if min_event_step <= elapsed_minutes <= event_horizon else event_horizon
                data["elapsed"] = {"amount": safe_elapsed, "unit": "minutes"}
                stop_title = str(data.get("major_event_title") or "Major personal turning point")
                stop_kind = str(data.get("major_event_kind") or "personal")
            data["major_event_reached"] = True
            data["major_event_kind"] = stop_kind
            data["major_event_title"] = stop_title
            # "Skip to next major event" existing to save time narrating routine
            # beats between now and the goal doesn't mean a real canon-timeline
            # event the player is actually standing in the middle of should be
            # flattened into a plain report — it deserves the same live scene
            # (banner art, "take part" vs "let it play out") that reaching the
            # same boundary via a normal multi-day skip already gets, via the
            # canon_stop-and-not-event_mode branch above. A personal
            # development never gets this treatment either way, per this
            # mode's own "never ask whether the player intervenes" contract.
            player_present = False
            if stop_kind == "canon" and canon_stop:
                # Same reasoning as the canon_stop-and-not-event_mode branch
                # above: only a wide-scope event lets shared location alone
                # force presence; everything else defaults to absence when
                # the model leaves this unset.
                if canon_stop.get("scope") == "wide" and self._same_place(self.state.get("location"), canon_stop.get("location")):
                    player_present = True
                else:
                    player_present = bool(data.get("interrupted")) if isinstance(data.get("interrupted"), bool) else False
            data["interrupted"] = player_present
            if player_present:
                data["interruption_kind"] = "canon_event"
                data["interruption_reason"] = data.get("interruption_reason") or f"Major canon event reached: {canon_stop.get('title', 'Timeline event')}."
                data["interruption_context"] = (data.get("interruption_context") or
                    f"{canon_stop.get('title', 'Timeline event')} is unfolding at {canon_stop.get('location', 'an unknown location')}. "
                    f"{canon_stop.get('summary', 'The situation has reached a point where the player may intervene.')}")
                data["intervention_prompt"] = (data.get("intervention_prompt") or
                    f"Will {self.state.get('name', 'the player')} intervene in {canon_stop.get('title', 'this event')}?")
                data["active_major_event"] = canon_stop.get("title", "")
            else:
                data["interruption_kind"] = ""
                data["interruption_reason"] = ""
                data["interruption_context"] = ""
                data["intervention_prompt"] = ""
                # Only add the flat "reached this and stopped" note when there
                # isn't already a full interactive scene covering the same
                # event — otherwise the player sees this note, the intervention
                # banner, AND the [MAJOR CANON EVENT] chronicle entry all for
                # the same single moment.
                if not isinstance(data.get("updates"), list): data["updates"] = []
                data["updates"].append({"sequence": 9998, "type": "canon_event" if stop_kind == "canon" else "consequence",
                    "title": f"Major Event Reached — {stop_title}", "related_action": "",
                    "narrative": "The advance stops here naturally, at the next real turning point for the campaign — decide how your character responds before time moves again.",
                    "why_it_matters": "", "player_knowledge": "", "next_pressure": ""})
        goal_status = data.get("goal_status") if isinstance(data.get("goal_status"), dict) else {}
        if goal_status.get("achieved"):
            goal_elapsed = goal_status.get("elapsed") if isinstance(goal_status.get("elapsed"), dict) else {}
            if goal_elapsed.get("amount") is not None and goal_elapsed.get("unit"):
                data["elapsed"] = goal_elapsed
            if event_mode:
                data["major_event_reached"] = True
                data["major_event_kind"] = "personal"
                data["major_event_title"] = data.get("major_event_title") or "Defining goal completed"
                data["interrupted"] = False
                data["interruption_kind"] = ""
                data["interruption_reason"] = ""
            else:
                data["interrupted"] = True
                data["interruption_kind"] = data.get("interruption_kind") or "goal_complete"
                data["interruption_reason"] = data.get("interruption_reason") or goal_status.get("explanation") or "The stated goal was achieved early."
        elif goal_status and goal_status.get("action"):
            explanation = str(goal_status.get("explanation") or "The goal was not completed within the available time.").strip()
            next_hint = str(goal_status.get("next_hint") or "Review the obstacle and choose a more focused next step.").strip()
            if not isinstance(data.get("updates"), list): data["updates"] = []
            if not isinstance(data.get("suggested_actions"), list): data["suggested_actions"] = []
            data["updates"].append({"sequence": 9990, "type": "consequence", "title": "Goal not yet complete",
                                    "related_action": goal_status.get("action"),
                                    "narrative": f"{explanation} Next lead: {next_hint}"})
            data["suggested_actions"].insert(0, next_hint)
        if moment_mode:
            elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
            elapsed_minutes = self.duration_minutes(elapsed.get("amount", 0), elapsed.get("unit", "minutes"))
            if elapsed_minutes <= 0:
                elapsed_minutes = min(1440, self.estimate_action_minutes(orders[0]) if orders else 5)
            data["elapsed"] = {"amount": min(1440, elapsed_minutes), "unit": "minutes"}
        actual_elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
        training_amount = actual_elapsed.get("amount", simulation_amount)
        training_unit = actual_elapsed.get("unit", simulation_unit)
        self.enforce_training_progress(data, results, training_amount, training_unit, orders, intensity)
        authored_deferred = data.get("deferred_actions") if isinstance(data.get("deferred_actions"), list) else []
        assessed_deferred = assessment.get("deferred_actions") if isinstance(assessment.get("deferred_actions"), list) else []
        completed = set(ai_text(x) for x in data.get("completed_actions", []) if ai_text(x))
        # Assessment is the authoritative time-budget gate. The narrator may
        # add deferrals, but it cannot silently erase actions the planning pass
        # already proved were unreachable (especially later Moment actions).
        data["deferred_actions"] = list(dict.fromkeys(
            ai_text(x) for x in [*authored_deferred, *assessed_deferred]
            if ai_text(x) and ai_text(x) not in completed
        ))
        return self.apply_time_skip(data, amount, unit, progression_context={
            "actions": orders, "rolls": results,
            "elapsed_minutes": self.duration_minutes(training_amount, training_unit),
            "intensity": intensity,
        })

    def next_canon_stop(self, amount, unit):
        """The next dated commitment that should force a skip to stop early
        and let the player decide — either from this world's fixed canon
        timeline, or from a scheduled_events entry the GM itself created for
        a promised/threatened future confrontation (a rival vowing to come
        for the player, a character approaching on a specific day, etc.).
        Both are treated identically once they have a resolvable day."""
        before = int(self.state.get("canon_time_minutes", self.state.get("canon_day", -7) * 1440 + 480))
        after = before + self.duration_minutes(amount, unit)
        fired = set(self.state.get("canon_events_fired", []))
        candidates = []
        for event in timeline_for(self.state.get("world", "Custom World")).get("events", []):
            if event.get("historical_only"):
                continue
            # Only a "major" fixed-timeline event forces a full stop-and-ask;
            # the many smaller scripted beats still fire (see
            # fire_canon_events) as background texture without interrupting
            # a skip over something the player may not even be present for.
            if not event.get("major", True):
                continue
            event_id = f"day:{event.get('day', 0)}:{event.get('title', 'event')}"
            minute = int(event.get("day", 0)) * 1440 + 480
            if before <= minute <= after and event_id not in fired:
                candidates.append((minute, event))
        for index, sched in enumerate(self.state.get("scheduled_events", [])):
            if not isinstance(sched, dict) or str(sched.get("visibility", "confirmed")).lower() == "hidden":
                continue
            if sched.get("resolved") or sched.get("due_canon_day") is None:
                continue
            try:
                day = int(sched["due_canon_day"])
            except (TypeError, ValueError):
                continue
            minute = day * 1440 + 480
            sched_id = f"scheduled:{index}:{sched.get('title', 'event')}"
            if before <= minute <= after and sched_id not in fired:
                candidates.append((minute, {"day": day, "title": sched.get("title", "Scheduled event"),
                                             "location": sched.get("location", "Unknown"),
                                             "summary": sched.get("when") or sched.get("notes") or "",
                                             "_scheduled_index": index}))
        if not candidates: return None
        minute, event = min(candidates, key=lambda item: item[0])
        return {"title": event.get("title", "Major canon event"), "location": event.get("location", "Unknown"),
                "summary": event.get("summary", ""), "canon_day": int(event.get("day", 0)),
                "minutes_until": max(1, minute - before), "scheduled_index": event.get("_scheduled_index"),
                # "wide" (a village under attack, a war, a public coronation) is
                # the only scope where merely sharing the event's broad location
                # justifies forcing presence — see the scope check in
                # run_time_skip. Everything else (the default) is a small-cast
                # incident that happens to be tagged with a village-level
                # location for convenience, not because the whole village
                # witnesses it — "same village" was never a reasonable proxy
                # for "in the room when Mizuki tricks Naruto into stealing the
                # scroll."  GM-created scheduled_events (a specific NPC's
                # threatened confrontation) default to personal for the same
                # reason: they name one person's action toward the player, not
                # a location-wide catastrophe.
                "scope": event.get("scope", "personal")}

    def enforce_training_progress(self, data, results, amount, unit, orders, intensity):
        """Guarantee that long training represents repeated daily work even if
        a narrator model under-awards the mechanical state patch."""
        training_words = ("train", "practice", "study", "research", "drill", "meditat", "spar", "learn", "master")
        training_orders = [str(x) for x in (orders or []) if any(k in str(x).lower() for k in training_words)]
        if not training_orders: return
        days = max(.05, self.duration_minutes(amount, unit) / 1440.0) / max(1, len(training_orders))
        rates = {"light": .12, "normal": .20, "intense": .35, "extreme": .50}
        base_rate = rates.get(str(intensity).lower(), .20)
        tuning = normalize_tuning(self.state)
        base_rate *= float(tuning.get("training_rate", 1.0) or 1.0)
        growth_profile = self.state.get("special", {}).get("Growth Profile", {})
        try:
            learning_rate = clamp(float(growth_profile.get("learning_rate", 1.0)), .6, 1.75)
        except (TypeError, ValueError):
            learning_rate = 1.0
        checks = results or []
        patch = data.setdefault("state_patch", {})
        stat_patch = patch.setdefault("stats", {})
        progress_patch = patch.setdefault("ability_progress", {})
        xp_mode = uses_xp_for(self.state.get("world"))
        progression_events = []
        for index, action in enumerate(training_orders):
            result = checks[min(index, len(checks) - 1)] if checks else None
            ability = (result or {}).get("ability") or (primary_stats_for(self.state.get("world"), self.state.get("special", {}).get("Archetype", "")) or list(self.state.get("stats", {})))[0]
            factor = 1.25 if not result or result.get("success") else .55
            breakthrough = bool((result or {}).get("breakthrough"))
            # Every training day also carries a small independent discovery
            # chance; aggregating it makes a month meaningfully different.
            per_day_breakthrough = max(.002, min(.04, .01 * float(tuning.get("breakthrough_rate", 1.0) or 1.0)))
            if not breakthrough and random.random() < 1 - ((1 - per_day_breakthrough) ** max(1, days)):
                breakthrough = True
            multiplier = random.uniform(2.2, 4.0) if breakthrough else 1.0
            gained_points = days * base_rate * factor * multiplier * learning_rate
            old_fraction = float(self.state.get("ability_progress", {}).get(ability, 0) or 0)
            total_points = old_fraction + gained_points
            current = int(self.state.get("stats", {}).get(ability, 1) or 1)
            if xp_mode:
                # System worlds retain proficiency progress, but base stats are
                # awarded only by the deterministic level-up routine.
                progress_patch[ability] = round(total_points, 3)
                applied_stat_gain = 0
            else:
                stat_gain = int(total_points)
                progress_patch[ability] = round(total_points - stat_gain, 3)
                proposed = int(stat_patch.get(ability, current) or current)
                stat_patch[ability] = max(proposed, current + stat_gain)
                applied_stat_gain = stat_patch[ability] - current
            entry = {"action": action, "ability": ability, "effective_training_days": round(days, 2),
                     "stat_gain": applied_stat_gain, "breakthrough": breakthrough,
                     "learning_rate_multiplier": round(learning_rate, 2),
                     "explanation": (f"Sustained {ability} repetition produced a lore-valid insight that multiplied the training return."
                                     if breakthrough else
                                     (f"{round(days, 1)} effective daily sessions built proficiency; System XP and levels govern base stats."
                                      if xp_mode else f"{round(days, 1)} effective daily sessions accumulated at the character's {learning_rate:.2f}× aptitude rate."))}
            progression_events.append(entry)
            if breakthrough:
                data.setdefault("updates", []).append({"sequence": 900 + index, "type": "consequence",
                    "title": "Lore Breakthrough", "related_action": action,
                    "narrative": f"Repeated {ability} practice aligned technique, conditioning and timing at once. The resulting insight produced an unusually large but setting-consistent leap in power."})
                data.setdefault("events", []).append({"type": "training", "message": f"Breakthrough: {ability} surged through sustained training."})
        patch.setdefault("progression_log", list(self.state.get("progression_log", [])) + progression_events)

    def sync_derived_pools(self, before):
        hp_max, resource_max = self.derive_pools(self.state.get("world", "Custom World"), self.state.get("stats", {}))
        for current_key, max_key, derived in (("hp", "hp_max", hp_max), ("resource", "resource_max", resource_max)):
            old_max = int(before.get(max_key, derived) or derived)
            authored_max = int(self.state.get(max_key, derived) or derived)
            new_max = max(authored_max, derived)
            delta = max(0, new_max - old_max)
            self.state[max_key] = new_max
            self.state[current_key] = min(new_max, max(0, int(self.state.get(current_key, new_max) or 0) + delta))

    @staticmethod
    def duration_minutes(amount, unit):
        multipliers = {"moment": 1, "minutes": 1, "hours": 60, "days": 1440, "weeks": 10080, "months": 43200}
        try:
            value = max(0, float(amount))
        except (TypeError, ValueError):
            value = 0
        return int(round(value * multipliers.get(str(unit), 1)))

    def advance_clock(self, before, amount, unit):
        minutes = self.duration_minutes(amount, unit)
        base_total = int(before.get("world_clock_minutes", 480) or 0)
        total = base_total + minutes
        self.state["world_clock_minutes"] = total
        cal_before = before.get("calendar", {}) if isinstance(before.get("calendar"), dict) else {}
        absolute = (
            (((int(cal_before.get("year", 1)) - 1) * 12 + (int(cal_before.get("month", 1)) - 1)) * 30
             + (int(cal_before.get("day", 1)) - 1)) * 1440
            + int(cal_before.get("hour", 8)) * 60 + int(cal_before.get("minute", 0)) + minutes
        )
        day_total, minute_of_day = divmod(absolute, 1440)
        month_total, day_index = divmod(day_total, 30)
        year_index, month_index = divmod(month_total, 12)
        hour, minute = divmod(minute_of_day, 60)
        self.state["calendar"] = {"day": day_index + 1, "month": month_index + 1, "year": year_index + 1, "hour": hour, "minute": minute}
        period = "Night" if hour < 5 or hour >= 21 else "Morning" if hour < 12 else "Afternoon" if hour < 17 else "Evening"
        canon_before = int(before.get("canon_time_minutes", int(before.get("canon_day", -7)) * 1440 + 480))
        canon_after = canon_before + minutes
        self.state["canon_time_minutes"] = canon_after
        canon_day = canon_after // 1440
        self.state["canon_day"] = canon_day
        date_str = format_calendar_date(self.state.get("world", "Custom World"), canon_day, self.state.get("calendar_epoch"), self.state.get("calendar_anchor_day"))
        self.state["world_time"] = f"{date_str} — {period}, {hour:02d}:{minute:02d}"
        pending_canon_appends = self.fire_canon_events(canon_before, canon_after)
        # A full status-window popup every ~3 in-game months (90 days),
        # regardless of how time was spent getting there — a periodic
        # check-in on the character's overall progress.
        self.state["minutes_since_status_window"] = int(self.state.get("minutes_since_status_window", 0) or 0) + minutes
        if self.state["minutes_since_status_window"] >= 90 * 1440:
            self.state["minutes_since_status_window"] = 0
            self.state["status_window_due"] = True
        return pending_canon_appends

    def fire_canon_events(self, before_minutes, after_minutes):
        """Returns pending Chronicle entries rather than appending them
        directly — the caller (apply_time_skip) merges these with the
        narrator's own per-day updates and appends everything together in
        one chronological pass, so a canon event's note lands in its actual
        day order instead of always jumping to the top of the batch."""
        if after_minutes <= before_minutes:
            return []
        fired = self.state.setdefault("canon_events_fired", [])
        pending_appends = []
        world = self.state.get("world", "Custom World")
        anchor_day = self.state.get("calendar_anchor_day")
        # This campaign's own start (not the world's generic default) is what
        # separates "already history before the story began" from "due to
        # happen during this campaign" — see the CANON HISTORY/UPCOMING split
        # in gm_rules. Only apply this filter when we actually KNOW the real
        # start (a save from before calendar_anchor_day existed has it as
        # None) — guessing the world's generic default here is wrong for any
        # save that actually began at a canon-character start or a chosen
        # starting era, and guessing wrong in this direction is much worse
        # than guessing wrong the other way: it would wrongly reclassify a
        # genuinely-upcoming event as already-historical and permanently
        # suppress it, exactly the "never actually happens" bug this exists
        # to prevent. When we don't know, don't filter at all.
        campaign_start_minute = int(anchor_day) * 1440 + 480 if anchor_day is not None else None
        for event in timeline_for(world).get("events", []):
            if event.get("historical_only"):
                continue
            event_id = f"day:{event.get('day', 0)}:{event.get('title', 'event')}"
            event_minute = int(event.get("day", 0)) * 1440 + 480
            if campaign_start_minute is not None and event_minute < campaign_start_minute:
                continue
            # Catch-up, not just a same-turn crossing: fire the moment we've
            # reached or passed its day even if an earlier turn should have
            # already caught it and, for whatever reason, didn't — a canon
            # event's day is a firm commitment and must never be left
            # permanently stuck as "still pending" once it's actually behind
            # the player. Minor and major events are both delivered as an
            # ordinary Chronicle update here; only major events additionally
            # get a chance to pause the skip and be played out live, via
            # next_canon_stop/canon_stop elsewhere — that's a separate,
            # unaffected mechanism.
            if event_minute <= after_minutes and event_id not in fired:
                fired.append(event_id)
                label = f"{format_calendar_date(world, event.get('day', 0), self.state.get('calendar_epoch'), anchor_day)} — {event.get('title', 'World event')}"
                divergence_note = (" This campaign already contains divergences, so the event's motive and pressure remain active even if its participants or outcome change."
                                   if self.state.get("canon_divergences") else
                                   " The player may engage with, avoid, redirect, or fundamentally alter what follows.")
                detail = f"{label}\nLocation: {event.get('location', 'Unknown')}. {event.get('summary', '')}{divergence_note}"
                self.state.setdefault("world_events", []).append(detail)
                self.state.setdefault("timeline", []).append(detail)
                # A canon-timeline beat delivered through this mechanical
                # backstop (as opposed to the interactive canon_stop path) is
                # by definition something the player is reading ABOUT, not
                # living through — see the docstring above. Mirrored into its
                # own list so the World Feed can show "the wider world" moved
                # on its own, distinct from the player's own scenes, without
                # touching the existing world_events/timeline shape anything
                # else already reads.
                self.state.setdefault("background_world_feed", []).append(detail)
                major = event.get("major", True)
                pending_appends.append({
                    "text": "[CANON TIMELINE]\n" + detail + "\nPrior divergences may alter how this event unfolds.",
                    "tag": "canon_event" if major else "system", "canon_day": int(event.get("day", 0)),
                    "major": bool(major), "event_title": event.get("title", ""),
                })
        # Mechanical backstop for GM-created scheduled_events (a promised
        # confrontation, a character due to approach the player, etc.): even
        # if the AI's own narrative update forgets to cover it, this always
        # leaves a concrete note the moment its date is crossed (or, per the
        # same catch-up guarantee above, the first time we notice it's
        # already behind us), so a commitment the player was told about can
        # never just silently pass.
        for index, sched in enumerate(self.state.get("scheduled_events", [])):
            if not isinstance(sched, dict) or sched.get("resolved") or sched.get("due_canon_day") is None:
                continue
            try:
                day = int(sched["due_canon_day"])
            except (TypeError, ValueError):
                continue
            event_minute = day * 1440 + 480
            sched_id = f"scheduled:{index}:{sched.get('title', 'event')}"
            if event_minute <= after_minutes and sched_id not in fired:
                fired.append(sched_id)
                sched["resolved"] = True
                label = f"{format_calendar_date(world, day, self.state.get('calendar_epoch'), anchor_day)} — {sched.get('title', 'Scheduled event')}"
                detail = f"{label}\n{sched.get('when') or ''} {sched.get('notes') or ''}".strip()
                pending_appends.append({"text": "[SCHEDULED EVENT]\n" + detail, "tag": "system", "canon_day": day,
                                         "major": True, "event_title": sched.get("title", "")})
        self.state["canon_events_fired"] = fired
        if any(p["major"] for p in pending_appends):
            self.state["active_canon_event"] = next(p["event_title"] for p in pending_appends if p["major"])
        return pending_appends

    def request_continuity_correction(self, new_warnings, narrative):
        """Continuity warnings used to just sit in the Journal for the player
        to notice eventually. Now a newly-detected contradiction gets one
        immediate, cheap correction pass instead — the same background model
        used for memory maintenance, asked to fix only what conflicts rather
        than re-narrate the scene. Best-effort: any failure here is silently
        swallowed, since a missed correction just falls back to the old
        passive-warning behavior."""
        if not new_warnings or not self.ai_bg_ready() or self.busy:
            return None
        payload = {
            "task": "continuity_correction", "role": "Continuity Auditor",
            "last_narrative": narrative, "detected_conflicts": new_warnings, "state": self.trimmed_state_for_ai(),
            "requirements": "The last response conflicts with established continuity. Reconcile it minimally: "
                            "either correct the specific state fields to match established facts, or write a brief "
                            "in-fiction addendum explaining the discrepancy (a correction, a rumor was wrong, a "
                            "misremembering) — never rewrite or repeat the original scene.",
            "schema": {"state_patch": "corrected fields only, or {}", "addendum": "1-3 sentences reconciling the conflict, or empty"},
        }
        rules = self.gm_rules() + " You are the CONTINUITY AUDITOR. Be conservative and minimal. Fix only what was flagged; change nothing else."
        try:
            data = self.ai_bg.request(rules, payload, max_output_tokens=350)
        except Exception as e:
            self.log("Continuity correction failed: " + str(e))
            return None
        patch = data.get("state_patch") if isinstance(data.get("state_patch"), dict) else {}
        if patch:
            apply_guarded_patch(self.state, patch, allow_time=False, source="continuity_correction")
        addendum = str(data.get("addendum", "")).strip()
        if addendum:
            self.append("[CONTINUITY NOTE]\n" + addendum, "meta")
        self.log("Continuity correction applied: " + "; ".join(new_warnings))
        return {"addendum": addendum, "patched": bool(patch)}

    @staticmethod
    def _beat_detail(update, narrative_text):
        """Structured extras for a dated time-skip beat, riding along on the
        story entry's existing free-form `detail` field: the entities the
        GM already bolded (same convention the Codex-linking already reads),
        plus the AI's own rare map_changes/quote flags — sanitized here so a
        malformed or overzealous response can't reach the Chronicle UI. A
        moment-to-moment single action never has canon_day set and never
        reaches this at all, so richer per-day cards fall out naturally from
        longer skips instead of needing a separate length check."""
        entities = []
        for name in re.findall(r"\*\*(.+?)\*\*", narrative_text):
            name = name.strip()
            if name and name not in entities:
                entities.append(name)
        map_changes = [ai_text(m) for m in (update.get("map_changes") or []) if ai_text(m)][:4]
        quote = update.get("quote")
        clean_quote = None
        if isinstance(quote, dict):
            text = ai_text(quote.get("text") or "")
            speaker = ai_text(quote.get("speaker") or "")
            if text:
                clean_quote = {"text": text, "speaker": speaker}
        if not entities and not map_changes and not clean_quote:
            return None
        return {"entities": entities[:6], "map_changes": map_changes, "quote": clean_quote}

    def apply_time_skip(self, data, requested_amount, requested_unit, progression_context=None):
        with self.lock:
            before = copy.deepcopy(self.state)
            validation = apply_guarded_patch(self.state, data.get("state_patch", {}), allow_time=False, source="time_skip")
            if not uses_xp_for(self.state.get("world")):
                self.state["xp"], self.state["level"], self.state["xp_next"] = before.get("xp", 0), before.get("level", 1), before.get("xp_next", 100)
            else:
                context = progression_context if isinstance(progression_context, dict) else {}
                self.apply_system_xp(before, context.get("actions", []), context.get("rolls", []),
                                     context.get("elapsed_minutes", self.duration_minutes(requested_amount, requested_unit)),
                                     context.get("intensity", "normal"), data.get("events", []))
            self.sync_derived_pools(before)
            elapsed = data.get("elapsed") if isinstance(data.get("elapsed"), dict) else {}
            elapsed_amount = elapsed.get("amount", requested_amount)
            elapsed_unit = elapsed.get("unit", requested_unit)
            pending_canon_appends = self.advance_clock(before, elapsed_amount, elapsed_unit)
            for ev in data.get("timeline_events", []) or []:
                self.state.setdefault("timeline", []).append(ev)
            for c in data.get("new_contacts", []) or []:
                if isinstance(c, dict):
                    self.ensure_contact(c.get("name"), c.get("kind", "person"), c)
                else:
                    self.ensure_contact(str(c))
            for m in data.get("incoming_chats", []) or []:
                thread = m.get("thread") or m.get("sender")
                self.ensure_contact(thread)
                self.add_chat_message(thread, m.get("sender"), m.get("message", ""), "incoming")
            updates = data.get("updates", []) if isinstance(data.get("updates"), list) else []
            updates = [u for u in updates if isinstance(u, dict) and str(u.get("narrative", "")).strip()]
            # Canon-event notes (from fire_canon_events, day-anchored but not
            # authored by this turn's narrator) are merged into the SAME
            # chronological pass as the narrator's own per-day updates —
            # sorted together by canon_day — instead of always being appended
            # first regardless of where their day actually falls among them.
            # A canon note gets sequence -1 so it reads as that day's opening
            # headline when it shares a day with a narrator update.
            entries = [{"canon_day": int(u.get("canon_day", 0) or 0), "sequence": int(u.get("sequence", 0) or 0), "kind": "update", "data": u} for u in updates]
            entries += [{"canon_day": p["canon_day"], "sequence": -1, "kind": "canon", "data": p} for p in (pending_canon_appends or [])]
            entries.sort(key=lambda e: (e["canon_day"], e["sequence"]))
            if entries:
                for entry in entries:
                    if entry["kind"] == "canon":
                        p = entry["data"]
                        self.append(p["text"], p["tag"], canon_day=p["canon_day"])
                        continue
                    update = entry["data"]
                    title = str(update.get("title") or update.get("type") or "Update").replace("_", " ").upper()
                    sections = [str(update.get("narrative")).strip()]
                    # These three used to print as their own separately-labeled
                    # lines ("Why it matters: ...", "What you know: ...",
                    # "Pressure: ..."), which read like a status report bolted
                    # onto the scene rather than part of it. Folding whichever
                    # of them are present into one plain closing sentence reads
                    # far closer to how a narrator would actually say it.
                    tail_bits = [str(update.get(key)).strip() for key in ("why_it_matters", "player_knowledge", "next_pressure") if update.get(key)]
                    if tail_bits:
                        sections.append(" ".join(bit if bit.endswith((".", "!", "?", '"', "”")) else bit + "." for bit in tail_bits))
                    canon_day = update.get("canon_day")
                    try: canon_day = int(canon_day) if canon_day is not None else None
                    except (TypeError, ValueError): canon_day = None
                    body = "\n\n".join(sections)
                    self.append(f"[{title}]\n" + body, "system" if update.get("type") != "action" else "narrative",
                                canon_day=canon_day, detail=self._beat_detail(update, body))
            else:
                self.append("[TIME SKIP]\n" + data.get("narrative", "Time passes."), "system")
            self.append_growth_deltas(before)
            interrupted = bool(data.get("interrupted"))
            if interrupted:
                is_canon = data.get("interruption_kind") == "canon_event"
                heading = "MAJOR CANON EVENT" if is_canon else "TIME SKIP INTERRUPTED"
                self.append(f"[{heading}]\n" + data.get("interruption_reason", "Something requires your attention."), "canon_event" if is_canon else "danger")
            # Drives which banner shows behind the scene (see scene_image_url)
            # — defaults to clearing rather than getting stuck on if a turn's
            # response ever omits it, since a banner reverting a beat early is
            # far less broken than one stuck on a resolved event forever.
            new_active_event = str(data.get("active_major_event") or "").strip()
            if new_active_event and new_active_event != self.state.get("active_canon_event"):
                # A fresh engagement (not a continuation of the same one) —
                # see the engagement-count comment in assess_time_skip for
                # why this resets rather than just incrementing.
                self.state["canon_event_engagement_count"] = 0
            elif new_active_event:
                self.state["canon_event_engagement_count"] = int(self.state.get("canon_event_engagement_count", 0) or 0) + 1
            self.state["active_canon_event"] = new_active_event
            context = progression_context if isinstance(progression_context, dict) else {}
            self.ensure_quest_briefings(before, "; ".join(str(x) for x in context.get("actions", [])))
            completed_quests = normalize_quest_state_machine(self.state)
            elapsed_minutes = self.duration_minutes(elapsed_amount, elapsed_unit)
            self.check_tower_deadline(before, elapsed_minutes)
            if data.get("major_event_reached"):
                self.state["last_major_beat_day"] = int(self.state.get("canon_day", 0) or 0)
            clock_events = tick_world_clocks(self.state, elapsed_minutes)
            for event in clock_events:
                message = event.get("message", "World agenda advanced.")
                self.state.setdefault("world_events", []).append(message)
                # NPC/faction clocks are, by construction, agendas moving
                # independently of the player — same background-feed mirror
                # as the canon catch-up backstop above.
                self.state.setdefault("background_world_feed", []).append(message)
                # These used to sit in the collapsed meta strip, tagged like
                # an engine notice — but this is the one channel that makes
                # the world visibly keep moving when the player isn't doing
                # anything, and hiding it defeated that. Back in the main
                # Chronicle as a real beat; the underlying message strings in
                # systems.py were also reworded off "[BRACKETED] status
                # report" phrasing into something closer to news reaching
                # the player, since visible-but-still-robotic wouldn't have
                # actually fixed the original complaint.
                self.append("[ELSEWHERE]\n" + message, "system")
            for name in completed_quests:
                self.append(f"[QUEST COMPLETE — {name}]\nAll required objectives have been completed.", "meta")
            notifications = self.notify(before, self.state, list(data.get("events", []) or []) + clock_events)
            if interrupted and data.get("interruption_kind") == "canon_event":
                notifications.append({"message": "MAJOR CANON EVENT: " + data.get("interruption_reason", "A major canon event is unfolding."),
                                       "tag": "danger", "cinematic": "canon_event"})
            self.state.setdefault("time_skip_history", []).append({
                "turn": self.state.get("turn", 0), "elapsed": data.get("elapsed"),
                "orders": self.state.get("standing_orders", []), "interrupted": interrupted
            })
            self.state["turn"] = before.get("turn", 0) + 1
            self.state["time_mode"] = "moment"
            self.state["queued_actions"] = [ai_text(x) for x in data.get("deferred_actions", []) if ai_text(x)]
            self.state["suggested_actions"] = self.guided_suggestions(data.get("suggested_actions"))
            prior_warnings = set(before.get("continuity_ledger", {}).get("warnings", []))
            continuity_warnings = update_continuity(before, self.state, "Advance: " + "; ".join(self.state.get("standing_orders", [])), data.get("narrative", ""))
            for note in self.state.pop("_pending_chronicle_notes", []):
                self.append(note, "meta")
            new_warnings = [w for w in continuity_warnings if w not in prior_warnings]
            if new_warnings:
                self.request_continuity_correction(new_warnings, data.get("narrative", ""))
            chapter = update_chapter_memory(before, self.state, "Advance: " + "; ".join(context.get("actions", [])), data.get("narrative", ""))
            if chapter:
                self.append(f"[CHAPTER RECORDED]\n{chapter['title']} is now available in Journal → Chapters.", "meta")
            self.archive_finished_quests()
            # A time skip can end the character's life just as surely as a
            # single action or a combat round can (a failed extreme-danger
            # roll, or the Tower deadline below) — this path never checked
            # for it, so death during an ordinary Advance silently had no
            # death modal at all. Same check apply_resolution already uses.
            died = False
            if self.state.get("hp", 1) <= 0 or not self.state.get("alive", True):
                self.state["hp"] = 0
                self.state["alive"] = False
                died = True
            self.autosave()
        return {"status": "resolved", "narrative": data.get("narrative", ""), "interrupted": interrupted,
                "died": died, "can_rewind": died and bool(self.checkpoints),
                "elapsed": data.get("elapsed", {"amount": requested_amount, "unit": requested_unit}),
                "interruption_reason": data.get("interruption_reason", ""),
                "interruption_kind": data.get("interruption_kind", ""),
                "interruption_context": data.get("interruption_context", ""),
                "intervention_prompt": data.get("intervention_prompt", ""),
                "major_event_reached": bool(data.get("major_event_reached")),
                "major_event_kind": data.get("major_event_kind", ""),
                "major_event_title": data.get("major_event_title", ""),
                "goal_status": data.get("goal_status", {}),
                "notifications": notifications, "state": self.public_state(), "story": self._flush_story(),
                "validation": validation, "continuity_warnings": continuity_warnings,
                "deferred_actions": self.state.get("queued_actions", []),
                "completed_actions": data.get("completed_actions", []), "updates": updates}

    TOWER_FLOOR_DEADLINE_DAYS = 90

    def check_tower_deadline(self, before, elapsed_minutes):
        """Solo Max-Level Newbie only: each floor carries a hard 90-day
        countdown. Resets the moment the AI actually advances tower_floor
        (mechanically, not left to the AI to also self-report the reset —
        the same reasoning as every other hardcoded guarantee in this file).
        Hitting zero is an unavoidable, application-forced death: the doom
        itself must never depend on the AI choosing to narrate/apply it."""
        if self.state.get("world") != "Solo Max-Level Newbie" or self.state.get("tower_over"):
            return
        floor = max(1, int(self.state.get("tower_floor", 1) or 1))
        prior_floor = max(1, int(before.get("tower_floor", 1) or 1))
        deadline = self.state.get("tower_floor_deadline_day")
        if floor > prior_floor or not isinstance(deadline, (int, float)):
            self.state["tower_floor_deadline_day"] = self.state.get("canon_day", 0) + self.TOWER_FLOOR_DEADLINE_DAYS
            return
        if elapsed_minutes >= 1440:
            days_left = max(0, int(deadline - self.state.get("canon_day", 0)))
            self.append(f"[TOWER COUNTDOWN]\n{days_left} day(s) remain before this floor's countdown reaches zero.", "meta")
        if self.state.get("canon_day", 0) >= deadline:
            self.state["tower_over"] = True
            self.state["alive"] = False
            self.state["hp"] = 0
            self.append(
                "[FLOOR COUNTDOWN EXPIRED]\nThe Tower's judgment falls due. Without warning, the floor itself turns against "
                "everyone still standing on it — a purge no strength, plan, or plea can turn aside. There was no surviving this.",
                "danger",
            )

    def canon_countdown(self):
        now = int(self.state.get("canon_time_minutes", self.state.get("canon_day", -7) * 1440 + 480))
        fired = set(self.state.get("canon_events_fired", []))
        upcoming = []
        for event in timeline_for(self.state.get("world", "Custom World")).get("events", []):
            event_id = f"day:{event.get('day', 0)}:{event.get('title', 'event')}"
            minute = int(event.get("day", 0)) * 1440 + 480
            if minute > now and event_id not in fired: upcoming.append((minute, event))
        if not upcoming: return {"available": False, "label": "No fixed major canon event remains on the loaded timeline."}
        minute, event = min(upcoming, key=lambda item: item[0])
        delta = minute - now
        days, remainder = divmod(delta, 1440); hours = remainder // 60
        date_str = format_calendar_date(self.state.get("world", "Custom World"), event.get("day", 0), self.state.get("calendar_epoch"), self.state.get("calendar_anchor_day"))
        return {"available": True, "title": event.get("title"), "location": event.get("location"),
                "canon_day": int(event.get("day", 0)), "minutes_until": delta,
                "label": f"{days} days, {hours} hours until {event.get('title')} ({date_str})"}
