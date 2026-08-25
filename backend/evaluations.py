"""Opt-in, repeatable quality evaluations for the configured narrator model."""
import copy
import json
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

from lore import format_lore_context
from util import DATA_DIR


EVAL_DIR = DATA_DIR / "evaluations"


def _evaluation_dir():
    try:
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        return EVAL_DIR
    except OSError:
        # Read-only/test sandboxes should not make the whole application
        # unimportable merely because optional evaluation history cannot use
        # the normal roaming-data folder.
        fallback = Path(tempfile.gettempdir()) / "WorldwalkerRPG_evaluations"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

EVALUATION_SCENARIOS = [
    {"id": "queued_actions", "name": "Multiple queued actions", "world": "Naruto",
     "action": "Travel to the training ground; ask Iruka about chakra control; practice until sunset.",
     "state": {"location": "Konohagakure", "world_time": "Morning", "stats": {"Chakra Control": 38}, "skills": {}},
     "must_address": ["travel", "iruka", "practice"], "expected_fields": ["location"], "lore_terms": ["chakra"]},
    {"id": "long_training", "name": "Long training proportionality", "world": "Hunter x Hunter",
     "action": "Train Ten and Ren consistently for thirty days with a qualified mentor.",
     "state": {"location": "Heaven's Arena", "world_time": "Day 12", "stats": {"Aura Control": 42}, "skills": {"Ten": {"rank": "Novice"}}},
     "must_address": ["thirty", "training", "mentor"], "expected_fields": ["skills", "training_log"], "lore_terms": ["nen", "aura"]},
    {"id": "canon_intervention", "name": "Canon intervention", "world": "One Piece",
     "action": "Warn the people of Marineford before the scheduled execution and try to change who arrives.",
     "state": {"location": "Marineford", "active_canon_event": "Portgas D. Ace's execution", "canon_divergences": []},
     "must_address": ["warn", "execution", "consequence"], "expected_fields": ["canon_divergences"], "lore_terms": ["marine"]},
    {"id": "hidden_class", "name": "Concealed hidden class", "world": "Overgeared",
     "action": "Examine the strange crafting intuition without knowing its true class name.",
     "state": {"location": "Winston", "class_profile": {"name": "Unidentified Hidden Class", "true_name": "Ashen Relic Smith", "discovery": {"concealed": True, "progress": 25}}},
     "must_address": ["examine", "clue"], "expected_fields": ["memory_updates"], "forbidden": ["ashen relic smith"]},
    {"id": "difficult_combat", "name": "Difficult combat realism", "world": "Bleach",
     "action": "A barely trained spirit-sensitive human attacks a Menos Grande head-on.",
     "state": {"location": "Karakura Town", "stats": {"Reiatsu Control": 18}, "combat": {}},
     "must_address": ["danger", "failure"], "expected_fields": ["combat", "hp"], "lore_terms": ["spiritual"]},
    {"id": "npc_secrecy", "name": "NPC knowledge boundary", "world": "Reincarnated as a Slime",
     "action": "Speak with a merchant who has never witnessed or heard about my concealed Unique Skill.",
     "state": {"location": "Dwargon", "skills": {"Hidden Devourer": {"hidden": True}},
               "npc_memories": {"Merchant Toma": {"knowledge": {"confirmed": [], "heard": [], "suspected": [], "false_beliefs": []}}}},
     "must_address": ["merchant"], "expected_fields": ["npc_memories"], "forbidden": ["hidden devourer"]},
]


def list_evaluations():
    history = []
    for path in sorted(_evaluation_dir().glob("evaluation_*.json"), reverse=True)[:20]:
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            history.append({"file": path.name, "created_at": row.get("created_at"), "model": row.get("model"),
                            "score": row.get("score"), "scenario_count": len(row.get("results", []))})
        except Exception:
            continue
    return {"scenarios": [{k: v for k, v in row.items() if k not in {"state"}} for row in EVALUATION_SCENARIOS], "history": history}


def _text_blob(value):
    return json.dumps(value, ensure_ascii=False).lower()


def score_evaluation(scenario, response):
    criteria = []
    structured = isinstance(response, dict) and isinstance(response.get("narrative"), str) and isinstance(response.get("state_patch", {}), dict)
    criteria.append({"name": "Structured response", "score": 20 if structured else 0, "max": 20,
                     "detail": "Required narrative and state-patch fields are present." if structured else "Required JSON fields are missing."})
    if not isinstance(response, dict):
        return {"score": 0, "criteria": criteria}
    narrative = str(response.get("narrative") or "")
    clean = 80 <= len(narrative) <= 2400 and not re.search(r"Generated (Ability|Backstory|Class)|\[\s*\{|undefined|null", narrative, re.I)
    criteria.append({"name": "Readable narrative", "score": 20 if clean else 8 if narrative else 0, "max": 20,
                     "detail": "Narrative is readable and free of internal-generation labels." if clean else "Narrative is empty, unusually sized, or exposes internal formatting."})
    blob = _text_blob(response)
    addressed = [term for term in scenario.get("must_address", []) if term.lower() in blob]
    coverage = round(20 * len(addressed) / max(1, len(scenario.get("must_address", []))))
    criteria.append({"name": "Action coverage", "score": coverage, "max": 20,
                     "detail": f"Addressed {len(addressed)} of {len(scenario.get('must_address', []))} required action elements."})
    patch = response.get("state_patch") if isinstance(response.get("state_patch"), dict) else {}
    fields = scenario.get("expected_fields", [])
    present = [field for field in fields if field in patch or field in blob]
    state_score = round(20 * len(present) / max(1, len(fields)))
    forbidden_owned = {"turn", "campaign_canon", "continuity_ledger", "narrative_memory", "progression_ledger"}.intersection(patch)
    if forbidden_owned: state_score = max(0, state_score - 8)
    criteria.append({"name": "State accuracy", "score": state_score, "max": 20,
                     "detail": f"Represented {len(present)} of {len(fields)} expected persistent outcomes" + (f"; illegally authored {', '.join(sorted(forbidden_owned))}." if forbidden_owned else ".")})
    forbidden = [term for term in scenario.get("forbidden", []) if term.lower() in blob]
    lore_found = [term for term in scenario.get("lore_terms", []) if term.lower() in blob]
    lore_score = 0 if forbidden else (20 if not scenario.get("lore_terms") or lore_found else 8)
    criteria.append({"name": "Lore and secrecy", "score": lore_score, "max": 20,
                     "detail": ("No forbidden reveal or lore violation detected." if not forbidden else "Revealed or used forbidden information: " + ", ".join(forbidden))})
    return {"score": sum(row["score"] for row in criteria), "criteria": criteria}


def run_model_evaluation(game, scenario_ids=None, client=None):
    selected_ids = set(scenario_ids or [EVALUATION_SCENARIOS[0]["id"]])
    scenarios = [row for row in EVALUATION_SCENARIOS if row["id"] in selected_ids]
    if not scenarios:
        raise ValueError("Choose at least one known evaluation scenario.")
    if client is None and not game.ai_ready():
        raise RuntimeError("Configure a narrator model before running a live evaluation.")
    client = client or game.make_client(game.settings.get("model", ""))
    before_usage = copy.deepcopy(getattr(client, "usage", {}))
    results = []
    for scenario in scenarios:
        instructions = (
            "You are being evaluated as the Worldwalker RPG narrator. Resolve the isolated scenario without changing any real campaign. "
            "Return one JSON object with narrative, state_patch, events, and suggested_actions. Address every action in order, preserve lore, "
            "respect what NPCs can personally know, and never write application-owned bookkeeping fields.\n\n" +
            format_lore_context(scenario["world"], scenario["action"], scenario["state"])
        )
        payload = {"evaluation": scenario["name"], "world": scenario["world"], "action": scenario["action"],
                   "state": scenario["state"], "required_output": {"narrative": "string", "state_patch": {}, "events": [], "suggested_actions": []}}
        started = time.perf_counter()
        try:
            response = client.request(instructions, payload, timeout=240, max_output_tokens=900)
            scored = score_evaluation(scenario, response)
            results.append({"id": scenario["id"], "name": scenario["name"], "world": scenario["world"],
                            "score": scored["score"], "criteria": scored["criteria"], "duration_seconds": round(time.perf_counter() - started, 2),
                            "response_excerpt": str(response.get("narrative", ""))[:1200] if isinstance(response, dict) else ""})
        except Exception as exc:
            results.append({"id": scenario["id"], "name": scenario["name"], "world": scenario["world"], "score": 0,
                            "criteria": [{"name": "Model call", "score": 0, "max": 100, "detail": str(exc)[:800]}],
                            "duration_seconds": round(time.perf_counter() - started, 2), "error": str(exc)[:1000]})
    usage = getattr(client, "usage", {})
    usage_delta = {key: usage.get(key, 0) - before_usage.get(key, 0) for key in ("calls", "input_tokens", "output_tokens", "cost_usd")}
    report = {"created_at": datetime.now().isoformat(timespec="seconds"), "model": getattr(client, "model", game.settings.get("model", "")),
              "provider": getattr(client, "provider", game.settings.get("provider", "")),
              "score": round(sum(row["score"] for row in results) / len(results)), "results": results, "usage": usage_delta,
              "campaign_mutated": False}
    filename = "evaluation_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json"
    (_evaluation_dir() / filename).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["file"] = filename
    return report
