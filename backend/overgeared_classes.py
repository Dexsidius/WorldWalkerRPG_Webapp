"""Canon-informed Satisfy class design without turning every turn into lore bloat.

The catalog is names-only design precedent gathered from the Overgeared class
index.  It is supplied to the model only when a class is actually being
created or transformed.  Ordinary turns use the compact family rules below.
"""
from __future__ import annotations

import re


# Excludes wiki administration/template pages.  Keep the broad and strange
# entries: the point is to teach the generator that Satisfy supports far more
# than blacksmiths and ordinary combat jobs.
CANON_CLASS_NAMES = tuple(x.strip() for x in """
Accessory Maker
Acrobat
Alchemist
Apostle of Justice's Partner
Archer
Architect
Artisan
Assassin
Asura
Aura Master
Baal's Contractor
Beast Master
Beginner
Beriache's Knight
Beriache's Warrior
Berserker
Black Knight (Yatan Church)
Black Magician
Blacksmith
Blood Warrior
Blue Sky Rider
Bow Saint
Braham's Descendant
Builder
Chef
Cleaner
Commander
Construction Worker
Contractor Freed From Baal's Curse
Crusher
Dancing Death Knight Who Speaks Ancient Languages
Dancing Lich Who Distorts Space
Dark Magician
Dark Sorcerer
Death God
Debirion's Envoy
Demon Slayer
Demon World Noble
Destroyer Skeleton Clown
Destroyer Skeleton Dancer
Destroyer Skeleton Dancing Smith
Destroyer Skeleton Miner
Destroyer Skeleton Swordsman
Destruction Warrior
Doctor
Dragon Slayer
Duke of Wisdom
Dungeon Maker
Duplicator
Explosion Sorcerer
Farmer
Fire Magician
Fisherman
Flow Master
Goddess' Agent
Great Magician
Guardian Knight
Guardian of Light
Gunman
Hidden Sword
Ice Mystic
Illusionist
Impregnable Fortress
Knight
Legendary Assassin
Legendary Blacksmith
Legendary Farmer
Legendary Great Magician
Legendary Knight
Legendary Martial Artist
Legendary Painter
Legendary Scientist
Legendary Spearman
Legendary Tailor
Lightning Swordsman
Linker
Magic Spearman
Magic Swordsman
Magic Swordsman of the Epics
Magician
Martial Artist
Martial God Follower
Master of Swiftness
Master of the Flow
Merchant
Miner
Mixed Magician
Monk
Monster Discerner
Mumud's Successor
Necromancer
Orator
Overgeared God
Overgeared God Church's Messenger
Pagma's Successor
Painter
Paladin
Pet Master
Povia's Successor
Priest (Rebecca Church)
Prince
Qigong Master
Quick Draw Swordsman
Red Flame Archer
Red Sage
Restorer Skeleton Clown
Restorer Skeleton Dancer
Restorer Skeleton Dancing Smith
Restorer Skeleton Mage
Restorer Skeleton Miner
Rider
Saintess
Saintess' Knight
Saurabi
Scholar
Scientist
Sculptor
Shadow Master
Shadow Master's Student
Skeleton Bishop
Skeleton Dancer
Skeleton Destroyer
Skeleton Miner
Skeleton Restorer
Skeleton Sword Dancer
Skin Maker
Soldier
Soul Predator
Spear Knight
Spearman
Spiritualist
Steel Farmer
Storm Magician
Summoner
Sword Saint
Swordsman
Tactician
Tailor
Thief
Tyrant
War Commander
Warrior
White Swordsman
Wind Magician
Woodcutter
""".strip().splitlines())


CLASS_DESIGN_FAMILIES = {
    "Martial and weapon": "warriors, knights, martial artists, weapon specialists, riders, saints and growth-type successors",
    "Magic and supernatural": "elemental magicians, mystics, necromancers, spiritualists, illusionists and mixed magic paths",
    "Support and faith": "priests, healers, guardians, envoys, linkers, doctors and party-enabling specialists",
    "Command and society": "commanders, tacticians, nobles, merchants, orators, guild leaders and territorial rulers",
    "Companions and control": "summoners, pet masters, beast masters, contractors and minion-development paths",
    "Exploration and utility": "thieves, acrobats, monster discerners, scholars, fishermen and unusual condition-based jobs",
    "Production and creation": "blacksmiths, tailors, alchemists, architects, builders, artists, farmers, miners and scientists",
    "Hybrid and transformational": "magic swordsmen, production-combat hybrids, evolving classes, successors and classes born from exceptional deeds",
}


def infer_class_type(*values):
    text = " ".join(str(v or "") for v in values).lower()
    production = r"blacksmith|smith|craft|artific|tailor|alchem|architect|build|farmer|miner|paint|sculpt|chef|scient|maker|woodcut|production|wright"
    support = r"saintess|priest|healer|doctor|support|guardian|linker|envoy|messenger|restore|bishop"
    command = r"commander|tactician|prince|duke|noble|merchant|orator|leader|lord|king|guild|govern"
    magic = r"magic|magician|sorcer|mystic|necrom|spiritual|illusion|sage|caster|spell|element"
    companion = r"summon|pet master|beast master|contractor|minion|skeleton"
    utility = r"thief|acrobat|discerner|scholar|fisher|cleaner|duplicator|tracker|scout|explor"
    martial = r"warrior|knight|sword|spear|archer|assassin|martial|monk|gunman|crusher|rider|fighter|tank|paladin|berserker"
    matches = []
    for label, pattern in (("Production", production), ("Support", support),
                           ("Command / Social", command), ("Magic", magic),
                           ("Companion / Summoning", companion),
                           ("Exploration / Utility", utility), ("Combat", martial)):
        if re.search(pattern, text, re.I):
            matches.append(label)
    if len(matches) > 1:
        return "Hybrid: " + " + ".join(matches[:2])
    return matches[0] if matches else "Adventuring / Flexible"


def canon_class_prompt_reference():
    """Detailed reference used only during class authorship, not normal turns."""
    families = "; ".join(f"{name}: {detail}" for name, detail in CLASS_DESIGN_FAMILIES.items())
    names = ", ".join(CANON_CLASS_NAMES)
    return (
        "Satisfy class design families: " + families + ".\n"
        "Complete canon class-name precedent catalog (design inspiration only): " + names + ".\n"
        "Study the full range and structural variety, but do not copy a canon class, its signature mechanics, "
        "or acquisition story unless the player explicitly chose that canon class. Create a new class whose "
        "identity, rarity, features, limitations, quests, and evolution fit this character. Production is optional. "
        "Do not force crafting onto a combat, magic, support, command, social, summoning, or exploration concept."
    )


COMPACT_CLASS_GENERATION_RULE = (
    "Satisfy supports combat, weapon, magic, faith/support, command/social, companion/summoning, exploration/utility, "
    "production, and unusual hybrid or growth-type classes. Generated classes may combine these when the background "
    "supports it. Give every original class a distinct playstyle, class type, rarity, 2-4 coherent features, a named "
    "signature skill, limitations, class quests, advancement conditions, and later specializations. Crafting is never "
    "assumed unless the character actually follows a production path."
)
