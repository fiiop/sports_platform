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
        self.assertEqual(self.record().status_code, 400)
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


if __name__ == "__main__":
    unittest.main()
