"""Flask application: serves the frontend, game assets, and the JSON API
that the browser-based UI drives the game engine through."""
import io, json, os, secrets, threading, traceback, sys
from urllib.parse import quote
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file

from worlds import APP_VERSION, WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, WORLD_PACKS_LOADED, WORLD_PACK_ERRORS, expansion_for, abilities_for, stat_style_for, start_options_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, starting_eras_for
from util import ASSET_ROOT, DATA_DIR, world_slug, scene_selection_reason
from game import GameSession
from portrait_generator import PORTRAIT_CACHE_DIR, generate_portrait, save_reference, portrait_history, revert_portrait, portrait_usage
from lore import (list_lore_sources, import_lore_pack, import_lore_url, lore_library_status,
                  lore_automation_status, configure_lore_automation, refresh_lore_sources,
                  seed_recommended_lore_sources)
from content_audit import audit_all_worlds
from systems import (normalize_tuning, progression_preset_for, relationship_snapshot,
                     campaign_health, map_snapshot, quest_presentation_for,
                     normalize_quest_state_machine)
from reliability import narrative_memory_snapshot, canon_event_tracker, visible_class_profile, visible_skills
from knowledge import knowledge_snapshot
from causality import causality_snapshot
from simulation_integrity import (integrity_snapshot, campaign_search,
                                  apply_player_correction, build_travel_graph,
                                  travel_route, canon_dependency_graph)
from evaluations import list_evaluations, run_model_comparison, run_model_evaluation
from support import repair_campaign_state, build_diagnostic_bundle

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else BACKEND_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
MUSIC_ROOT = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT_DIR) / "music"
MUSIC_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".ogg", ".wav"}


def ensure_music_folders():
    MUSIC_ROOT.mkdir(parents=True, exist_ok=True)
    for folder in ["Shared", *WORLD_DATA.keys()]:
        (MUSIC_ROOT / folder).mkdir(parents=True, exist_ok=True)
    return MUSIC_ROOT


ensure_music_folders()

app = Flask(__name__, static_folder=None)
app.json.sort_keys = False  # preserve dict insertion order (ability lists, skills, etc. are meaningfully ordered)
game = GameSession()


@app.after_request
def disable_desktop_cache(response):
    """A desktop build must never reuse JS/assets from an older extraction."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Worldwalker-Version"] = APP_VERSION
    return response

_bg_lock = threading.Lock()
_bg_running = False
_bg_pending = []

_busy_lock = threading.Lock()
_evaluation_lock = threading.Lock()
_portrait_lock = threading.Lock()
_lore_refresh_lock = threading.Lock()
_lore_refresh_started = False


def _start_due_lore_refresh_once():
    """Launch one non-blocking due-source pass on app startup/first use."""
    global _lore_refresh_started
    with _lore_refresh_lock:
        if _lore_refresh_started:
            return
        _lore_refresh_started = True
    status = lore_automation_status()
    if not status.get("settings", {}).get("enabled") or not status.get("due"):
        return
    threading.Thread(target=refresh_lore_sources, kwargs={"force": False}, daemon=True,
                     name="worldwalker-lore-refresh").start()


@app.before_request
def start_background_lore_refresh():
    _start_due_lore_refresh_once()


def acquire_busy():
    """Guards against two AI-calling requests racing on the shared GameSession
    (e.g. an accidental double-submit) — first one in wins, the second gets a
    clean 409 instead of corrupting shared state via concurrent apply_resolution."""
    with _busy_lock:
        if game.busy:
            return False
        game.busy = True
        return True


def release_busy():
    game.busy = False


def busy_error():
    return jsonify({"error": "Another AI request is already in progress."}), 409


def err(e, code=500):
    traceback.print_exc()
    return jsonify({"error": str(e)}), code


# ---------- static / frontend ----------
def _render_index():
    """Serve index.html with its CSS/JS hrefs tagged to APP_VERSION.

    A desktop build's own no-store headers only stop the plain HTTP cache —
    they do nothing about a browser engine's Cache Storage / service-worker
    cache, which can keep answering with a snapshot from a much older
    version indefinitely. A version-stamped URL sidesteps the question of
    which cache layer is misbehaving: every cache treats it as a brand new
    resource it has never seen, so there is nothing stale left to serve.
    """
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/css/style.css"', f'href="/css/style.css?v={APP_VERSION}"')
    html = html.replace('src="/js/app.js"', f'src="/js/app.js?v={APP_VERSION}"')
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/")
def index():
    return _render_index()


@app.route("/<path:path>")
def frontend_files(path):
    full = FRONTEND_DIR / path
    if full.exists() and full.is_file():
        return send_from_directory(FRONTEND_DIR, path)
    return _render_index()


@app.route("/assets/<path:path>")
def assets(path):
    return send_from_directory(ASSET_ROOT, path)


@app.route("/music/<path:path>")
def music_file(path):
    return send_from_directory(MUSIC_ROOT, path, conditional=True)


@app.route("/portrait-cache/<path:filename>")
def portrait_cache(filename):
    return send_from_directory(PORTRAIT_CACHE_DIR, filename)


# ---------- world / campaign data ----------
@app.route("/api/version")
def api_version():
    return jsonify({"version": APP_VERSION})


@app.route("/api/worlds")
def api_worlds():
    out = {}
    for name, wd in WORLD_DATA.items():
        ex = expansion_for(name)
        out[name] = {
            "tagline": wd["tagline"], "resource": wd["resource"], "start": wd["start"],
            "origins": ex["origins"], "archetypes": ex["archetypes"], "currency": ex["currency"],
            "abilities": abilities_for(name), "stat_style": stat_style_for(name),
            "start_options": start_options_for(name) or [
                {"label": wd["start"], "location": wd["start"], "note": "Default starting location for this world."}
            ],
            "playable_characters": playable_characters_for(name),
            "starting_eras": starting_eras_for(name) or [{
                "id": "default", "label": "Main story opening",
                "start_day": int(timeline_for(name).get("start_day", -7)),
                "anchor": timeline_for(name).get("anchor", "Shortly before the main story."),
            }],
        }
    return jsonify({"worlds": out, "difficulties": DIFFICULTIES, "order": list(WORLD_DATA.keys())})


@app.route("/api/campaign/new", methods=["POST"])
def api_campaign_new():
    d = request.get_json(force=True)
    try:
        world = d.get("world", "Custom World")
        stats = {k: int(d.get("stats", {}).get(k, 0)) for k in abilities_for(world)}
        state = game.new_campaign(
            name=d.get("name", "Traveler"), world=world,
            difficulty=d.get("difficulty", "Adventurer"), background=d.get("background", ""),
            appearance_desc=d.get("appearance", ""), custom_world=d.get("custom_world", ""),
            origin=d.get("origin", ""), archetype=d.get("archetype", ""), stats=stats,
            start_location=d.get("start_location", ""), start_note=d.get("start_note", ""),
            preview_stats=d.get("preview_stats"),
            preview_profile=d.get("preview_profile"),
            canon_character_id=d.get("canon_character_id", ""),
            starting_era_id=d.get("starting_era_id", ""),
            age=d.get("age", ""),
        )
        return jsonify({"state": state, "story": game._flush_story()})
    except Exception as e:
        return err(e)


@app.route("/api/campaign/preview", methods=["POST"])
def api_campaign_preview():
    d = request.get_json(force=True)
    try:
        preview = game.preview_campaign(
            d.get("name", "Traveler"), d.get("world", "Custom World"), d.get("difficulty", "Adventurer"),
            d.get("background", ""), d.get("appearance", ""), d.get("custom_world", ""),
            d.get("origin", ""), d.get("archetype", ""), d.get("stats", {}),
            d.get("start_location", ""), d.get("start_note", ""),
            d.get("canon_character_id", ""), d.get("starting_era_id", ""),
        )
        return jsonify({"preview": preview})
    except Exception as e:
        return err(e, 400)


@app.route("/api/campaign/preview/reroll", methods=["POST"])
def api_campaign_preview_reroll():
    d = request.get_json(force=True)
    try:
        preview = game.reroll_campaign_preview(
            d.get("preview", {}), d.get("kind", ""), d.get("background", ""),
        )
        return jsonify({"preview": preview})
    except Exception as e:
        return err(e, 400)


@app.route("/api/campaign/opening", methods=["POST"])
def api_campaign_opening():
    if not game.ai_ready():
        return jsonify({"error": "AI not configured. Open Settings and select a model."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = game.opening()
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


# ---------- turn loop ----------
@app.route("/api/state")
def api_state():
    return jsonify({"state": game.public_state(), "busy": game.busy, "campaign_active": game.campaign_active,
                     "ai_ready": game.ai_ready(), "local_mode": game.local_mode()})


@app.route("/api/action/submit", methods=["POST"])
def api_action_submit():
    d = request.get_json(force=True)
    action = (d.get("action") or "").strip()
    if not action:
        return jsonify({"error": "No action given."}), 400
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    try:
        # Legacy endpoint kept for older frontends, but v2.4's contract is
        # strict: submitting plans only queues them. Advance is the sole
        # resolution/time/world-response endpoint.
        return jsonify({"status": "queued", "queued_actions": game.queue_action(action), "state": game.public_state()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/event/respond", methods=["POST"])
def api_event_respond():
    """One beat of an already-active major event — resolved as a scoped,
    ordinary action (no time/calendar movement, no world-clock ticking),
    so the player can go back and forth inside the event for as long as it
    takes without the wider campaign silently simulating forward."""
    d = request.get_json(force=True)
    action = (d.get("action") or "").strip()
    if not action:
        return jsonify({"error": "No action given."}), 400
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    try:
        return jsonify(game.respond_to_event(action))
    except Exception as e:
        return err(e, 400)


@app.route("/api/actions/queue", methods=["POST"])
def api_actions_queue():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    try:
        return jsonify({"queued_actions": game.queue_action((request.get_json(force=True).get("action") or ""))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/actions/remove", methods=["POST"])
def api_actions_remove():
    try:
        return jsonify({"queued_actions": game.remove_queued_action(request.get_json(force=True).get("index", -1))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/combat/state")
def api_combat_state():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    game.ensure_combat_numbers()
    return jsonify({"combat": game.state.get("combat") or {}, "hp": game.state.get("hp"), "hp_max": game.state.get("hp_max"),
                     "resource": game.state.get("resource"), "resource_max": game.state.get("resource_max"),
                     "skills": game.state.get("skills", {})})


@app.route("/api/combat/mercy", methods=["POST"])
def api_combat_mercy():
    """Toggles combat.spare_enemy — a player choice, independent of the AI's
    own combat.non_lethal (spar/test) flag. Sparing the enemy only protects
    THEM from dying to the player's hits; it does nothing for the player's
    own HP, which stays fully at risk if the fight goes the other way."""
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    if not game.combat_active():
        return jsonify({"error": "Not in combat."}), 400
    d = request.get_json(force=True)
    game.state["combat"]["spare_enemy"] = bool(d.get("spare"))
    return jsonify({"combat": game.state["combat"]})


@app.route("/api/combat/action", methods=["POST"])
def api_combat_action():
    """Resolves exactly one exchange locally — no AI call, near-instant.
    Only /api/combat/narrate spends an AI call, and only when asked to."""
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    if not game.combat_active():
        return jsonify({"error": "Not in combat."}), 400
    d = request.get_json(force=True)
    action = (d.get("action") or "attack").strip().lower()
    if action not in ("attack", "defend", "flee", "overwhelm"):
        action = "attack"
    try:
        result = game.resolve_combat_round(action, ability_name=d.get("ability"))
        return jsonify(result)
    except Exception as e:
        return err(e, 400)


@app.route("/api/combat/narrate", methods=["POST"])
def api_combat_narrate():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = game.narrate_combat()
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


@app.route("/api/usage")
def api_usage():
    """Session-total estimated AI spend, for the topbar cost indicator.
    Numbers only get more accurate as calls happen — nothing here is
    predictive, it's a running tally of what's already been spent."""
    main_u, bg_u, major_u, portrait_u = game.ai.usage, game.ai_bg.usage, game.ai_major.usage, portrait_usage()
    unique_clients = list({id(client): client for client in (game.ai, game.ai_bg, game.ai_major)}.values())
    cost_known = not any(client.usage.get("cost_unknown") for client in unique_clients)
    total_cost = sum(client.usage.get("cost_usd", 0.0) for client in unique_clients) + portrait_u.get("cost_usd", 0.0)
    warning_at = max(0.0, float(game.settings.get("session_budget_warning_usd", 0) or 0))
    return jsonify({
        "provider": game.settings.get("provider", "local"),
        "main": main_u, "background": bg_u, "major": major_u, "portraits": portrait_u,
        "major_model": game.settings.get("major_event_model", ""),
        "major_is_separate": game.ai_major is not game.ai,
        "total_cost_usd": round(total_cost, 4),
        "session_budget_warning_usd": warning_at,
        "over_session_budget": bool(warning_at and total_cost >= warning_at),
        "cost_estimate_complete": cost_known,
        "cost_is_conservative": any(client.usage.get("cost_is_conservative") for client in unique_clients),
        "cached_input_tokens": sum(client.usage.get("cached_input_tokens", 0) for client in unique_clients),
        "total_calls": sum(client.usage.get("calls", 0) for client in unique_clients),
    })


@app.route("/api/status_window/dismiss", methods=["POST"])
def api_status_window_dismiss():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    game.state["status_window_due"] = False
    game.autosave()
    return jsonify({"ok": True})


@app.route("/api/action/rewind_death", methods=["POST"])
def api_rewind_death():
    result = game.rewind_death()
    if result is None:
        return jsonify({"error": "No checkpoint available."}), 400
    return jsonify(result)


@app.route("/api/action/undo", methods=["POST"])
def api_undo():
    result = game.undo()
    if result is None:
        return jsonify({"error": "No checkpoint available."}), 400
    return jsonify(result)


# ---------- time skip ----------
@app.route("/api/time/assess", methods=["POST"])
def api_time_assess():
    d = request.get_json(force=True)
    if not game.ai_ready():
        return jsonify({"error": "AI not configured."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = game.assess_time_skip(d.get("amount", 1), d.get("unit", "moment"), d.get("orders", ""),
                                       d.get("intensity", "normal"), use_model=False)
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


@app.route("/api/time/resolve", methods=["POST"])
def api_time_resolve():
    d = request.get_json(force=True)
    if not acquire_busy():
        return busy_error()
    try:
        result = game.run_time_skip(d.get("amount", 1), d.get("unit", "moment"), d.get("orders", []),
                                     d.get("intensity", "normal"), d.get("assessment", {}),
                                     confirmed_lethal=bool(d.get("confirmed_lethal")),
                                     confirmed_power_goal=bool(d.get("confirmed_power_goal")),
                                     manual_rolls=d.get("manual_rolls", {}),
                                     challenge_modes=d.get("challenge_modes", {}),
                                     challenge_resolution_mode=d.get("challenge_resolution_mode", "continue"),
                                     danger_warning_acknowledged=bool(d.get("danger_warning_acknowledged")))
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


@app.route("/api/dice/d100", methods=["POST"])
def api_dice_d100():
    """Server-authored entropy for the animated major-event roll UI."""
    return jsonify({"roll": secrets.randbelow(100) + 1})


# ---------- chat ----------
@app.route("/api/chats")
def api_chats():
    s = game.state
    return jsonify({"contacts": s.get("contacts", {}), "chat_threads": s.get("chat_threads", {}), "unread": s.get("unread_chats", [])})


@app.route("/api/chats/read", methods=["POST"])
def api_chats_read():
    d = request.get_json(force=True)
    thread = d.get("thread")
    game.state["unread_chats"] = [x for x in game.state.get("unread_chats", []) if x.get("thread") != thread]
    game.autosave()
    return jsonify({"ok": True})


@app.route("/api/chats/send", methods=["POST"])
def api_chats_send():
    d = request.get_json(force=True)
    thread, message = d.get("thread"), (d.get("message") or "").strip()
    if not thread or not message:
        return jsonify({"error": "Thread and message are required."}), 400
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = game.resolve_side_chat(thread, message)
        return jsonify(result)
    except Exception as e:
        return err(e, 400)
    finally:
        release_busy()


# ---------- advisor ----------
@app.route("/api/advisor")
def api_advisor_get():
    return jsonify({"thread": game.state.get("advisor_thread", [])})


@app.route("/api/advisor/ask", methods=["POST"])
def api_advisor_ask():
    d = request.get_json(force=True)
    question = (d.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Ask the Advisor something first."}), 400
    if not acquire_busy():
        return busy_error()
    try:
        result = game.ask_advisor(question, fourth_wall=bool(d.get("fourth_wall")))
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        release_busy()


# ---------- background world simulation (non-blocking) ----------
def _run_background_jobs():
    global _bg_running
    try:
        local = game.run_local_background()
        # Economy and Balanced never spend an extra background-model call.
        # Deep mode opts into at most one such call every four resolved
        # turns, alternating communications and wider-world narration.
        if game.background_ai_due():
            if int(game.state.get("turn", 0) or 0) % 8:
                chat = game.maybe_generate_incoming_chat()
                if chat:
                    with _bg_lock:
                        _bg_pending.append({"type": "chat", **chat, "state": game.public_state()})
            else:
                tick = game.create_world_event_if_due()
                if tick and tick.get("heard_event"):
                    with _bg_lock:
                        _bg_pending.append({"type": "world_event", "message": tick["heard_event"], "state": game.public_state()})
        with _bg_lock:
            _bg_pending.append({"type": "maintenance", **local, "state": game.public_state()})
    except Exception:
        traceback.print_exc()
    finally:
        with _bg_lock:
            _bg_running = False


@app.route("/api/background/run", methods=["POST"])
def api_background_run():
    global _bg_running
    with _bg_lock:
        if _bg_running or game.busy:
            return jsonify({"started": False})
        _bg_running = True
    threading.Thread(target=_run_background_jobs, daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/background/poll")
def api_background_poll():
    with _bg_lock:
        items, _bg_pending_local = _bg_pending[:], None
        _bg_pending.clear()
    return jsonify({"events": items})


# ---------- shops / training / codex snapshots (derived, no AI call) ----------
@app.route("/api/panels")
def api_panels():
    s = game.state
    normalize_quest_state_machine(s)
    ex = expansion_for(s.get("world", "Custom World"))
    world = s.get("world", "Custom World")
    world_map = WORLD_DATA.get(world, {}).get("map", [])
    canon_events = timeline_for(world).get("events", [])
    tracker = canon_event_tracker(s, canon_events)
    dependencies = canon_dependency_graph(s)
    if not game.settings.get("canon_foreknowledge", False):
        now = int(s.get("canon_day", -7) or -7)
        secret_keys = {(int(event.get("day", 0) or 0), str(event.get("title", "")))
                       for event in canon_events if event.get("spoiler") and int(event.get("day", 0) or 0) > now}
        def spoiler_safe(rows):
            safe = []
            for raw in rows:
                row = dict(raw)
                if (int(row.get("day", 0) or 0), str(row.get("title", ""))) in secret_keys:
                    row.update(title="Unrevealed future pressure", location="Unknown",
                               summary="Details remain hidden until the campaign can discover them.",
                               requires=[], reason="Character-knowledge mode is hiding future canon spoilers.", replacement="")
                safe.append(row)
            return safe
        canon_events = spoiler_safe(canon_events)
        tracker = spoiler_safe(tracker)
        dependencies = dict(dependencies)
        dependencies["events"] = spoiler_safe(dependencies.get("events", []))
    return jsonify({
        "currency": s.get("currency", {"name": ex["currency"], "amount": 0}),
        "currencies": s.get("currencies", {}),
        "tracks_currency": bool(ex.get("tracks_currency", True)),
        "gear_style": gear_style_for(s.get("world", "Custom World")),
        "shops": s.get("shops", []),
        "shop_types": ex["shop_types"],
        "training_options": ex["training"],
        "ability_progress": s.get("ability_progress", {}),
        "progression_log": s.get("progression_log", []),
        "progression_ledger": s.get("progression_ledger", []),
        "uses_xp": uses_xp_for(s.get("world", "Custom World"), s.get("custom_world", "")),
        "level": s.get("level", 1), "xp": s.get("xp", 0), "xp_next": s.get("xp_next", 100),
        "stats": s.get("stats", {}),
        "quests": s.get("quests", []),
        "quest_presentation": quest_presentation_for(world),
        "hidden_quests_count": len(s.get("hidden_quests", [])),
        "codex": s.get("codex", []),
        "inventory": s.get("inventory", []),
        "equipment": s.get("equipment", {}),
        "companions": s.get("companions", []),
        "titles": s.get("titles", []),
        "skills": visible_skills(s),
        "special": s.get("special", {}),
        "overgeared_system": s.get("overgeared_system", {}),
        "solo_system": s.get("solo_system", {}),
        "class_profile": visible_class_profile(s),
        "combat": s.get("combat", {}),
        "world_events": s.get("world_events", []),
        "timeline": s.get("timeline", []),
        "background_world_feed": s.get("background_world_feed", []),
        "achievements": s.get("achievements", []),
        "map": world_map,
        "map_data": map_snapshot(s, world_map, world),
        "map_image": f"/assets/generated_maps/{world_slug(s.get('world', 'Custom World'))}.webp",
        "world": s.get("world", "Custom World"),
        "discovered_locations": s.get("discovered_locations", []),
        "location": s.get("location", ""),
        "prerequisite_tracks": s.get("prerequisite_tracks", []),
        "canon_day": s.get("canon_day", -7),
        "canon_anchor": s.get("canon_anchor", ""), "calendar_epoch": s.get("calendar_epoch", ""),
        "calendar_anchor_day": s.get("calendar_anchor_day"),
        "canon_events": canon_events,
        "canon_event_tracker": tracker,
        "canon_events_fired": s.get("canon_events_fired", []),
        "scheduled_events": game.visible_schedule(),
        "quest_archive": s.get("quest_archive", []),
        "continuity": s.get("continuity_ledger", {}),
        "campaign_canon": s.get("campaign_canon", []),
        "chapter_summaries": s.get("chapter_summaries", []), "chapter_buffer": s.get("chapter_buffer", []),
        "npc_clocks": s.get("npc_clocks", {}), "faction_clocks": s.get("faction_clocks", {}),
        "relationships_view": relationship_snapshot(s),
        "progression_preset": progression_preset_for(world), "difficulty_controls": normalize_tuning(s),
        "campaign_health": campaign_health(s), "lore_sources": list_lore_sources(),
        "lore_automation": lore_automation_status(s.get("world", "Custom World")),
        "director_notes": s.get("director_notes", ""),
        "narrative_memory": narrative_memory_snapshot(s),
        "npc_knowledge": knowledge_snapshot(s),
        "causality": causality_snapshot(s),
        "lore_status": lore_library_status(s.get("world", "Custom World")),
        "evaluations": list_evaluations(),
        "evaluation_models": [model for model in dict.fromkeys([
            game.settings.get("model", ""), game.settings.get("major_event_model", "")
        ]) if model],
        "simulation": {"profile": game.simulation_profile(),
                       "intentions": s.get("npc_intentions", {}),
                       "campaign_direction": s.get("campaign_direction", {}),
                       "relationship_opportunities": s.get("relationship_opportunities", []),
                       "recent_events": s.get("simulation_events", [])[-40:],
                       "integrity": integrity_snapshot(s)},
        "travel_graph": build_travel_graph(s),
        "canon_dependencies": dependencies,
    })


@app.route("/api/campaign/search")
def api_campaign_search():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    query = str(request.args.get("q") or "").strip()
    return jsonify({"query": query, "results": campaign_search(game.state, query, request.args.get("limit", 30))})


@app.route("/api/campaign/correct", methods=["POST"])
def api_campaign_correct():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    d = request.get_json(force=True)
    if game.state.get("world") == "Bleach" and d.get("type") == "currency":
        return jsonify({"error": "Bleach does not maintain a tracked currency balance."}), 400
    try:
        record = apply_player_correction(game.state, d.get("type"), d.get("target"), d.get("value"), d.get("explanation", ""))
        game.append("[PLAYER CORRECTION]\n" + record["fact"], "meta")
        game.autosave()
        return jsonify({"ok": True, "correction": record, "state": game.public_state(), "story": game._flush_story()})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/travel/route")
def api_travel_route():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    destination = str(request.args.get("destination") or "").strip()
    return jsonify(travel_route(game.state, destination))


@app.route("/api/campaign/tuning", methods=["POST"])
def api_campaign_tuning():
    d = request.get_json(force=True)
    controls = game.state.setdefault("difficulty_controls", {})
    for key in ("check_warning_threshold", "xp_rate", "training_rate", "breakthrough_rate", "combat_danger", "resource_pressure"):
        if key in d: controls[key] = d[key]
    if "director_notes" in d:
        game.state["director_notes"] = str(d["director_notes"] or "")[:500]
    clean = normalize_tuning(game.state)
    game.autosave()
    return jsonify({"difficulty_controls": clean, "state": game.public_state()})


@app.route("/api/lore")
def api_lore_sources():
    return jsonify({"sources": list_lore_sources(), "folder": str(DATA_DIR / "lore"),
                    "status": lore_library_status(game.state.get("world", "Custom World")),
                    "automation": lore_automation_status(game.state.get("world", "Custom World"))})


@app.route("/api/lore/import", methods=["POST"])
def api_lore_import():
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "Choose a JSON, Markdown, or text lore file."}), 400
    try:
        result = import_lore_pack(uploaded.filename or "lore.json", uploaded.read(2 * 1024 * 1024 + 1), request.form.get("world", "Custom World"))
        return jsonify({"imported": result, "sources": list_lore_sources()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/lore/update-url", methods=["POST"])
def api_lore_update_url():
    d = request.get_json(silent=True) or {}
    try:
        result = import_lore_url(
            d.get("url", ""), d.get("world") or game.state.get("world", "Custom World"),
            d.get("source_type", "wiki"), auto_refresh=bool(d.get("auto_refresh", True)),
            discover=bool(d.get("discover", False)),
        )
        return jsonify({"updated": result, "sources": list_lore_sources(),
                        "status": lore_library_status(game.state.get("world", "Custom World")),
                        "automation": lore_automation_status(game.state.get("world", "Custom World"))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/lore/automation", methods=["GET", "POST"])
def api_lore_automation():
    world = game.state.get("world", "Custom World")
    if request.method == "GET":
        return jsonify(lore_automation_status(world))
    try:
        settings = request.get_json(silent=True) or {}
        status = configure_lore_automation(settings)
        if settings.get("enabled") and settings.get("recommended_sources", True):
            seed_recommended_lore_sources()
            status = lore_automation_status(world)
        return jsonify(status)
    except Exception as e:
        return err(e, 400)


@app.route("/api/lore/refresh", methods=["POST"])
def api_lore_refresh():
    d = request.get_json(silent=True) or {}
    try:
        result = refresh_lore_sources(force=bool(d.get("force", True)),
                                      world=d.get("world") or game.state.get("world", "Custom World"))
        return jsonify({"refresh": result, "automation": lore_automation_status(game.state.get("world", "Custom World")),
                        "sources": list_lore_sources(), "status": lore_library_status(game.state.get("world", "Custom World"))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/content-audit")
def api_content_audit():
    return jsonify(audit_all_worlds())


@app.route("/api/quick_action", methods=["POST"])
def api_quick_action():
    d = request.get_json(force=True)
    text = (d.get("text") or "").strip()
    try:
        return jsonify({"status": "queued", "queued_actions": game.queue_action(text), "state": game.public_state()})
    except Exception as e:
        return err(e, 400)

# ---------- settings ----------
@app.route("/api/music")
def api_music():
    ensure_music_folders()
    requested = request.args.get("world") or game.state.get("world", "Custom World")
    world = requested if requested in WORLD_DATA else "Custom World"
    tracks = []
    for folder, source in ((MUSIC_ROOT / world, world), (MUSIC_ROOT / "Shared", "Shared")):
        for file in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
            if file.is_file() and file.suffix.lower() in MUSIC_EXTENSIONS:
                rel = file.relative_to(MUSIC_ROOT).as_posix()
                tracks.append({"name": file.stem, "filename": file.name, "source": source,
                               "url": "/music/" + quote(rel, safe="/")})
    return jsonify({"world": world, "folder": str(MUSIC_ROOT / world), "root": str(MUSIC_ROOT), "tracks": tracks,
                    "supported": sorted(MUSIC_EXTENSIONS)})


@app.route("/api/music/open_folder", methods=["POST"])
def api_music_open_folder():
    ensure_music_folders()
    d = request.get_json(silent=True) or {}
    requested = d.get("world") or game.state.get("world", "Custom World")
    world = requested if requested in WORLD_DATA else "Custom World"
    target = MUSIC_ROOT / world
    if sys.platform == "win32":
        os.startfile(str(target))
    return jsonify({"ok": True, "folder": str(target)})


@app.route("/api/portrait/generate", methods=["POST"])
def api_portrait_generate():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign before generating a portrait."}), 400
    d = request.get_json(silent=True) or {}
    if not _portrait_lock.acquire(blocking=False):
        return jsonify({"error": "A portrait is already being generated."}), 409
    try:
        result = generate_portrait(game.state, game.settings, force=bool(d.get("force")))
        return jsonify(result)
    except Exception as e:
        return err(e)
    finally:
        _portrait_lock.release()


@app.route("/api/portrait/identity", methods=["POST"])
def api_portrait_identity():
    d = request.get_json(force=True)
    identity = game.state.setdefault("portrait_identity", {})
    history = identity.setdefault("history", [])
    history.append({"appearance_desc": game.state.get("appearance_desc", ""),
                    "portrait_traits": list(game.state.get("portrait_traits", [])),
                    "canonical_description": identity.get("canonical_description", ""),
                    "temporary_traits": list(identity.get("temporary_traits", [])),
                    "turn": game.state.get("turn", 0)})
    identity["history"] = history[-20:]
    if "canonical_description" in d:
        identity["canonical_description"] = str(d.get("canonical_description") or "")[:2000]
    if "temporary_traits" in d:
        value = d.get("temporary_traits")
        identity["temporary_traits"] = [str(x)[:300] for x in value] if isinstance(value, list) else []
    if "locked" in d:
        identity["locked"] = bool(d.get("locked"))
    game.autosave()
    return jsonify({"identity": identity, "state": game.public_state()})


@app.route("/api/portrait/reference", methods=["POST"])
def api_portrait_reference():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    uploaded = request.files.get("image")
    if not uploaded:
        return jsonify({"error": "Choose a portrait image first."}), 400
    try:
        result = save_reference(game.state, uploaded.read(12 * 1024 * 1024 + 1))
        game.autosave()
        return jsonify({**result, "state": game.public_state()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/portrait/history")
def api_portrait_history():
    return jsonify({"history": portrait_history(game.state), "identity": game.state.get("portrait_identity", {})})


@app.route("/api/portrait/revert", methods=["POST"])
def api_portrait_revert():
    try:
        return jsonify({**revert_portrait(game.state), "state": game.public_state()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    s = dict(game.settings)
    s.pop("api_key", None)
    s["has_api_key"] = bool(game.settings.get("api_key"))
    return jsonify(s)


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    d = request.get_json(force=True)
    patch = {k: d[k] for k in [
        "provider", "local_base_url", "local_token", "api_key", "model", "secondary_model", "major_event_model",
        "max_ai_cost_per_request_usd", "session_budget_warning_usd",
        "narration", "autosave", "sound_enabled", "music_enabled", "music_volume", "animations_enabled",
        "portrait_generation_enabled", "portrait_auto_generate", "image_model", "local_image_model", "portrait_quality", "developer_mode",
        "onboarding_seen", "simulation_mode", "canon_foreknowledge"
    ] if k in d}
    game.update_settings(patch)
    return jsonify({"ok": True})


@app.route("/api/settings/detect_models", methods=["POST"])
def api_detect_models():
    d = request.get_json(force=True)
    try:
        models = game.detect_models(d.get("base_url", ""), d.get("token", ""))
        return jsonify({"models": models})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------- save / load ----------
@app.route("/api/saves")
def api_saves():
    return jsonify({"saves": game.list_saves()})


@app.route("/api/save", methods=["POST"])
def api_save():
    path = game.save()
    return jsonify({"path": path})


@app.route("/api/save/delete", methods=["POST"])
def api_save_delete():
    try:
        return jsonify(game.delete_save((request.get_json(force=True).get("name") or "")))
    except Exception as e:
        return err(e, 400)


@app.route("/api/save/recover", methods=["POST"])
def api_save_recover():
    try:
        state = game.recover_save(request.get_json(force=True).get("name", ""))
        return jsonify({"state": state, "story": game.story_log})
    except Exception as e:
        return err(e, 400)


@app.route("/api/save/export")
def api_save_export():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign first."}), 400
    raw = json.dumps(game.save_bundle("export"), indent=2, ensure_ascii=False).encode("utf-8")
    filename = world_slug(game.state.get("name", "Traveler") + "_" + game.state.get("world", "World")) + ".worldwalker.json"
    return send_file(io.BytesIO(raw), mimetype="application/json", as_attachment=True, download_name=filename)


@app.route("/api/save/import", methods=["POST"])
def api_save_import():
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "Choose a Worldwalker JSON export."}), 400
    try:
        raw = uploaded.read(15 * 1024 * 1024 + 1)
        if len(raw) > 15 * 1024 * 1024:
            raise ValueError("Campaign exports must be smaller than 15 MB.")
        return jsonify(game.import_bundle(json.loads(raw.decode("utf-8"))))
    except Exception as e:
        return err(e, 400)


@app.route("/api/load", methods=["POST"])
def api_load():
    d = request.get_json(force=True)
    try:
        state = game.load(d.get("name", ""))
        return jsonify({"state": state, "story": game.story_log})
    except Exception as e:
        return err(e)


@app.route("/api/reentry_recap", methods=["POST"])
def api_reentry_recap():
    try:
        result = game.generate_reentry_recap()
        if not result:
            return jsonify({"recap": "", "state": game.public_state(), "story": []})
        return jsonify(result)
    except Exception as e:
        return err(e)


@app.route("/api/quests/note", methods=["POST"])
def api_quest_note():
    d = request.get_json(force=True)
    try:
        return jsonify({"quest": game.quest_note(d.get("name", ""), d.get("note", ""))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/shop/buy", methods=["POST"])
def api_shop_buy():
    d = request.get_json(force=True)
    try:
        return jsonify(game.buy_shop_item(d.get("shop", ""), d.get("item", "")))
    except Exception as e:
        return err(e, 400)


@app.route("/api/purchase_offer/buy", methods=["POST"])
def api_purchase_offer_buy():
    d = request.get_json(force=True)
    try:
        return jsonify(game.buy_purchase_offer(d.get("id", "")))
    except Exception as e:
        return err(e, 400)


@app.route("/api/turn/rate_good", methods=["POST"])
def api_turn_rate_good():
    try:
        return jsonify(game.rate_last_turn_good())
    except Exception as e:
        return err(e, 400)


@app.route("/api/diagnostics")
def api_diagnostics():
    data = game.diagnostics_snapshot()
    data["scene"]["reason"] = scene_selection_reason(game.state)
    data["campaign_health"] = campaign_health(game.state)
    data["npc_knowledge"] = knowledge_snapshot(game.state)
    data["causality"] = causality_snapshot(game.state)
    data["lore_status"] = lore_library_status(game.state.get("world", "Custom World"))
    data["content_audit"] = audit_all_worlds()["summary"]
    return jsonify(data)


@app.route("/api/diagnostics/export")
def api_diagnostics_export():
    data = game.diagnostics_snapshot()
    data["scene"]["reason"] = scene_selection_reason(game.state)
    raw = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    return send_file(io.BytesIO(raw), mimetype="application/json", as_attachment=True, download_name="worldwalker-diagnostics.json")


@app.route("/api/diagnostics/bundle")
def api_diagnostics_bundle():
    return send_file(build_diagnostic_bundle(game), mimetype="application/zip", as_attachment=True,
                     download_name=f"worldwalker-support-{APP_VERSION}.zip")


@app.route("/api/campaign/health/repair", methods=["POST"])
def api_campaign_health_repair():
    if not game.campaign_active:
        return jsonify({"error": "Start or load a campaign before repairing it."}), 400
    d = request.get_json(silent=True) or {}
    try:
        result = repair_campaign_state(game.state, str(d.get("repair_id") or "safe_all"))
        game.autosave()
        return jsonify({"repair": result, "campaign_health": campaign_health(game.state), "state": game.public_state()})
    except Exception as e:
        return err(e, 400)


@app.route("/api/actions/update", methods=["POST"])
def api_actions_update():
    try:
        d = request.get_json(force=True)
        return jsonify({"queued_actions": game.update_queued_action(d.get("index", -1), d.get("action", ""))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/actions/move", methods=["POST"])
def api_actions_move():
    try:
        d = request.get_json(force=True)
        return jsonify({"queued_actions": game.move_queued_action(d.get("index", -1), d.get("to_index", -1))})
    except Exception as e:
        return err(e, 400)


@app.route("/api/evaluations")
def api_evaluations():
    return jsonify(list_evaluations())


@app.route("/api/evaluations/run", methods=["POST"])
def api_evaluations_run():
    if not _evaluation_lock.acquire(blocking=False):
        return jsonify({"error": "A model evaluation is already running."}), 409
    try:
        d = request.get_json(silent=True) or {}
        ids = d.get("scenario_ids") if isinstance(d.get("scenario_ids"), list) else []
        return jsonify(run_model_evaluation(game, ids))
    except Exception as e:
        return err(e, 400)
    finally:
        _evaluation_lock.release()


@app.route("/api/evaluations/compare", methods=["POST"])
def api_evaluations_compare():
    if not _evaluation_lock.acquire(blocking=False):
        return jsonify({"error": "A model evaluation is already running."}), 409
    try:
        d = request.get_json(silent=True) or {}
        ids = d.get("scenario_ids") if isinstance(d.get("scenario_ids"), list) else []
        models = d.get("models") if isinstance(d.get("models"), list) else []
        return jsonify(run_model_comparison(game, models, ids))
    except Exception as e:
        return err(e, 400)
    finally:
        _evaluation_lock.release()


@app.route("/api/world-packs")
def api_world_packs():
    return jsonify({"loaded": WORLD_PACKS_LOADED, "errors": WORLD_PACK_ERRORS,
                    "folder": str(DATA_DIR / "world_packs")})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=True, threaded=True, use_reloader=False)
