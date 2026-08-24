"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, json, random, re, secrets, threading
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, world_primer_for, world_supports_races, infer_race_from_background, WORLD_RACES, format_calendar_date, starting_eras_for, starting_era_by_id
from ai_client import AI
from lore import format_lore_context
from portrait_generator import portrait_view
from state_guard import apply_guarded_patch, migrate_state
from continuity import update_continuity
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks)


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

# A concrete, named starting weapon/tool per archetype — "a sword", not "a
# travel-worn weapon" — so the opening loadout already looks like it belongs
# to this specific character instead of a generic placeholder. Falls back to
# WORLD_STARTER_GEAR's vaguer default only for an archetype not listed here
# (e.g. a freeform archetype the player typed in that doesn't match).
WORLD_ARCHETYPE_GEAR = {
    "One Piece": {
        "Brawler": "Reinforced Combat Gloves", "Swordsman": "Standard Cutlass",
        "Marksman": "Flintlock Pistol", "Navigator": "Compass and Rigging Knife",
        "Shipwright": "Carpenter's Hatchet and Toolkit", "Medic": "Medical Satchel and Scalpel",
        "Roguish Fighter": "Concealed Throwing Knives",
    },
    "Hunter x Hunter": {
        "Martial Artist": "Wrapped Hand Guards", "Tracker": "Hunting Knife and Rope",
        "Strategist": "Field Notebook and Compass", "Infiltrator": "Lockpicks and Grappling Wire",
        "Medic": "Field Medical Kit", "Treasure Hunter": "Prybar and Lantern",
        "Information Broker": "Hidden Recorder and Contact Ledger",
    },
    "Naruto": {
        "Taijutsu Specialist": "Wrapped Forearm Guards", "Ninjutsu Student": "Kunai and Shuriken Set",
        "Genjutsu Student": "Chakra Paper and Sealing Tags", "Scout": "Binoculars and Smoke Bombs",
        "Medic": "Medical Ninja Pouch", "Weapon Specialist": "Short Ninjatō",
        "Tactician": "Tactical Scroll Case",
    },
    "Solo Max-Level Newbie": {
        "All-Rounder": "Balanced Steel Longsword", "Melee": "Iron Broadsword",
        "Ranged": "Reinforced Shortbow", "Caster": "Novice's Focus Wand",
        "Assassin": "Twin Curved Daggers", "Tank": "Kite Shield and Mace",
        "Support": "Beginner's Healing Wand",
    },
    "Overgeared": {
        "Warrior": "Plain Iron Longsword", "Swordsman": "Balanced One-Handed Sword",
        "Archer": "Basic Recurve Bow", "Mage": "Apprentice's Wooden Staff",
        "Assassin": "Paired Daggers", "Blacksmith": "Smithing Hammer and Tongs",
        "Support": "Novice Healing Rod",
    },
    "Custom World": {
        "Warrior": "Sword and Shield", "Scout": "Hunting Bow",
        "Scholar": "Satchel of Notes and a Quill", "Mage": "Apprentice's Spellbook",
        "Rogue": "Concealed Dagger", "Healer": "Herbalist's Satchel",
    },
    "Reincarnated as a Slime": {
        "Brawler Monster": "Natural Claws and Tough Hide", "Skill Analyst": "Innate Analytical Sense",
        "Elementalist": "Elemental Affinity Core", "Beast-kin Warrior": "Bone-forged Claw Blade",
        "Diplomat/Leader": "Ceremonial Sash of Office", "Support/Healer": "Herbal Pouch and Regenerative Trait",
        "Assassin-type Monster": "Venomous Fangs",
    },
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
    # Each world gets several (mentor descriptor, formative event) pairs
    # instead of one fixed pair always used verbatim — with only one option,
    # every character in a world shared the exact same origin story.
    "Naruto": (
        ("a retired local shinobi", "a mission-era accident exposed the cost of acting without preparation"),
        ("a strict academy proctor", "a failed graduation attempt taught the difference between talent and discipline"),
        ("an aging weapons specialist", "a border skirmish forced a choice between running and standing with the unit"),
        ("a clan elder outside the main line", "a sealed technique misfired and revealed a hidden family debt"),
    ),
    "One Piece": (
        ("a weathered island veteran", "a pirate raid forced the community to rely on anyone willing to stand up"),
        ("a retired Marine turned innkeeper", "a Marine inspection exposed corruption no one else would name"),
        ("an old ship's navigator", "a storm at sea cost the crew someone the whole village still remembers"),
        ("a former bounty hunter", "a bounty gone wrong left a debt that could only be repaid at sea"),
    ),
    "Hunter x Hunter": (
        ("a traveling specialist", "an encounter with a far stronger stranger revealed how large the world really was"),
        ("a retired Hunter-exam veteran", "a failed exam attempt exposed exactly how much further real strength went"),
        ("a reclusive Nen instructor", "an unexplained ability surfaced under pressure with no one able to explain it"),
        ("a guild-affiliated tracker", "a job gone wrong left a debt only a Hunter's license could realistically repay"),
    ),
    "Solo Max-Level Newbie": (
        ("an obsessive strategy partner", "years spent mastering impossible game scenarios turned obscure knowledge into instinct"),
        ("a burned-out pro gamer", "a tournament collapse taught how thin the gap between talent and preparation is"),
        ("an eccentric theorycrafter", "a game update no one else understood rewarded the one person who'd read every patch note"),
        ("a former guild officer", "a guild's collapse under bad leadership left a lasting distrust of easy promises"),
    ),
    "Overgeared": (
        ("a demanding workshop senior", "a costly failure made persistence more important than easy talent"),
        ("an unlicensed blacksmith", "a ruined commission taught the real price of cutting corners"),
        ("a jaded former guild crafter", "a stolen recipe exposed how little goodwill exists among top players"),
        ("a stubborn old adventurer", "a near-fatal dungeon run left a debt only steady, unglamorous work could repay"),
    ),
    "Reincarnated as a Slime": (
        ("an elder familiar with local monsters", "a territorial crisis revealed both the value and danger of unusual abilities"),
        ("a wary goblin elder", "a raid by a rival tribe forced an uneasy alliance no one fully trusted yet"),
        ("a wandering monster tamer", "a botched taming attempt showed how little separates a monster from a companion"),
        ("a cautious forest-dwelling sage", "a magic-born disaster proved the forest's peace was more fragile than it looked"),
    ),
    "Custom World": (
        ("a locally respected mentor", "a dangerous incident revealed that talent without understanding creates consequences"),
        ("a retired local specialist", "a close call in the field taught respect for what looked like routine work"),
        ("a demanding local elder", "a broken promise exposed a debt that still needed to be repaid"),
        ("a wandering former professional", "an old failure became the reason they never let a student make the same mistake"),
    ),
}

WORLD_BACKGROUND_NAMES = {
    "Naruto": ("Mika Sato", "Daichi Mori", "Ren Aburame", "Hana Inuzuka", "Kaede Yamashiro", "Isamu Nara",
               "Tsubaki Fuma", "Genzo Hatake", "Yui Kamizuki", "Botan Sarutobi", "Rei Uzuki", "Haru Tanaka"),
    "One Piece": ("Mara Venn", "Old Corin", "Tessa Flint", "Captain Dael", "Bellamy Cross", "Noa Sancroft",
                  "Grey Marlow", "Iris Cabrera", "Tomas Reyes", "Selka Vane", "Old Pell", "Marin Osgood"),
    "Hunter x Hunter": ("Ilya Rook", "Mina Vale", "Toren Ash", "Kessa Vail", "Doran Ferro", "Yuna Marsh",
                        "Cael Rennick", "Lior Densu", "Tamsin Cray", "Odell Vance", "Nira Kolt", "Bram Astley"),
    "Solo Max-Level Newbie": ("Seo Min-jae", "Han Yu-ri", "Park Do-jin", "Choi Hae-won", "Jung Si-woo", "Kang Nari",
                              "Oh Tae-yang", "Lim Su-bin", "Baek Jun-ho", "Yoon Ara", "Shin Dae-hyun", "Moon Ji-hu"),
    "Overgeared": ("Elian Voss", "Mira Anvil", "Garron Pell", "Kesta Ward", "Ordin Vale", "Sela Marrow",
                   "Bram Kessler", "Tovin Reed", "Anya Coldiron", "Fenric Bale", "Mira Duskwright", "Talon Grey"),
    "Reincarnated as a Slime": ("Rilsa", "Gelm", "Nemu", "Sorel", "Fadda", "Mireth", "Gobzo", "Ranith",
                                "Elmis", "Korgu", "Vessa", "Draska"),
    "Custom World": ("Ari Vale", "Mara Stone", "Toren Reed", "Elan Ashford", "Sena Cobb", "Rook Delaney",
                      "Ivy Marchetti", "Dashiell Kern", "Wren Castellan", "Marlow Finch", "Talia Voss", "Corin Blake"),
}

BACKGROUND_HOMES = (
    "A practical household taught them to contribute early, even when its members did not fully understand their ambitions.",
    "They were raised by a small circle of relatives and neighbors whose support came with duties they still feel responsible for.",
    "Their home life was modest and sometimes unstable, making preparation, loyalty, and self-reliance learned habits rather than slogans.",
    "They grew up in a household that valued quiet competence over recognition, and rarely praised anything less than results.",
    "A tight-knit but overextended family left them used to picking up responsibilities no one else had time for.",
    "They were raised mostly by example rather than instruction, learning more from watching than from being taught outright.",
)



class CampaignMixin:
    def roll_starting_stats(self, world, archetype, player_stats):
        """Generate an open-ended, world-relative starting profile.

        Thirty represents a competent local beginner, not a universal human
        maximum. Values have no hard ceiling and mean something only against
        other characters in the same setting and era.
        """
        primary = primary_stats_for(world, archetype)
        bonus_for = {}
        if len(primary) > 0:
            bonus_for[primary[0]] = 12
        if len(primary) > 1:
            bonus_for[primary[1]] = 7
        if len(primary) > 2:
            bonus_for[primary[2]] = 4
        final = {}
        for ability in abilities_for(world):
            base = random.randint(26, 36)
            bonus = bonus_for.get(ability, 0)
            delta = int(player_stats.get(ability, 0) or 0)
            final[ability] = max(1, base + bonus + delta)
        return final

    @staticmethod
    def derive_pools(world, stats):
        hp_keys, resource_keys = POOL_STATS.get(world, POOL_STATS["Custom World"])
        hp_primary = int(stats.get(hp_keys[0], 30)); hp_secondary = int(stats.get(hp_keys[1], 30))
        re_primary = int(stats.get(resource_keys[0], 30)); re_secondary = int(stats.get(resource_keys[1], 30))
        # These are setting-relative capacities, intentionally not a flat 100.
        return max(20, 25 + hp_primary * 2 + hp_secondary), max(10, 15 + re_primary * 2 + re_secondary)

    @staticmethod
    def background_ability_requested(background):
        """Treat an underspecified power claim as permission to instantiate it."""
        text = str(background or "").lower()
        return bool(re.search(
            r"\b(ability|abilities|power|powers|gift|gifted|talent|talented|technique|skill|"
            r"bloodline|mutation|magic|chakra|nen|hatsu|devil fruit|class)\b", text
        ))

    @staticmethod
    def ability_aspect(background):
        text = str(background or "").lower()
        for keyword, aspect in ABILITY_ASPECTS.items():
            if keyword in text:
                return aspect
        return random.choice(("Ember", "Tide", "Gale", "Stone", "Echo", "Flash", "Shadow", "Radiance"))

    def generate_background_ability(self, world, background, boost):
        aspect = self.ability_aspect(background)
        form = random.choice(WORLD_ABILITY_FORMS.get(world, WORLD_ABILITY_FORMS["Custom World"]))
        values = {"aspect": aspect, "aspect_lower": aspect.lower()}
        name, origin, effect, limitation, growth = (part.format(**values) for part in form)
        return {
            "name": name,
            "details": {
                "rank": "Awakened" if boost >= 20 else "Nascent",
                "bonus": 3 + boost // 20,
                "description": effect.capitalize() + ".",
                "origin": origin.capitalize() + ".",
                "effect": effect.capitalize() + ".",
                "limitation": limitation.capitalize() + ".",
                "growth_path": growth.capitalize() + ".",
                "generated_from": str(background or "A vague request for an unusual starting ability.").strip(),
            },
        }

    def build_background_profile(self, world, origin, archetype, background, boost, primary_stats):
        """Fill narrative gaps and expose the factors that affect growth."""
        raw = str(background or "").strip()
        lowered = raw.lower()
        mentor, formative_event = random.choice(WORLD_BACKGROUND_COLOR.get(world, WORLD_BACKGROUND_COLOR["Custom World"]))
        mentor_name = random.choice(WORLD_BACKGROUND_NAMES.get(world, WORLD_BACKGROUND_NAMES["Custom World"]))
        home_context = random.choice(BACKGROUND_HOMES)
        origin_label = str(origin or "the local community").strip()
        role_label = str(archetype or "adventurer").strip()

        if any(k in lowered for k in ("prodigy", "genius", "exceptional talent", "gifted")):
            learning_rate, aptitude = 1.35, "Exceptional aptitude"
        elif any(k in lowered for k in ("trained", "graduate", "veteran", "disciplined", "studied")):
            learning_rate, aptitude = 1.15, "Practiced learner"
        elif any(k in lowered for k in ("slow learner", "struggle to learn", "poor student", "untalented")):
            learning_rate, aptitude = .85, "Persistent late bloomer"
        else:
            learning_rate, aptitude = 1.0, "Typical local potential"

        if any(k in lowered for k in ("protect", "save", "help", "family")):
            motivation = "They want enough skill and influence to protect the people they choose to call their own."
        elif any(k in lowered for k in ("revenge", "avenge", "vengeance")):
            motivation = "They are driven to uncover the truth behind an old wrong and become capable of answering it."
        elif any(k in lowered for k in ("strongest", "powerful", "master")):
            motivation = "They intend to prove that their potential can become genuine mastery rather than an untested boast."
        elif any(k in lowered for k in ("explore", "adventure", "world", "freedom")):
            motivation = "They want to see what lies beyond their familiar life and earn the freedom to choose their own path."
        else:
            motivation = "They want to turn an uncertain beginning into earned capability and decide what place they will claim in the world."

        training = (
            f"Their early {role_label.lower()} practice was uneven but persistent, emphasizing "
            f"{', '.join(primary_stats[:2]) if primary_stats else 'the fundamentals their role demands'}."
        )
        relationship = f"{mentor_name}, {mentor}, supplied guidance, friction, and an unfinished expectation."
        complication = (
            "Their potential is ahead of their experience, so judgment, resources, and reliable control remain real obstacles."
            if boost >= 20 else
            "They still lack the experience and resources to turn every promising instinct into a dependable result."
        )
        supplied = f"Their own account adds: \"{raw.rstrip('.')}\"." if raw else "They have not given a fixed account of their earlier life."
        expanded = " ".join((
            f"Raised around {origin_label}, they learned the habits and pressures expected of a {role_label}.",
            home_context,
            supplied,
            training,
            relationship,
            f"The turning point came when {formative_event}.",
            motivation,
            complication,
        ))
        accelerators = []
        if learning_rate > 1:
            accelerators.append("Prior practice and unusually fast pattern recognition")
        if self.background_ability_requested(raw):
            accelerators.append("A starting ability that can create specialized training routes")
        accelerators.append("Focused practice, a suitable mentor, and world-valid resources")
        constraints = ["Fatigue and recovery", "Current mastery and diminishing returns", "Access to teachers, knowledge, and materials"]
        return {
            "expanded_background": expanded,
            "background_details": {
                "upbringing": f"Raised around {origin_label} with expectations suited to a {role_label}. {home_context}",
                "training_history": training,
                "key_connection": relationship,
                "formative_event": formative_event.capitalize() + ".",
                "motivation": motivation,
                "starting_complication": complication,
            },
            "growth_profile": {
                "aptitude": aptitude,
                "learning_rate": learning_rate,
                "starting_strengths": list(primary_stats[:3]),
                "accelerators": accelerators,
                "constraints": constraints,
                "explanation": "This multiplier affects sustained training gains, while teachers, resources, rolls, recovery, and current mastery still determine actual results.",
            },
        }

    def infer_starting_wealth(self, world, origin, archetype, background, boost):
        """How much starting currency a character plausibly has, from their
        stated background rather than one flat number for every campaign.
        Two independent signals: this world's own economic scale (a Berries
        economy and a Ryo economy aren't the same order of magnitude), and
        this specific background's wealth relative to an ordinary local
        (a runaway noble starts richer than a street orphan even if neither
        is a strong fighter — wealth and combat power are different axes,
        so this stays separate from the power `boost` above, with only a
        light additive nudge from it for a genuinely major starting figure)."""
        baseline = int(expansion_for(world).get("currency_baseline", 250))
        text = f"{origin} {archetype} {background}".lower()
        multiplier = 1.0
        if any(k in text for k in ("noble", "royal", "prince", "princess", "heir", "aristocrat", "wealthy", "rich merchant", "merchant family", "clan heir")):
            multiplier = 5.0
        elif any(k in text for k in ("merchant", "shopkeeper", "trader", "blacksmith", "crafter", "landowner")):
            multiplier = 2.0
        elif any(k in text for k in ("soldier", "recruit", "academy graduate", "guild", "hunter", "mercenary", "military")):
            multiplier = 1.3
        elif any(k in text for k in ("orphan", "street", "runaway", "poor", "impoverished", "homeless", "beggar", "survivor", "refugee")):
            multiplier = 0.35
        elif any(k in text for k in ("bandit", "smuggler", "black market", "criminal", "thief")):
            multiplier = 1.6
        amount = baseline * multiplier + boost * (baseline / 50.0)
        # +/-15% so two characters with the same background text don't start
        # with the exact identical number down to the last coin.
        amount *= random.uniform(0.85, 1.15)
        return max(1, int(round(amount / 5.0)) * 5)

    @staticmethod
    def naruto_identity_title(origin, start_location):
        """Naruto's ongoing character identity is rank and affiliation, not
        a combat-focus archetype like "Ninjutsu Student" — that only ever
        mattered at character creation. "Leaf - Chunin", "Sand - Genin",
        "Akatsuki - Member" is what actually reads as a shinobi's standing
        to another shinobi, so that's what the title chip should show."""
        village = {
            "Konohagakure": "Leaf", "Sunagakure": "Sand", "Kirigakure": "Mist",
            "Kumogakure": "Cloud", "Iwagakure": "Stone", "Iron Country": "Iron Country",
        }.get(str(start_location).strip(), "")
        text = f"{origin}".lower()
        if str(start_location).strip() == "Amegakure" or "akatsuki" in text:
            return "Akatsuki - Member"
        if "jonin" in text:
            rank = "Jonin"
        elif "chunin" in text:
            rank = "Chunin"
        elif "anbu" in text or "root" in text:
            rank = "Anbu"
        elif "rogue" in text or "missing-nin" in text:
            return "Rogue - Missing-nin"
        elif "samurai" in text:
            rank = "Samurai"
        elif "graduate" in text:
            rank = "Genin"
        else:
            rank = "Academy Student"
        return f"{village or 'Unaffiliated'} - {rank}"

    def infer_starting_profile(self, world, origin, archetype, background, stats, start_location=""):
        text = f"{origin} {archetype} {background}".lower()
        boost, band = 0, "Average beginner"
        if any(k in text for k in ("omnipotent", "godlike", "six paths", "demon lord", "yonko", "emperor of the sea")):
            boost, band = 100, "World-shaking"
        elif any(k in text for k in ("hokage", "kage", "admiral", "master assassin", "legendary", "s-rank")):
            boost, band = 55, "Elite / major power"
        elif any(k in text for k in ("veteran", "prodigy", "genius", "bloodline", "elite", "champion", "jonin", "notorious", "renowned")):
            boost, band = 20, "Exceptional starter"
        elif any(k in text for k in ("trained", "graduate", "martial artist", "soldier", "hunter", "chunin", "samurai")):
            boost, band = 8, "Trained starter"
        primary = primary_stats_for(world, archetype)
        background_profile = self.build_background_profile(world, origin, archetype, background, boost, primary)
        learning_rate = background_profile["growth_profile"]["learning_rate"]
        aptitude_bonus = 4 if learning_rate >= 1.3 else (2 if learning_rate > 1 else (-2 if learning_rate < 1 else 0))
        adjusted = {k: max(1, int(v) + boost + (aptitude_bonus if k in primary else 0)) for k, v in stats.items()}
        skill_name = WORLD_STARTER_SKILL.get(world, "Background Expertise")
        if "uchiha" in text: skill_name = "Uchiha Fire and Dōjutsu Foundations"
        elif "medic" in text or "healer" in text: skill_name = f"{archetype or 'Field'} Healing Fundamentals"
        elif archetype: skill_name = f"{archetype} Fundamentals"
        title = self.naruto_identity_title(origin, start_location) if world == "Naruto" else f"{origin or 'Local'} {archetype or 'Adventurer'}".strip()
        skills = {skill_name: {"rank": "Trained" if boost < 20 else "Exceptional", "bonus": 4 + boost // 10,
                               "description": "Generated from the character's stated background and starting role."}}
        generated_ability = None
        if self.background_ability_requested(background):
            generated_ability = self.generate_background_ability(world, background, boost)
            skills[generated_ability["name"]] = copy.deepcopy(generated_ability["details"])
        specific_gear = WORLD_ARCHETYPE_GEAR.get(world, {}).get(archetype)
        equipment = {"Weapon": specific_gear or WORLD_STARTER_GEAR.get(world, WORLD_STARTER_GEAR["Custom World"])}
        hp_max, resource_max = self.derive_pools(world, adjusted)
        notice = ""
        if boost >= 20:
            notice = (f"This background creates an {band.lower()} character who begins far above an average local starter. "
                      "The campaign allows it; rivals, factions and consequences will respond at the same scale.")
        race = infer_race_from_background(world, background, origin, archetype) if world_supports_races(world) else ""
        starting_currency = self.infer_starting_wealth(world, origin, archetype, background, boost)
        return {"stats": adjusted, "skills": skills, "titles": [title], "equipment": equipment,
                "hp_max": hp_max, "resource_max": resource_max, "power_band": band, "power_notice": notice,
                "primary_stats": primary, "generated_ability": generated_ability, "race": race,
                "starting_currency": starting_currency,
                **background_profile}

    def canon_character_scenario(self, world, scenario_id):
        return next((copy.deepcopy(x) for x in playable_characters_for(world) if x.get("id") == scenario_id), None)

    def preview_campaign(self, name, world, difficulty, background, appearance_desc, custom_world, origin, archetype, stats, start_location="", start_note="", canon_character_id="", starting_era_id=""):
        if world not in WORLD_DATA:
            raise ValueError("Unknown world selected.")
        if difficulty not in DIFFICULTIES:
            raise ValueError("Unknown difficulty selected.")
        wd, canon = WORLD_DATA[world], timeline_for(world)
        scenario = self.canon_character_scenario(world, canon_character_id) if canon_character_id else None
        if scenario:
            name, background, appearance_desc = scenario["name"], scenario.get("background", ""), scenario.get("appearance", "")
            origin, archetype, start_location = scenario.get("origin", origin), scenario.get("archetype", archetype), scenario.get("location", start_location)
        # An original character can begin in a different era of the same
        # world instead of always the default anchor — a canon-character
        # scenario (which already fixes its own start_day) always wins.
        era = None if scenario else starting_era_by_id(world, starting_era_id)
        start = str(start_location or wd["start"]).strip()
        rolled = self.roll_starting_stats(world, archetype, stats or {})
        profile = self.infer_starting_profile(world, origin, archetype, background, rolled, start_location=start)
        if scenario:
            start_day, canon_anchor = int(scenario.get("start_day")), scenario.get("background")
        elif era:
            start_day, canon_anchor = int(era["start_day"]), era["anchor"]
        else:
            start_day, canon_anchor = int(canon.get("start_day", -7)), canon.get("anchor", "")
        return {
            "name": str(name or "Traveler").strip() or "Traveler", "world": world,
            "difficulty": difficulty, "tagline": wd["tagline"], "rules": wd["rules"],
            "origin": origin, "archetype": archetype, "start_location": start,
            "start_day": start_day, "canon_anchor": canon_anchor,
            "abilities": profile["stats"], "resource": wd["resource"], "appearance": appearance_desc,
            "starting_profile": profile, "uses_xp": uses_xp_for(world),
            "race": profile.get("race", ""), "race_options": WORLD_RACES.get(world, {}).get("options", []),
            "background": profile.get("expanded_background", background),
            "background_details": profile.get("background_details", {}),
            "growth_profile": profile.get("growth_profile", {}), "custom_world": custom_world,
            "world_pack_id": wd.get("pack_id", "builtin"),
            "canon_character": scenario,
            "world_primer": world_primer_for(world, custom_world),
            "starting_era": era, "starting_era_options": starting_eras_for(world),
        }

    def new_campaign(self, name, world, difficulty, background, appearance_desc, custom_world, origin, archetype, stats, start_location="", start_note="", preview_stats=None, preview_profile=None, canon_character_id="", starting_era_id="", age=""):
        wd = WORLD_DATA[world]
        scenario = self.canon_character_scenario(world, canon_character_id) if canon_character_id else None
        era = None if scenario else starting_era_by_id(world, starting_era_id)
        if scenario:
            name, background, appearance_desc = scenario["name"], scenario.get("background", ""), scenario.get("appearance", "")
            origin, archetype, start_location = scenario.get("origin", origin), scenario.get("archetype", archetype), scenario.get("location", start_location)
        start = start_location.strip() or wd["start"]
        rolled = copy.deepcopy(preview_stats) if isinstance(preview_stats, dict) else self.roll_starting_stats(world, archetype, stats)
        profile = copy.deepcopy(preview_profile) if isinstance(preview_profile, dict) else self.infer_starting_profile(world, origin, archetype, background, rolled, start_location=start)
        profile_stats = profile.get("stats") if isinstance(profile.get("stats"), dict) else rolled
        hp_max, resource_max = self.derive_pools(world, profile_stats)
        with self.lock:
            self.state = copy.deepcopy(BASE_STATE)
            self.state.update(
                name=name.strip() or "Traveler", world=world, difficulty=difficulty,
                background=profile.get("expanded_background", background), appearance_desc=appearance_desc, custom_world=custom_world,
                race=profile.get("race", "") if world_supports_races(world) else "",
                calendar_epoch=datetime.today().date().isoformat(),
                location=start, resource_name=wd["resource"],
                factions=copy.deepcopy(wd["factions"]), reputation=copy.deepcopy(wd["factions"]),
                special=copy.deepcopy(wd["special"]), discovered_locations=[start],
                stats=copy.deepcopy(profile_stats), skills=copy.deepcopy(profile.get("skills", {})),
                titles=copy.deepcopy(profile.get("titles", [])), equipment=copy.deepcopy(profile.get("equipment", {})),
                hp=hp_max, hp_max=hp_max, resource=resource_max, resource_max=resource_max,
                starting_power_band=profile.get("power_band", "Average beginner"),
                starting_power_notice=profile.get("power_notice", ""),
                campaign_id=secrets.token_hex(8),
                campaign_created_version=APP_VERSION, campaign_last_saved_version=APP_VERSION,
                schema_version=BASE_STATE.get("schema_version", 5), world_pack_id=wd.get("pack_id", "builtin"),
                player_identity={"mode": "canon" if scenario else "original", "canon_character_id": scenario.get("id", "") if scenario else "", "canon_gravity": True},
            )
            ex = expansion_for(world)
            prefix = f"Origin: {origin}\nStarting archetype: {archetype}\n"
            if start_note.strip():
                prefix += start_note.strip() + "\n"
            self.state["background"] = (prefix + self.state.get("background", "")).strip()
            self.state["currency"] = {"name": ex["currency"], "amount": profile.get("starting_currency", ex.get("currency_baseline", 250))}
            self.state["special"]["Origin"] = origin
            self.state["special"]["Archetype"] = archetype
            self.state["special"]["Background Details"] = copy.deepcopy(profile.get("background_details", {}))
            self.state["special"]["Growth Profile"] = copy.deepcopy(profile.get("growth_profile", {}))
            normalize_tuning(self.state)
            if isinstance(profile.get("generated_ability"), dict):
                self.state["special"]["Generated Ability"] = copy.deepcopy(profile["generated_ability"])
            self.state["portrait_traits"] = [appearance_desc] if appearance_desc.strip() else []
            canon = timeline_for(world)
            if scenario:
                start_day, anchor_text = int(scenario.get("start_day")), scenario.get("background")
            elif era:
                start_day, anchor_text = int(era["start_day"]), era["anchor"]
            else:
                start_day, anchor_text = int(canon.get("start_day", -7)), canon.get("anchor", "Before the main story")
            self.state["canon_day"] = start_day
            self.state["canon_time_minutes"] = start_day * 1440 + 480
            self.state["canon_anchor"] = anchor_text
            self.state["canon_events_fired"] = []
            # This campaign's own start_day is Year 1/Month 1/Day 1 for calendar
            # purposes, not necessarily the world's generic default — a canon
            # character (e.g. Naruto at birth, start_day -4380) or a chosen
            # starting era begins far from the default and must anchor its own
            # calendar, or every date the player sees reads as a nonsense
            # negative year.
            self.state["calendar_anchor_day"] = start_day
            self.state["world_time"] = f"{format_calendar_date(world, start_day, self.state.get('calendar_epoch'), start_day)} — Morning, 08:00"
            self.state["timeline"] = [f"{self.state['name']} enters the story at {start}. {self.state['canon_anchor']}." ]
            if scenario:
                self.state["age"] = scenario.get("age", "")
                self.state["campaign_canon"] = [{"turn": 0, "type": "canon_character_start", "text": f"The player assumes full control of {scenario['name']} at {scenario['label']}."}]
            # An explicit typed age always wins, even over a canon scenario's
            # own default — the player is deliberately choosing an unusual
            # combination on purpose (see the "odd combos for fun" note in
            # the UI), not making a mistake to be corrected. Left blank, the
            # existing opening() needs_age path already asks the AI to
            # invent a plausible age fitting the origin/archetype/background,
            # which is a better fit for "match the closest age" than a fixed
            # rule table would be.
            if str(age).strip():
                self.state["age"] = str(age).strip()
            self.state["codex"] = [{"name": start, "type": "Location", "notes": "Starting location."}]
            # Major world polities/groups are contactable from day one, not
            # only after the story happens to introduce them — the player can
            # try reaching out to the Marines, a Hidden Village, the Hunter
            # Association, a guild, etc. immediately, for whatever that's worth
            # given their current standing and station in life.
            for faction_name in wd["factions"]:
                self.ensure_contact(faction_name, "group", {
                    "status": "Known", "can_contact": True,
                    "notes": ["A major faction/polity in this world — reachable from the start, though willingness to engage depends on your reputation and station."],
                })
            # A fresh campaign always has useful direction, even before the
            # opening narration model is available.
            self.state["suggested_actions"] = self.guided_suggestions([])
            self.checkpoints = []
            self.history = []
            self.story_log = []
            self.system_log = []
            self.campaign_active = True
            self.append(f"[CAMPAIGN START]\n{self.state['name']} — {world} — {difficulty}\n{wd['tagline']}", "system")
        return self.public_state()

    def opening(self):
        needs_background = not self.state.get("background", "").strip()
        needs_appearance = not self.state.get("appearance_desc", "").strip()
        needs_name = self.state.get("name", "").strip().lower() in ("", "traveler")
        needs_age = not str(self.state.get("age", "")).strip()
        requirements = []
        if needs_name:
            requirements.append("The player didn't choose a name — invent one that fits the world, origin and archetype, and set it in state_patch.name. Never leave it as 'Traveler'.")
        if needs_age:
            requirements.append("The player's age is unset — invent a plausible age fitting the origin/archetype/world and set it in state_patch.age (a number).")
        if needs_background:
            requirements.append("The player left their background blank — invent a plausible backstory consistent with their origin, archetype and world, and set it in state_patch.background.")
        if needs_appearance:
            requirements.append("The player left their appearance blank — invent a fitting physical description consistent with origin/archetype/world, and write the ACTUAL descriptive sentence into state_patch.appearance_desc as a real string (e.g. 'A lean youth with gray eyes and a scar along his jaw') — never a placeholder, a reference to another field, or a note saying it's set elsewhere. portrait_traits is a separate short list of the same distinctive details, in addition to (not instead of) appearance_desc.")
        requirements.append("Treat every ability, education, social status, possession and trait claimed in the player's background as an authoritative starting fact unless it directly contradicts the chosen world. The generated Background Details, Growth Profile, and Generated Ability in state.special are authoritative starting context; preserve and deepen them rather than erasing them. Very powerful starts are allowed.")
        if world_supports_races(self.state.get("world", "Custom World")):
            options = WORLD_RACES.get(self.state.get("world"), {}).get("options", [])
            requirements.append(
                f"This world distinguishes race/species. state.race currently holds only a quick keyword guess ({self.state.get('race', 'Human')}) made before you could actually read the background — confirm or correct it in state_patch.race. "
                f"Established races in this world include: {', '.join(options)}. If the player's background clearly describes something else, invent a specific, fitting race name instead of forcing it into one of these — it just needs to logically follow this world's actual rules for what that race can do (a slime that breathes fire needs an in-fiction reason a human turned monster wouldn't). Keep it a short name (1-3 words), not a sentence."
            )
        requirements.append("If the player's original background was vague, complete the missing upbringing, family or community context, training history, formative event, important relationship, motivation, and complication. Keep supplied facts unchanged, make the additions setting-valid, and return the enriched account in state_patch.background.")
        requirements.append("Every generated starting ability must remain named in state_patch.skills and be explainable through its origin, effect, limitation or cost, and growth path. Introduce it naturally in the opening; it is a real ability, not a rumor or disposable plot hook.")
        requirements.append("Open with a concrete situation and at least one actionable lead tied to this location, background, goal or upcoming world pressure. End with exactly 3 optional next actions: follow the lead, prepare/progress, or explore an alternate hook.")
        p = {"task": "opening", "state": self.trimmed_state_for_ai(), "requirements": requirements,
             "schema": {"narrative": "1 short paragraph, 3-5 sentences, ending with an open situation",
                        "state_patch": "persistent changes including appearance/portrait_traits when relevant",
                        "events": "system notifications", "timeline_event": "major event or empty",
                        "suggested_actions": ["exactly 3 optional, contextual next actions, each naming a specific person/place/thread just established in this opening — not a generic template. At least one clear lead. A suggestion can span more than a moment if that's genuinely what it calls for."]}}
        # The opening asks for more than a routine turn — name/age/background/
        # appearance/abilities plus narrative and state_patch all at once —
        # so it gets a bigger budget than a normal resolution. Truncated
        # responses are now repaired automatically (see repair_truncated_json),
        # so this no longer needs to be oversized purely as insurance against
        # a cut-off reply.
        data = self.request_with_narrative(self.gm_context("campaign opening starting location origin archetype"), p, 1500)
        return self.apply_resolution(data, is_opening=True)
