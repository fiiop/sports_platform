"""Old tabs and the v4 activity list must share state and publication limits."""
import os
os.environ['DATABASE_URL'] = 'sqlite://'
import unittest
from datetime import datetime, timedelta, timezone
from app.services.campus import migrate_legacy
import test_buddies
import test_regressions


class LegacyActivityTests(unittest.TestCase):
    setUp = test_regressions.RegressionTests.setUp
    tearDown = test_regressions.RegressionTests.tearDown
    login = test_regressions.RegressionTests.login
    status = test_buddies.BuddyTests.status
    another = test_buddies.BuddyTests.another

    def test_old_publish_edit_withdraw_stay_consistent_and_do_not_reappear(self):
        self.login()
        owner = self.status().json()['user_id']
        other = self.another('other')
        row = other.get('/api/activities').json()[0]
        self.assertEqual(row['user_id'], owner)
        self.status(exercise_type='篮球')
        self.assertEqual(other.get('/api/activities').json()[0]['exercise_type'], '篮球')
        self.client.delete('/api/buddies/me')
        migrate_legacy(self.engine)
        self.assertEqual(other.get('/api/activities').json(), [])
        self.assertEqual(other.post(f'/api/buddies/{owner}/chat').status_code, 404)
        self.assertEqual(self.status().status_code, 200)
        self.assertEqual(len(other.get('/api/activities').json()), 1)
        self.assertEqual(other.get('/api/activities').json()[0]['id'], row['id'])

    def test_new_edit_and_withdraw_update_old_clients(self):
        self.login()
        self.status()
        row = self.client.get('/api/activities/mine').json()[0]
        payload = dict(exercise_type='乒乓球', location='新体育馆',
                       starts_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
        result = self.client.put(f"/api/activities/{row['id']}", json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.get('/api/buddies/me').json()['exercise_type'], '乒乓球')
        self.client.delete(f"/api/activities/{row['id']}")
        self.assertIsNone(self.client.get('/api/buddies/me').json())
        migrate_legacy(self.engine)
        self.assertEqual(self.client.get('/api/activities').json(), [])

    def test_old_page_cannot_bypass_three_status_limit(self):
        self.login()
        payload = dict(exercise_type='跑步', location='操场',
                       starts_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
        for _ in range(3):
            self.assertEqual(self.client.post('/api/activities', json=payload).status_code, 200)
        self.assertEqual(self.status().status_code, 409)
        self.assertIsNone(self.client.get('/api/buddies/me').json())
        self.assertEqual(len(self.client.get('/api/activities/mine').json()), 3)


if __name__ == '__main__':
    unittest.main()
