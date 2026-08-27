"""Durable two-player rooms for the private friend server.

The campaign engine remains authoritative for the shared world.  This module
owns membership, per-player plans/readiness, character snapshots, heartbeats,
and the ten-minute round clock.  Keeping those facts in SQLite means a browser
refresh, phone sleep, or server restart cannot reset the turn.
"""
from __future__ import annotations

import copy
import json
import secrets
import sqlite3
import string
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROUND_SECONDS = 10 * 60
CONNECTED_SECONDS = 45
MAX_PLAYERS = 2


def _now():
    return datetime.now(timezone.utc)


def _stamp(value=None):
    return (value or _now()).isoformat(timespec="seconds")


def _parse(value):
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return datetime.fromtimestamp(0, timezone.utc)


CHARACTER_FIELDS = {
    "name", "age", "race", "origin", "archetype", "position", "background",
    "appearance", "appearance_desc", "location", "sublocation", "status",
    "conditions", "current_activity", "stats", "hidden_stats", "skills",
    "titles", "inventory", "equipment", "special", "class_profile", "hp",
    "hp_max", "resource", "resource_max", "level", "xp", "xp_next", "alive",
    "portrait_identity", "portrait_traits", "growth_profile", "affiliations",
}


def character_from_state(state, name=""):
    character = {key: copy.deepcopy(state.get(key)) for key in CHARACTER_FIELDS if key in state}
    if name:
        character["name"] = str(name).strip()[:80]
    return character


def new_friend_character(state, name, background=""):
    """Create a conservative world-valid second protagonist without an AI call."""
    character = character_from_state(state, name or "Second Traveler")
    character["background"] = str(background or "A newly arrived ally whose history will be established through play.")[:3000]
    character["appearance"] = ""
    character["appearance_desc"] = ""
    character["position"] = "Player Character"
    character["current_activity"] = "Joining the shared journey"
    # The main game models visible status effects as a list.  Keeping the
    # joined character on that contract prevents renderers from treating a
    # plain string as a collection of status entries.
    character["status"] = ["Normal"]
    character["conditions"] = []
    character["titles"] = []
    character["inventory"] = []
    character["equipment"] = {}
    character["affiliations"] = []
    # Keep the world's stat vocabulary and sensible starting scale, but do not
    # clone the original hero's earned end-game power into a newly joined PC.
    source_stats = state.get("stats", {}) if isinstance(state.get("stats"), dict) else {}
    character["stats"] = {key: max(1, min(60, int(value or 1))) for key, value in source_stats.items()}
    character["skills"] = {}
    character["special"] = {}
    character["class_profile"] = {}
    max_hp = max(20, min(300, int(state.get("hp_max", 100) or 100)))
    max_resource = max(20, min(300, int(state.get("resource_max", 100) or 100)))
    character.update({"hp": max_hp, "hp_max": max_hp, "resource": max_resource,
                      "resource_max": max_resource, "level": 1, "xp": 0,
                      "xp_next": 100, "alive": True})
    character.pop("portrait_identity", None)
    character.pop("portrait_traits", None)
    return character


def player_view(shared_state, character, queued_actions):
    view = copy.deepcopy(shared_state)
    for key, value in (character or {}).items():
        if key in CHARACTER_FIELDS:
            view[key] = copy.deepcopy(value)
    if isinstance(view.get("status"), str):
        view["status"] = [view["status"]] if view["status"] else []
    view["queued_actions"] = list(queued_actions or [])
    return view


def apply_character_update(character, patch):
    clean = copy.deepcopy(character or {})
    if not isinstance(patch, dict):
        return clean
    for key, value in patch.items():
        if key not in CHARACTER_FIELDS:
            continue
        if key in {"hp", "hp_max", "resource", "resource_max", "level", "xp", "xp_next"}:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                clean[key] = int(value)
        elif key in {"stats", "hidden_stats", "skills", "equipment", "special", "class_profile", "portrait_identity", "growth_profile"}:
            if isinstance(value, dict):
                clean[key] = copy.deepcopy(value)
        elif key in {"titles", "inventory", "conditions", "affiliations", "status"}:
            if isinstance(value, list):
                clean[key] = copy.deepcopy(value[:500])
        elif key == "alive":
            if isinstance(value, bool):
                clean[key] = value
        elif isinstance(value, (str, int, float)) or value is None:
            clean[key] = copy.deepcopy(value)
    clean["hp_max"] = max(1, int(clean.get("hp_max", 100) or 100))
    clean["resource_max"] = max(1, int(clean.get("resource_max", 100) or 100))
    clean["hp"] = max(0, min(clean["hp_max"], int(clean.get("hp", clean["hp_max"]) or 0)))
    clean["resource"] = max(0, min(clean["resource_max"], int(clean.get("resource", clean["resource_max"]) or 0)))
    return clean


class MultiplayerStore:
    def __init__(self, account_store):
        self.accounts = account_store
        self.root = Path(account_store.root) / "multiplayer"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = account_store.db_path
        self._schema_lock = threading.Lock()
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=15000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self._schema_lock, self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS multiplayer_rooms (
                    id TEXT PRIMARY KEY,
                    join_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    host_user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    save_name TEXT NOT NULL DEFAULT 'shared_campaign',
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    round_number INTEGER NOT NULL DEFAULT 1,
                    round_deadline TEXT NOT NULL,
                    time_amount INTEGER NOT NULL DEFAULT 1,
                    time_unit TEXT NOT NULL DEFAULT 'moment',
                    intensity TEXT NOT NULL DEFAULT 'normal',
                    resolving INTEGER NOT NULL DEFAULT 0,
                    last_result_round INTEGER NOT NULL DEFAULT 0,
                    last_result_json TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS multiplayer_members (
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'player',
                    character_json TEXT NOT NULL DEFAULT '{}',
                    ready INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    joined_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY(room_id, user_id),
                    FOREIGN KEY(room_id) REFERENCES multiplayer_rooms(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS multiplayer_actions (
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    action_index INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    PRIMARY KEY(room_id, user_id, round_number, action_index),
                    FOREIGN KEY(room_id) REFERENCES multiplayer_rooms(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_multiplayer_active ON multiplayer_members(user_id, active);
                CREATE INDEX IF NOT EXISTS idx_multiplayer_deadline ON multiplayer_rooms(status, resolving, round_deadline);
            """)

    def room_root(self, room_id):
        if not str(room_id).replace("-", "").isalnum():
            raise ValueError("Invalid multiplayer room.")
        root = self.root / str(room_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _join_code(self, db):
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(30):
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if not db.execute("SELECT 1 FROM multiplayer_rooms WHERE join_code=?", (code,)).fetchone():
                return code
        raise RuntimeError("Could not allocate a multiplayer invite code.")

    def create_room(self, user, bundle):
        state = bundle.get("state") if isinstance(bundle, dict) else None
        if not isinstance(state, dict):
            raise ValueError("Start, load, or import a campaign before creating multiplayer.")
        room_id = uuid.uuid4().hex
        now = _now()
        with self._connect() as db:
            db.execute("UPDATE multiplayer_members SET active=0 WHERE user_id=?", (user["id"],))
            code = self._join_code(db)
            db.execute("""INSERT INTO multiplayer_rooms
                (id,join_code,host_user_id,title,created_at,round_deadline)
                VALUES(?,?,?,?,?,?)""",
                (room_id, code, user["id"], f"{state.get('name', 'Traveler')} · {state.get('world', 'World')}",
                 _stamp(now), _stamp(now + timedelta(seconds=ROUND_SECONDS))))
            db.execute("""INSERT INTO multiplayer_members
                (room_id,user_id,username,role,character_json,ready,active,joined_at,last_seen_at)
                VALUES(?,?,?,?,?,0,1,?,?)""",
                (room_id, user["id"], user["username"], "host",
                 json.dumps(character_from_state(state), ensure_ascii=False), _stamp(now), _stamp(now)))
        target = self.room_root(room_id) / "shared_campaign.json"
        clean_bundle = copy.deepcopy(bundle)
        clean_bundle["save_kind"] = "multiplayer"
        clean_bundle["multiplayer_room_id"] = room_id
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(clean_bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(target)
        return self.status(room_id, user["id"], heartbeat=False)

    def join_room(self, user, code, character_name="", background=""):
        now = _now()
        with self._connect() as db:
            room = db.execute("SELECT * FROM multiplayer_rooms WHERE join_code=? COLLATE NOCASE AND status='active'", (str(code or "").strip(),)).fetchone()
            if not room:
                raise ValueError("That multiplayer invite code is not active.")
            existing = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? AND user_id=?", (room["id"], user["id"])).fetchone()
            count = db.execute("SELECT COUNT(*) FROM multiplayer_members WHERE room_id=?", (room["id"],)).fetchone()[0]
            if not existing and count >= MAX_PLAYERS:
                raise ValueError("That campaign already has two players.")
            db.execute("UPDATE multiplayer_members SET active=0 WHERE user_id=?", (user["id"],))
            if existing:
                db.execute("UPDATE multiplayer_members SET active=1,last_seen_at=? WHERE room_id=? AND user_id=?", (_stamp(now), room["id"], user["id"]))
            else:
                bundle = json.loads((self.room_root(room["id"]) / "shared_campaign.json").read_text(encoding="utf-8"))
                character = new_friend_character(bundle.get("state", {}), character_name or user["username"], background)
                db.execute("""INSERT INTO multiplayer_members
                    (room_id,user_id,username,role,character_json,ready,active,joined_at,last_seen_at)
                    VALUES(?,?,?,?,?,0,1,?,?)""",
                    (room["id"], user["id"], user["username"], "player",
                     json.dumps(character, ensure_ascii=False), _stamp(now), _stamp(now)))
        return self.status(room["id"], user["id"], heartbeat=False)

    def active_room(self, user_id):
        with self._connect() as db:
            row = db.execute("""SELECT r.* FROM multiplayer_rooms r
                JOIN multiplayer_members m ON m.room_id=r.id
                WHERE m.user_id=? AND m.active=1 AND r.status='active' LIMIT 1""", (user_id,)).fetchone()
        return dict(row) if row else None

    def member(self, room_id, user_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? AND user_id=?", (room_id, user_id)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["character"] = json.loads(data.pop("character_json") or "{}")
        return data

    def actions(self, room_id, user_id, round_number=None):
        with self._connect() as db:
            if round_number is None:
                round_number = db.execute("SELECT round_number FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()[0]
            rows = db.execute("""SELECT action FROM multiplayer_actions
                WHERE room_id=? AND user_id=? AND round_number=? ORDER BY action_index""",
                (room_id, user_id, int(round_number))).fetchall()
        return [row["action"] for row in rows]

    def queue_action(self, room_id, user_id, text):
        action = str(text or "").strip()
        if not action:
            raise ValueError("Type an action before adding it to the queue.")
        if len(action) > 800:
            raise ValueError("Queued actions must be under 800 characters each.")
        with self._connect() as db:
            room = db.execute("SELECT round_number,resolving FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["resolving"]:
                raise ValueError("The shared turn is currently resolving.")
            next_index = db.execute("""SELECT COALESCE(MAX(action_index),-1)+1 FROM multiplayer_actions
                WHERE room_id=? AND user_id=? AND round_number=?""", (room_id, user_id, room["round_number"])).fetchone()[0]
            if next_index >= 50:
                raise ValueError("A player can queue at most 50 actions per round.")
            db.execute("INSERT INTO multiplayer_actions VALUES(?,?,?,?,?)", (room_id, user_id, room["round_number"], next_index, action))
            db.execute("UPDATE multiplayer_members SET ready=0,last_seen_at=? WHERE room_id=? AND user_id=?", (_stamp(), room_id, user_id))
        return self.actions(room_id, user_id)

    def replace_actions(self, room_id, user_id, actions):
        clean = [str(x).strip()[:800] for x in (actions or []) if str(x).strip()][:50]
        with self._connect() as db:
            room = db.execute("SELECT round_number,resolving FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["resolving"]:
                raise ValueError("The shared turn is currently resolving.")
            db.execute("DELETE FROM multiplayer_actions WHERE room_id=? AND user_id=? AND round_number=?", (room_id, user_id, room["round_number"]))
            db.executemany("INSERT INTO multiplayer_actions VALUES(?,?,?,?,?)",
                           [(room_id, user_id, room["round_number"], index, action) for index, action in enumerate(clean)])
            db.execute("UPDATE multiplayer_members SET ready=0,last_seen_at=? WHERE room_id=? AND user_id=?", (_stamp(), room_id, user_id))
        return clean

    def remove_action(self, room_id, user_id, index):
        actions = self.actions(room_id, user_id)
        index = int(index)
        if index < 0 or index >= len(actions):
            raise IndexError("Queued action no longer exists.")
        actions.pop(index)
        return self.replace_actions(room_id, user_id, actions)

    def update_action(self, room_id, user_id, index, text):
        actions = self.actions(room_id, user_id)
        index = int(index)
        if index < 0 or index >= len(actions):
            raise IndexError("Queued action no longer exists.")
        actions[index] = str(text or "").strip()
        return self.replace_actions(room_id, user_id, actions)

    def move_action(self, room_id, user_id, index, to_index):
        actions = self.actions(room_id, user_id)
        index, to_index = int(index), int(to_index)
        if index < 0 or index >= len(actions):
            raise IndexError("Queued action no longer exists.")
        action = actions.pop(index)
        actions.insert(max(0, min(to_index, len(actions))), action)
        return self.replace_actions(room_id, user_id, actions)

    def set_ready(self, room_id, user_id, ready):
        with self._connect() as db:
            db.execute("UPDATE multiplayer_members SET ready=?,last_seen_at=? WHERE room_id=? AND user_id=?",
                       (1 if ready else 0, _stamp(), room_id, user_id))
        return self.status(room_id, user_id, heartbeat=False)

    def set_time(self, room_id, user_id, amount, unit, intensity):
        allowed = {"moment", "hours", "days", "weeks", "months", "next_event"}
        unit = str(unit or "moment")
        if unit not in allowed:
            raise ValueError("Invalid time unit.")
        amount = 1 if unit in {"moment", "next_event"} else max(1, min(999, int(amount or 1)))
        intensity = str(intensity or "normal")
        if intensity not in {"light", "normal", "intense", "extreme"}:
            intensity = "normal"
        with self._connect() as db:
            room = db.execute("SELECT host_user_id FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["host_user_id"] != user_id:
                raise ValueError("Only the host chooses the shared time advance.")
            db.execute("UPDATE multiplayer_rooms SET time_amount=?,time_unit=?,intensity=? WHERE id=?",
                       (amount, unit, intensity, room_id))
        return self.status(room_id, user_id, heartbeat=False)

    def leave(self, room_id, user_id):
        with self._connect() as db:
            room = db.execute("SELECT host_user_id FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room:
                return
            if room["host_user_id"] == user_id:
                db.execute("UPDATE multiplayer_rooms SET status='closed' WHERE id=?", (room_id,))
                db.execute("UPDATE multiplayer_members SET active=0,ready=0 WHERE room_id=?", (room_id,))
            else:
                db.execute("UPDATE multiplayer_members SET active=0,ready=0 WHERE room_id=? AND user_id=?", (room_id, user_id))

    def status(self, room_id, user_id, heartbeat=True, since_round=None):
        now = _now()
        with self._connect() as db:
            if heartbeat:
                db.execute("UPDATE multiplayer_members SET last_seen_at=? WHERE room_id=? AND user_id=?", (_stamp(now), room_id, user_id))
            room = db.execute("SELECT * FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            membership = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? AND user_id=?", (room_id, user_id)).fetchone()
            if not room or not membership:
                return {"active": False}
            rows = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? ORDER BY CASE role WHEN 'host' THEN 0 ELSE 1 END, joined_at", (room_id,)).fetchall()
            members = []
            for row in rows:
                character = json.loads(row["character_json"] or "{}")
                connected = (now - _parse(row["last_seen_at"])).total_seconds() <= CONNECTED_SECONDS
                members.append({"user_id": row["user_id"], "username": row["username"], "role": row["role"],
                                "character_name": character.get("name", row["username"]), "ready": bool(row["ready"]),
                                "connected": connected, "is_you": row["user_id"] == user_id})
            deadline = _parse(room["round_deadline"])
            result = {
                "active": room["status"] == "active" and bool(membership["active"]),
                "room_id": room["id"], "join_code": room["join_code"], "title": room["title"],
                "is_host": room["host_user_id"] == user_id, "round": int(room["round_number"]),
                "deadline": room["round_deadline"], "seconds_left": max(0, int((deadline - now).total_seconds())),
                "resolving": bool(room["resolving"]), "time_amount": int(room["time_amount"]),
                "time_unit": room["time_unit"], "intensity": room["intensity"], "members": members,
                "your_actions": self.actions(room_id, user_id, room["round_number"]),
                "your_ready": bool(membership["ready"]), "last_result_round": int(room["last_result_round"]),
                "last_error": room["last_error"],
            }
            if since_round is not None and int(room["last_result_round"]) > int(since_round or 0):
                result["result"] = json.loads(room["last_result_json"] or "{}")
            return result

    def resolution_plan(self, room_id):
        now = _now()
        with self._connect() as db:
            room = db.execute("SELECT * FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["status"] != "active":
                return None
            rows = db.execute("SELECT * FROM multiplayer_members WHERE room_id=? ORDER BY joined_at", (room_id,)).fetchall()
            participants, orders = [], []
            for row in rows:
                character = json.loads(row["character_json"] or "{}")
                connected = (now - _parse(row["last_seen_at"])).total_seconds() <= CONNECTED_SECONDS
                actions = self.actions(room_id, row["user_id"], room["round_number"])
                acts = bool(row["ready"] and connected)
                participant = {"user_id": row["user_id"], "username": row["username"],
                               "character": character, "ready": bool(row["ready"]),
                               "connected": connected, "actions": actions if acts else [], "passes": not acts}
                participants.append(participant)
                if acts:
                    for action in actions:
                        orders.append(f"{character.get('name', row['username'])}: {action}")
            if not orders:
                orders = ["All player characters pass and take no deliberate action during this moment."]
            return {"room": dict(room), "participants": participants, "orders": orders}

    def all_connected_ready(self, room_id):
        plan = self.resolution_plan(room_id)
        connected = [p for p in (plan or {}).get("participants", []) if p["connected"]]
        return len(connected) >= 2 and all(p["ready"] for p in connected)

    def claim(self, room_id, force=False):
        now = _now()
        with self._connect() as db:
            room = db.execute("SELECT * FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room or room["status"] != "active" or room["resolving"]:
                return False
            if not force and _parse(room["round_deadline"]) > now:
                return False
            changed = db.execute("UPDATE multiplayer_rooms SET resolving=1,last_error='' WHERE id=? AND resolving=0", (room_id,)).rowcount
        return bool(changed)

    def due_rooms(self):
        with self._connect() as db:
            rows = db.execute("SELECT id FROM multiplayer_rooms WHERE status='active' AND resolving=0 AND round_deadline<=?", (_stamp(),)).fetchall()
        return [row["id"] for row in rows]

    def save_characters(self, room_id, characters):
        with self._connect() as db:
            for user_id, character in characters.items():
                db.execute("UPDATE multiplayer_members SET character_json=? WHERE room_id=? AND user_id=?",
                           (json.dumps(character, ensure_ascii=False), room_id, user_id))

    def save_character(self, room_id, user_id, character):
        self.save_characters(room_id, {user_id: character})

    def complete(self, room_id, result):
        compact = {key: copy.deepcopy(result.get(key)) for key in (
            "status", "narrative", "interrupted", "died", "elapsed", "interruption_reason",
            "interruption_kind", "intervention_prompt", "major_event_reached", "major_event_title",
            "notifications", "story", "updates", "rolls") if key in result}
        with self._connect() as db:
            room = db.execute("SELECT round_number FROM multiplayer_rooms WHERE id=?", (room_id,)).fetchone()
            if not room:
                return
            completed_round = int(room["round_number"])
            next_round = completed_round + 1
            db.execute("""UPDATE multiplayer_rooms SET round_number=?,round_deadline=?,resolving=0,
                last_result_round=?,last_result_json=?,last_error='' WHERE id=?""",
                (next_round, _stamp(_now() + timedelta(seconds=ROUND_SECONDS)), completed_round,
                 json.dumps(compact, ensure_ascii=False, separators=(",", ":")), room_id))
            db.execute("UPDATE multiplayer_members SET ready=0 WHERE room_id=?", (room_id,))
            db.execute("DELETE FROM multiplayer_actions WHERE room_id=? AND round_number<=?", (room_id, completed_round))

    def fail(self, room_id, error):
        with self._connect() as db:
            db.execute("UPDATE multiplayer_rooms SET resolving=0,round_deadline=?,last_error=? WHERE id=?",
                       (_stamp(_now() + timedelta(seconds=60)), str(error)[:500], room_id))
