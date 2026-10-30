import os
import unittest
from datetime import date, datetime, timedelta

# Set before importing the application so create_all never touches sports.db.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["COOKIE_SECURE"] = "false"
os.environ["AI_API_KEY"] = ""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base, get_db
from app.models import LoginSession


class RegressionTests(unittest.TestCase):
    def test_page_and_worker_share_versioned_assets(self):
        from app.main import ASSET_VERSION
        page = self.client.get("/")
        self.assertEqual(page.headers["cache-control"], "no-store")
        for name in ("app.js", "buddies.js", "campus.js", "notifications.js", "identity.js",
                     "discovery.js", "style.css", "identity.css", "discovery.css"):
            url = f"/static/{name}?v={ASSET_VERSION}"
            self.assertIn(url, page.text)
            self.assertEqual(self.client.get(url).status_code, 200)
        worker = self.client.get("/sw.js")
        self.assertIn(ASSET_VERSION, worker.text)
        self.assertNotIn("__ASSET_VERSION__", worker.text)

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        def database():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        self.credentials = {"username": "student", "password": "test-pass-123"}
        self.assertEqual(self.client.post("/api/register", json=self.credentials).status_code, 200)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def login(self):
        response = self.client.post("/api/login", json=self.credentials)
        self.assertEqual(response.status_code, 200)
        return self.client.cookies.get("session")

    def record(self, minutes=60, days=0):
        return self.client.post("/api/records", json={
            "exercise_date": (date.today() - timedelta(days=days)).isoformat(),
            "exercise_type": "running", "duration": minutes})

    def plan(self, minutes=60, start=-10, end=10):
        return self.client.post("/api/plans", json={"title": "Training",
            "weekly_minutes": minutes,
            "start_date": (date.today()+timedelta(days=start)).isoformat(),
            "end_date": (date.today()+timedelta(days=end)).isoformat()})

    def test_forged_cookie_and_anonymous_requests_rejected(self):
        self.client.cookies.set("uid", "1")
        self.assertFalse(self.client.get("/api/me").json()["logged_in"])
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)
        self.client.cookies.set("session", "a" * 64)
        self.assertEqual(self.client.get("/api/records").status_code, 401)

    def test_logout_revokes_token(self):
        token = self.login()
        self.assertTrue(self.client.get("/api/me").json()["logged_in"])
        self.client.post("/api/logout")
        self.client.cookies.set("session", token)
        self.assertEqual(self.client.get("/api/plans").status_code, 401)

    def test_expired_session_rejected(self):
        self.login()
        with self.sessions() as db:
            session = db.query(LoginSession).one()
            session.expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)

    def test_review_uses_active_plan_and_real_completion(self):
        self.login()
        self.assertEqual(self.plan(60).status_code, 200)
        self.plan(500, start=1, end=20)
        self.plan(400, start=-20, end=-1)
        self.assertEqual(self.record(180).status_code, 200)
        review = self.client.get("/api/review").json()
        self.assertEqual(review["target"], 60)
        self.assertEqual(review["completion"], 300)
        self.plan(300)
        updated = self.client.get("/api/review").json()
        self.assertEqual(updated["target"], 300)
        self.assertEqual(updated["completion"], 60)
        self.assertNotEqual(updated["status"], review["status"])

    def test_record_isolation_and_duplicate(self):
        self.login()
        row = self.record().json()
        self.assertEqual(self.record().status_code, 409)
        other = {"username": "other", "password": "test-pass-456"}
        self.client.post("/api/register", json=other)
        self.client.post("/api/login", json=other)
        self.assertEqual(self.client.get("/api/records").json(), [])
        self.assertEqual(self.client.delete(f"/api/records/{row['id']}").status_code, 404)

    def test_statistics_boundaries_and_rule_advice(self):
        self.login()
        for days in (0, 6, 7, 29, 30):
            self.assertEqual(self.record(30, days).status_code, 200)
        data = self.client.get("/api/dashboard").json()
        self.assertEqual(data["summary"]["total_minutes"], 120)
        self.assertEqual(data["summary"]["last7_minutes"], 60)
        self.assertEqual(len(data["chart"]["labels"]), 14)
        self.assertEqual(data["review"]["target"], 150)
        self.assertTrue(self.client.post("/api/ai-advice").json()["advice"])

    def test_validation_and_home_page(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.login()
        self.assertEqual(self.plan(start=10, end=1).status_code, 400)
        payload = {"exercise_date": date.today().isoformat(), "exercise_type": "   ", "duration": 30}
        self.assertEqual(self.client.post("/api/records", json=payload).status_code, 422)
        payload.update(exercise_type="running", feeling="x" * 21)
        self.assertEqual(self.client.post("/api/records", json=payload).status_code, 422)

    def test_edit_record_and_conflict_rollback(self):
        self.login()
        first = self.record(30).json()
        second = self.record(40, 1).json()
        first["duration"] = 90
        self.assertEqual(self.client.put(f"/api/records/{first['id']}", json=first).status_code, 200)
        second["exercise_date"] = first["exercise_date"]
        self.assertEqual(self.client.put(f"/api/records/{second['id']}", json=second).status_code, 409)
        self.assertEqual(self.client.get("/api/dashboard").json()["summary"]["total_minutes"], 130)

    def test_edit_and_delete_plan_updates_target(self):
        self.login()
        plan_id = self.plan(60).json()["id"]
        plan = self.client.get("/api/plans").json()[0]
        plan["weekly_minutes"] = 300
        self.assertEqual(self.client.put(f"/api/plans/{plan_id}", json=plan).status_code, 200)
        self.assertEqual(self.client.get("/api/review").json()["target"], 300)
        self.record()
        self.assertEqual(self.client.delete(f"/api/plans/{plan_id}").status_code, 200)
        self.assertEqual(self.client.get("/api/review").json()["target"], 150)
        self.assertEqual(len(self.client.get("/api/records").json()), 1)

    def test_weekly_comparison_and_reflection(self):
        self.login()
        self.record(60, 0)
        self.record(30, 6)
        self.record(40, 7)
        self.record(10, 13)
        self.record(100, 14)
        review = self.client.get("/api/review").json()
        self.assertEqual(review["weekly_minutes"], 90)
        self.assertEqual(review["previous_minutes"], 50)
        self.assertEqual(review["delta_minutes"], 40)
        self.assertEqual(review["change_percent"], 80)
        self.assertEqual(review["active_days"], 2)
        for text in ("first", "updated"):
            response = self.client.put("/api/reflection", json={"reflection": text, "next_action": "Walk"})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/reflection").json()["reflection"], "updated")
        self.assertEqual(self.client.post("/api/ai-advice").json()["source"], "rules")

    def test_edit_routes_and_reflections_are_isolated(self):
        self.login()
        row = self.record().json()
        plan_id = self.plan().json()["id"]
        plan = self.client.get("/api/plans").json()[0]
        self.client.put("/api/reflection", json={"reflection": "private"})
        other = {"username": "another", "password": "test-pass-456"}
        self.client.post("/api/register", json=other)
        self.client.post("/api/login", json=other)
        self.assertEqual(self.client.put(f"/api/records/{row['id']}", json=row).status_code, 404)
        self.assertEqual(self.client.put(f"/api/plans/{plan_id}", json=plan).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/plans/{plan_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/reflection").json()["reflection"], "")

    def test_pagination_and_install_assets(self):
        self.login()
        for days in range(3):
            self.record(days=days)
        first = self.client.get("/api/records?limit=2").json()
        second = self.client.get("/api/records?offset=2&limit=2").json()
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 1)
        self.assertNotIn(second[0]["id"], [r["id"] for r in first])
        self.assertEqual(self.client.get("/api/records?offset=-1").status_code, 422)
        manifest = self.client.get("/static/manifest.webmanifest").json()
        self.assertEqual(manifest["display"], "standalone")
        for icon in manifest["icons"]:
            self.assertTrue(self.client.get(icon["src"]).content.startswith(b"\x89PNG"))
        self.assertEqual(self.client.get("/sw.js").headers["service-worker-allowed"], "/")
        self.assertEqual(self.client.get("/static/offline.html").status_code, 200)


if __name__ == "__main__":
    unittest.main()
