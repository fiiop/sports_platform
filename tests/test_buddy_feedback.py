import os
os.environ['DATABASE_URL'] = 'sqlite://'
import unittest
import test_buddies
import test_regressions
from datetime import datetime, timedelta
from app.models import Meetup, MeetupMember


class BuddyFeedbackTests(unittest.TestCase):
    setUp = test_regressions.RegressionTests.setUp
    tearDown = test_regressions.RegressionTests.tearDown
    login = test_regressions.RegressionTests.login
    status = test_buddies.BuddyTests.status
    another = test_buddies.BuddyTests.another

    def pair(self):
        self.login()
        uid = self.status().json()['user_id']
        other = self.another('partner')
        oid = other.get('/api/me').json()['id']
        chat = other.post(f'/api/buddies/{uid}/chat').json()['id']
        return uid, oid, chat, other

    def test_rating_requires_completed_meetup_one_vote_and_highest_first(self):
        uid, oid, chat, other = self.pair()
        url = f'/api/buddies/{uid}/rating'
        self.assertEqual(other.put(url, json={'score': 5}).status_code, 403)
        other.post(f'/api/buddy-chats/{chat}/messages', json={'body': '一起运动吗'})
        self.assertEqual(other.put(url, json={'score': 5}).status_code, 403)
        self.client.post(f'/api/buddy-chats/{chat}/messages', json={'body': '可以'})
        self.assertEqual(other.put(url, json={'score': 5}).status_code, 403)
        with self.sessions() as db:
            meeting = Meetup(owner_id=uid, chat_id=chat, exercise_type='羽毛球',
                             starts_at=datetime.utcnow()-timedelta(hours=2), location='体育馆', state='completed')
            db.add(meeting)
            db.flush()
            db.add_all([MeetupMember(meetup_id=meeting.id, user_id=u, status='accepted', attended=1) for u in (uid, oid)])
            db.commit()
        for invalid in (0, 6, 2.5, '5', True):
            self.assertEqual(other.put(url, json={'score': invalid}).status_code, 422)
        self.assertEqual(other.put(url, json={'score': 5}).status_code, 200)
        self.assertEqual(other.put(url, json={'score': 4}).status_code, 200)
        score = other.get(url).json()
        self.assertEqual((score['rating'], score['rating_count'], score['my_score']), (4.0, 1, 4))
        self.assertEqual(self.client.put(url, json={'score': 5}).status_code, 403)
        other.put('/api/buddies/me', json={'exercise_type': '篮球', 'location': '学校篮球场', 'starts_at': '2099-01-01T00:00:00Z'})
        rows = other.get('/api/buddies').json()
        self.assertEqual(rows[0]['user_id'], uid)
        self.assertEqual(other.get('/api/buddies?exercise_type=篮球').json()[0]['user_id'], oid)
        self.assertEqual(other.get('/api/buddies?sort=time').json()[0]['user_id'], uid)

    def test_block_is_two_way_and_unblock_only_removes_own_block(self):
        uid, oid, chat, other = self.pair()
        other.put('/api/buddies/me', json={'exercise_type': '跑步', 'location': '操场', 'starts_at': '2099-01-01T00:00:00Z'})
        base = f'/api/buddy-chats/{chat}/messages'
        self.client.post(base, json={'body': '原来的消息'})
        self.assertEqual(self.client.put(f'/api/buddy-blocks/{oid}').status_code, 200)
        self.assertEqual(self.client.put(f'/api/buddy-blocks/{oid}').status_code, 200)
        self.assertEqual(len(self.client.get('/api/buddy-blocks').json()), 1)
        self.assertNotIn(oid, [r['user_id'] for r in self.client.get('/api/buddies').json()])
        self.assertNotIn(uid, [r['user_id'] for r in other.get('/api/buddies').json()])
        self.assertEqual(other.post(f'/api/buddies/{uid}/chat').status_code, 403)
        for client in (self.client, other):
            self.assertEqual(client.post(base, json={'body': '不能发送'}).status_code, 403)
            self.assertEqual(client.get(base).json()[0]['body'], '原来的消息')
            self.assertTrue(client.get('/api/buddy-chats').json()[0]['blocked'])
        other.delete(f'/api/buddy-blocks/{uid}')
        self.assertEqual(other.post(base, json={'body': '仍不可发'}).status_code, 403)
        self.client.delete(f'/api/buddy-blocks/{oid}')
        self.assertEqual(other.post(base, json={'body': '已解除'}).status_code, 200)
        self.assertEqual(self.client.put(f'/api/buddy-blocks/{uid}').status_code, 400)
