import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FriendServerRouteTests(unittest.TestCase):
    def test_two_browser_sessions_cannot_see_each_others_campaigns(self):
        script = textwrap.dedent(r"""
            import copy, io, json, sys
            from pathlib import Path
            sys.path.insert(0, str(Path.cwd() / "backend"))
            from app import app
            from worlds import BASE_STATE

            anonymous = app.test_client()
            blocked = anonymous.get("/api/state")
            assert blocked.status_code == 401, blocked.data

            first = app.test_client()
            second = app.test_client()
            first_auth = first.get("/api/auth/session").get_json()
            second_auth = second.get("/api/auth/session").get_json()
            assert first_auth["accounts_enabled"] and not first_auth["authenticated"]

            registered_one = first.post("/api/auth/register", json={"username":"friend_one","password":"password-one"})
            registered_two = second.post("/api/auth/register", json={"username":"friend_two","password":"password-two"})
            assert registered_one.status_code == 201, registered_one.data
            assert registered_two.status_code == 201, registered_two.data
            csrf_one = registered_one.get_json()["csrf_token"]
            csrf_two = registered_two.get_json()["csrf_token"]

            created_one = first.post("/api/campaign/new", json={
                "name":"Friend One Hero", "world":"Naruto", "difficulty":"Adventurer", "background":"A traveling shinobi."
            }, headers={"X-Worldwalker-CSRF":csrf_one})
            created_two = second.post("/api/campaign/new", json={
                "name":"Friend Two Hero", "world":"Bleach", "difficulty":"Adventurer", "background":"A recent academy graduate."
            }, headers={"X-Worldwalker-CSRF":csrf_two})
            assert created_one.status_code == 200 and created_two.status_code == 200
            first.post("/api/actions/queue", json={"action":"Train chakra control"}, headers={"X-Worldwalker-CSRF":csrf_one})
            second.post("/api/actions/queue", json={"action":"Practice Hado"}, headers={"X-Worldwalker-CSRF":csrf_two})
            first_state = first.get("/api/state").get_json()["state"]
            second_state = second.get("/api/state").get_json()["state"]
            assert first_state["name"] == "Friend One Hero" and first_state["world"] == "Naruto"
            assert second_state["name"] == "Friend Two Hero" and second_state["world"] == "Bleach"
            assert first_state["queued_actions"] == ["Train chakra control"]
            assert second_state["queued_actions"] == ["Practice Hado"]

            old_state = copy.deepcopy(BASE_STATE)
            old_state.update(name="Old Save Hero", world="Naruto", turn=33, campaign_created_version="3.6.4")
            bundle = {"version":"3.6.4", "schema_version":7, "state":old_state, "history":[], "story_log":[], "system_log":[]}
            imported = first.post("/api/save/import", data={
                "file": (io.BytesIO(json.dumps(bundle).encode()), "friend-old-save.worldwalker.json")
            }, headers={"X-Worldwalker-CSRF": csrf_one}, content_type="multipart/form-data")
            assert imported.status_code == 200, imported.data
            save_id = imported.get_json()["id"]
            first_saves = first.get("/api/saves").get_json()["saves"]
            second_saves = second.get("/api/saves").get_json()["saves"]
            assert save_id in {item["id"] for item in first_saves}
            assert save_id not in {item["id"] for item in second_saves}
            assert all("Friend Two Hero" not in item.get("label", "") for item in first_saves)
            assert all("Friend One Hero" not in item.get("label", "") for item in second_saves)

            cross_load = second.post("/api/load", json={"name":save_id}, headers={"X-Worldwalker-CSRF":csrf_two})
            assert cross_load.status_code != 200

            changed = first.post("/api/settings", json={"narration":"Detailed"}, headers={"X-Worldwalker-CSRF":csrf_one})
            assert changed.status_code == 200
            assert first.get("/api/settings").get_json()["narration"] == "Detailed"
            assert second.get("/api/settings").get_json()["narration"] != "Detailed"

            logout = first.post("/api/auth/logout", json={}, headers={"X-Worldwalker-CSRF":csrf_one})
            assert logout.status_code == 200
            assert first.get("/api/saves").status_code == 401
            login = first.post("/api/auth/login", json={"username":"friend_one","password":"password-one"})
            assert login.status_code == 200
            assert len(first.get("/api/saves").get_json()["saves"]) >= 1
        """)
        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env.update({
                "WORLDWALKER_DATA_DIR": str(Path(td) / "data"),
                "WORLDWALKER_ACCOUNTS_ENABLED": "1",
                "WORLDWALKER_SECURE_COOKIES": "0",
                "WORLDWALKER_MAX_ACCOUNTS": "10",
            })
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=90,
            )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)


if __name__ == "__main__":
    unittest.main()
