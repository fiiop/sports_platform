import os
os.environ["DATABASE_URL"] = "sqlite://"

from datetime import date, timedelta
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, inspect, text
import test_regressions
import test_buddies
from app.models import BuddyMessage, WeeklyReflection
from app.services.migrations import allow_place_only_statuses


class ExperienceBackendTests(unittest.TestCase):
    setUp = test_regressions.RegressionTests.setUp
    tearDown = test_regressions.RegressionTests.tearDown
    login = test_regressions.RegressionTests.login
    record = test_regressions.RegressionTests.record
    plan = test_regressions.RegressionTests.plan
    another = test_buddies.BuddyTests.another
    status = test_buddies.BuddyTests.status

    def chat(self):
        self.login()
        owner = self.status().json()["user_id"]
        other = self.another("other")
        chat_id = other.post(f"/api/buddies/{owner}/chat").json()["id"]
        return owner, other, chat_id

    def test_place_only_status_and_coordinate_pair_validation(self):
        self.login()
        response = self.status(latitude=None, longitude=None)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["latitude"])
        self.assertEqual(self.client.get("/api/buddies").json()[0]["location"], "校体育馆")
        for changes in (dict(latitude=None), dict(longitude=None)):
            self.assertEqual(self.status(**changes).status_code, 422)
        self.assertEqual(self.status().status_code, 200)
        self.assertEqual(self.client.get("/api/buddies/me").json()["latitude"], 31.23)
        data = {"exercise_type": "散步", "location": "图书馆门口", "starts_at": "2099-01-01T10:00:00+08:00"}
        response = self.client.put("/api/buddies/me", json=data)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["longitude"])

    def test_buddy_time_window_is_timezone_aware_and_half_open(self):
        self.login()
        at = "2099-01-01T10:00:00+08:00"
        self.status(starts_at=at)
        query = {"starts_after": "2099-01-01T02:00:00Z", "starts_before": "2099-01-01T03:00:00Z"}
        self.assertEqual(len(self.client.get("/api/buddies", params=query).json()), 1)
        query.update(starts_after="2099-01-01T01:00:00Z", starts_before="2099-01-01T02:00:00Z")
        self.assertEqual(self.client.get("/api/buddies", params=query).json(), [])
        for invalid in ({"starts_after": "2099-01-01T10:00:00"},
                        {"starts_after": at, "starts_before": "2099-01-01T01:00:00Z"}):
            self.assertEqual(self.client.get("/api/buddies", params=invalid).status_code, 422)

    def test_unread_is_private_monotonic_and_only_incoming(self):
        owner, other, chat_id = self.chat()
        base = f"/api/buddy-chats/{chat_id}"
        first = other.post(base + "/messages", json={"body": "第一条"}).json()["id"]
        second = other.post(base + "/messages", json={"body": "第二条"}).json()["id"]
        self.assertEqual(self.client.get("/api/buddy-chats/unread").json()["count"], 2)
        self.assertEqual(other.get("/api/buddy-chats/unread").json()["count"], 0)
        self.assertEqual(self.client.get("/api/buddy-chats").json()[0]["unread_count"], 2)
        self.assertEqual(self.client.post(base + "/read", json={"message_id": second}).json()["message_id"], second)
        self.assertEqual(self.client.post(base + "/read", json={"message_id": first}).json()["message_id"], second)
        self.assertEqual(self.client.post(base + "/read", json={"message_id": 0}).json()["message_id"], second)
        self.assertEqual(self.client.get("/api/buddy-chats/unread").json()["count"], 0)
        other.post(base + "/messages", json={"body": "第三条"})
        self.assertEqual(self.client.get("/api/buddy-chats/unread").json()["count"], 1)
        outsider = self.another("outsider")
        self.assertEqual(outsider.get("/api/buddy-chats/unread").json()["count"], 0)
        self.assertEqual(outsider.post(base + "/read", json={"message_id": second}).status_code, 404)
        foreign_chat = outsider.post(f"/api/buddies/{owner}/chat").json()["id"]
        foreign_message = outsider.post(f"/api/buddy-chats/{foreign_chat}/messages", json={"body": "另一会话"}).json()["id"]
        self.assertEqual(self.client.post(base + "/read", json={"message_id": foreign_message}).status_code, 422)
        self.assertEqual(self.client.post(base + "/read", json={"message_id": 9999999}).status_code, 422)

    def test_conversation_order_follows_activity_not_creation(self):
        owner, other, old_chat = self.chat()
        third = self.another("third")
        new_chat = third.post(f"/api/buddies/{owner}/chat").json()["id"]
        self.assertEqual(self.client.get("/api/buddy-chats").json()[0]["id"], new_chat)
        other.post(f"/api/buddy-chats/{old_chat}/messages", json={"body": "新回复"})
        chats = self.client.get("/api/buddy-chats").json()
        self.assertEqual(chats[0]["id"], old_chat)
        self.assertTrue(chats[0]["last_at"].endswith("Z"))
        self.assertIsNone(chats[1]["last_at"])
        self.assertEqual(len(self.client.get("/api/buddy-chats?offset=1").json()), 1)

    def test_message_history_pages_latest_first_without_duplicates(self):
        owner, other, chat_id = self.chat()
        with self.sessions() as db:
            rows = [BuddyMessage(chat_id=chat_id, sender_id=owner, body=f"消息{i}") for i in range(125)]
            db.add_all(rows)
            db.commit()
            ids = [row.id for row in rows]
        base = f"/api/buddy-chats/{chat_id}/messages"
        last = other.get(base, params={"latest": True, "limit": 50}).json()
        self.assertEqual([r["id"] for r in last], ids[75:])
        middle = other.get(base, params={"before": last[0]["id"], "limit": 50}).json()
        self.assertEqual([r["id"] for r in middle], ids[25:75])
        oldest = other.get(base, params={"before": middle[0]["id"], "limit": 50}).json()
        self.assertEqual([r["id"] for r in oldest], ids[:25])
        self.assertEqual([r["id"] for r in other.get(base, params={"after": ids[-2]}).json()], ids[-1:])
        self.assertEqual(len(other.get(base).json()), 100)
        for query in ({"limit": 101}, {"before": 0}, {"after": ids[0], "latest": True}):
            self.assertEqual(other.get(base, params=query).status_code, 422)

    def test_duplicate_record_links_original_and_get_is_private(self):
        self.login()
        original = self.record().json()
        duplicate = self.record()
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["detail"]["record_id"], original["id"])
        self.assertEqual(self.client.get(f"/api/records/{original['id']}").json(), original)
        other = self.another("other")
        self.assertEqual(other.get(f"/api/records/{original['id']}").status_code, 404)

    def test_current_plan_and_reflection_history_are_owned_and_ordered(self):
        self.login()
        self.plan(60)
        current_id = self.plan(90).json()["id"]
        self.plan(500, start=2, end=20)
        plans = self.client.get("/api/plans").json()
        self.assertEqual([p["id"] for p in plans if p["is_current"]], [current_id])
        self.assertEqual(self.client.get("/api/review").json()["plan_id"], current_id)
        self.client.put("/api/reflection", json={"reflection": "本周", "next_action": "散步"})
        current_week = date.fromisoformat(self.client.get("/api/reflection").json()["week_start"])
        user_id = self.client.get("/api/me").json()["id"]
        with self.sessions() as db:
            db.add(WeeklyReflection(user_id=user_id, week_start=current_week - timedelta(days=7), reflection="上周"))
            db.commit()
        rows = self.client.get("/api/reflections").json()
        self.assertEqual([row["reflection"] for row in rows], ["本周", "上周"])
        self.assertEqual(len(self.client.get("/api/reflections?limit=1&offset=1").json()), 1)
        other = self.another("other")
        self.assertEqual(other.get("/api/reflections").json(), [])
        self.assertEqual(other.get("/api/plans").json(), [])


class StatusMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO users VALUES (1), (2)")
            connection.exec_driver_sql("""CREATE TABLE buddy_statuses (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                exercise_type VARCHAR(50) NOT NULL, starts_at DATETIME NOT NULL,
                location VARCHAR(200) NOT NULL, latitude FLOAT NOT NULL,
                longitude FLOAT NOT NULL, note TEXT NOT NULL, custom_note TEXT DEFAULT 'keep'
            )""")
            connection.exec_driver_sql("CREATE INDEX ix_buddy_statuses_starts_at ON buddy_statuses (starts_at)")
            connection.exec_driver_sql("CREATE TABLE status_audit (user_id INTEGER)")
            connection.exec_driver_sql("CREATE TRIGGER status_insert AFTER INSERT ON buddy_statuses BEGIN INSERT INTO status_audit VALUES (NEW.user_id); END")
            connection.exec_driver_sql("INSERT INTO buddy_statuses (user_id, exercise_type, starts_at, location, latitude, longitude, note) VALUES (1, '跑步', '2099-01-01 02:00:00', '操场', 31.2, 121.4, '原状态')")

    def test_legacy_migration_preserves_rows_constraints_indexes_and_triggers(self):
        allow_place_only_statuses(self.engine)
        allow_place_only_statuses(self.engine)
        columns = {c["name"]: c for c in inspect(self.engine).get_columns("buddy_statuses")}
        self.assertTrue(columns["latitude"]["nullable"])
        self.assertTrue(columns["longitude"]["nullable"])
        self.assertFalse(columns["location"]["nullable"])
        with self.engine.begin() as connection:
            row = connection.execute(text("SELECT * FROM buddy_statuses WHERE user_id=1")).mappings().one()
            self.assertEqual(row["note"], "原状态")
            self.assertEqual(row["custom_note"], "keep")
            self.assertEqual(row["latitude"], 31.2)
            self.assertEqual(connection.execute(text("SELECT count(*) FROM status_audit")).scalar_one(), 1)
            connection.exec_driver_sql("INSERT INTO buddy_statuses (user_id, exercise_type, starts_at, location, note) VALUES (2, '散步', '2099-01-01 02:00:00', '图书馆', '')")
            self.assertEqual(connection.execute(text("SELECT count(*) FROM status_audit")).scalar_one(), 2)
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])
        self.assertIn("ix_buddy_statuses_starts_at", [i["name"] for i in inspect(self.engine).get_indexes("buddy_statuses")])
        self.assertNotIn("buddy_statuses_nullable_v1", inspect(self.engine).get_table_names())

    def test_failed_rebuild_rolls_back_without_losing_original_table(self):
        with patch("sqlalchemy.sql.schema.Table.drop", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                allow_place_only_statuses(self.engine)
        self.assertNotIn("buddy_statuses_nullable_v1", inspect(self.engine).get_table_names())
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT note FROM buddy_statuses")).scalar_one(), "原状态")
        self.assertFalse(next(c for c in inspect(self.engine).get_columns("buddy_statuses") if c["name"] == "latitude")["nullable"])


if __name__ == "__main__":
    unittest.main()
