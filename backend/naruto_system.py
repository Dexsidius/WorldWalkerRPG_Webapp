"""Naruto-specific Jinchuriki creation, migration, and mechanics.

A tailed beast is an independent character and a sealed power system, not a
generic skill.  The profile records the host's current access separately from
the beast's full canon potential so an unmastered host receives the reserve,
social consequences, seal pressure, and loss-of-control risks without being
treated as a perfect Jinchuriki on day one.
"""
from __future__ import annotations

import copy
import hashlib
import random
import re


TAILED_BEASTS = {
    1: {
        "name": "Shukaku", "title": "One-Tail", "nature": ["Wind Release", "Magnet Release"],
        "traits": ["Sand manipulation and defense", "Cursed seal markings", "Exceptional sealing techniques"],
    },
    2: {
        "name": "Matatabi", "title": "Two-Tails", "nature": ["Fire Release"],
        "traits": ["Blue-flame generation", "Extreme feline speed and agility", "Claw and pounce combat"],
    },
    3: {
        "name": "Isobu", "title": "Three-Tails", "nature": ["Water Release"],
        "traits": ["Coral generation", "Armored shell defense", "High-speed rolling charges and aquatic combat"],
    },
    4: {
        "name": "Son Goku", "title": "Four-Tails", "nature": ["Fire Release", "Earth Release", "Lava Release"],
        "traits": ["Lava Release chakra", "Enormous physical strength", "Volcanic heat and terrain attacks"],
    },
    5: {
        "name": "Kokuo", "title": "Five-Tails", "nature": ["Fire Release", "Water Release", "Boil Release"],
        "traits": ["Boil Release steam pressure", "Explosive physical acceleration", "Horn and charge combat"],
    },
    6: {
        "name": "Saiken", "title": "Six-Tails", "nature": ["Water Release"],
        "traits": ["Corrosive alkali and acid", "Adhesive slime", "Bubble techniques and fluid body defense"],
    },
    7: {
        "name": "Chomei", "title": "Seven-Tails", "nature": ["Wind Release"],
        "traits": ["True flight", "Scale powder and blinding dust", "Cocoon and insect-body techniques"],
    },
    8: {
        "name": "Gyuki", "title": "Eight-Tails", "nature": ["Lightning Release"],
        "traits": ["Ink generation and sealing ink", "Eight prehensile tentacles", "Exceptional strength and durable regeneration"],
    },
    9: {
        "name": "Kurama", "title": "Nine-Tails", "nature": ["Fire Release", "Wind Release"],
        "traits": ["Vast chakra and rapid recovery", "Chakra arms and protective cloaks", "Negative-emotion sensing after sufficient synchronization", "Chakra sharing with allies at high mastery"],
    },
    10: {
        "name": "Ten-Tails", "title": "Ten-Tails", "nature": ["All five basic nature transformations", "Yin-Yang Release"],
        "traits": ["Six Paths-level chakra", "Truth-Seeking Ball potential", "Flight and extreme regeneration", "World-scale sensory and destructive power"],
    },
}

NAME_TO_TAILS = {
    "shukaku": 1, "one tail": 1, "one tails": 1, "one tailed": 1, "ichibi": 1,
    "matatabi": 2, "two tail": 2, "two tails": 2, "two tailed": 2, "nibi": 2,
    "isobu": 3, "three tail": 3, "three tails": 3, "three tailed": 3, "sanbi": 3,
    "son goku": 4, "four tail": 4, "four tails": 4, "four tailed": 4, "yonbi": 4,
    "kokuo": 5, "five tail": 5, "five tails": 5, "five tailed": 5, "gobi": 5,
    "saiken": 6, "six tail": 6, "six tails": 6, "six tailed": 6, "rokubi": 6,
    "chomei": 7, "chōmei": 7, "seven tail": 7, "seven tails": 7, "seven tailed": 7, "nanabi": 7,
    "gyuki": 8, "gyūki": 8, "eight tail": 8, "eight tails": 8, "eight tailed": 8, "hachibi": 8,
    "kurama": 9, "nine tail": 9, "nine tails": 9, "nine tailed": 9, "kyubi": 9, "kyuubi": 9,
    "ten tail": 10, "ten tails": 10, "ten tailed": 10, "juubi": 10, "jubi": 10,
}

GENERAL_CANON_ABILITIES = [
    "Access to the tailed beast's immense chakra reserve",
    "Tailed-beast chakra cloak and progressive tail manifestations",
    "Version 1 and Version 2 transformations when sufficient chakra and control are reached",
    "Partial transformation into the beast's limbs or traits",
    "Full tailed-beast transformation after genuine cooperation or overpowering control",
    "Tailed Beast Ball and derived variants after the necessary ratio and control are mastered",
    "Telepathic communication and combat coordination with the sealed beast",
]

UNMASTERED_DRAWBACKS = [
    "The tailed beast is an independent person and may resist, deceive, withhold chakra, or attempt to seize control.",
    "Fear, rage, injury, exhaustion, or seal damage can trigger involuntary chakra leakage and escalating transformations.",
    "Dense cloaks can burn or tear the host's body, distort judgment, and injure nearby allies.",
    "Forcing more tails than the host can control can cause berserk behavior, memory loss, and a weakened seal.",
    "Villages may fear, isolate, monitor, weaponize, or politically control a known host; Akatsuki and other hunters may target them.",
    "Extraction of the tailed beast is normally fatal to the host without extraordinary intervention.",
]

MASTERED_LIMITS = [
    "The tailed beast remains an independent ally rather than an inventory item; cooperation can be strained by betrayal or conflicting goals.",
    "Large transformations and Tailed Beast Balls still consume immense chakra and can devastate allies, civilians, and terrain.",
    "Sealing disruption, specialized suppression, extraction, and sufficiently powerful opponents remain real threats.",
]

CHAKRA_NATURES = ("Fire Release", "Wind Release", "Lightning Release", "Earth Release", "Water Release")
_NATURE_ALIASES = {
    "fire": "Fire Release", "katon": "Fire Release",
    "wind": "Wind Release", "futon": "Wind Release", "fuuton": "Wind Release",
    "lightning": "Lightning Release", "raiton": "Lightning Release",
    "earth": "Earth Release", "doton": "Earth Release",
    "water": "Water Release", "suiton": "Water Release",
}


def _stated_natures(text):
    lowered = str(text or "").lower().replace("ū", "u").replace("ō", "o")
    found = []
    for token, nature in _NATURE_ALIASES.items():
        patterns = (
            rf"\b{token}\s+(?:chakra\s+)?(?:nature|affinity|release)\b",
            rf"\b(?:nature|chakra)\s+affinity\s+(?:for|to|with)\s+{token}\b",
            rf"\b(?:natural|innate|primary|secondary)\s+{token}\b",
        )
        matches = [match for pattern in patterns for match in re.finditer(pattern, lowered)]
        # "I want to learn Water Release" describes a goal, not a natural
        # Water affinity. The learned nature will be added later when a real
        # technique/training record establishes it.
        matches = [match for match in matches if not re.search(
            r"(?:want|hope|plan|try|trying|seek|seeking|learn|learning|study|studying|train|training)\s+(?:to\s+)?$",
            lowered[max(0, match.start() - 24):match.start()],
        )]
        if matches and nature not in found:
            found.append(nature)
    return found


def build_chakra_affinity_profile(background="", seed="", established=None):
    """Create persistent nature-learning rules, not a cosmetic label."""
    stated = []
    if isinstance(established, list):
        stated = [str(row) for row in established if str(row) in CHAKRA_NATURES]
    elif str(established or "").strip().lower() not in {"", "unknown", "none"}:
        stated = [nature for nature in CHAKRA_NATURES if nature.lower() in str(established).lower()]
    stated = stated or _stated_natures(background)
    if not stated:
        digest = hashlib.sha256(f"{background}|{seed}|chakra-affinity".encode("utf-8")).digest()
        stated = [random.Random(int.from_bytes(digest[:8], "big")).choice(CHAKRA_NATURES)]
    primary = stated[0]
    secondary = stated[1:]
    rates = {nature: (1.35 if nature == primary else 1.15 if nature in secondary else 0.6) for nature in CHAKRA_NATURES}
    return {
        "primary": primary,
        "secondary": secondary,
        "mastered_natures": list(stated),
        "discovery_status": "Known" if _stated_natures(background) or established not in (None, "", "Unknown") else "Latent / not yet tested",
        "learning_rates": rates,
        "native_rule": "Matching elemental jutsu are learned and refined faster, cost less chakra to stabilize, and reach advanced shape transformations more naturally.",
        "off_affinity_rule": "Other basic natures remain learnable, but normally require substantially more time, control, instruction, and repeated practice.",
        "combined_nature_rule": "A combined nature needs the required component natures plus a Kekkei Genkai, equivalent special mechanism, or a world-valid original research route.",
        "external_natures": [],
        "training_evidence": [],
    }


def normalize_chakra_affinity_profile(profile=None, legacy="", background="", seed=""):
    current = copy.deepcopy(profile) if isinstance(profile, dict) else {}
    base = build_chakra_affinity_profile(background, seed, established=(current.get("mastered_natures") if current else legacy))
    for key, value in current.items():
        if value not in (None, "", [], {}):
            base[key] = copy.deepcopy(value)
    primary = base.get("primary") if base.get("primary") in CHAKRA_NATURES else build_chakra_affinity_profile(background, seed, legacy)["primary"]
    base["primary"] = primary
    base["secondary"] = [row for row in base.get("secondary", []) if row in CHAKRA_NATURES and row != primary]
    base["mastered_natures"] = list(dict.fromkeys([primary, *base["secondary"], *[row for row in base.get("mastered_natures", []) if row in CHAKRA_NATURES]]))
    base["learning_rates"] = {nature: float((base.get("learning_rates") or {}).get(nature, 1.35 if nature == primary else 1.15 if nature in base["secondary"] else 0.6)) for nature in CHAKRA_NATURES}
    return base


def jinchuriki_requested(background):
    text = str(background or "").lower()
    return bool(re.search(r"\bjinch[uū]riki\b|\b(?:host|vessel|sealed within me|sealed inside me)\b.{0,35}\b(?:tailed beast|tails?|kurama|shukaku|matatabi|isobu|gy[uū]ki|ch[oō]mei|saiken|koku[oō]|son goku|juubi|j[uū]bi)\b", text))


def _tails_from_text(text, seed=""):
    lowered = str(text or "").lower().replace("-", " ")
    for token, tails in sorted(NAME_TO_TAILS.items(), key=lambda row: len(row[0]), reverse=True):
        if token in lowered:
            return tails
    digest = hashlib.sha256(f"{text}|{seed}|jinchuriki".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big")).choice(tuple(range(1, 10)))


def _mastery_from_text(text):
    lowered = str(text or "").lower()
    if re.search(r"\b(perfect jinch[uū]riki|fully mastered|complete mastery|full cooperation|befriended|perfect sync|total control)\b", lowered):
        return "Perfect Jinchuriki", 100
    if re.search(r"\b(cooperative|friends? with|partnered with|synchronized|controlled transformation|bijuu mode|tailed beast mode)\b", lowered):
        return "Cooperative", 72
    if re.search(r"\b(partial control|training with|can use.{0,35}cloak|first tail|one tail cloak|developing(?: control)?)\b", lowered):
        return "Developing", 38
    return "Unmastered", 8


def build_jinchuriki_profile(background, seed="", legacy=""):
    text = " ".join(str(x or "") for x in (background, legacy)).strip()
    tails = _tails_from_text(text, seed)
    beast = copy.deepcopy(TAILED_BEASTS[tails])
    pending = bool(re.search(r"not yet (?:sealed|completed)|seal not yet|before.{0,30}(?:seal|attack)", text, re.I))
    mastery, control = _mastery_from_text(text)
    if pending:
        mastery, control = "Seal Pending", 0
    mastered = mastery == "Perfect Jinchuriki"
    cooperative = mastery in {"Perfect Jinchuriki", "Cooperative"}
    available = []
    if not pending:
        available.append("Passive access to an abnormally large chakra reserve, limited by the seal and the beast's willingness")
        if mastery in {"Developing", "Cooperative", "Perfect Jinchuriki"}:
            available.extend(["Controlled tailed-beast chakra cloak", "Version 1 transformation", *beast["traits"][:2]])
        if cooperative:
            available.extend(["Version 2 transformation", "Partial transformation", *beast["traits"]])
        if mastered:
            available.extend(["Full tailed-beast transformation", "Tailed Beast Ball", "Tailed-beast chakra sharing and coordinated combat where the beast supports it"])
    drawbacks = list(MASTERED_LIMITS if mastered else UNMASTERED_DRAWBACKS)
    if pending:
        drawbacks = ["The sealing event has not happened yet; the character has no tailed-beast chakra access until it occurs.", *UNMASTERED_DRAWBACKS]
    reserve_multiplier = 1.0 if pending else 1.65 if tails >= 8 else 1.45 if tails >= 4 else 1.35
    if mastered:
        reserve_multiplier += .25
    return {
        "name": f"{beast['name']} Jinchuriki",
        "beast": beast["name"], "title": beast["title"], "tails": tails,
        "status": "Awaiting sealing" if pending else "Sealed host",
        "seal": "Not yet completed" if pending else "Established seal; exact design follows the background and campaign canon",
        "mastery": mastery, "control": control,
        "relationship": "Trusted partnership" if mastered else "Working alliance" if cooperative else "Unstable / undeveloped",
        "nature_transformations": beast["nature"],
        "beast_traits": beast["traits"],
        "canonical_abilities": [*GENERAL_CANON_ABILITIES, *beast["traits"]],
        "available_abilities": list(dict.fromkeys(available)),
        "locked_by_mastery": [ability for ability in [*GENERAL_CANON_ABILITIES, *beast["traits"]] if ability not in available],
        "drawbacks": drawbacks,
        "mastered_drawbacks_removed": list(UNMASTERED_DRAWBACKS) if mastered else [],
        "reserve_multiplier": round(reserve_multiplier, 2),
        "bond_progress": 100 if mastered else 70 if cooperative else 20 if mastery == "Developing" else 0,
        "transformation_stage": "Full Tailed Beast Mode" if mastered else "Version 2 / partial transformation" if cooperative else "Version 1 cloak" if mastery == "Developing" else "Uncontrolled chakra leakage" if not pending else "Unavailable",
        "progression": ["Communicate with the tailed beast as an independent person", "Improve seal knowledge and chakra control", "Survive controlled cloak practice", "Build trust or establish legitimate control", "Achieve coordinated full transformation and Tailed Beast Ball mastery"],
        "independent_beast": True,
        "canon": True,
    }


def normalize_jinchuriki_profile(profile=None, legacy="", background="", seed=""):
    current = copy.deepcopy(profile) if isinstance(profile, dict) else {}
    text = f"{legacy} {background}".strip()
    if not current:
        # A value read from the legacy ``special['Jinchuriki']`` field is
        # already explicit evidence; it often contains only "Nine-Tails
        # (identity concealed)" and therefore has no second host keyword.
        if not str(legacy or "").strip() and not jinchuriki_requested(text) and not re.search(r"(?:tails?|kurama|shukaku|matatabi|isobu|gy[uū]ki|ch[oō]mei|saiken|koku[oō]|son goku).{0,20}(?:seal|host|jinch)", text, re.I):
            return {}
        return build_jinchuriki_profile(text, seed=seed, legacy=legacy)
    beast_text = f"{current.get('beast', '')} {current.get('title', '')} {current.get('tails', '')} {current.get('mastery', '')} {current.get('relationship', '')} {text}"
    base = build_jinchuriki_profile(beast_text, seed=seed, legacy=legacy)
    derived = {"canonical_abilities", "available_abilities", "locked_by_mastery", "drawbacks",
               "mastered_drawbacks_removed", "reserve_multiplier", "transformation_stage"}
    for key, value in current.items():
        if key not in derived and value not in (None, "", [], {}):
            base[key] = copy.deepcopy(value)
    # Preserve story-earned original applications while recomputing the canon
    # mastery gates and drawbacks from the current mastery stage.
    base["available_abilities"] = list(dict.fromkeys([*base["available_abilities"], *current.get("available_abilities", [])]))
    base["locked_by_mastery"] = [row for row in base["canonical_abilities"] if row not in base["available_abilities"]]
    custom_drawbacks = [row for row in current.get("drawbacks", []) if row not in UNMASTERED_DRAWBACKS and row not in MASTERED_LIMITS]
    base["drawbacks"] = list(dict.fromkeys([*base["drawbacks"], *custom_drawbacks]))
    base["independent_beast"] = True
    base["canon"] = True
    return base


def apply_jinchuriki_start(stats, profile):
    """Reflect sealed chakra/vitality without pretending it is jutsu mastery."""
    stats = copy.deepcopy(stats)
    if not isinstance(profile, dict) or profile.get("mastery") == "Seal Pending":
        return stats
    control = int(profile.get("control", 0) or 0)
    if "Willpower" in stats:
        stats["Willpower"] = max(1, int(stats["Willpower"]) + 6 + control // 12)
    if "Chakra Control" in stats:
        # Perfect hosts gain usable control; an unmastered seal creates power
        # without disguising it as technical precision.
        stats["Chakra Control"] = max(1, int(stats["Chakra Control"]) + (12 if control >= 100 else 5 if control >= 70 else 0))
    return stats
