"""Jujutsu Kaisen creation and progression helpers.

The birth slot is deliberately exclusive: one innate technique OR one
Heavenly Restriction. Applications remain ordinary skills so they can be
trained, rolled and displayed without pretending each is a second technique.
"""
from __future__ import annotations

import copy
import hashlib
import random
import re


GRADES = ("Grade 4", "Grade 3", "Grade 2", "Grade 1", "Special Grade")
GRADE_BASELINES = {"Grade 4": 20, "Grade 3": 34, "Grade 2": 52, "Grade 1": 82, "Special Grade": 135}

CONCEPTS = (
    ("Threshold", "Imposes a chosen boundary between two measurable states", "Crossing the declared threshold triggers the stored change"),
    ("Afterimage Ledger", "Records the last movement made inside the user's cursed-energy field", "The recorded movement can be imposed once on a marked target"),
    ("Hollow Measure", "Removes a chosen quantity from one object and preserves it as an invisible measure", "The preserved quantity may be restored to a touched target"),
    ("Faultline Script", "Writes short cursed-energy seams into solid surfaces", "A seam redirects force along its written path when struck"),
    ("Borrowed Silence", "Collects sound that fails to reach the user", "Stored silence can erase a sound or erupt as compressed vibration"),
    ("Pale Orbit", "Binds small objects into cursed-energy orbits around a selected center", "Orbit speed and radius determine impact and defense"),
    ("Witness Mark", "A witnessed action leaves a temporary symbolic mark", "The user may strengthen, delay or interrupt that exact action once"),
    ("Mercy Debt", "Converts deliberately spared harm into cursed-energy credit", "The credit can reinforce protection or healing-like stabilization"),
)

CURSE_SOURCES = (
    ("Fear of abandonment", "a long-limbed figure with empty doorways opening across its body", "isolates targets and turns distance between allies into cursed pressure"),
    ("Fear of public humiliation", "a masked humanoid covered in staring glass eyes", "weaponizes attention, exposure and remembered embarrassment"),
    ("Fear of drowning", "a waterlogged shape whose outline drips upward", "creates crushing pressure and false currents without needing real water"),
    ("Fear of hospitals", "a pale stitched spirit trailing bent instrument-shadows", "distorts pain, diagnosis and the boundary between treatment and injury"),
    ("Fear of being forgotten", "a paper-thin spirit whose features vanish when unobserved", "erodes recognition, names and immediate memory"),
)


def _rng(*parts):
    digest = hashlib.sha256("|".join(str(x or "") for x in parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def is_curse_origin(origin):
    return "sentient cursed spirit" in str(origin or "").lower()


def normalized_grade(value, default="Grade 3"):
    text = str(value or "").strip().title()
    return text if text in GRADES else default


def generate_curse_identity(background, seed=""):
    text = str(background or "").strip()
    chooser = _rng(text, seed, "curse")
    source, form, instinct = chooser.choice(CURSE_SOURCES)
    explicit = re.search(r"(?:born from|curse of|fear of|fear surrounding)\s+([^,.;\n]{3,80})", text, re.I)
    if explicit:
        source = explicit.group(1).strip().rstrip(" ,")
    return {
        "source": source,
        "manifestation": form,
        "instinct": instinct,
        "temperament": "Self-aware; its choices can resist or embrace the instinct that created it.",
        "feeding_rule": "Killing any human can increase power. Victims with greater cursed energy grant exponentially more growth.",
    }


def _background_concept(background):
    text = str(background or "").lower()
    mappings = (
        (("shadow", "dark"), ("Eclipsed Interval", "Stores actions performed while the user is hidden from direct sight", "A stored action can repeat from the nearest connected shadow")),
        (("sound", "music", "voice"), ("Borrowed Silence", "Collects sound that fails to reach the user", "Stored silence can erase a sound or erupt as compressed vibration")),
        (("time", "delay"), ("Deferred Second", "Assigns a short delay to one touched transfer of force", "The delayed force resumes at the declared beat without changing its original direction")),
        (("memory", "forget"), ("Witness Mark", "A witnessed action leaves a temporary symbolic mark", "The user may strengthen, delay or interrupt that exact action once")),
        (("space", "spatial", "distance"), ("Threshold", "Imposes a chosen boundary between two measurable states", "Crossing the declared threshold triggers the stored change")),
        (("blood", "wound"), ("Red Testament", "Cursed energy records the shape and intent of blood the user willingly sheds", "Recorded blood becomes controllable seals, threads or projectiles")),
    )
    for words, concept in mappings:
        if any(word in text for word in words):
            return concept
    return None


def generate_birth_slot(background="", guarantee_strong=False, seed="", force_kind=""):
    text = str(background or "")
    chooser = _rng(text, seed, guarantee_strong, force_kind)
    explicit_hr = bool(re.search(r"heavenly restriction|no cursed energy|zero cursed energy|toji|maki", text, re.I))
    explicit_technique = bool(re.search(r"innate technique|cursed technique|technique that|power to|ability to", text, re.I))
    kind = str(force_kind or "").lower()
    heavenly = kind == "heavenly_restriction" or explicit_hr or (not explicit_technique and chooser.random() < .16)
    if heavenly:
        total_loss = bool(re.search(r"no cursed energy|zero cursed energy|complete heavenly restriction", text, re.I)) or (guarantee_strong and chooser.random() < .62)
        return {
            "slot_type": "Heavenly Restriction", "name": "Heavenly Restriction — Liberated Body" if total_loss else "Heavenly Restriction — Bound Reservoir",
            "governing_rule": "Cursed-energy capacity is exchanged at birth for physical perception, strength, speed, resilience and bodily efficiency.",
            "sacrifice": "Cursed Energy Reserves and Output are effectively zero" if total_loss else "Severely reduced Cursed Energy Reserves and Output",
            "enhancement": "An overwhelmingly enhanced body capable of perceiving and combating curses through sharpened senses and cursed tools." if total_loss else "Exceptional physical ability and senses far beyond sorcerers of similar experience.",
            "activation": "Always active; this is the body's condition, not a technique.", "applications": [],
            "limitations": "Cannot use an innate cursed technique. Barriers and cursed-energy arts requiring personal output are unavailable or extremely limited." if total_loss else "Has no innate technique and must ration a very small cursed-energy pool.",
            "weaknesses": "No unique exploitable weakness beyond the sacrificed cursed-energy options; injury, exhaustion, superior force and suitable enemy techniques still matter.",
            "growth_path": "Condition the body, master cursed tools, sharpen perception and develop tactics that exploit freedom from ordinary cursed-energy assumptions.",
            "power_grade": "Exceptional" if guarantee_strong else "High potential", "overwhelming": bool(guarantee_strong), "no_inherent_weakness": False,
            "stat_modifiers": {"Physical Ability": 95 if total_loss else 55, "Speed & Reflexes": 80 if total_loss else 45, "Soul Stability": 35, "Cursed Energy Reserves": -999 if total_loss else -28, "Cursed Energy Output": -999 if total_loss else -24},
        }
    name, rule, application_rule = _background_concept(text) or chooser.choice(CONCEPTS)
    overwhelming = bool(guarantee_strong or re.search(r"overwhelming|godlike|limitless|strongest|immeasurable", text, re.I))
    no_weakness = bool(re.search(r"no weakness|without weakness|unconditional", text, re.I))
    applications = [
        {"name": f"{name}: First Application", "effect": application_rule, "limitation": "Requires the technique's rule, a valid target and controlled cursed-energy output."},
        {"name": f"{name}: Reinforced Application", "effect": f"Pushes {application_rule[:1].lower() + application_rule[1:]} across a larger or more forceful target.", "limitation": "Costs substantially more cursed energy and precision than the first application."},
    ]
    return {
        "slot_type":"Innate Cursed Technique", "name":name, "governing_rule":rule,
        "activation":"The user deliberately channels cursed energy through the governing rule; gestures or words may improve control but are not mandatory unless established in play.",
        "targets":"Self, touched targets or targets inside the user's controlled cursed-energy reach, depending on the application.",
        "applications":applications,
        "limitations":"No special built-in limitation beyond cursed-energy cost, output, control, range and comprehension." if overwhelming else "The governing rule cannot create effects unrelated to its concept; scale and simultaneous targets increase cost sharply.",
        "weaknesses":"No inherent technique-specific weakness. It is still limited by the user's energy, output, control and ability to satisfy activation." if no_weakness else "Opponents can exploit incomplete information, range, setup, divided attention, depleted cursed energy or a more favorable technique interaction.",
        "growth_path":"Invent and master additional applications, improve efficiency and interpretation, then pursue a maximum technique or domain that expresses the same rule.",
        "domain_potential":f"A future domain could make the central rule of {name} unavoidable within a completed barrier.",
        "power_grade":"Overwhelming" if overwhelming else "Setting-comparable", "overwhelming":overwhelming, "no_inherent_weakness":no_weakness,
        "stat_modifiers":{"Cursed Energy Reserves":30 if overwhelming else 8,"Cursed Energy Output":36 if overwhelming else 10,"Cursed Energy Control":20 if overwhelming else 6,"Jujutsu Insight":18 if overwhelming else 5},
    }


def apply_birth_slot(profile, slot, curse_grade=""):
    profile = copy.deepcopy(profile)
    stats = profile.setdefault("stats", {})
    if curse_grade:
        baseline = GRADE_BASELINES[normalized_grade(curse_grade)]
        for stat in stats:
            stats[stat] = max(int(stats[stat]), baseline + (8 if "Cursed Energy" in stat else 0))
    for stat, amount in (slot.get("stat_modifiers") or {}).items():
        if stat not in stats:
            continue
        stats[stat] = 1 if amount <= -900 else max(1, int(stats.get(stat, 1)) + int(amount))
    skills = profile.setdefault("skills", {})
    for row in slot.get("applications", [])[:3]:
        skills[row["name"]] = {"rank":"Technique Application", "bonus":9 if slot.get("overwhelming") else 6,
            "description":row["effect"], "effect":row["effect"], "limitation":row.get("limitation", ""),
            "growth_path":slot.get("growth_path", ""), "parent_technique":slot.get("name", ""),
            "combat_usable":True, "effect_type":"utility", "category":"cursed technique"}
    profile["jjk_birth_slot"] = slot
    return profile


def initialize_jjk_state(state, slot, origin, curse_grade="", curse_identity=None):
    special = state.setdefault("special", {})
    is_curse = is_curse_origin(origin)
    grade = normalized_grade(curse_grade, "Grade 3") if is_curse else str(special.get("Grade") or "Unassessed")
    special.update({"Birth Slot":slot["slot_type"], "Innate Technique":slot["name"] if slot["slot_type"] == "Innate Cursed Technique" else "None",
                    "Heavenly Restriction":slot["name"] if slot["slot_type"] == "Heavenly Restriction" else "None", "Grade":grade})
    profile_key = ("Innate Technique Profile" if slot["slot_type"] == "Innate Cursed Technique"
                   else "Heavenly Restriction Profile" if slot["slot_type"] == "Heavenly Restriction"
                   else "Birth Slot Profile")
    special[profile_key] = copy.deepcopy(slot)
    state["jjk_system"] = {"birth_slot":copy.deepcopy(slot), "grade":grade, "official_status":"Unregistered" if is_curse else "Student / unaffiliated",
        "curse_identity":copy.deepcopy(curse_identity or {}), "humans_killed":0, "feeding_growth":0, "black_flash_count":0,
        "binding_vows":[], "barrier_mastery":"Foundational", "domain_status":"Unachieved", "reverse_cursed_technique":"Unachieved"}
    if is_curse:
        special["Cursed Spirit Nature"] = copy.deepcopy(curse_identity or {})


def feeding_growth_for_target(target_kind):
    text = str(target_kind or "ordinary human").lower()
    if "special grade" in text: return 220
    if "grade 1" in text: return 85
    if "grade 2" in text: return 34
    if "grade 3" in text: return 13
    if "grade 4" in text or "sorcerer" in text: return 6
    return 1
