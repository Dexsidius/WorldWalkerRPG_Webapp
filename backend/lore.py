"""Small offline lore retrieval layer.

The game cannot silently browse the web from a packaged EXE. Instead it keeps
structured, source-conscious lore notes for the setting's important systems
and retrieves only the entries relevant to the current action. Additional JSON
packs can be placed in assets/lore without changing engine code.
"""
import json
import re
import copy
from pathlib import Path
from util import DATA_DIR, safe_filename

LORE_DIR = Path(__file__).resolve().parent.parent / "assets" / "lore"
USER_LORE_DIR = DATA_DIR / "lore"
USER_LORE_DIR.mkdir(parents=True, exist_ok=True)

# Higher-ranked evidence wins when two sources make incompatible claims.
# This is intentionally explicit instead of assuming every imported file is
# equally trustworthy merely because it contains confident prose.
SOURCE_AUTHORITY = {
    "official_source": 100, "official_reference": 95, "licensed_reference": 90,
    "curated": 82, "wiki": 65, "forum": 42, "fan_analysis": 38,
    "imported": 55, "custom": 50, "unknown": 30,
}

_LORE_CACHE = {}
_LORE_CACHE_STATS = {"hits": 0, "misses": 0, "generation": 0}

BUILTIN_LORE = {
    "One Piece": [
        {"title":"Haki", "keys":"haki observation armament conqueror advanced coating future sight ryuo", "text":"Haki is trained willpower. Observation and Armament are broadly learnable through awakening, focused training, battle and instruction. Conqueror's Haki requires the rare inborn disposition; advanced applications require exceptional mastery and circumstances."},
        {"title":"Devil Fruits", "keys":"devil fruit ability awakening sea water seastone copy obtain", "text":"A Devil Fruit grants one unique power to one living user at a time. Eating another normally kills the user under accepted world rules; seawater and Seastone weaken users. Awakening demands deep synchronization and mastery, not XP alone."},
        {"title":"Rokushiki and combat arts", "keys":"rokushiki six powers soru geppo tekkai rankyaku shigan kami-e fishman karate", "text":"Rokushiki techniques and other martial schools are learnable physical disciplines when the player finds knowledge or a teacher and develops the required body. Faction secrecy can obstruct access but is not metaphysical exclusivity."},
        {"title":"Ships, navigation and world government", "keys":"ship sail navigator grand line log pose marine bounty government island", "text":"Grand Line travel requires appropriate navigation, supplies and often a Log Pose. Marines, pirates and governments respond to witnessed deeds; bounties measure perceived threat and notoriety, not a simple power level."},
    ],
    "Hunter x Hunter": [
        {"title":"Nen foundations", "keys":"nen aura ten zetsu ren hatsu awaken initiation", "text":"Nen is learnable by living beings with aura nodes, usually through training in Ten, Zetsu, Ren and Hatsu. Forced initiation is dangerous. Talent changes speed, not the basic possibility of learning."},
        {"title":"Nen categories", "keys":"enhancement emission transmutation conjuration manipulation specialization category water divination", "text":"A user's natural category shapes efficiency. Neighboring categories are easier; distant categories lose efficiency. Specialist abilities are exceptional and cannot be claimed merely by preference, though rare transformation or conditions can alter outcomes."},
        {"title":"Vows and limitations", "keys":"vow restriction condition covenant judgment chain power cost", "text":"Self-imposed restrictions can magnify Nen in proportion to genuine risk and resolve. A cosmetic promise grants little; severe enforceable limitations can produce extreme power and equally severe consequences."},
        {"title":"Hunter access", "keys":"hunter exam license association heavens arena greed island dark continent", "text":"Hunter privileges require passing the Exam or gaining equivalent access through the living world. Heaven's Arena, Greed Island, criminal networks and restricted frontiers each impose independent entry requirements."},
    ],
    "Naruto": [
        {"title":"Chakra and nature transformation", "keys":"chakra nature fire wind lightning earth water affinity transformation", "text":"Chakra combines physical and spiritual energy. Most shinobi have a natural elemental affinity but can train additional natures with greater effort; advanced transformations demand control, knowledge and time."},
        {"title":"Jutsu learning", "keys":"jutsu learn copy sharingan scroll teacher hand signs forbidden technique", "text":"Ordinary techniques can be learned through instruction, scrolls, observation and training. Copying does not bypass body, chakra, bloodline or comprehension requirements. Forbidden techniques remain possible but carry their stated costs and access risks."},
        {"title":"Bloodlines and dōjutsu", "keys":"kekkei genkai bloodline sharingan byakugan rinnegan wood release dojutsu transplant", "text":"Hereditary abilities require compatible biology, inheritance or a lore-valid transplant/experiment. Transplants can impose severe chakra and rejection costs. Training alone cannot simply manufacture a bloodline with no causal route."},
        {"title":"Ranks and village systems", "keys":"academy genin chunin jonin hokage mission village clan rank", "text":"Ranks and offices are social institutions earned through exams, appointments, reputation and politics. A player may diverge from canon and attain any office if its actual requirements and opposition are overcome."},
    ],
    "Solo Max-Level Newbie": [
        {"title":"Tower systems", "keys":"tower floor administrator scenario hidden condition achievement reward", "text":"Floors have explicit scenarios, administrators, hidden conditions and rewards. Knowledge can exploit them, but rewards still require satisfying the actual condition before its deadline."},
        {"title":"Copied abilities", "keys":"copy ability skill condition unique power", "text":"Ability copying follows the character's acquired skill and its stated conditions. It cannot copy outside those limits, but any demonstrated copy is reproducible when the same trigger and capacity are present."},
        {"title":"Artifacts and progression", "keys":"artifact item level stat mana boss raid", "text":"Artifacts, stats and skills are mechanically persistent. High-tier rewards require their encounter, achievement, ownership and compatibility conditions; foreknowledge changes the route, not the requirement."},
    ],
    "Overgeared": [
        {"title":"Classes and hidden classes", "keys":"class hidden class pagma successor quest satisfy", "text":"Classes arise through System-recognized choices, quests and items. A canon hidden class is not reserved by narrative privilege, but unique items or one-holder conditions may require reaching it first or causing a divergent route."},
        {"title":"Crafting", "keys":"craft forge blacksmith item rating legendary myth production mastery", "text":"Crafting quality depends on recipe knowledge, materials, tools, stats, mastery, time and inspiration. Legendary results are possible through the same mechanics demonstrated in-world, not arbitrary GM permission."},
        {"title":"NPC affinity and politics", "keys":"npc affinity guild kingdom lord reputation", "text":"Satisfy's NPCs are persistent people. Affinity, offices, territories and alliances follow relationships, achievements and politics; player status does not force compliance."},
    ],
    "Reincarnated as a Slime": [
        {"title":"Magicules and skills", "keys":"magicule skill extra unique ultimate great sage predator evolve", "text":"Skills emerge from desire, experience, naming, evolution and world-system synthesis. Unique and Ultimate Skills demand extraordinary causes; a demonstrated effect is possible if an equivalent causal path and capacity exist."},
        {"title":"Naming and evolution", "keys":"name naming monster evolve goblin ogre kijin magicules", "text":"Naming transfers magicules and can trigger monster evolution. The cost scales with the target and can exhaust or endanger the namer; mass naming requires exceptional reserves or recovery support."},
        {"title":"Demon Lord awakening", "keys":"demon lord seed harvest festival souls awakening", "text":"True Demon Lord awakening requires a valid seed plus the setting's soul/Harvest Festival conditions. Reputation or strength alone does not substitute, but a divergent player may fulfill those conditions."},
        {"title":"Resistances and analysis", "keys":"resistance immunity analysis great sage raphael consume predator", "text":"Resistance, analysis and absorption must come from acquired skills, species traits or evolution. Analysis does not grant knowledge beyond available observations and capabilities."},
    ],
    "Custom World": [
        {"title":"Setting consistency", "keys":"power magic technology learn copy ability rule", "text":"Treat demonstrated capabilities as reproducible when the custom world's stated prerequisites are met. Establish new restrictions consistently and record them in the codex rather than inventing one-off denials."},
    ],
}

_external_cache = None

def _external_entries():
    global _external_cache
    if _external_cache is not None:
        return _external_cache
    _external_cache = {}
    for directory in (LORE_DIR, USER_LORE_DIR):
      if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for world, entries in data.items():
                        if isinstance(entries, list):
                            for raw in entries:
                                if isinstance(raw, dict):
                                    entry = dict(raw)
                                    entry.setdefault("source", path.name)
                                    entry.setdefault("source_type", "imported")
                                    _external_cache.setdefault(world, []).append(entry)
            except Exception:
                continue
    return _external_cache


def reload_lore():
    _LORE_CACHE.clear()
    _LORE_CACHE_STATS["generation"] += 1
    global _external_cache
    _external_cache = None


def list_lore_sources():
    sources = [{"name": "Built-in Worldwalker notes", "kind": "builtin", "path": str(LORE_DIR),
                "source_type": "curated", "authority": SOURCE_AUTHORITY["curated"],
                "entries": sum(len(value) for value in BUILTIN_LORE.values())}]
    for path in sorted(USER_LORE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            count = sum(len(v) for v in data.values() if isinstance(v, list)) if isinstance(data, dict) else 0
            all_entries = [entry for values in data.values() if isinstance(values, list) for entry in values if isinstance(entry, dict)] if isinstance(data, dict) else []
            types = sorted(set(str(entry.get("source_type") or "imported") for entry in all_entries))
            sources.append({"name": path.name, "kind": "imported", "path": str(path), "entries": count,
                            "source_types": types, "authority": max([SOURCE_AUTHORITY.get(t, 30) for t in types] or [55]),
                            "worlds": [k for k, v in data.items() if isinstance(v, list)] if isinstance(data, dict) else []})
        except Exception as exc:
            sources.append({"name": path.name, "kind": "invalid", "path": str(path), "entries": 0, "error": str(exc)[:180]})
    return sources


def import_lore_pack(filename, raw, world="Custom World"):
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Lore files must be 2 MB or smaller.")
    suffix = Path(filename or "lore.json").suffix.lower()
    text = raw.decode("utf-8-sig")
    if suffix == ".json":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("A JSON lore pack must map world names to lists of entries.")
        cleaned = {}
        for world_name, entries in data.items():
            if not isinstance(entries, list): continue
            valid = []
            for entry in entries[:500]:
                if not isinstance(entry, dict) or not str(entry.get("text", "")).strip(): continue
                source_type = str(entry.get("source_type") or entry.get("kind") or "imported").lower().strip()
                if source_type not in SOURCE_AUTHORITY: source_type = "unknown"
                claims = entry.get("claims") if isinstance(entry.get("claims"), dict) else {}
                valid.append({"title": str(entry.get("title") or "Imported lore")[:160],
                              "keys": str(entry.get("keys") or entry.get("keywords") or "")[:1000],
                              "text": str(entry.get("text"))[:8000],
                              "source": str(entry.get("source") or filename)[:500],
                              "source_type": source_type,
                              "citation": str(entry.get("citation") or entry.get("url") or "")[:1000],
                              "claims": {str(k)[:160]: str(v)[:1000] for k, v in claims.items()}})
            if valid: cleaned[str(world_name)[:120]] = valid
        if not cleaned: raise ValueError("The lore pack contained no usable entries with text.")
    elif suffix in {".md", ".txt"}:
        body = text.strip()
        if not body: raise ValueError("The lore file is empty.")
        title = next((line.lstrip("# ").strip() for line in body.splitlines() if line.strip()), Path(filename).stem)
        keywords = " ".join(re.findall(r"[A-Za-z0-9'-]{4,}", body[:5000])[:80])
        cleaned = {world: [{"title": title[:160], "keys": keywords[:1000], "text": body[:8000], "source": filename,
                            "source_type": "imported", "citation": "", "claims": {}}]}
    else:
        raise ValueError("Import JSON, Markdown, or plain-text lore files.")
    stem = safe_filename(Path(filename or "lore_pack").stem) or "lore_pack"
    target = USER_LORE_DIR / f"{stem}.json"
    index = 2
    while target.exists():
        target = USER_LORE_DIR / f"{stem}_{index}.json"; index += 1
    target.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    reload_lore()
    return {"name": target.name, "path": str(target), "entries": sum(len(v) for v in cleaned.values()), "worlds": list(cleaned)}

def _normalized_entry(entry, default_source="Source not recorded", default_type="unknown"):
    row = dict(entry)
    row["source"] = str(row.get("source") or default_source)
    row["source_type"] = str(row.get("source_type") or default_type).lower()
    row["authority"] = SOURCE_AUTHORITY.get(row["source_type"], SOURCE_AUTHORITY["unknown"])
    row["citation"] = str(row.get("citation") or row.get("url") or "")
    row["claims"] = row.get("claims") if isinstance(row.get("claims"), dict) else {}
    return row


def detect_lore_conflicts(entries):
    """Resolve explicit claim conflicts while retaining the losing evidence."""
    claims = {}
    for entry in entries:
        for key, value in entry.get("claims", {}).items():
            claims.setdefault(str(key).strip().lower(), []).append((str(value).strip(), entry))
    conflicts = []
    for claim, rows in claims.items():
        values = {value.lower() for value, _ in rows if value}
        if len(values) <= 1:
            continue
        ranked = sorted(rows, key=lambda row: (-row[1].get("authority", 0), row[1].get("source", "")))
        winner_value, winner = ranked[0]
        conflicts.append({"claim": claim, "resolution": winner_value, "authority": winner.get("authority", 0),
                          "source": winner.get("source", "Unknown"), "source_type": winner.get("source_type", "unknown"),
                          "alternatives": [{"value": value, "source": entry.get("source", "Unknown"),
                                            "source_type": entry.get("source_type", "unknown"), "authority": entry.get("authority", 0)}
                                           for value, entry in ranked[1:] if value.lower() != winner_value.lower()]})
    return conflicts


def all_lore_entries(world):
    entries = [_normalized_entry(entry, "Built-in Worldwalker notes", "curated") for entry in BUILTIN_LORE.get(world, BUILTIN_LORE["Custom World"])]
    entries.extend(_external_entries().get(world, []))
    return [_normalized_entry(entry, entry.get("source", "Imported lore"), entry.get("source_type", "imported")) for entry in entries]


def _cache_key(world, query, state, limit):
    location = str((state or {}).get("location", "")).strip().lower()
    skills = (state or {}).get("skills", {})
    skill_names = sorted(str(x).lower() for x in (skills.keys() if isinstance(skills, dict) else skills if isinstance(skills, list) else []))[:30]
    # Narrative wording varies wildly while retrieval meaning usually does
    # not. A normalized keyword key lets repeated questions/actions reuse the
    # same ranked evidence without retaining any campaign secrets globally.
    terms = sorted(set(re.findall(r"[a-z0-9'-]{3,}", str(query or "").lower())))[:40]
    return (str(world), tuple(terms), location, tuple(skill_names), int(limit), _LORE_CACHE_STATS["generation"])


def retrieve_lore(world, query, state=None, limit=5):
    key = _cache_key(world, query, state, limit)
    if key in _LORE_CACHE:
        _LORE_CACHE_STATS["hits"] += 1
        return copy.deepcopy(_LORE_CACHE[key])
    _LORE_CACHE_STATS["misses"] += 1
    entries = all_lore_entries(world)
    query_blob = " ".join([str(query or ""), str((state or {}).get("location", "")), " ".join((state or {}).get("skills", {}).keys())]).lower()
    terms = set(re.findall(r"[a-z0-9'-]+", query_blob))
    ranked = []
    for index, entry in enumerate(entries):
        hay = f"{entry.get('title','')} {entry.get('keys','')} {entry.get('text','')}".lower()
        score = sum(3 if term in str(entry.get("keys", "")).lower() else 1 for term in terms if len(term) > 2 and term in hay)
        # Relevance dominates; authority breaks close calls and determines
        # conflict resolution. A forum can still surface when it is the only
        # relevant source, but it cannot silently overrule official material.
        ranked.append((score, entry.get("authority", 0), -index, entry))
    ranked.sort(reverse=True, key=lambda row: (row[0], row[1], row[2]))
    selected = [entry for score, _, _, entry in ranked if score > 0][:limit]
    if not selected:
        selected = [entry for _, _, _, entry in ranked[:min(2, limit)]]
    _LORE_CACHE[key] = copy.deepcopy(selected)
    # Bound memory even across very long sessions with many free-form queries.
    if len(_LORE_CACHE) > 256:
        _LORE_CACHE.pop(next(iter(_LORE_CACHE)))
    return copy.deepcopy(selected)

def format_lore_context(world, query, state=None, limit=5):
    entries = retrieve_lore(world, query, state, limit=limit)
    if not entries:
        return ""
    conflicts = detect_lore_conflicts(entries)
    lines = ["RETRIEVED LORE EVIDENCE (ranked by source authority; preserve uncertainty and never blend incompatible claims):"]
    lines.extend(f"- {entry.get('title','Lore')} [{entry.get('source_type','unknown')} {entry.get('authority',0)}/100 · {entry.get('source','Source not recorded')}{' · ' + entry.get('citation') if entry.get('citation') else ''}]: {entry.get('text','')}" for entry in entries)
    if conflicts:
        lines.append("SOURCE CONFLICTS — use the authoritative resolution below and treat alternatives as disputed:")
        lines.extend(f"- {row['claim']}: {row['resolution']} ({row['source']}); disputed by " + ", ".join(x['source'] for x in row['alternatives']) for row in conflicts)
    return "\n".join(lines)


def lore_library_status(world=None, query=""):
    worlds = [world] if world else list(BUILTIN_LORE)
    entries = []
    for world_name in worlds:
        entries.extend(all_lore_entries(world_name))
    conflicts = detect_lore_conflicts(entries)
    return {"authority_scale": SOURCE_AUTHORITY, "conflicts": conflicts,
            "entry_count": len(entries), "highest_authority": max([e.get("authority", 0) for e in entries] or [0]),
            "cache": {**_LORE_CACHE_STATS, "entries": len(_LORE_CACHE)}}
