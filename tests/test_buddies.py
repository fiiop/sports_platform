import os
os.environ['DATABASE_URL'] = 'sqlite://'
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import test_regressions
from app.main import app
from app.models import Activity, BuddyStatus
from sqlalchemy import select
import unittest
from unittest.mock import patch
import httpx
from app.services import map_tiles


class BuddyTests(unittest.TestCase):
    setUp = test_regressions.RegressionTests.setUp
    tearDown = test_regressions.RegressionTests.tearDown
    login = test_regressions.RegressionTests.login

    def test_map_fallback_auth_validation_and_cache(self):
        map_tiles._cache.clear()
        self.addCleanup(map_tiles._cache.clear)
        url = "/api/map-tiles/2/1/1.png"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.login()
        body = b"\x89PNG\r\n\x1a\nmock-tile"
        with patch.object(map_tiles.httpx, "get", return_value=httpx.Response(
                200, content=body, headers={"cache-control": "max-age=604800", "etag": "tile-v1"})) as upstream:
            first = self.client.get(url, headers={"referer": "https://campus.example/"})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.content, body)
            self.assertTrue(first.headers["content-type"].startswith("image/png"))
            self.assertIn("max-age=604800", first.headers["cache-control"])
            self.assertEqual(self.client.get(url).content, body)
            self.assertEqual(upstream.call_count, 1)
            self.assertIn("CampusMove", upstream.call_args.kwargs["headers"]["User-Agent"])
            self.assertEqual(upstream.call_args.kwargs["headers"]["Referer"], "https://campus.example/")
            for bad in ("/20/1/1.png", "/2/4/1.png", "/2/1/-1.png"):
                self.assertEqual(self.client.get("/api/map-tiles" + bad).status_code, 404)
            self.assertEqual(upstream.call_count, 1)
            map_tiles._cache[(2, 1, 1)]["expires"] = 0
            upstream.return_value = httpx.Response(304, headers={"cache-control": "max-age=60"})
            self.assertEqual(self.client.get(url).content, body)
            self.assertEqual(upstream.call_args.kwargs["headers"]["If-None-Match"], "tile-v1")

    def test_map_fallback_does_not_cache_failures(self):
        map_tiles._cache.clear()
        self.addCleanup(map_tiles._cache.clear)
        self.login()
        url = "/api/map-tiles/2/1/1.png"
        with patch.object(map_tiles.httpx, "get", side_effect=httpx.ConnectTimeout("unreachable")):
            self.assertEqual(self.client.get(url).status_code, 502)
        with patch.object(map_tiles.httpx, "get", return_value=httpx.Response(200, text="<html>error</html>")):
            self.assertEqual(self.client.get(url).status_code, 502)
        self.assertFalse(map_tiles._cache)

    def status(self, **changes):
        data = dict(exercise_type='羽毛球', location='校体育馆',
                    starts_at=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),
                    latitude=31.23, longitude=121.47, note='新手友好')
        data.update(changes)
        return self.client.put('/api/buddies/me', json=data)

    def another(self, name):
        client = TestClient(app)
        credentials = dict(username=name, password='test-pass-123')
        client.post('/api/register', json=credentials)
        client.post('/api/login', json=credentials)
        self.addCleanup(client.close)
        return client

    def test_status_visibility_update_expiry_and_removal(self):
        self.assertEqual(self.client.get('/api/buddies').status_code, 401)
        self.assertEqual(self.status().status_code, 401)
        self.login()
        self.assertEqual(self.status().status_code, 200)
        self.assertEqual(self.status(note='更新状态').status_code, 200)
        other = self.another('other')
        rows = other.get('/api/buddies').json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['note'], '更新状态')
        self.assertEqual(other.get('/api/buddies?exercise_type=跑步').json(), [])
        other.delete('/api/buddies/me')
        self.assertEqual(len(other.get('/api/buddies').json()), 1)
        with self.sessions() as db:
            row = db.get(BuddyStatus, rows[0]['user_id'])
            row.starts_at = datetime.utcnow()-timedelta(minutes=1)
            activity = db.scalar(select(Activity).where(Activity.legacy_user_id == row.user_id))
            activity.starts_at = row.starts_at
            db.commit()
        self.assertEqual(other.get('/api/buddies').json(), [])
        self.assertEqual(other.post(f"/api/buddies/{rows[0]['user_id']}/chat").status_code, 404)
        self.assertIsNotNone(self.client.get('/api/buddies/me').json())
        self.client.delete('/api/buddies/me')
        self.assertIsNone(self.client.get('/api/buddies/me').json())

    def test_validation(self):
        self.login()
        for changes in [dict(latitude=91),dict(longitude=181),dict(exercise_type=' '),
                        dict(location=' '),dict(starts_at='2020-01-01T10:00:00Z'),
                        dict(starts_at='2099-01-01T10:00:00')]:
            self.assertEqual(self.status(**changes).status_code, 422, changes)

    def test_chat_privacy_messages_and_persistence(self):
        self.login()
        owner = self.status().json()['user_id']
        self.assertEqual(self.client.post(f'/api/buddies/{owner}/chat').status_code, 400)
        other = self.another('other')
        outsider = self.another('outsider')
        chat_id = other.post(f'/api/buddies/{owner}/chat').json()['id']
        self.assertEqual(other.post(f'/api/buddies/{owner}/chat').json()['id'], chat_id)
        base = f'/api/buddy-chats/{chat_id}/messages'
        self.assertEqual(outsider.get(base).status_code, 404)
        self.assertEqual(outsider.post(base,json={'body':'hacked'}).status_code, 404)
        self.assertEqual(outsider.get('/api/buddy-chats').json(), [])
        self.assertEqual(other.post(base,json={'body':'   '}).status_code,422)
        first = other.post(base,json={'body':'周日上午十点可以吗？'}).json()['id']
        self.client.post(base,json={'body':'可以，体育馆见！'})
        messages = other.get(base).json()
        self.assertEqual(len(messages),2)
        self.assertEqual(len(other.get(base+f'?after={first}').json()),1)
        self.assertEqual(self.client.get('/api/buddy-chats').json()[0]['username'],'other')
        self.client.delete('/api/buddies/me')
        self.assertEqual(other.post(base,json={'body':'好的'}).status_code,200)
        self.assertEqual(other.post(f'/api/buddies/{owner}/chat').json()['id'],chat_id)
        self.assertEqual(len(self.client.get(base).json()),3)

if __name__ == '__main__':
    unittest.main()
