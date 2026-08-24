"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, json, random, re, secrets, threading
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, world_supports_races, WORLD_RACES, tower_floor_theme, TOWER_FLOOR_COUNT, tower_band
from ai_client import AI
from lore import format_lore_context
from portrait_generator import portrait_view
from state_guard import apply_guarded_patch, migrate_state
from continuity import update_continuity
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks, pacing_guidance, active_nemesis_threats)


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
    "onboarding_seen": False,
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
    "Custom World": "Background Expertise",
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



class CoreMixin:
    def __init__(self):
        self.lock = threading.RLock()
        self.settings = self.load_settings()
        self.ai = self.make_client(self.settings.get("model", ""))
        self.ai_bg = self.make_client(self.settings.get("secondary_model", "") or self.settings.get("model", ""))
        self.state = copy.deepcopy(BASE_STATE)
        self.history = []
        self.checkpoints = []
        self.story_log = []   # [{"text":..., "tag":...}]
        self.system_log = []  # [str, ...]
        self.busy = False
        self.campaign_active = False
        self.last_autosave = ""
        self.last_lore_context = ""
        self.last_assessment = {}
        self._pending_reentry_hours = None

    def load_settings(self):
        try:
            return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))}
        except Exception:
            return dict(DEFAULT_SETTINGS)

    def save_settings(self):
        SETTINGS_PATH.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")

    def make_client(self, model):
        s = self.settings
        return AI(
            key=s.get("api_key", ""),
            model=model or DEFAULT_MODEL,
            provider=s.get("provider", "local"),
            base_url=s.get("local_base_url", "http://localhost:1234/v1"),
            local_token=s.get("local_token", ""),
        )

    def local_mode(self):
        return self.settings.get("provider", "local") != "cloud"

    def ai_ready(self):
        if self.local_mode():
            return bool(self.settings.get("model", ""))
        return bool(self.settings.get("api_key", "") and self.settings.get("model", ""))

    def ai_bg_ready(self):
        if self.local_mode():
            return bool(self.settings.get("secondary_model", "") or self.settings.get("model", ""))
        return bool(self.settings.get("api_key", "") and (self.settings.get("secondary_model", "") or self.settings.get("model", "")))

    def update_settings(self, patch):
        self.settings.update(patch)
        self.save_settings()
        self.ai = self.make_client(self.settings["model"])
        self.ai_bg = self.make_client(self.settings.get("secondary_model") or self.settings["model"])

    def detect_models(self, base_url, token):
        client = AI(provider="local", base_url=base_url or "http://localhost:1234/v1", local_token=token or "", model="unused")
        return client.list_models()

    # Pure application bookkeeping the AI never needs to read and must never
    # re-author. A prompt instruction alone isn't reliable protection against
    # this — a smaller/local model prone to pattern-completion over real
    # instruction-following will still often mimic a field's shape just
    # because it saw the key sitting in its own context, wasting output
    # budget re-typing it and raising the odds of getting cut off mid-JSON
    # before the response ever closes. The fix is to not show it the
    # temptation at all rather than trust it to resist one it can see.
    AI_HIDDEN_FIELDS = ("continuity_ledger", "validation_log", "diagnostics", "canon_events_fired", "pending_minor_events", "calendar_anchor_day", "last_protagonist_tick_day", "active_canon_event", "last_major_beat_day")

    def trimmed_state_for_ai(self):
        """The raw state grows without bound over a long campaign —
        campaign_canon alone can hold up to 250 full turn records. Once a
        stretch of turns has been consolidated into a chapter_summaries
        entry, the older campaign_canon rows it covers are redundant weight
        in every AI call from then on. Trim them (and drop a handful of
        purely mechanical fields entirely) from what's actually SENT to the
        model, not from the saved state itself (the Journal's Chapter Memory
        and Continuity tabs, and campaign export, still want the full
        record)."""
        snapshot = dict(self.state)
        for key in self.AI_HIDDEN_FIELDS:
            snapshot.pop(key, None)
        canon = self.state.get("campaign_canon") or []
        if not canon:
            snapshot.pop("campaign_canon", None)
            return snapshot
        chapters = self.state.get("chapter_summaries") or []
        if chapters:
            try:
                last_covered_turn = int((chapters[-1].get("turns") or [0, 0])[-1] or 0)
                canon = [entry for entry in canon if int(entry.get("turn", 0) or 0) > last_covered_turn]
            except (TypeError, ValueError, IndexError):
                pass
        # No chapter summary yet to lean on (early campaign) — still cap to a
        # recent tail so a fresh campaign's first few requests aren't already
        # carrying unnecessary bulk.
        snapshot["campaign_canon"] = canon[-15:]
        return snapshot

    def append(self, text, tag=None, canon_day=None, detail=None):
        entry = {"text": text, "tag": tag, "time": datetime.now().isoformat(timespec="seconds")}
        if canon_day is not None:
            entry["canon_day"] = canon_day
        if detail:
            entry["detail"] = detail
        self.story_log.append(entry)

    def log(self, text):
        self.system_log.append(text)

    def ability_enum(self):
        return "|".join(abilities_for(self.state.get("world", "Custom World")))

    def gm_context(self, query=""):
        """Core rules plus a compact, query-relevant offline lore retrieval."""
        lore = format_lore_context(self.state.get("world", "Custom World"), query, self.state)
        self.last_lore_context = lore
        return self.gm_rules() + (("\n\n" + lore) if lore else "")

    def request_with_narrative(self, instructions, payload, max_output_tokens):
        """Some models (smaller/cheaper ones especially) occasionally fill in
        state_patch correctly but leave narrative blank under attention
        pressure. That's a failed response, not a usable one — retry once
        with a sharper reminder before accepting it."""
        data = self.ai.request(instructions, payload, max_output_tokens=max_output_tokens)
        if not (data.get("narrative") or "").strip():
            sharper = instructions + "\n\nREMINDER: your previous attempt left \"narrative\" empty. Write 2-5 sentences of narrative FIRST, then the rest."
            data = self.ai.request(sharper, payload, max_output_tokens=max_output_tokens)
        return data

    def _scale_lock_rule(self):
        """Shared by gm_rules() and core_rules() so the scale-lock/contact/
        identity/information-fog block — genuinely relevant to almost any
        AI call, light or heavy — stays byte-identical in both instead of
        drifting into two slightly different copies over time."""
        scale = str(self.state.get("simulation_scale") or "Individual").strip() or "Individual"
        return (
            f"\n- SCALE LOCK (current scale: {scale}): the player's simulation_scale is Individual, Organization, Guild, Company, City, "
            "Nation, or Empire — exactly one at a time, tracked in state_patch.simulation_scale, and it NEVER silently upgrades. It only "
            "changes when the player has genuinely, deliberately built up to that scale through real in-fiction action (founding and "
            "growing an organization, being formally installed in a national office, etc.), the same bar as state.position. "
            + (
                "The player is currently at INDIVIDUAL scale, which hard-locks the following until they explicitly earn otherwise: the "
                "player never owns or governs a country, never controls national territory, never appears on the map as a political "
                "entity, never receives national diplomacy, international summits, embassies, UN-style invitations, unsolicited direct "
                "contact from a government, or military command. Never invent a country for them, never rename, split, or hand over a "
                "map region because of them, and never manufacture diplomacy just to involve them in it — if the story wants that scale of "
                "consequence, it happens among nations and organizations that already exist, and the player experiences it from whatever "
                "vantage their actual scale allows."
                if scale == "Individual" else
                f"The player has earned {scale}-scale standing — the simulation should now actually reflect that reach in what reaches "
                "them (relevant diplomacy, contact, or authority at that scale becomes plausible), without retroactively pretending they "
                "were ever bigger than what they actually built."
            ) +
            " Regardless of scale: an unidentified individual is never contactable by a government or agency out of nowhere — identity "
            "must be discovered (video, DNA, financial/electronic/travel traces, surveillance, multiple witnesses, captured allies, "
            "communications intercepts), then verified, then cleared through a real threat assessment and bureaucratic approval, before any "
            "direct contact is even possible; agencies investigate and coordinate internally first, they do not immediately call, recruit, "
            "or negotiate. No single observation ever identifies someone — a power level, aura, or energy reading reveals capability, never "
            "identity. Information about the player spreads in physical layers with real delay and real loss at each step (direct "
            "observation -> witness account -> rumor -> local authorities -> regional authorities -> national agencies -> international "
            "intelligence -> broadly verified fact) — most rumors never make it all the way up that chain, witnesses can be wrong, and "
            "footage can be faked or disputed."
        )

    def core_rules(self, extra=""):
        """A much lighter instruction set for background/side tasks — a side
        chat reply, the incoming-message check, the background world tick,
        memory maintenance — that don't touch combat, quests, the Tower, or
        faction conflict, and don't need the full ~46,000-character turn-
        resolution rulebook to do their actual job. Modeled on Pax Historia's
        own approach of giving each distinct AI task its own right-sized
        prompt instead of reusing one giant shared one everywhere; these
        calls run far more often than a real turn (the incoming-chat check
        alone fires every other turn), so the savings compound."""
        wd = WORLD_DATA[self.state["world"]]
        return f"""You are the world-consistency layer for Worldwalker RPG's "{self.state['world']}" campaign — not narrating a full scene, just keeping one small piece of the simulation honest.
WORLD RULES: {wd['rules']}
CUSTOM SETTING: {self.state.get('custom_world', '')}

CORE PRINCIPLES
- NPCs, factions and world events continue independently and know only what they could plausibly know.
- Enforce information fog. Separate objective world changes from what the player can verify, infer, or hear as rumor. News requires a believable route — witness, messenger, broadcast, document, travel, surveillance, or ability — and distance and secrecy cause delay or uncertainty.
- Contacts are not omnipresent. Distance, access, relationship, danger, technology, secrecy, and availability matter.
- Communications must use lore-appropriate means. A "chat" can mean phone/text, guild chat, system DM, messenger bird, courier, letter, Den Den Mushi, radio, telepathy, or other setting-appropriate medium.
- Before proposing or reacting to anything, check campaign_canon (recent turn history) and the relevant npc_memories entry for whether it has already happened, been discussed, or been resolved — never re-raise, act surprised by, or contradict something already settled.
- Canon is the opening condition, not a railroad. Record meaningful changes as canon_divergences.{self._scale_lock_rule()}
{extra}
Return ONLY valid JSON. No markdown fences."""

    def gm_rules(self):
        wd = WORLD_DATA[self.state["world"]]
        ex = expansion_for(self.state["world"])
        d = DIFFICULTIES[self.state["difficulty"]]
        tuning = normalize_tuning(self.state)
        progression_preset = progression_preset_for(self.state.get("world"))
        narration = self.settings.get("narration", "Detailed")
        hidden_stat_rule = ""
        if stat_style_for(self.state.get("world", "Custom World")) == "full_sheet":
            hidden_stat_rule = (
                "\n- This is a status-window/LitRPG-style world: the player has hidden stats they have not discovered yet "
                "(e.g. Luck, a hidden class, a hidden talent). Do not reveal them for free. When the character earns a genuine "
                "in-fiction way to see them (a status window unlock, an analysis/appraisal skill, a milestone, a mentor's judgment), "
                "add the revealed stat and its value to state_patch.hidden_stats. Never put an undiscovered stat there."
            )
        world_name = self.state.get("world", "Custom World")
        race_rule = ""
        if world_supports_races(world_name):
            options = WORLD_RACES.get(world_name, {}).get("options", [])
            race_rule = (
                f"\n- This world distinguishes race/species (established options include: {', '.join(options)}, or a fitting custom one). "
                "state.race holds the character's current race — keep it consistent turn to turn. It only ever changes through a genuine, "
                "earned in-fiction evolution/transformation event (never casually or by player request alone), and such an event is always a major "
                "beat worth narrating properly, not a quiet state_patch line. A changed race must still logically follow this world's real rules for "
                "what that race can and can't do."
            )
        gear_style = gear_style_for(world_name)
        if gear_style == "full":
            gear_rule = (
                "\n- Itemization matters in this world. Track state_patch.equipment with clear slot keys (Head, Chest, Weapon, Off-Hand, Legs, "
                "Feet, Accessory, etc.) and put the item's name AND its concrete mechanical effect in the value text, e.g. "
                "'Iron Longsword (+3 Attack)' or 'Leather Boots (+2 Agility)' — the player sees these on a hoverable equipment mannequin."
            )
        else:
            gear_rule = (
                "\n- Itemization is not the focus in this world. Only track the character's signature weapon or held item in "
                "state_patch.equipment (key 'Weapon' is enough) — do not invent a full gear/armor slot system that doesn't fit this setting."
            )
        voice_rule = ""
        if world_name == "Reincarnated as a Slime":
            voice_rule = (
                "\n- This world has a signature narrative device: an internal analytical voice (Great Sage/Raphael-style), once the "
                "character has such a skill. It speaks like the source material's own AI construct actually does — terse, clinical, factual, "
                "reporting real analysis/calculation/recommendation, never flavor text dressed up to look clinical. Set it off from normal prose "
                "with 《...》 brackets inside narrative, e.g. 《Analysis complete. Recommend evasion.》 It is the correct voice for reporting a "
                "concrete skill acquisition, an evolution, or a calculated probability/recommendation — use it for those moments, not idle "
                "commentary. Use it sparingly and only once the skill genuinely exists — do not grant or use it prematurely."
            )
        elif world_name in ("Overgeared", "Solo Max-Level Newbie"):
            voice_rule = (
                "\n- This world has an in-fiction game System the character perceives directly, exactly like the source material's own status "
                "windows/notifications — never softened into ordinary prose. EVERY mechanical event (skill gained, level up, quest update, stat "
                "change, item/reward acquired, hidden condition met, achievement unlocked) must be phrased as a literal System message the "
                "character sees/hears, e.g. '[System Notification] Skill \"Iron Will\" has reached Level 2.' or '[System] Quest Complete — "
                "Reward: 500 Gold, Potion of Vigor x3.' Put these in the events list AND, whenever the moment allows, quote the System's exact "
                "wording inside the narrative itself so the player reads it the way the character actually experiences it — not a paraphrase, "
                "the literal message. Any XP or reward gained this turn must be named explicitly in one of these messages (exact amount, item, "
                "or title) — never leave the player to infer what they got. Keep ordinary scene description as normal prose; only mechanical "
                "notices get the System voice."
            )
        tower_rule = ""
        if world_name == "Solo Max-Level Newbie":
            current_floor = max(1, min(TOWER_FLOOR_COUNT, int(self.state.get("tower_floor", 1) or 1)))
            band_name, band_ecology = tower_band(current_floor)
            deadline_day = self.state.get("tower_floor_deadline_day")
            days_left = None
            if isinstance(deadline_day, (int, float)):
                days_left = max(0, int((deadline_day - int(self.state.get("canon_day", 0))) ))
            tower_rule = (
                "\nWORLD-FIRST / RULE-FIRST SIMULATION: this world is simulated for its own sake, not staged around the player. The player is "
                "one autonomous actor among billions, never the default protagonist. If a beat you're about to write would only make sense by "
                "quietly bending the rules below in the player's favor, simulation consistency wins — regenerate the beat instead. Priority "
                "order when anything conflicts: simulation consistency, then Tower rules, then world logic, then this campaign's own established "
                "history (campaign_canon/canon_divergences), then the player's actions, then narrative convenience — never reversed.\n"
                f"- TOWER STRUCTURE: this world's Tower has exactly {TOWER_FLOOR_COUNT} floors and is a single, singular structure — every Gate "
                "on Earth (Tokyo, Paris, New York, anywhere) opens into the exact same Tower, sharing the exact same current floor and the exact "
                "same countdown; there is no such thing as one country ahead of or behind another. The player is currently on Floor "
                f"{current_floor}, whose real internal identity is '{tower_floor_theme(current_floor)}' in the '{band_name}' ecological band "
                f"({band_ecology}) — use this to decide what monsters, factions, hazards and administrators canon-appropriately populate it, and "
                "keep that ecology internally consistent every time this floor is revisited (check campaign_canon/codex for what was already "
                "established here before inventing something new for it). Never mix a lower band's grounded logic with a higher band's rule-"
                "bending phenomena, and never let progression jump bands without an earned, gradual, narratively-justified transition — no "
                "one-turn leaps in floor difficulty or systemic complexity. NEVER reveal this internal name/theme/band to the player directly or "
                f"use it as state.location or a map label — state.location must always read exactly 'Floor {current_floor}' (e.g. 'Floor 12'), "
                "with the real flavor expressed only through narration, monsters, and scenery. A floor also holds content nobody has to find — "
                "secret bosses, hidden paths, rare alternate victories, bonus rewards — track any the player actually stumbles onto as normal "
                "hidden_quests, discovered like any other hidden content, not handed over for free. When the player actually clears/ascends "
                "past their current floor, set state_patch.tower_floor to the new floor number (integers only, and only forward, never skip "
                "floors arbitrarily) — the application resets the floor's own countdown timer automatically the moment this number goes up, and "
                "that reset applies globally: the instant the shared floor advances, EVERY Gate on Earth reconnects to the new floor at once, "
                "and the previous floor stays permanently open afterward for training, exactly like the source material."
                + (f" There are {days_left} day(s) left before this floor's countdown reaches zero — build rising urgency into the narrative "
                   "as it gets low, but the actual countdown and its consequences are handled by the application; never mention a specific "
                   "number of days yourself, that's the application's job."
                   if days_left is not None else "")
                + " The player does not have to be the one who clears the current floor — humanity as a whole (canon named clearers, rival "
                "guilds, militaries, companies, other players, any combination) is genuinely racing to clear it, and may succeed on its own "
                "initiative whether or not the player is directly involved; when appropriate, narrate that collective progress as background "
                "movement (via the existing faction/NPC clock and World Feed machinery) rather than always waiting on the player's own action. "
                "The player can fail a floor while humanity still clears it in time, and humanity can fail the countdown while the player "
                "personally survives — these are not contradictions, they're the whole premise.\n"
                "- WORLD AUTONOMY & REALISM: countries, guilds, militaries, scientists, religions, corporations and criminal organizations are "
                "all independently reacting to and racing through the Tower — surface this the same way any other independent world movement "
                "is surfaced, through faction/NPC clocks and the World Feed, not just told about in passing. New Tower-derived technology, "
                "weapons, or infrastructure still costs real knowledge, money, materials, engineers, testing and production time — a working "
                "prototype is not mass deployment, and there is no such thing as a one-week aircraft, a one-day reactor, or an overnight army; "
                "research, industrial expansion, training, travel, communication and construction all still consume realistic time. "
                "Administrators, Architects, and other apex Tower entities do not casually seek the player out — they act through intermediaries "
                "or systemic effects, and a direct meeting requires exceptional, earned justification, not proximity or power level alone. "
                "Nothing reverts on its own: a defeated floor boss stays defeated, a destroyed area stays destroyed, and established Tower "
                "facts persist in campaign_canon/codex exactly like any other campaign history — never re-introduce a cleared threat or a "
                "settled fact as if it were new."
            )
        progression_rule = (
            "\n- This is a status-window/LitRPG world: numbered XP and level-ups are the expected shape of base-stat progress. The application calculates XP, levels, thresholds and level-up stat gains after every meaningful action, so never write xp, xp_next, level, or direct base-stat increases in state_patch. Continue to record earned skills, proficiency, knowledge, items, titles, achievements and other world-specific progress normally."
            if uses_xp_for(world_name) else
            "\n- This world does not canonically expose XP or numbered levels. Never award XP or change level. Progress is shown through open-ended world-relative attributes, knowledge, techniques, ranks, titles and positions. Attributes have no fixed maximum."
        )
        position_rule = (
            "\n- If the character reaches a singular, defining position of power or authority appropriate to this world (e.g. Hokage, a Yonko or "
            "Pirate King, a Demon Lord or the Chairman of the Hunter Association, a Guild Master, a nation's ruler) — something the whole world "
            "would recognize as THE holder of that role, not just a strong individual — set it in state_patch.position. Leave state_patch.position "
            "unset otherwise; do not invent a grand title just to fill it. Clear or update it if the position is lost or changes."
        )
        scale_rule = self._scale_lock_rule()
        pacing_rule = pacing_guidance(self.state)
        director_notes = str(self.state.get("director_notes") or "").strip()
        director_notes_rule = (
            f"\n- PLAYER DIRECTOR'S NOTES (a standing tone/pacing preference the player set for this campaign — honor it "
            f"consistently across turns until it changes): {director_notes}"
            if director_notes else ""
        )
        nemesis_threats = active_nemesis_threats(self.state)
        nemesis_rule = ""
        if nemesis_threats:
            names = "; ".join(f"{t['name']} ({t['goal']})" for t in nemesis_threats if t.get("name"))
            nemesis_rule = (
                f"\n- NEMESIS AT A BREAKING POINT: {names}. This long-running villain's scheme has been building for a "
                "long stretch of the campaign and just reached its critical moment — engineer a real confrontation, "
                "revelation, or major escalation involving them within the next several turns rather than letting it "
                "fade quietly. Once the confrontation actually plays out, update their npc_memories entry to reflect "
                "the outcome (a new goal for their next scheme, or drop recurring/nemesis if they're truly finished). "
                "This is for a confrontation the player will actually be part of — if their scheme is instead something "
                "that should resolve independently of the player (a war with another faction, a power struggle with a "
                "rival), give their npc_clock an opponent instead and let it resolve automatically; see FACTION CONFLICT."
            )
        canon = timeline_for(world_name)
        current_canon_day = int(self.state.get("canon_day", canon.get("start_day", -7)))
        upcoming = [e for e in canon.get("events", []) if int(e.get("day", 0)) >= current_canon_day]
        past = sorted((e for e in canon.get("events", []) if int(e.get("day", 0)) < current_canon_day),
                      key=lambda e: -int(e.get("day", 0)))
        canon_schedule = "; ".join(f"Day {int(e.get('day', 0)):+d}: {e.get('title')} at {e.get('location')}" for e in upcoming[:5])
        canon_history = "; ".join(f"Day {int(e.get('day', 0)):+d}: {e.get('title')}" for e in past[:5])
        all_event_days = [int(e.get("day", 0)) for e in canon.get("events", [])]
        beyond_established_canon = bool(all_event_days) and current_canon_day > max(all_event_days)
        known_factions = list(self.state.get("factions", {}).keys())
        faction_conflict_rule = ""
        if known_factions:
            faction_conflict_rule = (
                f"\n- FACTION CONFLICT (this world's real factions: {', '.join(known_factions)}): faction_clocks and npc_clocks "
                "support optional fields — opponent (the rival faction/NPC name), ally (a faction/NPC who reinforces this side "
                "if the conflict resolves), power (1-100, their rough current strength), and contested_location (a place "
                "actually at stake) — and once a clock with an opponent reaches its turning point, the application resolves a "
                "real strength-weighted outcome automatically: territory can change hands, and a side that loses badly enough "
                "is genuinely destroyed (a faction, which also vacates its other territory and can cost its tracked leader — "
                "see npc_memories[name].leads_faction below) or lost (an NPC), off-screen, without needing the player present. "
                "Only set opponent/ally/power/contested_location when you intend that stake to be real. "
                + (f"This campaign is {current_canon_day - max(all_event_days)} day(s) beyond this world's last established "
                   "canon event — there is no more real script to follow here, so extrapolate each faction's next move as a "
                   "plausible, in-character continuation of their real trajectory and power level, not an arbitrary invention."
                   if beyond_established_canon else
                   "While still within the world's known timeline, base opponent/ally/power/contested_location on this "
                   "world's REAL canon-established relationships and conflicts at the current Canon Day — who is actually "
                   "at war, rivals, or allied at this point in the real story — unless a recorded canon_divergence has "
                   "plausibly changed that specific relationship.") +
                " A conflict the player should experience directly belongs in normal narrative/combat, not this off-screen "
                "mechanism — reserve it for agendas genuinely meant to resolve independently of the player. The application "
                "itself may occasionally propose a background skirmish on its own (marked proposed=true) — these always end "
                "in a stalemate with no real winner, since bare dice should never decide a faction's survival without your "
                "canon judgment. If the player becomes genuinely involved in one of these, set that clock's player_involved=true "
                "so it can resolve for real once you're actively narrating it. Track a faction's actual leader via "
                "npc_memories[name].leads_faction = \"Faction Name\" whenever one is established — it's what lets their "
                "faction's collapse cost them something real instead of them quietly continuing to exist untouched."
            )
        leadership_rule = ""
        if known_factions:
            leadership_rule = (
                "\n- If the player holds the TOP leadership rank of a faction (per state.affiliations or state.position — "
                "e.g. Hokage of Konoha, Captain of a pirate crew, a Guild Master), they can issue real orders and make "
                "binding decisions on that faction's behalf — deploying people, setting policy, delegating a mission — not "
                "just act as an individual member. A named subordinate, officer, or unit the player addresses or gives an "
                "order to should be tracked as a normal npc_memories entry (set npc_memories[name].faction_role to their "
                "position, e.g. 'Lieutenant' or 'Squad Captain'), with a goal reflecting the order and recurring=true, "
                "exactly like any other tracked subplot — this lets their progress carrying it out advance and report back "
                "independently. The player never needs to list or manage the faction's full membership — invent a "
                "plausible named subordinate on the spot whenever the fiction calls for one, staying consistent with any "
                "already named. A player who is only an ordinary member (not the top leader) can request or suggest to "
                "their faction's leadership, but cannot issue binding orders on its behalf."
            )
        espionage_rule = ""
        if known_factions:
            espionage_rule = (
                "\n- ESPIONAGE: when the player assigns someone — themself, a companion, a subordinate, a hired agent — to "
                "infiltrate, surveil, or spread disinformation against a faction, track that assignment exactly like any "
                "other delegated task: a named npc_memories entry (or the player's own standing_orders, if they're doing it "
                "personally) with a concrete goal and recurring=true. This is a standing commitment, not a one-time action — "
                "once set, keep advancing and reporting on it across time skips without the player having to re-issue the "
                "order every single time, exactly like standing_orders already work, until it's completed, blown, or the "
                "player changes it. What actually happens each skip must follow from the player's real orders, the agent's "
                "actual position and capability, and the current state of the world — never invent progress with nothing "
                "behind it, and never let it succeed just because it would be convenient. A skip can and should surface "
                "MULTIPLE distinct updates when multiple real things happened in it — an espionage report is exactly one "
                "more thing that can appear in the updates list (type npc_reaction or faction_reaction) alongside a "
                "companion's own subplot beat, a canon catch-up note, or a faction conflict resolution, each on its own "
                "line with its own canon_day, the same as any other update. A successful infiltration into a faction "
                "currently mid-conflict (its faction_clock has opponent/power/contested_location set — see FACTION "
                "CONFLICT) can genuinely reveal those specific details to the player through that update's narrative/"
                "player_knowledge — real forewarning, not vague flavor. A successful disinformation campaign can likewise "
                "alter that faction_clock's own power or contested_location in state_patch before it resolves, reflecting "
                "the sabotage actually landing. Espionage carries real risk: an exposed or captured agent should be "
                "reflected honestly (npc_memories[name].status can become 'captured', 'exiled', or 'deceased', the same "
                "vocabulary a fallen faction leader uses), and getting caught can itself trigger consequences — reprisal, "
                "diplomatic fallout, a burned source — not just a quiet failure."
            )
        # Deliberately placed at the very END of the returned prompt, not the
        # top — canon_day (and everything derived from it) changes on almost
        # every time skip, while the ~300 lines of NON-NEGOTIABLE RULES below
        # are near-static turn to turn. Putting the most volatile content
        # first would break the request's cacheable prefix (what OpenAI's and
        # local llama.cpp-style servers' automatic prompt caching key off of)
        # on every single skip, even though the bulk of this prompt hasn't
        # actually changed. Keeping it at the tail instead lets that long
        # static bulk stay a stable, cacheable prefix across ordinary turns.
        canon_clock_block = (
            f"\nCANON CLOCK: Day {current_canon_day:+d}; Day 0 is the main protagonist's story opening. Anchor: {self.state.get('canon_anchor') or canon.get('anchor', '')}\n"
            f"UPCOMING CANON PRESSURES: {canon_schedule or 'No fixed events remaining.'}\n"
            f"CANON HISTORY (already behind the current Canon Day — settled past, not upcoming): {canon_history or 'None on record before this point.'}"
        )
        return f"""You are the authoritative Game Master for Worldwalker RPG, a persistent freeform campaign. This world does not use D&D mechanics — checks are rolled against THIS world's own named abilities, not generic STR/DEX/CON/INT/WIS/CHA.
WORLD: {self.state['world']}
WORLD RULES: {wd['rules']}
CUSTOM SETTING: {self.state.get('custom_world', '')}
DIFFICULTY: {self.state['difficulty']} — {d['description']}
WORLD PROGRESSION PROFILE: {progression_preset['label']}; training ×{tuning['training_rate']}, breakthrough frequency ×{tuning['breakthrough_rate']}, XP ×{tuning['xp_rate']} where canonical XP exists.
CAMPAIGN TUNING: combat danger ×{tuning['combat_danger']}; resource pressure ×{tuning['resource_pressure']}; warn before checks whose expected requirement is at least {tuning['check_warning_threshold']}/100.
NARRATION MODE: {narration}
ABILITIES FOR THIS WORLD (use these exact names for every "ability" field, nothing else): {self.ability_enum()}

NON-NEGOTIABLE RULES
- Never write campaign_canon, continuity_ledger, chapter_summaries, chapter_buffer, canon_events_fired, or pending_minor_events in state_patch — you will see them inside "state" for context, but they are maintained automatically. Re-authoring them wastes your output budget on content that gets discarded and risks cutting off your own response before it's valid JSON.
- Write like a skilled tabletop DM narrating to a player, not a status report. Be decisive and concrete about what actually happened — when a stated goal succeeds, say so plainly ("You trail them through the back alleys and find the hideout — a boarded-up warehouse near the docks."), don't just describe atmosphere and leave the outcome implied or vague. Treat the roll/check result as settled fact you're narrating, not something to hedge around.
- The player's stated action is something they DO, not merely intend, consider, or move toward — "I grab her and pull her to safety" means she is now safely pulled aside by the end of this turn, not that the character merely started toward her or prepared to. Downgrading a clear, physically plausible action into "you prepare to..." or "you attempt to move toward..." with no actual outcome is a failure to resolve the turn, not a valid cautious answer. Only stop short of full success when there is a real, narratable obstacle — active resistance, a failed check, a physical impossibility, an interruption — and when that happens, say plainly and concretely what happened instead (she was already pulled away by someone else, a curse's barrier blocks the last few feet, the grab connects but she fights free) rather than leaving the action unresolved. Every stated action gets a real, concrete result by the end of the turn it was taken in — success, a specific kind of failure, or a stated reason it's impossible — never a suspended non-answer.
- NPCs and other actors in a scene should visibly be doing their own things, not just standing by to react to the player — glance up from what they were already doing, be mid-conversation, arrive somewhere for their own reason, leave to attend to their own business. The world should read as already in motion when the player arrives in it, every time, not just when a plot beat requires it.
- When a named character with an established voice/personality (canon or a recurring NPC the campaign has already characterized) is directly present or involved, and you have enough real context to know how they'd actually phrase something, give them an actual quoted line of dialogue in the narrative rather than only describing their actions in third person — a real line in their voice, not a paraphrase. Skip this for background extras with no established personality; never invent a quote you'd have to guess out of nothing.
- Favor developments that arrive through someone actively doing or saying something to the player — approaching, confronting, requesting, warning, challenging, informing — over passive scenery or waiting for the player to go looking. When you're deciding how to introduce a new development, default to a character bringing it to the player rather than the player stumbling onto an empty scene.
- The player controls their own character's decisions and dialogue. Never force a major choice.
- If player_identity.mode is 'canon', the player has complete control of that canon character from the selected start onward. Present canon-consistent pressures, relationships, opportunities, and likely events, but never force the character's original dialogue, loyalties, choices, victories, mistakes, or destination. Let player decisions create natural divergence.
- NPCs, factions and world events continue independently and know only what they could plausibly know.
- Simulate world-first: the player is one consequential actor, not the automatic center of every event. Keep the active scale grounded in the character's real reach—individual, party, organization, city, nation, or larger—and expand it only when their position and actions justify that reach.
- Enforce information fog. Separate objective world changes from what the player can verify, infer, or hear as rumor. News requires a believable route—witness, messenger, broadcast, document, travel, surveillance, or ability—and distance and secrecy cause delay or uncertainty.
- Identity and access are discovered, verified, and negotiated in-world. Governments, factions, experts, and canon characters do not magically know or contact the player without a causal information path.
- Any named character or group the player has a real interaction with — conversation, conflict, favor, negotiation, a direct introduction — becomes contactable going forward via state_patch.new_contacts (or ensure_contact through the normal state_patch route). Default to including them; a minor NPC worth naming in the narrative at all is worth being reachable later. This is separate from and in addition to the world's major factions/polities, which are contactable from the very start of the campaign regardless of whether the player has met them yet.
- Maintain npc_clocks and faction_clocks for important off-screen agendas. Each clock needs a plain goal, progress from 0 to its threshold, status, and last meaningful update. Player intervention can slow, redirect, expose, or accelerate a clock; never advance it merely to punish the player.
- A faction_clocks entry the application creates on its own starts with a flat placeholder goal ("Advance X's current agenda") — replace that with the real thing as soon as you actually know it, and for a major, ongoing power (not a one-scene faction), the same optional three-layer depth described above for NPCs applies here too: faction_clocks[name].immediate_goal (what they're actively doing right now — takes priority over the plain .goal field, same as for NPCs), .mid_term_goal, and .core_ambition. A faction whose immediate_goal keeps resolving into the same placeholder forever reads as inert scenery, not a real actor in a moving world.
- Whenever a character states, threatens, or promises a specific future action toward the player ("I'll come for you in a month"), or canon establishes a character would approach/target someone in the player's exact position on a knowable day, create a state_patch.scheduled_events entry: {{title, when (human-readable), due_canon_day (integer canon_day this is due — required, this is what actually schedules it), location, visibility (confirmed|rumor|hidden), notes}}. This applies to original/divergent characters too, adapted to their own situation — not only canon-identical placements. The application will force a stop at that day so the opportunity is never silently skipped; always include the full current list when updating this field, the same as other list fields.
- A skip that crosses a scheduled_events or canon-timeline date must explicitly cover it in that turn's updates — what happened, on which day, and any effect on the player — never let it pass with no mention just because the player didn't personally engage.
- A major canon event (listed in UPCOMING CANON PRESSURES) should never spring on the player fully formed out of nowhere. As its date gets close, seed rising rumors, preparations, tension, or logistics into ordinary narration beforehand — the kind of thing someone in the player's actual position would plausibly notice or hear about. When the event's day is actually reached, judge honestly whether the player's current location, standing, affiliation, and travel time make it plausible for them to be there or directly involved. If yes, treat it as a real scene: describe the concrete opportunity and let the player choose how (or whether) to personally engage, rather than narrating the outcome over their head. If no — they are somewhere else with no plausible way to attend or participate — do not manufacture a way to insert them into it; instead deliver a detailed, concrete report of what happened and its consequences (through news, a messenger, rumor, or documentation appropriate to how fast information could reach them) and continue the story from where the player actually is. Only ask the player an intervention/Yes-No question when they are plausibly present; never ask one of a player who could not possibly be there.
- For any time skip covering a full day or more, include at least one or two brief "meanwhile" beats about what the player character plausibly did during unaccounted stretches, inferred from their background, setting, and standing orders when no specific action was given for that time — the world should never read as if the character simply paused between explicit instructions.
- Independently of the player, regularly surface concrete movement from other major characters and factions relevant to the player's situation — not just abstract clock progress — so the world visibly continues advancing toward known future events in the background. This includes major story-scale milestones the player did not personally attempt: a canon protagonist clearing a dungeon/floor/trial, a rival guild completing a raid, a faction winning or losing a battle. The player is one actor in a moving world, not its bottleneck — canon and NPC-driven progress happens whether or not the player was there for it, and should be reported to the player as news/rumor/observation when it happens off-screen.
- background_world_feed (in the supplied state) is that same off-screen movement's own running record — check its recent entries before inventing new background color, and let an ordinary scene reference or build on what's already there when it's plausible for the player to have heard (a companion mentions it, a notice board has it, someone brings it up in conversation) rather than always generating a disconnected new mention. A recurring thread (a brewing war, a rival's climb, a faction's decline) should read as one continuous story the player can follow, not a fresh unrelated headline each time it comes up.
- Canon is the opening condition, not a railroad. Record meaningful changes as canon_divergences.
- Canon timeline events occur on their scheduled Canon Day unless prior player actions make the original version causally impossible. In that case, preserve the underlying NPC/faction motive, describe the altered event, and record the divergence instead of forcing canon.
- Compare every named canon event strictly against the current Canon Day, not against your own background knowledge of when it "usually" happens in the story. Anything listed under CANON HISTORY has already happened relative to this campaign's clock — treat it purely as settled past (something the world remembers, references, or still lives with the consequences of), and never narrate it, foreshadow it, or let a character speak of it as still pending, approaching, or rumored to be coming. Only events listed under UPCOMING CANON PRESSURES (or later additions with a day at or after the current Canon Day) are still ahead of the player. If a starting point lands after a major canon event, pick up the world already shaped by its aftermath and continue following canon's broader shape forward from there.
- Many of a world's scripted canon events are small, ordinary beats (someone else's minor mission, a routine incident three villages over), not personal turning points — these happen on schedule as background texture (a rumor, a mention, a headline, a world_event) and should not derail or interrupt the player's own scene unless the player is actually there or directly involved. Reserve real weight and any stop-and-decide moment for the world's genuinely major beats; weave the small ones into the world's ongoing motion instead.
- Use all reliable setting knowledge available in your model context and the campaign state/codex. Prefer official source material and internally consistent canon; use reference-wiki knowledge to reconcile details, and never treat forum speculation as established fact unless this campaign has explicitly adopted it. Do not invent a prohibition merely because a detail is obscure.
- Canon feats establish the setting's possibility space, not privileges reserved for canon protagonists. Anything a character in this universe can do is theoretically reproducible by the player when they meet the same underlying requirements: species/body, bloodline or unique biology, power source, aptitude, knowledge, teacher, item, contract, class, rank, training, cost, timing, and circumstances. The player's route may differ and canon may diverge.
- Canon is a foundation, never a creativity ceiling. Freely create original techniques, abilities, power combinations, classes, transformations, items, organizations, relationships, and divergent events when they follow this world's underlying mechanics and arise from the player's stated intent or earned consequences. Do not steer an original player path back toward the protagonist's story merely because it is unfamiliar.
- A vague background claim such as 'I have an ability,' 'I was gifted,' or 'I have some kind of fire power' authorizes a specific setting-valid starting ability within those parameters. Give it a memorable name, origin, practical effect, limitation or cost, and growth path. Preserve it as a real skill and explain it when relevant instead of asking the player to define it again.
- Fill gaps in an underspecified background with coherent upbringing, training, formative events, relationships, motivation, and complications. Never contradict details the player supplied. Starting stats, pools, skills, equipment, titles, contacts, aptitude, and training speed must reflect the resulting whole backstory.
- Treat special['Growth Profile'] as an established aptitude factor, not a guarantee: apply it alongside duration, repetition, teachers, resources, recovery, current mastery, and rolls whenever judging learning or growth.
- Treat established campaign_canon and canon_divergences as this campaign's own authoritative continuity. Once player-caused original material is established, preserve and develop it with the same seriousness as source canon unless later play changes it.
- Never reject an action merely because the original story assigned that feat, technique, item, title, or achievement to someone else. If it is learnable, obtainable, craftable, copyable, inheritable, stealable, trainable, or discoverable under world rules, allow the attempt or a concrete path toward it.
- Mark an action impossible only for a specific current contradiction with world rules or state. The returned reason must tell the player exactly which prerequisite, incompatibility, exclusive condition, missing resource, or physical/lore rule blocks it. If the obstacle can be overcome later, say what must change; do not use vague reasons such as 'not possible' or 'you cannot do that.'
- When the player expresses intent to acquire, reproduce, learn, craft, inherit, copy, awaken, or qualify for a notable canon capability, return/update a prerequisite_track. It must have name, source_feat, status (blocked|in_progress|ready|complete), known_requirements (list), met_requirements (list), missing_requirements (list), next_steps (list), and notes. Keep it honest as new lore is discovered; do not reveal secret requirements the character has no way to know.
- The application rolls uncertain checks. You assess the check; never secretly replace or reroll it.
- A supplied successful roll must produce meaningful success within the stated scope. A failed roll must matter.
- Impossible actions are not rollable.
- The world never arbitrarily scales to the player.
- NPCs, allies, rivals and enemies must have varied capability levels appropriate to their role and this world's power scale — a random background character, a seasoned specialist, and a named rival should feel meaningfully different in competence. Do not make everyone equally skilled.
- Track every currency the player obtains. The primary currency lives in state_patch.currency ({{name, amount}}) and MUST change in the SAME state_patch as any turn whose narrative describes a purchase, sale, payment, reward, bribe, fine, debt, or loss — if the prose says money changed hands, the number changes in the same response, never "implied" and left for later. If the player obtains a genuinely distinct second currency (guild points, faction tokens, foreign coin, event currency, arena tickets, etc.), track it separately in state_patch.currencies as {{"CurrencyName": amount}} — never conflate it with the primary currency or silently drop it.
- Currency is a tracked resource like XP, not an afterthought: award it whenever the fiction would obviously produce it — a completed job/quest/mission with pay, a bounty claimed, loot sold, wages earned, a bet won — sized realistically for this world's economy and the character's current standing. Deduct it just as reliably for purchases, bribes, fines, debts, and losses. A character who has clearly been working, adventuring, or trading for a stretch of time should not still be sitting on an unchanged amount.{(chr(10) + "- " + ex["economy_notes"]) if ex.get("economy_notes") else ""}
- Any gear, weapon, or item the player starts with, finds, or is given must be a specific, concrete, world-appropriate named thing ("a rusted shortsword", "a Kunai pouch") — never a vague placeholder like "a weapon" or "travel supplies". Fit it to the character's actual background, archetype, and station, not a generic default.
- Keep narrative prose short: a few sentences to one short paragraph per response. Only a single moment-to-moment turn focuses on one thing at a time — any longer timespan (a day, a training session, a journey) should move through several distinct beats/events across it rather than one flattened event, while still staying concise overall.
- Award XP only when this world's progression rule explicitly says it has a canonical in-fiction XP/level system.
- Explicitly update open-ended stats, knowledge, techniques, skills, titles, quests, items, reputation, companions, codex, locations and special world systems whenever justified.
- Stats are setting-relative and theoretically unbounded. Never use D&D benchmarks, modifiers, level caps or a universal human maximum.{hidden_stat_rule}{voice_rule}{tower_rule}{progression_rule}{position_rule}{scale_rule}{gear_rule}{race_rule}{pacing_rule}{director_notes_rule}{nemesis_rule}{faction_conflict_rule}{leadership_rule}{espionage_rule}
- Every high/extreme player-initiated lethal action must be warned about before resolution.
- Death is possible. If death occurs: hp=0 and alive=false.
- Keep all persistent mechanical changes in state_patch. Never rely on prose alone for a state change.
- The "narrative" field is never empty. Write it first, before working out state_patch — a turn with a populated state_patch but blank narrative is a failed response.
- New named NPCs/locations/factions the player meaningfully learns should be added to codex.
- Maintain character appearance continuity. Use appearance_desc as the starting look reference.
- Visually distinctive gear, scars, cloaks, masks, hairstyles, eyes, tattoos, weapons carried openly, and other memorable appearance changes should be reflected in state_patch.portrait_traits when appropriate.
- Act like a strong tabletop dungeon master: preserve player freedom, but continuously maintain an understandable journey with goals, obstacles, discoveries, escalation and earned progress. The player should rarely be left without a promising thread to pull.
- Every resolved scene and time skip must return exactly 3 concise suggested_actions that fit the current world, location, available knowledge and player goals. Write each as a concrete verb + named target + purpose and imply its main tradeoff when useful. These are optional hints, never forced actions or dialogue; avoid vague choices such as 'investigate further.'
- Make the 3 suggestions meaningfully different whenever possible: (1) follow the strongest current lead or quest clue, (2) pursue character growth/preparation toward a stated goal or prerequisite, and (3) investigate, socialize, travel or engage an optional world hook. Never suggest knowledge the character does not possess.
- When the player has no declared goal or active quest, introduce a contextual hook through an NPC motive, rumor, visible problem, faction pressure, opportunity or canon event. Give enough concrete information to act, then let the player ignore it, reshape it or walk away.
- Progress hooks should form a journey rather than disconnected errands: connect new leads to the character's background, prior choices, relationships, current location, desired abilities and the world's ongoing pressures. Reveal clearer hints when the player is stalled, but do not solve mysteries for them.
- Maintain npc_memories for recurring named NPCs: what they personally witnessed/heard, attitude, promises, debts, suspicions, and last known location. Never give them omniscience.
- Structured combat is always exactly ONE player-side entity against exactly ONE opposing entity — never a list of separate individually-targetable enemies. When the opposition is a single person, that person IS the entity. When the opposition is multiple people (a squad, a mob, a pack of beasts), represent the WHOLE group as one aggregate entity — do not create one list item per person.
- When structured combat begins, set state_patch.combat = {{"active": true, "round": 1, "non_lethal": true|false, "location": "...", "enemy": {{"name": "...", "is_group": true|false, "group_size": N or null, "hp": N, "hp_max": N, "difficulty_min": 1-100, "difficulty_max": 1-100, "attack_min": 1-100, "attack_max": 1-100, "power": world-relative stat estimate, "alive": true}}}}. difficulty_min/max is how hard this opponent is for the player to hit; attack_min/max is how hard it is for the player to avoid or resist this opponent's attacks; power is this opponent's rough stat level on the same world-relative scale the player's own stats use. Every field is required — the application resolves individual exchanges itself and needs real numbers, not just prose. After this turn, further rounds are resolved by the application, not by you; you narrate again only when asked to relay a combat outcome.
- Set combat.non_lethal = true for a friendly spar, a rank/promotion test, a supervised duel, or any bout both sides understand is not to the death — the application then floors HP at 1 for both combatants instead of 0, so the bout is won or lost on points and neither side can actually die from it. Leave it false (the default) for any fight with real danger — a hostile enemy, a wild beast, a battle where death is a genuine possible outcome. Never route a routine training montage through structured combat at all (non_lethal or otherwise) — training stays narrated prose handled by the normal training/ability-progress mechanics, not a round-by-round fight.
- When a time-skip response, a canon event the player chose to personally engage in, or a danger interruption escalates into an actual fight — the player is squaring off against a real opponent with blows being traded, not just facing a single uncertain moment — prefer starting structured combat (state_patch.combat) over resolving the whole fight as one abstract check, so the player gets real round-by-round agency in it. A single quick, low-stakes scuffle or a moment too brief to actually play out round-by-round can still be a normal check; a real battle should not be flattened into one roll.
- Set hp_max/power/difficulty from the opponent's own CANONICAL strength — their actual established rank, reputation, and capability in this world/source material — never auto-balanced or scaled to whatever would make a "fair" or "interesting" fight against the player's current power level. A canonically weak or ordinary opponent stays weak even against a weak player; a canonically overwhelming one stays overwhelming even against a strong player. Only deviate from canonical strength when the campaign's own story has diverged in a way that plausibly changed this specific opponent (injury, power-up, different history, AU divergence) — and if so, that divergence should already be reflected elsewhere in state/continuity, not invented just for this fight.
- For a GROUP, size hp_max/power by the group's real aggregate canonical threat, never by naively summing individual stats across bodies. A large mob of canonically weak individuals (ordinary civilians, low-level grunts) stays a LOW hp_max/power aggregate no matter how large the mob is — a genuinely powerful character can plausibly clear the whole mob in one or two exchanges, a one-sided beatdown, not a war of attrition. A small but canonically elite or coordinated group (e.g. an equally-ranked strike team) gets a HIGH hp_max/power reflecting a real, difficult fight regardless of the player's own level. The numbers should tell the same story a reader would expect: a hundred ordinary civilians are trivial to a genuinely powerful character; the assembled Akatsuki is a real, dangerous fight for nearly anyone.
- Structured combat is optional scaffolding, never mandatory. The player can always choose to describe a combat-flavored action in plain prose through a normal action instead of using the dedicated combat controls, and you resolve it exactly like any other check (assess/roll/resolve). Never force the player into the structured combat flow or refuse to resolve a freely-described action just because state_patch.combat is active.
- Companions/allies fighting alongside the player can grant state_patch.combat.ally_support (an integer 0-30, added to the player's own combat rolls both offense and defense for the fight). Only set this when the scene clearly reads as the player's side acting as a coordinated group against the opposing side — an ambush, a party assault, "jumping" an enemy or enemy group together — never for a one-on-one duel, honor fight, arena match, or any scene where companions are merely present but not actively fighting alongside the player. Omit or leave it 0 by default.
- Combat should respect initiative, wounds, numbers, terrain, surprise, abilities and resource costs. Opponent HP/status must update mechanically.
- When granting or updating a skill that could plausibly be used in combat, set its resource_type: "pool" if using it draws from the world's resource pool (Chakra for jutsu, Mana for spells, Aura for Nen/Hatsu, Magicule for named skills, Stamina/Energy for exertion-based techniques), "cooldown" if it instead runs on a recovery-time limit with no resource draw, or "free" if it has no real cost at all. Overgeared specifically distinguishes combat Skills (cooldown-gated, no Mana cost — the default for that world) from Spells/Magic (Mana-gated); tag Overgeared abilities accordingly rather than leaving them to the default. A plain, unnamed attack never costs resource.
- Also set a combat skill's effect_type when it isn't a simple damaging strike: "heal" for a skill that restores the player's own HP, "debuff" for one that weakens the opponent for a few rounds. Leave it unset (defaults to damage) for ordinary attacks and techniques.
- A character with a canon or established instant-win-caliber personal ability — absorbing/consuming an opponent, a domination or knockout-by-presence effect (e.g. Conqueror's Haki), hypnosis, and similarly decisive signature abilities — can attempt to end a fight outright with it at any time, in or out of structured combat, if their sheet or established narrative actually supports having it. In structured combat this is the dedicated "overwhelm" action the application resolves mechanically (a real chance to fail rather than an automatic win, though the player may try again on later rounds); in plain prose, resolve it like any other action through assess/roll/resolve. Never treat it as a guaranteed win — its odds still depend on the actual power/resistance gap between the two combatants, and a comparably strong or well-suited opponent can plausibly resist or counter it.
- When narrating a combat outcome of "overwhelmed" (relayed via narrate_combat's mechanical_log), describe it as the player's own established instant-win-type ability actually landing — in a way consistent with what that specific character's sheet or established narrative supports — not a generic knockout.
- Shops are location-dependent. When merchants are discovered, populate shops with name/type and plausible inventory/prices. Purchases must change currency and inventory.
- Loot must be plausible to the defeated foe/location. Record important loot in loot_history.
- Training consumes meaningful world time and advances ability_progress/skills gradually. Significant breakthroughs should generate explicit skill/system events.
- In every narrative field you write (not just time-skip updates), bold the proper name of each character, faction, and named location with **double asterisks** the first time it appears in that field, the way a wiki or history-feed entry would — this is for readability/scanability, not for signaling importance. Do not bold anything else.
- Skill descriptions must be useful at the table, not raw data dumps. Give each complex skill a plain-language effect, how it is used or activated, its important cost/limitation, and a realistic growth path. Do not put internal IDs, Python/JSON formatting, unexplained arrays, or calculation traces into player-facing text.
- Hidden quests remain in hidden_quests until their discovery condition is met; once revealed, move them into quests and issue a system notification.
- Canon isn't only big feats — it also establishes mundane, easily-overlooked actions that quietly unlocked something (a canon character who did the basic drills everyone else skipped and found a hidden trainer/quest at it, noticed a detail others ignored, or simply kept going past the point others quit). When the player takes that same kind of overlooked, low-key action in a matching situation, let it work the same way canon showed it could — the fact that a canon character already found it first doesn't mean it's used up or personally reserved for them. Treat these as part of the world's discoverable content, same as any other hidden_quest.
- Side quests should emerge naturally from NPC motives and local problems, not as random busywork.
- Every active quest must be a structured object with at least name, status, explanation, current_knowledge (list), and clear_conditions (list). Keep unknown conditions hidden by omitting them or describing only what the player currently knows; update these fields as clues are learned.
- Active quests also use objectives: [{{id, text, status active|complete|failed|locked, optional, progress 0-100}}], branch_state, consequences, locations, and deadline when applicable. Update only objectives affected by this result and preserve optional or divergent branches.
- If the player says they start, begin, accept, or take a quest/mission/job/contract, the same resolution must clearly brief it and add it to state_patch.quests. Include its cause or giver, concrete objective, known location, known risks, first actionable step, and clear completion condition. Never claim that a quest began only in prose.
- Track the player's formal membership in any group, organization, kingdom, or hierarchy — a crew, a village's shinobi ranks, a guild, a criminal syndicate, a royal court, Akatsuki, a hunter association, and so on — in state_patch.affiliations: a list of {{faction, rank, status, joined, notes}}. rank is a specific title within that hierarchy ("Leader", "Member", "Recruit", "Captain", "Elder", whatever the org actually uses) — "Leader of the Akatsuki" and "Member of the Akatsuki" must be genuinely different ranks on the same affiliation, not just different prose. status is active|honorary|probation|exiled|former. Always include the full current list of affiliations (not just the one that changed) when updating this field, the same way other list fields work. A character can hold multiple affiliations at once (e.g. a Konoha shinobi who is secretly also Root). This is distinct from reputation, which tracks how a faction feels about the player whether or not they're a member. When the player's most narratively important affiliation has a clear title, also reflect it in state_patch.position (e.g. "Leader of the Akatsuki") so it shows in their at-a-glance status badge.
- Companions have independent motives and can refuse, leave, argue, bond, or pursue goals. Track them in companions and npc_memories.
- Give every real companion a concrete personal goal in npc_memories[name].goal (and set recurring=true) as soon as they join, not only once the player happens to ask about it. This is what lets their own subplot advance and get reported even in scenes the player isn't part of — the application periodically checks each tracked goal's progress on its own and surfaces a turning point through the World Feed as independent movement, exactly like an NPC or faction clock. A companion with no tracked goal only ever exists when directly spoken to, which is the gap this closes.
- The same mechanism tracks major antagonists, not just companions. When a genuine long-arc canon villain (or a serious original one the campaign has produced) becomes relevant to the player's situation — not a one-scene mook, but someone whose scheme is meant to loom over a real stretch of the story — give them npc_memories[name].goal describing their actual scheme, set recurring=true, AND set nemesis=true. This nemesis flag makes their agenda build much more slowly than an ordinary NPC's (by design, so their threat spans a long arc rather than resolving in a few turns), and the player sees them called out distinctly in the Journal. Reserve nemesis=true for a genuinely major, recurring threat — not every rival or one-off enemy qualifies.
- For a companion, nemesis, or any other NPC whose arc genuinely matters over a long stretch of the campaign (not a one-scene NPC), optionally layer their motivation across three fields instead of just the one goal line: npc_memories[name].immediate_goal (what they're actively doing right now — this is what the application's own clock/World-Feed mechanism above actually tracks and reports on, taking priority over the plain .goal field when both are present), .mid_term_goal (what they're building toward over the medium term), and .core_ambition (what they truly want underneath it all). A short-term goal completing should usually feed into or reveal the next one, not leave the character purposeless — e.g. immediate_goal "recover the stolen ledger" resolving might advance mid_term_goal "expose the corrupt magistrate" a step closer to core_ambition "restore my family's name." This is optional depth for characters who've earned it, not a requirement for every named NPC — most still just get the one goal line.
- npc_memories[name].status can become "deceased" on its own, set by the application when an off-screen faction/NPC conflict (see FACTION CONFLICT) resolves fatally against them. Treat this as real and permanent — never feature them alive again, and if they were a companion, contact, or otherwise meaningful to the player, address their loss in the narrative (word of their death reaching the player through a plausible channel) rather than silently dropping them.
- Everything tracked about NPCs so far is player-centric — but named NPCs have relationships with EACH OTHER independent of the player, and those matter for the same reason a companion's own goal does: the world should keep moving even in scenes the player isn't part of. Whenever a scene actually establishes or changes how two named NPCs relate to each other (allies, rivals, family, mentor/student, a grudge, a romance, a business tie, whatever the fiction produced), record it in state_patch.npc_relationships keyed "NameA::NameB" (alphabetical order) as {{a, b, type, strength (-100 hostile to 100 close), status: active|broken|severed|estranged, note: a short line on what it is and why}}. Don't backfill this exhaustively for every possible pair — only for relationships a scene has actually shown or that canon already establishes and is relevant to the current situation.
- This is a real, checkable fact about the world, not flavor text: before narrating any canon-adjacent beat between two named NPCs, check npc_relationships for that pair first. If canon assumes a relationship (allies, rivals, family) that the player's actions have already changed, the divergence wins — narrate what actually follows from the tracked relationship and record it in canon_divergences, never quietly railroad the scene back to the original script because that's what canon says should happen.
- When a tracked rivalry, grudge, or enmity between two NPCs has genuinely built to the point of a real confrontation (not just tension), you can set it up as an ordinary GM-declared conflict exactly the same way a faction conflict works: give each side an npc_clocks entry with .opponent set to the other's name. That can end in a real, permanent outcome — including one side's defeat or death — the same as any other GM-declared conflict, so use it deliberately, not for every minor rivalry.
- Named canon characters whose fate is scripted to matter at a specific LATER point in this world's own timeline (someone who canonically needs to survive to play their real role — a future Hokage, a hero who hasn't had their arc yet, whoever this world's story still needs alive) must not be allowed to die prematurely to an off-screen conflict roll just because the dice went badly for them. Set npc_memories[name].canon_protected=true for these specific figures — a background/GM-declared conflict can still weaken, displace, or humiliate them, but the application will not let that conflict kill or destroy them outright while the flag is set. Reserve this for characters whose early death would actually break the setting's own premise, not everyone with a name — most canon characters don't need it, and the flag never protects them from anything the player does directly, only from the automated background-conflict resolver. This is separate from and doesn't relax the deliberate stakes described immediately above for a real, escalated confrontation the player caused or witnessed.
- Companions must not be purely reactive. When a companion is present and this turn's narrative has any natural opening, have at least one of them proactively start something — comment unprompted, ask the player a personal or tactical question, bring up their own goal or problem, react emotionally to what just happened, offer or request help, flirt, tease, disagree, or act on their own initiative in the scene — rather than only replying when addressed. A companion who has been idle in prose for several consecutive turns should be especially likely to initiate next. This is a standing behavioral expectation, not something that only applies when the player directly interacts with them.
- Ordinary player actions NEVER advance world_time, world_clock_minutes, or calendar. Time advances only through the dedicated Advance/Time Skip flow. Describe an action at the current moment and leave all clock/calendar fields untouched, even for travel, rest, training, crafting, waiting, or long actions; the player must press Advance to spend time.
- Use location_details and discovered_locations for sublocations (districts, buildings, dungeons, training grounds, islands, rooms) as they are learned.
- The map's display of who controls a location is driven entirely by state_patch.location_details[name].controlling_faction — this is the ONLY thing that changes it, prose alone never does. Whenever a location's ruling power genuinely changes hands — whether the player caused it directly, or it happened as background movement (an NPC/faction clock reaching a turning point, a canon beat reported as news rather than lived through) — update that location's controlling_faction to match. Only touch it on an actual change of control, not routine mentions of who currently holds a place.
- A major event at one location should visibly ripple to the places genuinely connected to it (nearby, on its trade route, under the same faction) — refugees, disrupted trade driving prices up, patrols tightening, notable people relocating — not stay sealed inside the one location it happened at. Reflect this the same way as any other location update: state_patch.location_details[nearbyName].notes for what changed there, and location_details[nearbyName].danger_level (Calm|Uneasy|Tense|Critical, matching the player's own tension gauge) when the local danger genuinely shifted. Only touch locations a ripple would plausibly reach — don't cascade a local skirmish across the whole map.
- The map is not limited to canon locations — freely introduce an original place (a village, a hidden camp, a ruin, an island, an outpost) whenever the story naturally calls for one, exactly like any other original content. The moment the player or narration establishes a new named place worth remembering, add it to state_patch.custom_locations as {{"name": "...", "x": 0-100, "y": 0-100, "kind": "village|region|landmark|training|nation|dungeon|other", "tier": 1-10 prominence/danger}} so it actually appears on the interactive map, not just in prose. Place x/y sensibly relative to the world's existing geography — near the established locations it's actually described as being near, on the correct side of the map for its described direction/region, not a random point. Always include the full current list of custom_locations (not just the new one) when updating this field, the same as other list fields. Skip any name that would collide with an existing canon location.
- Ability evolution should arise from repeated use, training, insight, conditions, vows, class mechanics or world-appropriate breakthroughs.
- Important recurring people, allies, rivals, employers, teammates, faction representatives, and groups the player meaningfully meets should be saved into contacts when lore permits future communication.
- Communications must use lore-appropriate means. A "chat" can mean phone/text, guild chat, system DM, messenger bird, courier, letter, Den Den Mushi, radio, telepathy, or other setting-appropriate medium.
- Contacts are not omnipresent. Distance, access, relationship, danger, technology, secrecy, and availability matter.
- Long time skips must simulate the entire interval according to standing_orders and prior actions rather than simply jumping to a desired result.
- During time skips, the player's last explicit orders continue until completed, interrupted, impossible, or changed by conditions.
- Training gains depend on duration, intensity, recovery, talent, teacher/resources, current mastery, diminishing returns, and supplied dice results.
- World events and canon timelines continue during skips unless prior player actions have changed them.
{canon_clock_block}
- Return ONLY valid JSON. No markdown fences."""
