"""Details use current activity data and the same visibility rules as discovery."""
import os
os.environ['DATABASE_URL'] = 'sqlite://'
from datetime import datetime, timedelta, timezone
import unittest

from app.models import Activity, ModerationAction
import test_buddies
import test_regressions


class ActivityDetailTests(unittest.TestCase):
    setUp = test_regressions.RegressionTests.setUp
    tearDown = test_regressions.RegressionTests.tearDown
    login = test_regressions.RegressionTests.login
    another = test_buddies.BuddyTests.another

    def activity(self):
        self.login()
        response = self.client.post('/api/activities', json={
            'exercise_type': '羽毛球', 'location': '体育馆', 'capacity': 3,
            'starts_at': (datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
            'note': '自备球拍，费用现场确认'})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_details_are_authenticated_and_reflect_current_members(self):
        row = self.activity()
        path = f"/api/activities/{row['id']}"
        other = self.another('other_student')
        before = other.get(path)
        self.assertEqual(before.status_code, 200, before.text)
        self.assertEqual(before.json()['joined'], 1)
        self.assertEqual(before.json()['note'], '自备球拍，费用现场确认')
        self.assertFalse(before.json()['is_member'])
        joined = other.post(f"{path}/join", json={})
        self.assertEqual(joined.status_code, 200, joined.text)
        after = other.get(path).json()
        self.assertEqual(after['joined'], 2)
        self.assertTrue(after['is_member'])
        other.post('/api/logout')
        self.assertEqual(other.get(path).status_code, 401)

    def test_blocked_suspended_and_withdrawn_activity_not_exposed(self):
        row = self.activity()
        path = f"/api/activities/{row['id']}"
        viewer = self.another('viewer')
        viewer.put(f"/api/buddy-blocks/{row['user_id']}")
        self.assertEqual(viewer.get(path).status_code, 404)
        viewer.delete(f"/api/buddy-blocks/{row['user_id']}")
        with self.sessions() as db:
            db.add(ModerationAction(user_id=row['user_id'], suspended_until=datetime.utcnow()+timedelta(days=1)))
            db.commit()
        self.assertEqual(viewer.get(path).status_code, 404)
        with self.sessions() as db:
            db.delete(db.get(ModerationAction,row['user_id']))
            db.get(Activity,row['id']).active=0
            db.commit()
        self.assertEqual(viewer.get(path).status_code, 404)

    def test_started_activity_is_not_offered_as_joinable(self):
        row = self.activity()
        with self.sessions() as db:
            db.get(Activity,row['id']).starts_at=datetime.utcnow()-timedelta(minutes=1)
            db.commit()
        self.assertEqual(self.client.get(f"/api/activities/{row['id']}").status_code, 404)
        self.assertEqual(self.client.get('/api/activities/999999').status_code, 404)
