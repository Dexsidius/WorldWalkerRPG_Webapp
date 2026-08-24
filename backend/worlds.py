"""Static world/game data: ported 1:1 from the original Tkinter build's
WORLD_DATA / WORLD_EXPANSIONS / DIFFICULTIES / BASE_STATE so campaign
mechanics and AI prompt schemas stay identical."""
import datetime

DEFAULT_MODEL = "gpt-5.6-luna"
SECONDARY_MODEL = "gpt-4o-mini"
APP_VERSION = "2.6.33"
APP_NAME = "Worldwalker RPG"

DIFFICULTIES = {
    "Story": {"difficulty_shift": -15, "dc_shift": -3, "enemy_edge": -2, "death": "rare", "freedom": "very high",
              "description": "Heroic d100 play with generous odds and frequent recovery. Death is rare unless you deliberately embrace lethal danger."},
    "Adventurer": {"difficulty_shift": -6, "dc_shift": 0, "enemy_edge": 0, "death": "possible", "freedom": "high",
                   "description": "Fair d100 play. Relevant training and titles noticeably improve the odds without making danger meaningless."},
    "Veteran": {"difficulty_shift": 5, "dc_shift": 3, "enemy_edge": 2, "death": "likely", "freedom": "high",
                "description": "Demanding d100 checks, capable opposition, resource pressure, and meaningful risk of death."},
    "Nightmare": {"difficulty_shift": 15, "dc_shift": 6, "enemy_edge": 4, "death": "severe", "freedom": "total",
                  "description": "Brutal simulation. Contextual difficulties are much higher and fatal mistakes are common."},
}

# The Tower of Trials — Solo Max-Level Newbie's 50-floor structure, sourced
# from a canon-inspired floor map the user supplied. Each entry is the
# floor's real internal name/theme, used to keep the GM's choice of
# monsters/factions per floor canon-consistent (murim floors get martial
# sects, workshop floors get golems and empires, and so on) — but the
# PLAYER only ever sees "Floor N" (see tower_floor_display / map below);
# the theme is GM-context only, never surfaced as the location label.
TOWER_FLOOR_THEMES = [
    ("Hapjeong Station", "Opening Survival"), ("Mangrove, Tree of Greed", "Carnivorous Forest"),
    ("Goblin Warrens", "First Hunt"), ("Poison Swamp", "Venom and Traps"),
    ("Ruined Temple", "Relic Puzzle"), ("Underground Aqueduct", "Water Beasts"),
    ("Beast Colosseum", "Strength Trial"), ("Cursed Catacombs", "Undead Ambush"),
    ("Mirror Passage", "Illusion Trial"), ("Orc Stronghold", "Siege Test"),
    ("Desecrated Chapel", "Curse Rite"), ("Frozen Rift", "Endurance Trial"),
    ("Lava Crossing", "Flames of Trial"), ("Alchemist's Lab", "Mutant Experiments"),
    ("Library of Records", "Knowledge Trial"), ("Assassin's Alley", "Silent Killers"),
    ("Phantom Ballroom", "Hallucination Zone"), ("Clockwork Workshop", "Golems and Gears"),
    ("Hidden Place", "Ruined Cave Labyrinth"), ("Murim Gate", "Jianghu Opens"),
    ("Beggar Sect Streets", "Espionage Web"), ("Poison Valley", "Venom Masters"),
    ("Shaolin Grounds", "Discipline Trial"), ("Mount Hua Paths", "Sword Sect Ordeal"),
    ("Namgung Arena", "Duel of Clans"), ("Demonic Cult Border", "Blood and Ambush"),
    ("Black Market of Jianghu", "Schemes and Trade"), ("Murim Battlefield", "Clash of Sects"),
    ("Heavenly Demon Ascent", "Murim Endgame"), ("Workshop Battle", "Tournament of Relics"),
    ("Imperial Frontier", "War on the March"), ("Arcane Academy", "Magic Examination"),
    ("Noble District", "Court Conspiracy"), ("Spirit Catacombs", "Ancient Capital Depths"),
    ("Knight Order Barracks", "Chivalric Trial"), ("Imperial Palace", "Audience with the Throne"),
    ("Magic Tower", "High Sorcery"), ("Rebellion Front", "Empire in Flames"),
    ("Abyssal Gate", "Rift to the Lower Dark"), ("Ancient Throne", "Demon Monarch's Court"),
    ("Ancient Archive", "Forgotten Histories"), ("Titan Graveyard", "Colossi of the Past"),
    ("Celestial Observatory", "Stars and Prophecy"), ("World Tree Canopy", "Ancient Spirit Realm"),
    ("Void Corridor", "Nothingness Trial"), ("Guardian Sanctuary", "Keepers of the Summit"),
    ("Divine Mechanism Chamber", "Clockwork Heaven"), ("Administrator's Garden", "Realm of the Overseers"),
    ("Final Ascent", "Path to the Apex"), ("Top of the Tower", "Destia and the Last Trial"),
]
TOWER_FLOOR_COUNT = len(TOWER_FLOOR_THEMES)


def tower_floor_theme(floor):
    """The internal canon name/theme for a floor (GM context only, 1-indexed)."""
    idx = max(1, min(TOWER_FLOOR_COUNT, int(floor or 1))) - 1
    name, theme = TOWER_FLOOR_THEMES[idx]
    return f"{name} — {theme}"


def _tower_tier(floor):
    if floor <= 19: return 2 + floor // 7
    if floor <= 29: return 5
    if floor <= 40: return 6 if floor <= 35 else 7
    if floor <= 45: return 8
    return 9 if floor <= 49 else 10


# Ecological "band" identity per tier — each is a distinct, internally
# consistent biome of threat logic and environmental behavior that must not
# bleed into neighboring bands. Compressed from an 11-band/100+-floor
# generic Tower framework down to this Tower's real 9-tier/50-floor
# structure (floor 50 is the canon-established top of THIS Tower), so the
# escalation curve still completes by the true final floor instead of
# treating floor 50 as merely "mid-tier" the way the uncompressed framework
# would.
_TOWER_BANDS = {
    2: ("Initial Survival", "unstable, partially degraded systems; low-level anomalies and reactive hazards that respond directly to presence and noise"),
    3: ("Adaptive Response", "more structured, semi-self-regulating surroundings; coordinated threats and environmental traps that begin predicting simple behavior patterns"),
    4: ("Structured Hunting", "organized predators with group intelligence and territorial systems; survival requires strategy, not just reaction"),
    5: ("Systemic Complexity", "layered, multi-condition hazards; engineered systems and hybrid threats where the environment itself turns adversarial"),
    6: ("Predictive Ecosystem", "a responsive, semi-adaptive layout where entities learn and counter the player's own patterns across repeated encounters"),
    7: ("Fractured Reality", "localized, bounded instability in physical law and perception — logic bends but every shift must stay traceable within Tower rules, never arbitrary"),
    8: ("Pre-Transition / High Ecosystem", "elite variants of earlier threats and multi-domain coordination; cross-system interaction and layered, sometimes indirect conflict"),
    9: ("Advanced Anomaly", "high-tier anomalies bound by specific, discoverable rules; exceptions exist but are never lawless, and system-breaking attempts are contained and structured"),
    10: ("Final Ascent / Upper System", "apex, overseer-caliber entities operating with near-complete awareness of the Tower's own rules; foundational Tower logic is partially exposed here but never fully broken"),
}


def tower_band(floor):
    """(band_name, ecology_summary) for the ecological band this floor's
    tier belongs to — GM context only, same non-player-facing status as
    tower_floor_theme()."""
    return _TOWER_BANDS.get(_tower_tier(max(1, min(TOWER_FLOOR_COUNT, int(floor or 1)))), _TOWER_BANDS[2])


def _tower_map_nodes():
    """Player-facing map nodes for all 50 floors — deliberately just 'Floor
    N', never the internal theme name (see TOWER_FLOOR_THEMES)."""
    nodes = [("Earth — Tower Entrance", 50, 96, "hub", 1)]
    for floor in range(1, TOWER_FLOOR_COUNT + 1):
        x = 42 if floor % 2 == 0 else 58
        y = round(90 - (floor - 1) * (86 / (TOWER_FLOOR_COUNT - 1)), 1)
        nodes.append((f"Floor {floor}", x, y, "floor", _tower_tier(floor)))
    return nodes


WORLD_DATA = {
    "One Piece": {
        "tagline": "Pirates, Marines, Haki, Devil Fruits, crews, bounties, and a living sea.",
        "resource": "Stamina",
        "progression": ["Level","XP","Haki","Combat Style","Bounty","Crew","Reputation","Titles"],
        "rules": "Honor One Piece world logic. Islands and seas matter. Marines, pirates, kingdoms and crews pursue their own motives. Devil Fruits are unique. Haki requires plausible awakening/training. Bounties respond to notoriety and government threat assessment. Canon may diverge permanently.",
        "start": "Foosha Village",
        "factions": {"Marines": 0, "World Government": 0, "Revolutionary Army": 0, "Pirates": 0},
        "map": [
            ("Foosha Village",12,70,"settlement",1), ("Goa Kingdom",20,64,"kingdom",2),
            ("Shells Town",30,74,"marine",2), ("Orange Town",38,65,"settlement",2),
            ("Syrup Village",46,73,"settlement",2), ("Baratie",56,63,"sea",3),
            ("Arlong Park",68,72,"enemy",4), ("Loguetown",78,61,"city",4),
            ("Reverse Mountain",86,51,"landmark",5), ("Whiskey Peak",72,42,"island",5),
            ("Little Garden",61,35,"island",6), ("Alabasta",50,44,"kingdom",7),
            ("Jaya",41,31,"island",7), ("Skypiea",38,17,"sky",8),
            ("Water 7",29,32,"city",8), ("Enies Lobby",20,24,"government",9),
            ("Sabaody",15,13,"archipelago",10), ("New World",78,17,"region",12)
        ],
        "special": {"Haki":{"Observation":0,"Armament":0,"Conqueror":0}, "Bounty":0, "Devil Fruit":"None", "Crew":"None"}
    },
    "Hunter x Hunter": {
        "tagline": "Hunters, Nen, dangerous exams, criminal underworlds, and unexplored frontiers.",
        "resource": "Aura",
        "progression": ["Level","XP","Aura","Nen","Hatsu","Hunter Status","Reputation","Titles"],
        "rules": "Honor Hunter x Hunter logic. Nen is not casually known by ordinary people and must be learned plausibly. Track Ten, Zetsu, Ren, Hatsu, aura and Nen category only after discovery. Vows and limitations can create power with real costs. Hunters, mafia, assassins and the Association act independently.",
        "start": "Yorknew City",
        "factions": {"Hunter Association":0,"Yorknew Mafia":0,"Phantom Troupe":0,"Zoldyck Family":0},
        "map": [
            ("Yorknew City",45,55,"city",4), ("Kukuroo Mountain",22,36,"estate",7),
            ("Whale Island",74,70,"island",1), ("Hunter Exam Site",60,62,"exam",3),
            ("Heavens Arena",58,38,"arena",6), ("Meteor City",18,62,"city",8),
            ("Greed Island",78,42,"island",9), ("NGL",70,22,"region",10),
            ("East Gorteau",55,16,"nation",11), ("Hunter Association HQ",37,23,"hq",7),
            ("Dark Continent Route",16,12,"frontier",15)
        ],
        "special": {"Nen Category":"Unknown","Ten":0,"Zetsu":0,"Ren":0,"Hatsu":"Undeveloped","Aura Control":0}
    },
    "Naruto": {
        "tagline": "Shinobi villages, chakra, missions, bloodlines, rival nations, and hidden techniques.",
        "resource": "Chakra",
        "progression": ["Level","XP","Chakra","Jutsu","Rank","Village Reputation","Titles"],
        "rules": "Honor Naruto world logic. Chakra, elemental affinities, clan techniques, ranks, missions and village politics matter. Jutsu require training, inheritance, instruction or legitimate copying conditions. Powerful bloodlines are rare. Villages remember betrayal, service and classified knowledge.",
        "start": "Konohagakure",
        "factions": {"Konohagakure":0,"Sunagakure":0,"Kirigakure":0,"Kumogakure":0,"Iwagakure":0},
        # Coordinates calibrated against a manga-sourced "Naruto World" map
        # (player-supplied) now used as this world's map background — most
        # placements are the confirmed canon locations from that reference,
        # not a generic/approximate layout. Iron Country and Forest of Death
        # aren't confirmed on that specific map (it flags Iron Country as
        # guesswork itself), so both use a reasonable nearby placement.
        "map": [
            ("Konohagakure",41,59,"village",3), ("Land of Fire",44,52,"region",2),
            ("Sunagakure",24,72,"village",5), ("Kirigakure",87,64,"village",6),
            ("Kumogakure",64,24,"village",7), ("Iwagakure",24,23,"village",7),
            ("Valley of the End",44,44,"landmark",6), ("Forest of Death",46,62,"training",5),
            ("Land of Waves",40,89,"region",4), ("Amegakure",32,56,"village",8),
            ("Iron Country",56,32,"nation",8)
        ],
        "special": {"Shinobi Rank":"Civilian","Nature Affinity":"Unknown","Chakra Control":0,"Known Jutsu":[],"Clan":"None"}
    },
    "Solo Max-Level Newbie": {
        "tagline": "Tower floors, hidden quests, achievements, copied abilities, artifacts, and exploitable secrets.",
        "resource": "Mana",
        "progression": ["Level","XP","Stats","Skills","Copied Abilities","Titles","Artifacts","Hidden Quests"],
        "rules": "Use Tower-progression logic inspired by Solo Max-Level Newbie. Floors have scenarios, administrators, hidden conditions, achievements, monsters, bosses and secret rewards. Clever foreknowledge can create enormous advantages when the player actually possesses or discovers it. System rewards must be explicit.",
        "start": "Earth — Tower Entrance",
        "factions": {"Players":0,"Major Guilds":0,"Tower Administrators":0,"Demons":0},
        "map": _tower_map_nodes(),
        "special": {"Unspent Stat Points":0,"Copied Abilities":[],"Achievements":[],"Floor":0,"Hidden Conditions Found":0}
    },
    "Overgeared": {
        "tagline": "Classes, hidden classes, crafting, legendary equipment, NPC affinity, guild politics, and Satisfy.",
        "resource": "Mana",
        "progression": ["Level","XP","Class","Stats","Skills","Crafting","Affinity","Reputation","Titles"],
        "rules": "Use an Overgeared-style VRMMO framework. Classes, hidden classes, item ratings, crafting proficiency, NPC affinity, guilds, kingdoms, quests and player competition matter. Exceptional equipment changes power substantially. NPCs are persistent people with memories and interests.",
        "start": "Winston",
        "factions": {"Players":0,"Local Lords":0,"Church":0,"Guilds":0,"Kingdom":0},
        "map": [
            ("Winston",22,65,"city",2), ("Patrian",38,58,"city",4), ("Reidan",52,68,"city",6),
            ("Bairan",34,42,"city",5), ("Titan",58,42,"capital",8), ("Frontier",78,60,"region",8),
            ("Saharan Empire",70,27,"empire",10), ("Northern Frontier",40,20,"region",10)
        ],
        "special": {"Class":"Beginner","Secondary Class":"None","Crafting Mastery":0,"Guild":"None","NPC Affinity":{}}
    },
    "Reincarnated as a Slime": {
        "tagline": "Magicules, named skills, monster evolution, demon lords, and a newborn nation in the Great Jura Forest.",
        "resource": "Magicule",
        "progression": ["Level","XP","Magicule Capacity","Named Skills","Evolution Stage","Reputation","Titles"],
        "rules": "Honor Tensura world logic. Magicules fuel skills and evolution. Named/Unique/Ultimate Skills are rare and earned through insight, naming, or extraordinary circumstance — never handed out casually. Monsters and demi-humans have species-based traits; evolution requires a genuine trigger (naming, mass magicule intake, a true crisis, or a Demon Lord's Seed/Awakening). Analytical skills akin to Great Sage, if present, must be foreshadowed and earned. Human kingdoms, demon lords and monster nations pursue independent agendas.",
        "start": "Great Jura Forest",
        "factions": {"Jura Forest Monsters": 0, "Kingdom of Falmuth": 0, "Demon Lords": 0, "Free Guild": 0},
        "map": [
            ("Great Jura Forest",50,60,"forest",1), ("Goblin Village",42,55,"settlement",2),
            ("Blumund",78,60,"town",2), ("Kingdom of Falmuth",70,78,"kingdom",3),
            ("Dwargon",30,40,"nation",5), ("Sorcerous Dynasty of Thalion",20,25,"nation",6),
            ("Demon Lord's Domain",65,20,"territory",8), ("Tempest",50,58,"nation",10)
        ],
        "special": {"Named Skills":[], "Evolution Stage":"Unnamed", "Magicule Capacity":0, "Species":"Unknown"}
    },
    "Custom World": {
        "tagline": "A freeform world defined by you.",
        "resource": "Energy",
        "progression": ["Level","XP","Stats","Skills","Inventory","Reputation","Titles"],
        "rules": "Use the player's custom setting as the source of truth. Maintain internal consistency, persistent NPC motives, meaningful geography and consequences.",
        "start": "Starting Region",
        "factions": {"Local Faction":0},
        "map": [("Starting Region",50,55,"region",1),("Northern Reach",50,20,"region",4),("Western March",20,50,"region",4),("Eastern Reach",80,50,"region",4),("Southern Wilds",50,82,"region",5)],
        "special": {}
    }
}

# Relative canon calendars. Most source worlds do not publish a consistent
# Gregorian date for every arc, so Canon Day 0 is the honest, deterministic
# anchor: the main protagonist's story begins then. Campaigns start shortly
# before it and these events become world pressures, not immutable rails.
CANON_TIMELINES = {
    "One Piece": {"start_day": -7, "anchor": "Seven days before Luffy leaves Foosha Village", "events": [
        # Day numbers below are calibrated against The Library of Ohara's
        # One Piece Timeline (V5.0, through chapter 1103), converted from its
        # real Gregorian-style Kaienreki dates into day-offsets from Luffy's
        # departure (day 0), which this world already anchors its calendar
        # to. Pre-departure history is flagged historical_only — it exists
        # for CANON HISTORY context only and predates every playable start.
        {"major": False, "historical_only": True, "day": -7799, "title": "Gol D. Roger's execution", "location": "Loguetown", "summary": "Roger is executed at Loguetown, his final words sending the world into the Great Pirate Era in search of the One Piece."},
        {"major": False, "historical_only": True, "day": -7331, "title": "Portgas D. Ace is born", "location": "South Blue", "summary": "Ace is born to Roger and Portgas D. Rouge, who dies shortly after giving birth; Garp takes the infant into Dadan's care."},
        {"major": False, "historical_only": True, "day": -7180, "title": "The Ohara Incident", "location": "Ohara", "summary": "The World Government orders a Buster Call on Ohara after learning its scholars are researching the Poneglyphs; Nico Robin survives as the island's last scholar."},
        {"major": False, "historical_only": True, "day": -6450, "title": "The execution of Kozuki Oden", "location": "Wano — Onigashima", "summary": "Kaido executes Kozuki Oden by boiling after his attack fails; Oden's retainers are sent twenty years into the future to one day open Wano's borders."},
        {"major": False, "historical_only": True, "day": -6112, "title": "Monkey D. Luffy is born", "location": "East Blue", "summary": "Monkey D. Luffy is born, the son of revolutionary Monkey D. Dragon and grandson of Marine hero Monkey D. Garp."},
        {"major": False, "historical_only": True, "day": -3530, "title": "Fisher Tiger's death", "location": "Fish-Man Island", "summary": "Fisher Tiger, who once freed thousands of slaves from Mary Geoise, is killed by Marines after refusing to spill human blood."},
        {"major": False, "historical_only": True, "day": -975, "title": "Ace joins the Whitebeard Pirates", "location": "New World", "summary": "After years pursuing him, Ace is defeated by Whitebeard and joins his crew, eventually becoming Second Division Commander."},
        {"major": False, "historical_only": True, "day": -123, "title": "Marshall D. Teach betrays the Whitebeard Pirates", "location": "New World", "summary": "Teach murders his crewmate Thatch to steal the Yami Yami no Mi, then leaves to form the Blackbeard Pirates — setting Ace on his pursuit."},
        {"day": 0, "title": "Luffy leaves Foosha Village", "location": "Foosha Village", "summary": "Seventeen-year-old Monkey D. Luffy sets out alone to become King of the Pirates, beginning the East Blue voyage."},
        {"major": False, "day": 2, "title": "Shells Town upheaval", "location": "Shells Town", "summary": "Roronoa Zoro is freed and Captain Morgan and his son Helmeppo are overthrown, ending the base's corrupt rule; Zoro joins Luffy."},
        {"major": False, "day": 5, "title": "Orange Town crisis", "location": "Orange Town", "summary": "Buggy the Clown's pirates are defeated; Nami temporarily allies with the crew."},
        {"major": False, "day": 10, "title": "Syrup Village conspiracy", "location": "Syrup Village", "summary": "Captain Kuro's plot against Kaya is exposed and defeated."},
        {"major": False, "day": 11, "title": "Kaya's decision and the Going Merry", "location": "Syrup Village", "summary": "Kaya, newly free of Kuro's manipulation, gives Usopp and the crew the ship that becomes the Going Merry; Usopp joins."},
        {"day": 13, "title": "Baratie conflict", "location": "Baratie", "summary": "Don Krieg's armada is repelled at the floating restaurant; Sanji joins the crew and Dracule Mihawk marks Zoro as a rival worth surviving for."},
        {"day": 14, "title": "Arlong Park revolt", "location": "Arlong Park", "summary": "Arlong is defeated and Cocoyasi Village is freed; Nami formally joins the crew."},
        {"major": False, "day": 17, "title": "Loguetown and the first bounty", "location": "Loguetown", "summary": "Luffy is nearly executed in the same square where Gold Roger died, crosses paths with the revolutionary Dragon, and receives his first bounty as the crew departs for the Grand Line."},
        {"major": False, "day": 17, "title": "Reverse Mountain and Laboon's promise", "location": "Reverse Mountain", "summary": "The crew crosses into the Grand Line proper via Reverse Mountain, and Luffy promises the whale Laboon they'll return for a rematch after circling the world."},
        {"major": False, "day": 18, "title": "Little Garden and Vivi's true identity", "location": "Little Garden", "summary": "The crew befriends the giants Dorry and Brogy, and Vivi is revealed as Alabasta's princess, secretly infiltrating Baroque Works from within."},
        {"day": 20, "title": "Drum Island — Chopper joins", "location": "Drum Island", "summary": "Wapol's tyranny is overthrown with Dr. Kureha's help, and the reindeer doctor Tony Tony Chopper joins the crew."},
        {"day": 31, "title": "Operation Utopia and Crocodile's defeat", "location": "Alabasta — Alubarna", "summary": "Crocodile's plot to seize the kingdom through civil war is exposed and defeated; Vivi's homeland is saved, though she stays behind rather than continue the voyage."},
        {"day": 36, "title": "Skypiea's golden bell rings", "location": "Skypiea", "summary": "The self-proclaimed god Enel is defeated and driven from Skypiea; the ancient bell of Shandora is rung for the whole world to hear, ending a four-century war."},
        {"major": False, "day": 45, "title": "Water 7 — the search for Robin", "location": "Water 7", "summary": "Nico Robin's history as Ohara's last scholar and the government's fear of the Rio Poneglyph begin surfacing as CP9 closes in."},
        {"day": 47, "title": "Enies Lobby raid — war on the World Government", "location": "Enies Lobby", "summary": "The crew storms the Government's judicial island to rescue Robin, defeats CP9's Rob Lucci, and burns their own flag in open defiance of the World Government. Shipwright Franky joins the crew."},
        {"day": 52, "title": "Thriller Bark — Moria defeated", "location": "Thriller Bark", "summary": "The Warlord Gecko Moria is defeated after his zombie-army scheme is unraveled; the skeleton musician Brook joins the crew, completing the original Straw Hat lineup."},
        {"day": 59, "title": "Sabaody Archipelago incident", "location": "Sabaody Archipelago", "summary": "A clash with a Celestial Dragon draws admiral-level attention; the Warlord Bartholomew Kuma disperses the entire crew across the world to save them from annihilation, ending Part 1 of the voyage."},
        {"major": False, "day": 67, "title": "Impel Down infiltration", "location": "Impel Down", "summary": "Luffy infiltrates the great undersea prison to save his brother Ace, breaking out an army of dangerous allies and enemies alike in the process."},
        {"day": 68, "title": "The Battle of Marineford", "location": "Marineford", "summary": "The Whitebeard Pirates clash with the full might of the Marines and Warlords to save Ace from execution, in the largest war the world has seen in decades."},
        {"day": 68, "title": "Ace's death", "location": "Marineford", "summary": "Portgas D. Ace dies shielding Luffy from Admiral Akainu's attack, moments after Whitebeard himself falls in the same battle — a loss that breaks Luffy and reshapes the balance of power in the world."},
        {"major": False, "day": 82, "title": "Luffy begins two years of training", "location": "Amazon Lily / Rusukaina", "summary": "Still reeling from Ace's death, Luffy accepts Rayleigh's offer of two years of solitary training before the crew reunites."},
        {"major": False, "day": 733, "title": "Reunion at Sabaody", "location": "Sabaody Archipelago", "summary": "After two years of separate training, the Straw Hat Pirates reunite at Sabaody Archipelago, each dramatically stronger and ready for the Grand Line's second half."},
        {"day": 734, "title": "Fishman Island saved", "location": "Fishman Island", "summary": "Hordy Jones's coup and his New Fishman Pirates are defeated; a lasting alliance between the surface and Fishman Island begins."},
        {"day": 735, "title": "Punk Hazard incident", "location": "Punk Hazard", "summary": "Caesar Clown's poison-gas weapons project is stopped and an alliance is formed with Trafalgar Law against Doflamingo and Kaido."},
        {"day": 736, "title": "Dressrosa liberated", "location": "Dressrosa", "summary": "The Warlord Donquixote Doflamingo is defeated and his decade-long tyranny over Dressrosa ends; the Straw Hat Grand Fleet is born from the allies made here."},
        {"major": False, "day": 748, "title": "The Alliance forms at Zou", "location": "Zou", "summary": "The Ninja–Pirate–Mink–Samurai Alliance forms against Kaido as the crew learns Sanji has been called to an arranged marriage on Whole Cake Island."},
        {"day": 758, "title": "Whole Cake Island — the Tea Party interrupted", "location": "Whole Cake Island — Totto Land", "summary": "Sanji is pulled from his arranged wedding to the Big Mom Pirates in a narrow, costly escape that earns the crew Big Mom's undying wrath."},
        {"major": False, "day": 760, "title": "Landing in Wano", "location": "Wano Country", "summary": "The crew arrives in the isolated shogunate of Wano and begins secretly allying with the Kozuki retainers to bring down Kaido, just as the Reverie convenes overseas."},
        {"day": 763, "title": "Nefertari Cobra's death and Imu's reveal", "location": "Mary Geoise", "summary": "King Cobra is killed after stumbling onto the truth of Imu, the world's hidden ruler — a secret the Celestial Dragons have kept for 800 years."},
        {"day": 774, "title": "The Raid on Onigashima — Wano liberated", "location": "Wano — Onigashima", "summary": "The Alliance defeats Kaido and Big Mom in an all-night raid; Luffy awakens his Devil Fruit's true Nika form, the puppet shogun Orochi falls, and Momonosuke is restored as Wano's rightful shogun."},
        {"day": 792, "title": "Lulusia Kingdom is destroyed", "location": "Lulusia Kingdom", "summary": "Imu orders the Government's ancient weapon fired on Lulusia using the Mother Flame, erasing the entire kingdom without warning."},
        {"day": 797, "title": "Egghead Island incident", "location": "Egghead Island", "summary": "Dr. Vegapunk's hidden truths come to light as CP0, an Admiral, and the shadowy St. Saturn move directly against the Straw Hats — an unprecedented direct confrontation between the crew and the world's ruling powers."},
    ]},
    "Hunter x Hunter": {"start_day": -7, "anchor": "Seven days before Gon leaves Whale Island", "events": [
        {"day": 0, "title": "Departure from Whale Island", "location": "Whale Island", "summary": "Gon Freecss leaves home to pursue the Hunter Exam."},
        {"major": False, "day": 1, "title": "Mito's reluctant blessing", "location": "Whale Island", "summary": "Gon's aunt Mito lets him go despite her fear, unwilling to be the one who stops him from following his father's path."},
        {"major": False, "day": 3, "title": "Meeting Kurapika and Leorio", "location": "Route to the Exam", "summary": "Gon meets Kurapika and Leorio en route to the exam site; the four future companions' paths first cross."},
        {"major": False, "day": 4, "title": "Leorio and Kurapika's clash", "location": "Route to the Exam", "summary": "Leorio and Kurapika nearly come to blows over their different reasons for wanting to be Hunters, before an uneasy respect forms."},
        {"major": False, "day": 5, "title": "Hisoka's warning", "location": "Exam Ship", "summary": "Gon draws Hisoka's attention aboard the ship to the exam site after standing up for Leorio."},
        {"day": 7, "title": "Hunter Exam begins", "location": "Hunter Exam Site", "summary": "The annual Hunter Exam gathers applicants and begins its lethal phases, opening with a punishing navigation trial."},
        {"major": False, "day": 8, "title": "The marathon trial", "location": "Hunter Exam Site", "summary": "An 80-kilometer run through shifting wetlands and traps thins the field of applicants before the real trials even begin."},
        {"major": False, "day": 9, "title": "Menchi's gourmet trial", "location": "Hunter Exam Site", "summary": "Examiner Menchi's cooking-based Second Phase forces applicants to hunt exam-specific prey, nearly costing Gon his chance."},
        {"major": False, "day": 12, "title": "Trick Tower phase", "location": "Hunter Exam Site", "summary": "A treacherous multi-choice trial forces uneasy cooperation and betrayal among applicants."},
        {"major": False, "day": 13, "title": "The choice of tunnels", "location": "Hunter Exam Site", "summary": "Gon's group must gamble on one of three unmarked tunnels through Trick Tower, each with a different hidden risk."},
        {"major": False, "day": 15, "title": "A duel of mercy", "location": "Hunter Exam Site", "summary": "A one-on-one bridge duel forces an applicant to choose between a clean win and a crueler, more certain one."},
        {"major": False, "day": 17, "title": "The exam's survival phase", "location": "Hunter Exam Site", "summary": "A lethal hunting phase thins the remaining applicants before the final trial."},
        {"major": False, "day": 18, "title": "Zevil Island's numbered hunt", "location": "Zevil Island", "summary": "Applicants hunt one another for numbered tags, and Killua's unnervingly casual lethality becomes hard to ignore."},
        {"day": 24, "title": "Exam final phase", "location": "Hunter Exam Site", "summary": "One-on-one battles decide the last Hunters of the year, including Hisoka's brutal match; the survivors receive their licenses."},
        {"major": False, "day": 26, "title": "Hisoka's promise", "location": "Hunter Exam Site", "summary": "Hisoka spares Gon and Killua after the exam, promising a real fight once they've grown strong enough to be worth killing."},
        {"major": False, "day": 30, "title": "Gon and Killua's bond forms", "location": "Various", "summary": "Fresh from the exam, Gon and Killua begin traveling and training together."},
        {"major": False, "day": 35, "title": "A call back to the Zoldyck estate", "location": "Various", "summary": "Killua is quietly summoned home, forcing an early test of how much his new friendships actually mean to him."},
        {"day": 40, "title": "Kukuroo Mountain visit", "location": "Kukuroo Mountain", "summary": "New Hunters challenge the Testing Gate and the Zoldyck estate's defenses."},
        {"major": False, "day": 41, "title": "Silva and Kikyo size up the visitors", "location": "Kukuroo Mountain", "summary": "Killua's parents coldly assess Gon and his companions, unconvinced their son's new path is anything but a phase."},
        {"major": False, "day": 55, "title": "Zushi and the discovery of Nen", "location": "Heavens Arena", "summary": "A young floor climber named Zushi and his teacher Wing introduce Gon and Killua to Nen, a hidden discipline that changes everything about how they fight."},
        {"day": 70, "title": "Heaven's Arena ascent", "location": "Heavens Arena", "summary": "Rising fighters enter the arena's upper floors, where Nen becomes decisive."},
        {"major": False, "day": 85, "title": "Nen categories mastered", "location": "Heavens Arena", "summary": "Gon and Killua work through grueling basic Nen training, each edging toward discovering their own natural affinity."},
        {"major": False, "day": 100, "title": "Reunion before Yorknew", "location": "Yorknew City", "summary": "The four companions reunite ahead of the Yorknew auction, each pursuing their own goal in the city."},
        {"major": False, "day": 170, "title": "The Phantom Troupe converges", "location": "Yorknew City", "summary": "Members of the infamous Phantom Troupe quietly gather in Yorknew ahead of the auction, drawn by rumors of a Kurta-scarlet-eyed item on the block."},
        {"day": 180, "title": "Yorknew auction crisis", "location": "Yorknew City", "summary": "The underground auction and Phantom Troupe converge in Yorknew City."},
    ]},
    "Naruto": {"start_day": -7, "anchor": "Seven days before Naruto's Academy graduation", "events": [
        # Day numbers below are calibrated against the Narutopedia community
        # timeline (User:Seelentau/Naruto Timeline), converted onto this
        # engine's 30-day-month/360-day-year calendar and linearly scaled so
        # Naruto's birth and his Academy graduation land exactly on this
        # world's two pre-existing anchor days (-4380 and 0). Everything else
        # keeps that source's actual relative spacing, so it's meaningfully
        # more accurate than a flat guess — but still an explicit campaign
        # estimate, since the source itself reconstructs approximate dates
        # from scattered manga/databook/novel evidence.
        # These five predate every currently-defined starting era (the
        # earliest is the Third Shinobi World War at day -4900) — they exist
        # purely as CANON HISTORY context for gm_rules, never as something a
        # campaign could actually reach or need to catch up on. historical_only
        # tells fire_canon_events to always skip them, regardless of how
        # confident the anchor-day filter above is for a given save.
        {"major": False, "historical_only": True, "day": -22319, "title": "Konohagakure is founded", "location": "Konohagakure", "summary": "Hashirama Senju and Madara Uchiha end generations of clan warfare, founding Konohagakure together; Hashirama becomes its First Hokage."},
        {"major": False, "historical_only": True, "day": -19822, "title": "Hashirama defeats Madara Uchiha", "location": "Valley of the End", "summary": "Madara Uchiha attacks Konoha and is defeated by Hashirama Senju in their legendary battle, later commemorated by the carved cliffs of the Valley of the End."},
        {"major": False, "historical_only": True, "day": -16710, "title": "The First Shinobi World War ends", "location": "Konohagakure", "summary": "The war closes with Tobirama Senju's death; Hiruzen Sarutobi becomes the Third Hokage in the aftermath."},
        {"major": False, "historical_only": True, "day": -9323, "title": "The Second Shinobi World War begins", "location": "Amegakure", "summary": "War breaks out across the shinobi nations; Kurama, the Nine-Tails, is sealed into Kushina Uzumaki, making her its second jinchuriki."},
        {"major": False, "historical_only": True, "day": -6641, "title": "Sakumo Hatake's death", "location": "Konohagakure", "summary": "The White Fang of Konoha takes his own life after being condemned for choosing to save his comrades over completing a mission — a shadow that will hang over his son Kakashi for years."},
        {"day": -4857, "title": "The Kannabi Bridge mission", "location": "Kannabi Bridge", "summary": "Rin Nohara dies and Obito Uchiha is believed killed during a mission gone wrong; Kakashi inherits Obito's Sharingan, and both awaken the Mangekyō Sharingan in their grief."},
        {"day": -4856, "title": "Yahiko's death and the founding of Akatsuki", "location": "Amegakure", "summary": "Yahiko dies at Hanzō and Danzō's hands; the survivor rescued from Kannabi Bridge — now calling himself Madara — along with Nagato and Konan, forms the organization that will become Akatsuki."},
        {"day": -4380, "title": "Naruto's birth and the Nine-Tails attack", "location": "Konohagakure", "banner": "nine_tails_attack_on_konoha", "scope": "wide", "summary": "Naruto is born as Obito's attack breaks Kushina's seal; Minato and Kushina confront the Nine-Tails while Konoha fights for survival."},
        {"major": False, "day": -4233, "title": "Might Duy's sacrifice", "location": "Land of Fire", "summary": "Might Duy rescues Guy, Ebisu, and Genma from the Seven Swordsmen of the Mist, killing two of them before dying from opening the Eight Gates."},
        {"major": False, "day": -3233, "title": "The Hyūga Affair", "location": "Konohagakure", "summary": "After Hiashi Hyūga kills a Kumogakure envoy in retaliation for an attempted kidnapping, his twin brother Hizashi sacrifices his own life under the branch seal to satisfy the peace treaty."},
        {"day": -1603, "title": "The Uchiha Massacre", "location": "Konohagakure — Uchiha District", "banner": "uchiha_massacre", "summary": "Itachi Uchiha kills nearly his entire clan in a single night under Konoha's own order to prevent a coup, sparing only his younger brother Sasuke. The truth behind why is hidden from the village for years."},
        {"day": 0, "title": "Academy graduation night — the Mizuki incident", "location": "Konohagakure", "summary": "Naruto's graduation is followed the same night by Mizuki's betrayal: he tricks Naruto into stealing the Forbidden Scroll of Seals before being stopped, and the new genin generation begins forming."},
        {"major": False, "day": 2, "title": "Ninja Registration Day", "location": "Konohagakure", "summary": "Naruto is formally registered as a shinobi of the Hidden Leaf, and meets Konohamaru for the first time."},
        {"major": False, "day": 3, "title": "The Graduation Ceremony", "location": "Konohagakure", "summary": "Twenty-seven students graduate into nine three-person genin teams."},
        {"major": False, "day": 4, "title": "Team 7 is formed", "location": "Konohagakure", "summary": "Kakashi Hatake accepts Naruto, Sasuke, and Sakura as Team 7, alongside the formation of Team 8 and Team 10."},
        {"major": False, "day": 20, "title": "D-rank missions begin", "location": "Konohagakure", "summary": "Team 7 starts a run of menial village chores and errands — the unglamorous reality before real missions are trusted to them."},
        {"major": False, "day": 40, "title": "The client's request", "location": "Konohagakure", "summary": "A traveling bridge-builder requests an escort mission undersold as routine, setting up a far more dangerous job than advertised."},
        {"day": 56, "title": "Land of Waves mission begins", "location": "Land of Waves", "banner": "land_of_waves_mission", "summary": "Team 7 begins the bridge-builder escort mission and is immediately ambushed, then confronted by the missing-nin Zabuza Momochi, revealing the client's true danger."},
        {"major": False, "day": 60, "title": "Zabuza's ambush", "location": "Land of Waves", "summary": "The Demon of the Hidden Mist attacks the escort team directly, aided by his masked companion Haku."},
        {"major": False, "day": 65, "title": "A quiet conversation in the woods", "location": "Land of Waves", "summary": "Haku speaks candidly about strength and precious people with Naruto in the forest, neither realizing they'll soon meet as enemies."},
        {"day": 70, "title": "Battle of the Great Naruto Bridge", "location": "Land of Waves", "summary": "Zabuza and Haku are confronted a final time; Haku dies protecting Zabuza, Zabuza kills Gato, and dies from Gato's men's wounds. The bridge battle reshapes Team 7's understanding of shinobi life and death."},
        {"major": False, "day": 76, "title": "Return to Konohagakure", "location": "Konohagakure", "summary": "Team 7 completes the Naruto Bridge and returns home, resuming routine missions."},
        {"major": False, "day": 100, "title": "Chūnin Exam nominations", "location": "Konohagakure", "summary": "Jōnin instructors across the village nominate their genin teams for the upcoming Chūnin Exams as foreign shinobi begin arriving in Konoha."},
        {"day": 161, "title": "Chūnin Exams begin", "location": "Konohagakure", "summary": "Genin from multiple villages gather for the written exam and the Forest of Death survival trial. Orochimaru infiltrates the exam and marks Sasuke with the cursed seal."},
        {"major": False, "day": 166, "title": "Chūnin Exam preliminaries", "location": "Konohagakure", "summary": "One-on-one preliminary matches thin the surviving genin ahead of the final tournament, revealing hidden strength and rivalries; Naruto meets Jiraiya the same night."},
        {"major": False, "day": 175, "title": "One month of final-round training", "location": "Konohagakure", "summary": "Finalists scatter to train intensively before the Chūnin Exam finals — Naruto with Jiraiya, Sasuke with Kakashi — each seeking an edge from a mentor or hidden technique."},
        {"major": False, "day": 185, "title": "The curse mark's temptation", "location": "Konohagakure", "summary": "Sasuke wrestles with the cursed seal's promised power as Kakashi works out a way to counter it before the finals."},
        {"day": 190, "title": "Chūnin Exam finals and the Konoha Crush", "location": "Konohagakure", "scope": "wide", "summary": "The exam finals become the cover for a coordinated invasion by Sunagakure and Otogakure; the Third Hokage, Hiruzen Sarutobi, dies sealing away Orochimaru's arms — unless prior divergences alter the outcome."},
        {"day": 192, "title": "The search for Tsunade begins", "location": "Konohagakure", "banner": "search_for_tsunade", "summary": "With Itachi and Kisame sighted entering the village, Jiraiya and Naruto set out to track down the Sannin Tsunade and convince her to become the Fifth Hokage."},
        {"major": False, "day": 229, "title": "Tsunade becomes Fifth Hokage", "location": "Konohagakure", "summary": "Tsunade returns to Konoha with Naruto and Jiraiya and formally accepts the title of Fifth Hokage."},
        {"day": 238, "title": "Sasuke's Departure", "location": "Konohagakure", "banner": "sasukes_departure", "summary": "Consumed by the pull of Orochimaru's power, Sasuke abandons Konoha in the night after clashing with Naruto on the hospital rooftop."},
        {"day": 241, "title": "Sasuke Retrieval Mission", "location": "Land of Rice Fields", "banner": "sasuke_retrieval_mission", "summary": "A team of genin pursues Sasuke to bring him back, each facing one of Orochimaru's Sound Four in a running battle that costs the team dearly; Naruto and Sasuke's confrontation at the Valley of the End ends with Sasuke continuing on to Orochimaru."},
        {"major": False, "day": 330, "title": "Naruto departs with Jiraiya", "location": "Konohagakure", "summary": "Naruto leaves Konoha with Jiraiya for two and a half years of training, after Jiraiya tells him of Akatsuki's true threat."},
        {"major": False, "day": 1069, "title": "Return to Konohagakure", "location": "Konohagakure", "summary": "Naruto and Jiraiya return to the village after roughly two and a half years, and Naruto retakes Kakashi's old bell test alongside Sakura."},
        {"day": 1076, "title": "Gaara's death and rescue", "location": "Sunagakure", "banner": "gaara_rescue", "summary": "Akatsuki's Deidara and Sasori extract Shukaku from Gaara, killing him; Sakura and Chiyo defeat Sasori, and Chiyo sacrifices her own life to revive Gaara — the crew's first direct confrontation with Akatsuki."},
        {"major": False, "day": 1337, "title": "Asuma Sarutobi's death", "location": "Land of Fire", "summary": "Hidan of Akatsuki kills Asuma Sarutobi before Shikamaru's team avenges him."},
        {"day": 1360, "title": "Jiraiya's death in Amegakure", "location": "Amegakure", "summary": "Jiraiya infiltrates Amegakure to learn the truth behind Pain, fights Pain and Konan, and dies delivering crucial intelligence back to Konoha with his final moments."},
        {"day": 1361, "title": "Itachi Uchiha's death", "location": "Land of Fire border", "summary": "Sasuke finally confronts and kills Itachi in single combat; Itachi, already dying of illness, ensures his brother survives the fight."},
        {"day": 1400, "title": "Itachi's Truth", "location": "Various", "banner": "itachis_truth", "summary": "In the aftermath of Itachi's death, the truth of the Uchiha Massacre comes to light: Itachi acted under Konoha's own order to prevent a coup, sacrificing his name and his brother's hatred to protect the village he loved."},
        {"day": 1409, "title": "Pain's Assault on Konoha", "location": "Konohagakure", "banner": "pains_assault_on_konoha", "scope": "wide", "summary": "Pain launches a full assault on Konohagakure in pursuit of Naruto, leveling much of the village within minutes."},
        {"day": 1409, "title": "Naruto vs. Pain", "location": "Konohagakure", "banner": "naruto_vs_pain", "summary": "Naruto confronts Pain directly, ultimately learning Nagato's true identity and choosing to spare him — a choice that reshapes the Akatsuki leader's own resolve as he sacrifices himself to revive the villagers he killed."},
        {"major": False, "day": 1410, "title": "The Five Kage Summit", "location": "Land of Iron", "summary": "The Five Kage meet to decide how to respond to Akatsuki, only for Sasuke to attack the summit himself; the masked Akatsuki leader declares the Fourth Shinobi World War in the chaos that follows."},
        {"day": 1420, "title": "Obito's Reveal", "location": "War Front", "banner": "obitos_reveal", "summary": "The masked man behind Akatsuki's true plan is revealed to be Obito Uchiha, Kakashi's presumed-dead teammate, radically reframing the entire war's cause."},
        {"day": 1684, "title": "The Fourth Shinobi World War begins", "location": "Allied Shinobi Forces Camp", "scope": "wide", "summary": "The Allied Shinobi Forces mobilize against Akatsuki's reanimated army, opening the war that will decide the future of the shinobi world."},
        {"day": 1685, "title": "Kaguya's Appearance", "location": "Kaguya's Dimension", "banner": "kaguyas_appearance", "summary": "Obito casts the Infinite Tsukuyomi, but Black Zetsu's betrayal uses him to revive Kaguya Ōtsutsuki instead — a threat beyond anything the shinobi world has faced, who kills Obito himself moments later."},
        {"day": 1686, "title": "Naruto and Sasuke vs. Kaguya", "location": "Kaguya's Dimension", "banner": "naruto_and_sasuke_vs_kaguya", "summary": "Naruto and a reconciled Sasuke seal Kaguya away for good, ending the Fourth Shinobi World War and the immediate threat to the entire world; Madara dies as the Ten-Tails is removed from him."},
        {"day": 1687, "title": "Naruto vs. Sasuke — Final Valley", "location": "Valley of the End", "banner": "naruto_vs_sasuke_final_valley", "summary": "With the war won, Naruto and Sasuke settle their own long rivalry in a final, defining battle at the Valley of the End, each losing an arm before finally reconciling."},
        {"major": False, "day": 2064, "title": "Kakashi becomes Sixth Hokage", "location": "Konohagakure", "summary": "Kakashi Hatake is named the Sixth Hokage in the war's aftermath, the same month Sasuke leaves the village once more to atone for the past on his own terms."},
        {"major": False, "day": 2553, "title": "Naruto and Hinata marry", "location": "Konohagakure", "summary": "Naruto Uzumaki and Hinata Hyūga marry in Konohagakure, years after the war's end."},
        {"day": 4413, "title": "Naruto Becomes Hokage", "location": "Konohagakure", "banner": "naruto_becomes_hokage", "scope": "wide", "summary": "Naruto is formally named the Seventh Hokage, fulfilling his childhood dream and the village's recognition of everything he sacrificed to earn it."},
        {"major": False, "day": 6910, "title": "Momoshiki and Kinshiki's attack", "location": "Konohagakure", "summary": "During the Chūnin Exams hosted in Konoha, the Ōtsutsuki invaders Momoshiki and Kinshiki attack the village, forcing the next generation of shinobi into their first real crisis."},
    ]},
    "Solo Max-Level Newbie": {"start_day": -3, "anchor": "Three days before the Tower appears", "events": [
        {"day": 0, "title": "Tower manifestation", "location": "Earth — Tower Entrance", "summary": "The Tower of Trials manifests in reality and humanity receives its first scenario, with a deadline for every player to clear each floor or face annihilation."},
        {"day": 1, "title": "First-floor scenario", "location": "Floor 1", "summary": "Players enter the opening floor while hidden conditions and first achievements become available to those who know to look."},
        {"major": False, "day": 1, "title": "Park Hana's ambush", "location": "Floor 1", "summary": "A desperate rival named Park Hana tries to stab Kang Jinhyuk in the Floor 1 labyrinth and is instead beaten and drawn into his growing circle."},
        {"major": False, "day": 2, "title": "The National Museum incident", "location": "Seoul — National Museum", "summary": "Min Jeong-woo attempts to steal a priceless map while Yu-ri Lee moves to stop him; someone with full foreknowledge of the game quietly benefits without being drawn into the fight."},
        {"major": False, "day": 3, "title": "The first deaths", "location": "Floor 1", "summary": "Casual players who underestimate the Tower begin dying in earnest, and the scale of the threat becomes impossible to deny."},
        {"major": False, "day": 5, "title": "Old instincts, new stakes", "location": "Floor 1", "summary": "A former streamer's old audience-building instincts resurface, this time backed by real, lethal consequences instead of a game score."},
        {"day": 7, "title": "Guild consolidation", "location": "Earth — Tower Entrance", "summary": "Major guilds and governments compete to control information, recruits, and early rewards."},
        {"major": False, "day": 10, "title": "Corporate scouting begins", "location": "Earth — Tower Entrance", "summary": "Goinmul Corporation and rival organizations start quietly identifying and recruiting standout early clearers."},
        {"major": False, "day": 14, "title": "First real boss attempts", "location": "Floor 1", "summary": "The strongest early clearers begin serious attempts on the floor's boss, exposing mechanics ordinary players never find."},
        {"day": 20, "title": "Early boss race", "location": "Floor 5", "summary": "Leading players race for first-clear rewards and concealed boss conditions."},
        {"major": False, "day": 25, "title": "Hidden achievement hunting", "location": "Floor 1-2", "summary": "Someone with complete foreknowledge of the game methodically claims hidden achievements no ordinary player would think to look for."},
        {"major": False, "day": 30, "title": "The gap widens", "location": "Floor 2", "summary": "The fastest climbers reach Floor 2 well ahead of the pack, and the divide between top players and everyone else becomes stark public knowledge."},
    ]},
    "Overgeared": {"start_day": -3, "anchor": "Three days before Grid discovers Pagma's legacy", "events": [
        {"major": False, "day": -3, "title": "The Sun Sword bargain", "location": "Winston", "summary": "Desperate for a way to progress, Grid takes on a quest to find Pagma's Rare Book in exchange for a legendary-class weapon, the Sun Sword."},
        {"day": 0, "title": "Pagma's legacy changes hands", "location": "Winston", "summary": "Grid finds Pagma's Rare Book, triggers the SS-rank quest Earl Ashur's Anger, and chooses to use the book himself rather than surrender it — a legendary-class turning point in Satisfy."},
        {"major": False, "day": 2, "title": "Piaro's offer", "location": "Kesan Canyon", "summary": "Piaro, the disgraced former knight captain of the Red Knights hiding from the Saharan Empire, judges Grid's rapid growth and offers him a revenge quest — one Grid isn't yet strong enough to accept."},
        {"major": False, "day": 4, "title": "The Temple of Yatan", "location": "Temple of Yatan", "summary": "Grid is drawn into Doran's quest to rescue Irene inside the Temple of Yatan; Doran is killed by the cultist Yura before it ends."},
        {"day": 7, "title": "Winston class-quest pressure", "location": "Winston", "summary": "Local politics, crafting opportunities, and player competition intensify around Winston."},
        {"major": False, "day": 10, "title": "Failure after failure", "location": "Winston", "summary": "Grid grinds through repeated failed crafting attempts, his results still far below the legendary standard Pagma once set."},
        {"major": False, "day": 15, "title": "Kesan Canyon expedition", "location": "Kesan Canyon", "summary": "Searching for Pagma's Swordsmanship, Grid discovers how to combine Skills into new, more powerful fused techniques."},
        {"major": False, "day": 22, "title": "Whispers of an unusual player", "location": "Winston", "summary": "Rumors begin spreading among competing guilds of an oddly overpowered low-level player operating out of Winston."},
        {"day": 30, "title": "Guild attention grows", "location": "Winston", "summary": "Major players and guilds begin pursuing rumors of exceptional crafted equipment."},
        {"major": False, "day": 45, "title": "An ancient lich takes notice", "location": "Winston region", "summary": "The arrogant, ancient lich Braham takes a distant, contemptuous interest in Grid's unorthodox mastery of Pagma's forbidden techniques."},
        {"major": False, "day": 60, "title": "Piaro's revenge, revisited", "location": "Kesan Canyon", "summary": "Now stronger, Grid returns to Piaro to finally take up the revenge quest he once had to refuse."},
        {"major": False, "day": 62, "title": "Piaro relocates to Reidan", "location": "Reidan", "summary": "Piaro leaves his hermitage in Kesan Canyon to train Grid directly at Reidan, the first of his knightly techniques passed on in earnest."},
        {"major": False, "day": 75, "title": "Guild recruitment pressure", "location": "Winston", "summary": "Large guilds attempt to recruit or quietly pressure the increasingly notable Grid into joining their ranks."},
        {"day": 90, "title": "Reidan frontier window", "location": "Reidan", "summary": "The neglected frontier becomes strategically important to emerging powers."},
    ]},
    "Reincarnated as a Slime": {"start_day": -7, "anchor": "Seven days before Satoru Mikami's reincarnation", "events": [
        {"day": 0, "title": "A new slime awakens", "location": "Great Jura Forest", "summary": "An otherworlder reincarnates as a slime inside the Sealed Cave."},
        {"major": False, "day": 1, "title": "Meeting Veldora", "location": "Great Jura Forest", "summary": "The newly reincarnated slime meets the imprisoned Storm Dragon Veldora, exchanging names and stories in the cave."},
        {"day": 2, "title": "Veldora disappears", "location": "Great Jura Forest", "summary": "The Storm Dragon's presence vanishes from the outside world, disturbing the Jura Forest's balance of power."},
        {"major": False, "day": 3, "title": "Naming a new Skill", "location": "Great Jura Forest", "summary": "The slime's analytical Skill takes on the name Great Sage, and cautious exploration of the cave's depths begins in earnest."},
        {"major": False, "day": 5, "title": "Ranga and the Direwolves", "location": "Great Jura Forest", "summary": "After an attack by goblin-hunting Direwolves, the slime becomes the pack's new leader, and Ranga emerges as a loyal companion."},
        {"major": False, "day": 8, "title": "Cautious goblin scouts", "location": "Goblin Village outskirts", "summary": "Goblin scouts spot the strange, talking slime and its new wolf pack, more curious than hostile."},
        {"day": 12, "title": "Goblin village crisis", "location": "Goblin Village", "summary": "Direwolf pressure forces a small goblin settlement toward a decisive alliance."},
        {"major": False, "day": 15, "title": "Shizu's final journey", "location": "Great Jura Forest", "summary": "The otherworlder Shizue Izawa is met in the forest; her death shortly after passes her Unique Skill and a promise on to the slime."},
        {"major": False, "day": 16, "title": "A new name taken up", "location": "Great Jura Forest", "summary": "Following Shizu's dying gift, the slime adopts the name she gave it — Rimuru Tempest — and starts being known by it."},
        {"major": False, "day": 20, "title": "The mass naming of the goblins", "location": "Goblin Village", "summary": "Naming the goblin tribe en masse evolves them into hobgoblins, at real cost to the namer's own magicule reserves."},
        {"major": False, "day": 30, "title": "Kaijin and the dwarven blacksmiths", "location": "Goblin Village", "summary": "Exiled dwarven craftsmen led by Kaijin are rescued and join the growing settlement, founding its early industry."},
        {"major": False, "day": 38, "title": "Rigurd takes up administration", "location": "Goblin Village", "summary": "A steady goblin elder named Rigurd begins organizing the growing settlement's daily affairs, freeing Rimuru to focus elsewhere."},
        {"day": 45, "title": "Dwargon contact window", "location": "Dwargon", "summary": "Crafting needs and diplomacy pull the growing monster community toward Dwargon."},
        {"major": False, "day": 52, "title": "A first cautious trade route", "location": "Dwargon", "summary": "A tentative trade relationship opens between the settlement and its dwarven neighbors, the first sign of real nationhood."},
        {"major": False, "day": 60, "title": "The Orc Disaster gathers", "location": "Great Jura Forest", "summary": "A starving Orc Lord's forces begin threatening every settlement in the forest, forcing old rivals into uneasy alliance."},
        {"major": False, "day": 65, "title": "Old rivals debate war", "location": "Great Jura Forest", "summary": "Leaders across the forest argue over how — or whether — to respond together to the swelling Orc threat."},
        {"major": False, "day": 70, "title": "The Orc Lord falls", "location": "Great Jura Forest", "summary": "The Orc Lord is defeated; a mass-naming on a catastrophic scale triggers a Demon Lord-tier awakening, and the Dragon Peak Demon Lord Milim Nava takes notice."},
        {"major": False, "day": 74, "title": "A Demon Lord's idle curiosity", "location": "Dragon Peak", "summary": "Rumors of an upstart monster settlement and its unusual leader first reach Milim Nava, who finds the idea more entertaining than threatening."},
        {"major": False, "day": 80, "title": "Benimaru steps up", "location": "Tempest", "summary": "The hobgoblin Benimaru distinguishes himself organizing the settlement's defenders in the Orc Disaster's aftermath."},
        {"major": False, "day": 90, "title": "New specialists arrive", "location": "Tempest", "summary": "Additional dwarven craftsmen round out the settlement's early industry, from potion-brewing to construction."},
        {"day": 100, "title": "Tempest emerges", "location": "Tempest", "summary": "A multi-species settlement begins to become a recognized nation."},
    ]},
    "Custom World": {"start_day": -7, "anchor": "Seven days before the world's opening incident", "events": [
        {"day": 0, "title": "Opening incident", "location": "Starting Region", "summary": "The custom world's first major story pressure begins; adapt this event to the player's setting."},
    ]},
}


def timeline_for(world):
    return CANON_TIMELINES.get(world, CANON_TIMELINES["Custom World"])


# Alternate starting points for an ORIGINAL (non-canon-character) campaign —
# distinct from MAJOR_CHARACTER_STARTS below, which is about playing a
# specific named canon character. This is about letting a player's own
# character begin in a meaningfully different era of the same world. Only
# added where a world actually has a well-known distant era to place a
# character in; not every world does, and these day offsets are the same
# kind of explicit campaign-relative estimate CANON_TIMELINES already uses
# for ancient-era entries — canon gives ages and rough eras, not a
# day-by-day calendar, so exact precision isn't the goal, a believable
# placement is. The first entry in each list is always the existing default.
WORLD_STARTING_ERAS = {
    "Naruto": [
        {"id": "academy_graduation", "label": "Academy Graduation (default)", "start_day": -7,
         "anchor": "Seven days before Naruto's Academy graduation."},
        {"id": "third_shinobi_war", "label": "The Third Shinobi World War", "start_day": -4900,
         "anchor": "During the closing stretch of the Third Shinobi World War, shortly before the Kannabi Bridge mission — Kakashi, Obito and Rin's generation are still on the front lines."},
        {"id": "before_naruto_birth", "label": "A week before Naruto's birth", "start_day": -4387,
         "anchor": "One week before Kushina gives birth to Naruto and the Nine-Tails attacks the village."},
    ],
    "One Piece": [
        {"id": "east_blue_departure", "label": "East Blue Departure (default)", "start_day": -7,
         "anchor": "Seven days before Luffy leaves Foosha Village."},
        {"id": "year_before_departure", "label": "One year before Luffy's departure", "start_day": -367,
         "anchor": "One year before Luffy leaves Foosha Village — still growing up there, well before the East Blue voyage begins."},
        {"id": "rogers_execution", "label": "Gold Roger's execution", "start_day": -7920,
         "anchor": "Twenty-two years before Luffy sets sail, on the day Gold Roger is executed at Loguetown and the Great Pirate Era begins."},
    ],
}


def starting_eras_for(world):
    return WORLD_STARTING_ERAS.get(world, [])


def starting_era_by_id(world, era_id):
    return next((e for e in starting_eras_for(world) if e.get("id") == era_id), None)


# Named-month calendars for worlds without a rigorously documented in-canon
# calendar of their own (which is most of them — these series track ages and
# rough eras, not a day-by-day date system). These are consistent, world-
# flavored invented calendars replacing the mechanical "Canon Day +7" counter
# with something that reads like a real place's dates — not a claim that
# this is documented source-material canon. Every invented calendar uses a
# uniform 30-day month / 12-month year, matching the schema the app already
# tracks internally (state.calendar). Solo Max-Level Newbie is contemporary
# real-world Earth and gets an actual Gregorian date instead — see
# format_calendar_date.
_REAL_MONTHS = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]
WORLD_CALENDARS = {
    "One Piece": _REAL_MONTHS,
    "Naruto": _REAL_MONTHS,
    "Hunter x Hunter": _REAL_MONTHS,
    "Overgeared": _REAL_MONTHS,
    "Reincarnated as a Slime": _REAL_MONTHS,
}
_CAL_DAYS_PER_MONTH = 30
_CAL_MONTHS_PER_YEAR = 12
_CAL_DAYS_PER_YEAR = _CAL_DAYS_PER_MONTH * _CAL_MONTHS_PER_YEAR


def canon_day_to_calendar_parts(world, canon_day, anchor_day=None):
    """Convert a canon_day offset into (year, month, day), 1-indexed, using
    a fixed 30-day-month/12-month-year scheme anchored so a start day lands
    on Year 1, Month 1, Day 1 — the same convention state.calendar already
    tracks live, but computable for any arbitrary day (a future scheduled
    event, a past beat) without needing that campaign's current state.
    anchor_day is the specific start_day THIS campaign actually began on
    (a canon character's start, a chosen starting era, or the world's
    default) — it can differ from the world's default start_day, so it must
    be passed explicitly rather than re-derived from CANON_TIMELINES, or a
    campaign starting somewhere other than the default reads absurd
    negative-year dates. Falls back to the world's default only when no
    anchor is given (an old save from before per-campaign anchors existed)."""
    start_day = anchor_day if anchor_day is not None else CANON_TIMELINES.get(world, CANON_TIMELINES["Custom World"]).get("start_day", -7)
    absolute_day = int(canon_day) - int(start_day)
    year, month_day = divmod(absolute_day, _CAL_DAYS_PER_YEAR)
    month, day = divmod(month_day, _CAL_DAYS_PER_MONTH)
    return year + 1, month + 1, day + 1


def format_calendar_date(world, canon_day, calendar_epoch=None, anchor_day=None):
    """The player-facing date string for a given canon_day — a real
    Gregorian date for Solo Max-Level Newbie (actual present-day Earth), an
    invented but consistent named-month date for worlds with a
    WORLD_CALENDARS entry, and a plain Year/Month/Day count for anything
    else (Custom World, an unrecognized world pack)."""
    year, month, day = canon_day_to_calendar_parts(world, canon_day, anchor_day)
    if world == "Solo Max-Level Newbie":
        try:
            epoch = datetime.date.fromisoformat(calendar_epoch) if calendar_epoch else datetime.date.today()
        except (TypeError, ValueError):
            epoch = datetime.date.today()
        elapsed_days = (year - 1) * _CAL_DAYS_PER_YEAR + (month - 1) * _CAL_DAYS_PER_MONTH + (day - 1)
        real_date = epoch + datetime.timedelta(days=elapsed_days)
        return f"{real_date.strftime('%B')} {real_date.day}, {real_date.year}"
    months = WORLD_CALENDARS.get(world)
    if months:
        return f"{months[(month - 1) % len(months)]} {day}, Year {year}"
    return f"Year {year}, Month {month}, Day {day}"


# A spoiler-free, hand-written "what you're getting into" primer for each
# world — deliberately static rather than AI-generated, so it costs nothing
# per campaign and can never accidentally leak a later-arc twist the way a
# fresh AI generation might. Everything here describes only the setting's
# starting status quo and what's public knowledge from its earliest chapters.
WORLD_PRIMERS = {
    "One Piece": {
        "premise": "The Pirate King's dying words revealed that an ultimate treasure, One Piece, is out there somewhere — and that revelation kicked off a new Great Pirate Era. Countless crews now sail dangerous seas chasing fortune, freedom, or legend.",
        "tone": "High-adventure shonen: big personalities, wild power scaling, found-family crews, comedy mixed with real stakes and loss.",
        "power_system": "Training, swordsmanship and marksmanship all matter, but the setting's wildcard is the Devil Fruit — a rare, cursed fruit granting a unique supernatural power at the cost of never being able to swim again. Haki, a latent inner power most people can awaken with training, adds perception and combat abilities on top.",
        "factions": ["The World Government & the Marines — the law of the seas, enforcing order (and their own interests)", "Pirates — from small-time crews to powers that rival nations", "The Revolutionary Army — a shadow movement opposing the World Government"],
        "locations": ["East Blue — the calmest, weakest sea, where most journeys begin", "The Grand Line — a violent, unpredictable ocean split into two very different halves", "Countless ports, kingdoms and islands scattered between them"],
        "starting_note": "Most campaigns begin as a nobody with a big dream, sailing a calm sea where the real monsters are still ahead.",
    },
    "Naruto": {
        "premise": "Hidden ninja villages, each led by a Kage, compete for military and political influence through trained shinobi. Old wars have left an uneasy peace between the Five Great Nations, and ancient tailed-beasts still shape the balance of power.",
        "tone": "Coming-of-age shonen: teamwork, rivalry and generational trauma alongside high-flying elemental combat.",
        "power_system": "Shinobi mold chakra — physical and spiritual energy — to perform ninjutsu, genjutsu and taijutsu. Clans often carry inherited bloodline techniques, and rank (Genin, Chunin, Jonin, Kage) reflects both skill and trust.",
        "factions": ["Konohagakure and the other Hidden Villages — Suna, Kiri, Kumo, Iwa", "The Land of Fire and the other Great Nations each village serves", "Missing-nin and rogue organizations operating outside village law"],
        "locations": ["Konohagakure, the Hidden Leaf Village", "The other four Great Hidden Villages, each with its own culture and specialty", "The smaller, neutral nations and border territories between them"],
        "starting_note": "Campaigns typically begin around an academy graduation — the cast is young, untested, and just starting to earn real trust.",
    },
    "Hunter x Hunter": {
        "premise": "Hunters are a licensed elite — explorers, bounty hunters, researchers and fighters — who've passed a brutal exam granting access to privileges ordinary people don't have. Beneath the adventure lies a much larger, stranger world of hidden powers.",
        "tone": "Adventure with a sharp, strategic edge — a deceptively cheerful surface hiding genuinely dark stakes and clever, rules-based power systems.",
        "power_system": "Nen — the ability to manipulate one's own life energy — is the setting's core hidden power, split into six categories (Enhancement, Transmutation, Conjuration, Emission, Manipulation, Specialization). It's normally unknown to the public and must be personally taught or discovered.",
        "factions": ["The Hunter Association — licenses and organizes Hunters worldwide", "Independent Hunters, bounty hunters and researchers pursuing their own goals", "Assassin families and criminal organizations operating in the shadows"],
        "locations": ["Whale Island and similar quiet starting communities", "Yorknew City — a major hub of commerce and the criminal underworld", "The wider world's remote wilds, mountains and unexplored regions Hunters chase"],
        "starting_note": "Campaigns usually begin before or during the annual Hunter Exam — Nen itself is typically still an undiscovered secret at this point.",
    },
    "Solo Max-Level Newbie": {
        "premise": "The Tower of Trials — once only a popular VR game — manifests in the real world without warning, forcing humanity to climb its floors or die. Anyone who clears a floor's trial gains real power; anyone who fails or refuses often doesn't survive.",
        "tone": "High-stakes survival/progression fantasy — cutthroat competition, constant escalation, and the tension of real death replacing a game-over screen.",
        "power_system": "Players gain stats, skills and items exactly like an RPG — leveling up, equipping gear, and learning abilities that persist and strengthen over time. Floors hide achievements and secret conditions that reward players clever or informed enough to find them.",
        "factions": ["Major guilds and corporations racing to control resources, information and territory", "Governments scrambling to manage a population suddenly forced into a life-or-death game", "Independent players and small groups just trying to survive"],
        "locations": ["Earth's cities, now home to Tower entrances", "The Tower's floors themselves, each a distinct trial and environment"],
        "starting_note": "Campaigns begin right as the Tower first appears — nobody yet has more than a few days' experience with it.",
    },
    "Overgeared": {
        "premise": "Satisfy is a hyper-realistic virtual-reality MMO where skill, crafting and clever play matter as much as raw stats. Legendary figures, ancient smiths and buried world-changing secrets are all still out there for a sufficiently determined — or lucky — player to find.",
        "tone": "Grounded MMO-fantasy power fantasy: meticulous crafting and itemization detail mixed with real cunning and hard-earned growth rather than pure luck.",
        "power_system": "Classes, stats and Skills work as expected for a VRMMO, but true depth comes from itemization — Legendary and higher-grade gear, forgotten smithing and crafting techniques, and Skill combinations most players never discover.",
        "factions": ["Major guilds and their sponsoring real-world corporations, competing for server-wide influence", "NPC kingdoms, nobility and factions with their own persistent politics", "Independent crafters, explorers and power players carving out their own niche"],
        "locations": ["Winston and similar starting kingdoms and towns", "Reidan and other contested or overlooked frontier territories", "The wider continent's dungeons, ruins and unclaimed wilderness"],
        "starting_note": "Campaigns typically begin with a character still finding their footing, long before anyone recognizes their name.",
    },
    "Reincarnated as a Slime": {
        "premise": "After death, an ordinary man wakes up reincarnated as a slime in another world — one where monsters can grow far beyond their humble start, and 'naming' a creature can radically change its fate.",
        "tone": "Optimistic, community-building isekai fantasy: diplomacy and found-family alongside real monster-world power scaling.",
        "power_system": "Monsters gain Skills and can evolve into stronger forms, often triggered by a major event or a name given by a sufficiently powerful being. Human-side magic draws on tangible magicules, channeled through spirits, techniques, or innate Unique/Ultimate Skills.",
        "factions": ["The scattered monster tribes and races of the Jura Forest and beyond, historically wary of each other", "Human nations, generally distrustful of monsters", "The world's Demon Lords — a handful of individually terrifying, world-shaping rulers"],
        "locations": ["The Great Jura Forest — a vast, monster-heavy wilderness", "Dwargon and other established dwarven and human kingdoms", "The wider continent's nations, both human- and monster-led"],
        "starting_note": "Campaigns begin at the very start of a new life in this world — before any settlement, alliance or reputation exists.",
    },
}


# Worlds where species/race is a meaningful, canon-established axis of a
# character — not every setting has one (Naruto, Hunter x Hunter, Solo
# Max-Level Newbie and Overgeared are effectively human-only), so this is
# opt-in per world rather than a universal field.
WORLD_RACES = {
    "One Piece": {
        "options": ["Human", "Fishman", "Merman", "Giant", "Mink", "Skypiean"],
        "default": "Human",
    },
    "Reincarnated as a Slime": {
        "options": ["Human", "Slime", "Goblin", "Hobgoblin", "Orc", "Ogre", "Direwolf",
                    "Lizardman", "Dwarf", "Spirit", "Dragonoid", "Kijin", "Demon", "Angel"],
        "default": "Slime",
    },
}

# Keyword hints for the instant, no-AI preview guess — the authoritative
# assignment (including inventing a fitting custom race the background
# describes but this list doesn't name) happens during the actual opening,
# where the GM can really read and interpret the free-text background.
_RACE_KEYWORDS = {
    "One Piece": [
        (("fishman", "fish-man", "fish man"), "Fishman"),
        (("merman", "mermaid"), "Merman"),
        (("giant",), "Giant"),
        (("mink",), "Mink"),
        (("skypiean", "sky island", "birka", "shandia"), "Skypiean"),
    ],
    "Reincarnated as a Slime": [
        (("slime",), "Slime"),
        (("hobgoblin",), "Hobgoblin"),
        (("goblin",), "Goblin"),
        (("direwolf", "dire wolf"), "Direwolf"),
        (("lizardman", "lizard man"), "Lizardman"),
        (("dwarf",), "Dwarf"),
        (("spirit", "elemental"), "Spirit"),
        (("dragonoid", "dragon"), "Dragonoid"),
        (("kijin", "oni"), "Kijin"),
        (("demon",), "Demon"),
        (("angel",), "Angel"),
        (("ogre",), "Ogre"),
        (("orc",), "Orc"),
        (("human",), "Human"),
    ],
}


def world_supports_races(world):
    return world in WORLD_RACES


def infer_race_from_background(world, background="", origin="", archetype=""):
    """A fast, deterministic best-guess for the instant campaign-preview
    screen — no AI call needed yet. This is never the final word: the actual
    opening reads the full background with real comprehension and can
    override it with an established race that fits better, or invent a
    fitting custom one the keyword list doesn't know about."""
    if world not in WORLD_RACES:
        return ""
    text = f"{origin} {archetype} {background}".lower()
    for keywords, race in _RACE_KEYWORDS.get(world, []):
        if any(k in text for k in keywords):
            return race
    return WORLD_RACES[world]["default"]


def world_primer_for(world, custom_world_text=""):
    if world in WORLD_PRIMERS:
        return WORLD_PRIMERS[world]
    text = str(custom_world_text or "").strip()
    return {
        "premise": text or "An original setting the player is defining through play — there's no fixed lore to summarize yet.",
        "tone": "Whatever tone fits the player's own concept; the GM follows their lead.",
        "power_system": "Rules and power systems will be established and kept consistent as the campaign unfolds.",
        "factions": [],
        "locations": [],
        "starting_note": "As an original world, its rules, factions and locations take shape through play rather than being fixed in advance.",
    }


# Optional player-controlled canon-character scenarios. Dates use each world's
# relative Canon Day clock; ancient-era starts are explicitly campaign-relative
# estimates where the source does not provide a complete day-by-day calendar.
MAJOR_CHARACTER_STARTS = {
    "One Piece": [
        {"id":"luffy_departure","name":"Monkey D. Luffy","label":"Luffy — leaving Foosha Village","start_day":0,"location":"Foosha Village","age":17,"origin":"Foosha Village","archetype":"Brawler","appearance":"A lean young pirate with black hair, a straw hat, red vest, shorts, sandals, and a small scar under one eye.","background":"The morning he intends to begin his pirate voyage."},
        {"id":"zoro_shells","name":"Roronoa Zoro","label":"Zoro — prisoner at Shells Town","start_day":3,"location":"Shells Town","age":19,"origin":"Bounty Hunter","archetype":"Swordsman","appearance":"A muscular green-haired swordsman wearing simple travel clothes and carrying three swords when armed.","background":"Imprisoned at the Marine base after protecting civilians."}
    ],
    "Hunter x Hunter": [
        {"id":"gon_departure","name":"Gon Freecss","label":"Gon — leaving Whale Island","start_day":0,"location":"Whale Island","age":12,"origin":"Whale Island","archetype":"Tracker","appearance":"A small athletic boy with spiky black-green hair, bright brown eyes, a green jacket and shorts, and sturdy boots.","background":"The morning he leaves Whale Island to pursue the Hunter Exam."},
        {"id":"kurapika_exam","name":"Kurapika","label":"Kurapika — Hunter Exam journey","start_day":1,"location":"Hunter Exam Route","age":17,"origin":"Kurta Survivor","archetype":"Strategist","appearance":"A slight blond teenager with gray-brown eyes and a blue-and-gold traditional tunic.","background":"Traveling toward the Hunter Exam while pursuing information about the Kurta eyes."}
    ],
    "Naruto": [
        {"id":"naruto_birth","name":"Naruto Uzumaki","label":"Naruto — night of his birth","start_day":-4380,"location":"Konohagakure","age":0,"origin":"Uzumaki newborn","archetype":"Unformed Potential","appearance":"A newborn boy with fine blond hair and three faint whisker-like marks on each cheek.","background":"The night of his birth, before the Nine-Tails attack reshapes the village and his life."},
        {"id":"yahiko_akatsuki","name":"Yahiko","label":"Yahiko — founding the Akatsuki","start_day":-4856,"location":"Amegakure","age":17,"origin":"Amegakure War Orphan","archetype":"Ninjutsu Student","appearance":"A lean orange-haired young shinobi with determined eyes, rain gear, and a forehead protector worn openly.","background":"During the war-torn era when Yahiko, Nagato, and Konan begin organizing the original Akatsuki around peace."},
        {"id":"naruto_graduation","name":"Naruto Uzumaki","label":"Naruto — Academy graduation night","start_day":0,"location":"Konohagakure","age":12,"origin":"Academy Student","archetype":"Ninjutsu Student","appearance":"A short blond academy student with blue eyes, whisker-like cheek marks, goggles, and an orange-and-blue outfit.","background":"The day of the Academy graduation and the Scroll of Seals incident."}
    ],
    "Solo Max-Level Newbie": [
        {"id":"jinhyeok_tower","name":"Kang Jinhyeok","label":"Jinhyeok — Tower manifestation","start_day":0,"location":"Earth — Tower Entrance","age":27,"origin":"Veteran Gamer","archetype":"All-Rounder","appearance":"A sharp-eyed young Korean man with dark hair, practical modern clothing, and a calm calculating expression.","background":"The day the Tower of Trials becomes reality."}
    ],
    "Overgeared": [
        {"id":"grid_pagma","name":"Grid","label":"Grid — Pagma's legacy turning point","start_day":0,"location":"Winston","age":26,"origin":"New Player","archetype":"Blacksmith","appearance":"A dark-haired young man with a stubborn expression, novice adventuring gear, and worn blacksmith tools.","background":"At the turning point where Pagma's legacy can change his life in Satisfy."}
    ],
    "Reincarnated as a Slime": [
        {"id":"rimuru_awakens","name":"Rimuru Tempest","label":"Rimuru — awakening in the cave","start_day":0,"location":"Great Jura Forest — Sealed Cave","age":0,"origin":"Reincarnated Otherworlder","archetype":"Skill Analyst","appearance":"A small translucent blue slime with a soft internal glow and an expressive, fluid silhouette.","background":"The first moments after reincarnating inside the Sealed Cave."}
    ],
}


def playable_characters_for(world):
    return MAJOR_CHARACTER_STARTS.get(world, [])

# Worlds where the source material actually supports starting somewhere
# (or with someone) different — a shonen world has multiple villages/crews/
# factions to begin in or with. Worlds without a lore reason for variety
# (an MMO tutorial city, a single tower entrance) are simply omitted here,
# and the New Campaign form falls back to that world's single wd["start"].
WORLD_START_OPTIONS = {
    "One Piece": [
        {"label": "Foosha Village (East Blue civilian)", "location": "Foosha Village", "note": ""},
        {"label": "Shells Town (Marine recruit)", "location": "Shells Town", "note": "Starting posted as a Marine recruit at Shells Town."},
        {"label": "Goa Kingdom (kingdom-born)", "location": "Goa Kingdom", "note": "Starting life in the Goa Kingdom."},
    ],
    "Hunter x Hunter": [
        {"label": "Whale Island (rural start)", "location": "Whale Island", "note": ""},
        {"label": "Yorknew City (urban start)", "location": "Yorknew City", "note": "Starting in the streets of Yorknew City."},
        {"label": "Hunter Exam Site (already an applicant)", "location": "Hunter Exam Site", "note": "Already en route to sit the Hunter Exam."},
    ],
    "Naruto": [
        {"label": "Konohagakure", "location": "Konohagakure", "note": ""},
        {"label": "Sunagakure", "location": "Sunagakure", "note": "A shinobi of Sunagakure, the Hidden Sand Village."},
        {"label": "Kirigakure", "location": "Kirigakure", "note": "A shinobi of Kirigakure, the Hidden Mist Village."},
        {"label": "Kumogakure", "location": "Kumogakure", "note": "A shinobi of Kumogakure, the Hidden Cloud Village."},
        {"label": "Iwagakure", "location": "Iwagakure", "note": "A shinobi of Iwagakure, the Hidden Stone Village."},
        {"label": "Akatsuki (Amegakure)", "location": "Amegakure", "note": "Starting already recruited into the Akatsuki, an international criminal organization operating out of Amegakure — not affiliated with any Hidden Village."},
        {"label": "Iron Country", "location": "Iron Country", "note": "A samurai-in-training of Iron Country — chakra plays little part in daily life here; skill is earned through the blade and discipline, not jutsu."},
    ],
}


def start_options_for(world):
    return WORLD_START_OPTIONS.get(world, [])


BASE_STATE = {
    "name":"Traveler","age":"","position":"","world":"Custom World","difficulty":"Adventurer","background":"","custom_world":"","race":"","calendar_epoch":"","calendar_anchor_day":None,"last_protagonist_tick_day":None,"active_canon_event":"","player_identity":{"mode":"original","canon_character_id":"","canon_gravity":True},
    "level":1,"xp":0,"xp_next":100,"hp":100,"hp_max":100,"resource_name":"Energy","resource":100,"resource_max":100,
    "stats":{"Strength":10,"Dexterity":10,"Constitution":10,"Intelligence":10,"Wisdom":10,"Charisma":10},"hidden_stats":{},
    "skills":{},"titles":[],"inventory":[],"equipment":{},"quests":[],"relationships":{},"reputation":{},
    "factions":{},"affiliations":[],"companions":[],"codex":[],"location":"Starting Region","discovered_locations":[],"custom_locations":[],
    "tower_floor":1,"tower_floor_deadline_day":None,"tower_over":False,"canon_event_engagement_count":0,"background_world_feed":[],
    "last_major_beat_day":None,"director_notes":"","simulation_scale":"Individual",
    "world_time":"Day 1 — Morning","status":[],"alive":True,"turn":0,"timeline":[],"special":{},
    "canon_divergences":[],"campaign_canon":[],"world_events":[],"currency":{"name":"Currency","amount":250},"currencies":{},"npc_memories":{},"shops":[],"known_recipes":[],"training_log":[],"combat":{},"active_encounters":[],"hidden_quests":[],"quest_archive":[],"achievements":[],"world_clock_minutes":480,"location_details":{},"travel_history":[],"loot_history":[],"ability_progress":{},"contacts":{},"chat_threads":{},"unread_chats":[],"group_chats":{},"time_mode":"moment","queued_actions":[],"standing_orders":[],"time_skip_history":[],"current_activity":None,"calendar":{"day":1,"month":1,"year":1,"hour":8,"minute":0},"scheduled_events":[],"long_term_projects":[],"appearance_desc":"","portrait_traits":[],"portrait_identity":{"locked":False,"canonical_description":"","temporary_traits":[],"history":[],"reference_file":""},"campaign_id":"","campaign_created_version":"","campaign_last_saved_version":"","schema_version":6,"world_pack_id":"builtin","last_autosave":"","suggested_actions":[],"advisor_thread":[],"prerequisite_tracks":[],"continuity_ledger":{"facts":[],"warnings":[],"last_checked_turn":0},"validation_log":[],"diagnostics":{},"weather":"clear","canon_day":-7,"canon_time_minutes":-9600,"canon_anchor":"","canon_events_fired":[],"pending_minor_events":[],"minutes_since_status_window":0,"status_window_due":False,"progression_log":[],"starting_power_band":"Average","starting_power_notice":"","chapter_summaries":[],"chapter_buffer":[],"npc_clocks":{},"faction_clocks":{},"difficulty_controls":{},"progression_preset":{},"planned_route":[],"lore_sources":[]
}

WORLD_EXPANSIONS = {
    "One Piece": {
        "currency":"Berries", "currency_baseline":5000,
        "origins":["East Blue Civilian","Island Martial Artist","Dockworker","Bounty-Hunter Trainee","Runaway Noble","Aspiring Pirate","Marine Recruit",
                   "Veteran Crew Member","Notorious Bounty-Head"],
        "archetypes":["Brawler","Swordsman","Marksman","Navigator","Shipwright","Medic","Roguish Fighter"],
        "training":["Physical Conditioning","Weapon Mastery","Observation Drills","Armament Conditioning","Navigation","Seamanship"],
        "shop_types":["General Store","Weapon Shop","Ship Supply","Tavern","Black Market"],
        "loot":["Berries","Rations","Weapon Materials","Log Pose Lead","Rare Ingredient","Treasure Map Fragment"],
        "encounters":["Bandit Crew","Pirate Scouts","Marine Patrol","Sea Beast","Bounty Hunter","Island Wildlife"],
        "systems":["Bounty","Haki","Devil Fruit","Crew","Ship","Wanted Status"]
    },
    "Hunter x Hunter": {
        "currency":"Jenny", "currency_baseline":3000,
        "origins":["Yorknew Local","Rural Prodigy","Martial-Arts Student","Street Survivor","Merchant Family","Exam Aspirant",
                   "Licensed Hunter","Veteran Hunter"],
        "archetypes":["Martial Artist","Tracker","Strategist","Infiltrator","Medic","Treasure Hunter","Information Broker"],
        "training":["Ten Practice","Zetsu Practice","Ren Endurance","Gyo Focus","Combat Conditioning","Hatsu Theory"],
        "shop_types":["General Market","Auction Contact","Martial-Arts Supplier","Information Broker","Hunter Shop"],
        "loot":["Jenny","Medical Supplies","Auction Lead","Rare Material","Hunter Intel","Training Notes"],
        "encounters":["Exam Rival","Criminal Crew","Wild Beast","Arena Fighter","Mafia Enforcer","Nen User"],
        "systems":["Nen Category","Aura","Ten","Zetsu","Ren","Hatsu","Hunter License"]
    },
    "Naruto": {
        "currency":"Ryo", "currency_baseline":500,
        "origins":["Civilian Academy Hopeful","Shinobi Clan Child","Orphan Trainee","Merchant Family","Border-Village Youth","Academy Graduate",
                   "Uchiha Clan Child","Iron Country Samurai-in-Training","Rogue Ninja (Missing-nin)","Anbu Root Recruit",
                   "Chunin on Active Duty","Jonin Squad Leader"],
        "archetypes":["Taijutsu Specialist","Ninjutsu Student","Genjutsu Student","Scout","Medic","Weapon Specialist","Tactician","Samurai"],
        "training":["Chakra Control","Tree Walking","Water Walking","Taijutsu Drills","Shurikenjutsu","Nature Transformation"],
        "shop_types":["Ninja Tools","General Store","Medic Supplies","Scroll Shop","Black Market"],
        "loot":["Ryo","Kunai","Shuriken","Explosive Tags","Medic Supplies","Technique Notes"],
        "encounters":["Bandits","Rogue Ninja","Wildlife","Rival Genin","Missing-nin Scouts","Enemy Patrol"],
        "systems":["Chakra","Nature Affinity","Jutsu","Rank","Village Standing","Mission Record"]
    },
    "Solo Max-Level Newbie": {
        "currency":"Coins", "currency_baseline":300,
        "origins":["Veteran Gamer","Competitive Raider","Puzzle Specialist","Martial Artist","Streamer","Ordinary Survivor","Elite Ranker"],
        "archetypes":["All-Rounder","Melee","Ranged","Caster","Assassin","Tank","Support"],
        "training":["Stat Optimization","Weapon Mastery","Mana Control","Skill Repetition","Boss Pattern Study","Hidden-Condition Research"],
        "shop_types":["Tower Shop","Player Market","Artifact Broker","Potion Merchant","Secret Merchant"],
        "loot":["Coins","Potions","Skill Stone","Artifact Fragment","Monster Core","Hidden-Key Fragment"],
        "encounters":["Goblin Pack","Elite Monster","Rival Player","Floor Guardian","Trap Room","Hidden Boss"],
        "systems":["Floor","Stats","Skills","Copied Abilities","Achievements","Hidden Conditions","Artifacts"]
    },
    "Overgeared": {
        "currency":"Gold", "currency_baseline":200,
        "origins":["New Player","Crafter","Mercenary Player","Merchant","Blacksmith Apprentice","Quest Hunter","Veteran Adventurer","Renowned Craftsman"],
        "archetypes":["Warrior","Swordsman","Archer","Mage","Assassin","Blacksmith","Support"],
        "training":["Weapon Proficiency","Blacksmithing","Crafting","Skill Grinding","Stat Training","NPC Affinity"],
        "shop_types":["Smithy","General Store","Auction House","Potion Shop","Guild Market"],
        "loot":["Gold","Ore","Crafting Material","Recipe","Equipment","Quest Item"],
        "encounters":["Field Monsters","Bandits","Rival Players","Dungeon Mob","Elite Monster","Boss"],
        "systems":["Class","Crafting","Item Rating","Guild","NPC Affinity","Reputation"]
    },
    "Custom World": {
        "currency":"Currency", "currency_baseline":250,
        "origins":["Local","Traveler","Soldier","Scholar","Outcast","Artisan"],
        "archetypes":["Warrior","Scout","Scholar","Mage","Rogue","Healer"],
        "training":["Physical Training","Weapon Training","Study","Meditation","Crafting","Social Practice"],
        "shop_types":["General Store","Weapon Shop","Apothecary","Market","Specialist"],
        "loot":["Currency","Supplies","Equipment","Crafting Material","Clue","Rare Item"],
        "encounters":["Bandits","Wildlife","Rival","Patrol","Elite Enemy","Boss"],
        "systems":["Level","Skills","Reputation","Titles"]
    },
    "Reincarnated as a Slime": {
        "currency":"Gold Coin", "currency_baseline":150,
        "origins":["Reincarnated Otherworlder","Native Monster","Isekai'd Human","Orphaned Demi-Human","Failed Hero Candidate","Displaced Noble",
                   "Veteran Tempest Officer","Named Monster of Renown"],
        "archetypes":["Brawler Monster","Skill Analyst","Elementalist","Beast-kin Warrior","Diplomat/Leader","Support/Healer","Assassin-type Monster"],
        "training":["Magicule Circulation","Skill Synthesis Practice","Combat Instinct Drills","Insight Meditation","Leadership & Diplomacy","Elemental Control"],
        "shop_types":["Goblin Village Market","Dwarven Craftsmen","Blumund Trade Post","Black Market Artifacts","Tempest Bazaar"],
        "loot":["Gold Coin","Magic Crystal","Monster Core","Dwarven-forged Gear","Rare Ingredient","Demon Lord Insignia"],
        "encounters":["Rogue Monster","Human Adventurer Party","Demon Lord Subordinate","Orc Lord Remnant","Bandit Crew","Awakened Beast"],
        "systems":["Named Skills","Evolution","Magicule Capacity","Demon Lord Seed","Nation Reputation"]
    }
}

def expansion_for(world):
    return WORLD_EXPANSIONS.get(world, WORLD_EXPANSIONS["Custom World"])


# Each world rolls checks against its OWN named abilities instead of being
# forced through generic D&D stats — a Naruto check calls on Taijutsu/
# Ninjutsu/Genjutsu, not raw STR/INT. These names are used directly as the
# state.stats dict keys, as the GM's roll-schema enum, and as the Attributes
# panel labels — one source of truth for "what this world's checks are about."
WORLD_ABILITIES = {
    "One Piece": ["Strength", "Agility", "Endurance", "Willpower", "Instinct", "Charisma"],
    "Hunter x Hunter": ["Strength", "Agility", "Aura Control", "Cunning", "Willpower", "Charisma"],
    "Naruto": ["Taijutsu", "Ninjutsu", "Genjutsu", "Chakra Control", "Willpower", "Intellect"],
    "Solo Max-Level Newbie": ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Luck"],
    "Overgeared": ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Luck"],
    "Custom World": ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"],
    "Reincarnated as a Slime": ["Magicule Control", "Skill Mastery", "Instinct", "Insight", "Willpower", "Presence"],
}

# "full_sheet" worlds are status-window/LitRPG genres where the classic
# stat sheet — including stats the player hasn't discovered yet — is a core
# genre convention. "narrative" worlds just show their named abilities plainly.
WORLD_STAT_STYLE = {
    "One Piece": "narrative",
    "Hunter x Hunter": "narrative",
    "Naruto": "narrative",
    "Solo Max-Level Newbie": "full_sheet",
    "Overgeared": "full_sheet",
    "Custom World": "full_sheet",
    "Reincarnated as a Slime": "narrative",
}

# Numbered XP/levels remain available only where the source world presents
# them as a literal in-fiction system. Narrative worlds progress through
# open-ended attributes, techniques, knowledge, ranks and titles instead.
WORLD_XP_MODE = {"Solo Max-Level Newbie": True, "Overgeared": True}


def uses_xp_for(world):
    return bool(WORLD_XP_MODE.get(world, False))

# How much itemization matters to this world. "full" worlds (gear-driven
# LitRPGs) show the whole equipped set; "weapon_only" worlds only surface
# the character's signature weapon/held item, not a full loadout.
WORLD_GEAR_STYLE = {
    "One Piece": "weapon_only",
    "Hunter x Hunter": "weapon_only",
    "Naruto": "weapon_only",
    "Solo Max-Level Newbie": "full",
    "Overgeared": "full",
    "Custom World": "full",
    "Reincarnated as a Slime": "weapon_only",
}


def abilities_for(world):
    return WORLD_ABILITIES.get(world, WORLD_ABILITIES["Custom World"])


def gear_style_for(world):
    return WORLD_GEAR_STYLE.get(world, "full")


# A character who has already chosen to specialize should not start
# statistically identical to everyone else. Each archetype gets a primary
# (and sometimes secondary) ability from that world's own ability set that
# starts noticeably higher — applied on top of a randomized, non-flat
# baseline in game.new_campaign's stat rolling.
ARCHETYPE_PRIMARY_STAT = {
    "One Piece": {
        "Brawler": ["Strength"], "Swordsman": ["Agility", "Strength"], "Marksman": ["Instinct", "Agility"],
        "Navigator": ["Instinct", "Willpower"], "Shipwright": ["Endurance", "Strength"],
        "Medic": ["Willpower", "Instinct"], "Roguish Fighter": ["Agility", "Instinct"],
    },
    "Hunter x Hunter": {
        "Martial Artist": ["Strength", "Agility"], "Tracker": ["Cunning", "Agility"],
        "Strategist": ["Cunning", "Willpower"], "Infiltrator": ["Agility", "Cunning"],
        "Medic": ["Willpower", "Cunning"], "Treasure Hunter": ["Cunning", "Agility"],
        "Information Broker": ["Charisma", "Cunning"],
    },
    "Naruto": {
        "Taijutsu Specialist": ["Taijutsu"], "Ninjutsu Student": ["Ninjutsu"], "Genjutsu Student": ["Genjutsu"],
        "Scout": ["Intellect", "Chakra Control"], "Medic": ["Chakra Control", "Intellect"],
        "Weapon Specialist": ["Taijutsu", "Chakra Control"], "Tactician": ["Intellect", "Willpower"],
    },
    "Solo Max-Level Newbie": {
        "All-Rounder": ["Strength", "Dexterity", "Intelligence"], "Melee": ["Strength", "Constitution"],
        "Ranged": ["Dexterity", "Wisdom"], "Caster": ["Intelligence", "Wisdom"], "Assassin": ["Dexterity", "Luck"],
        "Tank": ["Constitution", "Strength"], "Support": ["Wisdom", "Intelligence"],
    },
    "Overgeared": {
        "Warrior": ["Strength", "Constitution"], "Swordsman": ["Dexterity", "Strength"],
        "Archer": ["Dexterity", "Wisdom"], "Mage": ["Intelligence", "Wisdom"], "Assassin": ["Dexterity", "Luck"],
        "Blacksmith": ["Strength", "Constitution"], "Support": ["Wisdom", "Intelligence"],
    },
    "Custom World": {
        "Warrior": ["Strength", "Constitution"], "Scout": ["Dexterity", "Wisdom"], "Scholar": ["Intelligence"],
        "Mage": ["Intelligence", "Wisdom"], "Rogue": ["Dexterity", "Charisma"], "Healer": ["Wisdom", "Intelligence"],
    },
    "Reincarnated as a Slime": {
        "Brawler Monster": ["Instinct", "Magicule Control"], "Skill Analyst": ["Insight", "Skill Mastery"],
        "Elementalist": ["Magicule Control", "Skill Mastery"], "Beast-kin Warrior": ["Instinct", "Willpower"],
        "Diplomat/Leader": ["Presence", "Willpower"], "Support/Healer": ["Insight", "Presence"],
        "Assassin-type Monster": ["Instinct", "Insight"],
    },
}


def primary_stats_for(world, archetype):
    return ARCHETYPE_PRIMARY_STAT.get(world, {}).get(archetype, [])


# Whether a world's named abilities draw from the world resource pool
# (Chakra/Mana/Aura/Magicule/Stamina/Energy) when used, or run on a cooldown
# instead. Every world here defaults to pool-based costs — jutsu cost
# Chakra, Solo Max-Level Newbie skills cost Mana, Nen/Hatsu cost Aura, named
# skills cost Magicule — except Overgeared, which by genre convention splits
# combat Skills (cooldown-gated, no mana cost) from Spells/Magic
# (mana-gated); see ability_resource_type_for.
WORLD_DEFAULT_ABILITY_RESOURCE = {
    "Overgeared": "cooldown",
}


# Speed and defense analogs per world, used by the local combat resolver to
# turn a large stat mismatch into a real tactical swing — extra attacks for
# a decisive speed edge, damage negation for a decisive defense edge — the
# same way MASSIVE_GAP_THRESHOLD turns a decisive offense edge into a much
# bigger hit. Independent of POOL_STATS (which sizes HP/resource pools):
# these are specifically "how quick" and "how tough in a fight" for a
# world's genre, and deliberately distinct from each other and from the
# archetype's primary offense stat so the three axes can pull apart.
WORLD_SPEED_STAT = {
    "One Piece": "Agility", "Hunter x Hunter": "Agility", "Naruto": "Taijutsu",
    "Solo Max-Level Newbie": "Dexterity", "Overgeared": "Dexterity",
    "Reincarnated as a Slime": "Instinct", "Custom World": "Dexterity",
}
WORLD_DEFENSE_STAT = {
    "One Piece": "Endurance", "Hunter x Hunter": "Willpower", "Naruto": "Willpower",
    "Solo Max-Level Newbie": "Constitution", "Overgeared": "Constitution",
    "Reincarnated as a Slime": "Willpower", "Custom World": "Constitution",
}


def speed_stat_for(world):
    return WORLD_SPEED_STAT.get(world, "Dexterity")


def defense_stat_for(world):
    return WORLD_DEFENSE_STAT.get(world, "Constitution")


def ability_resource_type_for(world, archetype=""):
    """Default resource_type for a skill that hasn't explicitly tagged one
    (see the skill-authoring rules in engine_core.gm_rules). Overgeared's
    Mage archetype is the one common case where a character's *default*
    combat ability is actually a mana-spending Spell rather than a
    cooldown Skill, so it gets its own default; everything else falls back
    to the world-level default above."""
    if world == "Overgeared" and archetype == "Mage":
        return "pool"
    return WORLD_DEFAULT_ABILITY_RESOURCE.get(world, "pool")


def stat_style_for(world):
    return WORLD_STAT_STYLE.get(world, "full_sheet")


# Load user-installed worlds after every built-in registry exists. Invalid
# packs are isolated and reported through /api/world-packs.
import os as _os
from pathlib import Path as _Path
from world_packs import load_world_packs as _load_world_packs

_pack_root = _Path(_os.getenv("APPDATA") or _Path.home()) / "WorldwalkerRPG" / "world_packs"
WORLD_PACKS_LOADED, WORLD_PACK_ERRORS = _load_world_packs(_pack_root, {
    "data": WORLD_DATA, "expansions": WORLD_EXPANSIONS, "abilities": WORLD_ABILITIES,
    "stat_style": WORLD_STAT_STYLE, "gear_style": WORLD_GEAR_STYLE,
    "starts": WORLD_START_OPTIONS, "timelines": CANON_TIMELINES,
    "primary": ARCHETYPE_PRIMARY_STAT, "characters": MAJOR_CHARACTER_STARTS,
})
