"""Current chat avatars/nicknames and restricted-profile privacy."""
import os
os.environ['DATABASE_URL'] = 'sqlite://'
from datetime import datetime, timedelta
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import app
from app.models import BuddyMessage, ModerationAction, ProfileAvatar, PublicIdentity
import test_campus
import test_regressions


class ChatIdentityTests(unittest.TestCase):
    setUp = test_campus.CampusTests.setUp
    tearDown = test_regressions.RegressionTests.tearDown
    login = test_campus.CampusTests.login
    another = test_campus.CampusTests.another
    activity = test_campus.CampusTests.activity
    pair = test_campus.CampusTests.pair
    group = test_campus.CampusTests.group

    def identity(self, user_id, nickname, version='photo-v1'):
        with self.sessions() as db:
            db.merge(PublicIdentity(user_id=user_id, nickname=nickname, bio='private-to-profile'))
            db.merge(ProfileAvatar(user_id=user_id, version=version, content=b'test-avatar'))
            db.commit()

    def test_private_chat_uses_current_identity_and_avatar_version(self):
        uid, oid, chat, other = self.pair()
        default = other.get('/api/buddy-chats').json()[0]
        self.assertEqual(default['display_name'], 'student')
        self.assertIsNone(default['avatar_url'])
        self.identity(uid, '阿青')
        self.identity(oid, '小林')
        for client, body in ((self.client, '周末一起运动'), (other, '好呀')):
            self.assertEqual(client.post(f'/api/buddy-chats/{chat}/messages', json={'body': body}).status_code, 200)
        listing = other.get('/api/buddy-chats').json()[0]
        self.assertEqual(listing['username'], 'student')
        self.assertEqual(listing['display_name'], '阿青')
        self.assertIn(f'/api/users/{uid}/avatar?v=photo-v1', listing['avatar_url'])
        messages = other.get(f'/api/buddy-chats/{chat}/messages').json()
        self.assertEqual([m['display_name'] for m in messages], ['阿青', '小林'])
        self.assertEqual([m['sender_id'] for m in messages], [uid, oid])
        self.assertNotIn('bio', messages[0])
        self.identity(uid, '阿青新昵称', 'photo-v2')
        refreshed = other.get(f'/api/buddy-chats/{chat}/messages?latest=true&limit=1').json()[0]
        self.assertEqual(refreshed['sender_id'], oid)
        history = other.get(f'/api/buddy-chats/{chat}/messages?before={messages[-1]["id"]}').json()[0]
        self.assertEqual(history['display_name'], '阿青新昵称')
        self.assertTrue(history['avatar_url'].endswith('v=photo-v2'))
        outsider = self.another('outsider')
        self.assertEqual(outsider.get(f'/api/buddy-chats/{chat}/messages').status_code, 404)
        anonymous = TestClient(app)
        self.addCleanup(anonymous.close)
        self.assertEqual(anonymous.get(f'/api/buddy-chats/{chat}/messages').status_code, 401)

    def test_private_history_preserves_text_but_hides_restricted_identity(self):
        uid, oid, chat, other = self.pair()
        self.identity(uid, '不向受限同伴展示的昵称')
        self.identity(oid, '自己的昵称')
        self.client.post(f'/api/buddy-chats/{chat}/messages', json={'body': '保留的历史消息'})
        other.post(f'/api/buddy-chats/{chat}/messages', json={'body': '我的消息'})
        for blocker, target in ((self.client, oid), (other, uid)):
            self.assertEqual(blocker.put(f'/api/buddy-blocks/{target}').status_code, 200)
            listing = other.get('/api/buddy-chats').json()[0]
            self.assertTrue(listing['identity_hidden'])
            self.assertEqual(listing['display_name'], 'student')
            self.assertIsNone(listing['avatar_url'])
            messages = other.get(f'/api/buddy-chats/{chat}/messages').json()
            self.assertEqual(messages[0]['body'], '保留的历史消息')
            self.assertEqual(messages[0]['display_name'], 'student')
            self.assertIsNone(messages[0]['avatar_url'])
            self.assertEqual(messages[1]['display_name'], '自己的昵称')
            self.assertIsNotNone(messages[1]['avatar_url'])
            blocker.delete(f'/api/buddy-blocks/{target}')
        with self.sessions() as db:
            db.add(ModerationAction(user_id=uid, suspended_until=datetime.utcnow()+timedelta(days=1)))
            db.commit()
        restricted = other.get(f'/api/buddy-chats/{chat}/messages').json()[0]
        self.assertTrue(restricted['identity_hidden'])
        self.assertIsNone(restricted['avatar_url'])
        own = self.client.get(f'/api/buddy-chats/{chat}/messages').json()[0]
        self.assertFalse(own['identity_hidden'])
        self.assertEqual(own['display_name'], '不向受限同伴展示的昵称')

    def test_group_messages_and_members_hide_blocked_or_suspended_profiles(self):
        activity, other, meeting = self.group()
        uid = self.client.get('/api/me').json()['id']
        oid = other.get('/api/me').json()['id']
        self.identity(uid, '组局发起人')
        self.identity(oid, '参与同学')
        path = f'/api/meetups/{meeting["id"]}'
        self.client.post(path+'/messages', json={'body': '群聊原消息'})
        other.post(path+'/messages', json={'body': '收到'})
        messages = other.get(path+'/messages').json()
        self.assertEqual([m['display_name'] for m in messages], ['组局发起人', '参与同学'])
        self.assertTrue(all(m['avatar_url'] for m in messages))
        people = other.get(path).json()['members']
        self.assertEqual({p['display_name'] for p in people}, {'组局发起人', '参与同学'})
        self.client.put(f'/api/buddy-blocks/{oid}')
        hidden = other.get(path+'/messages').json()[0]
        self.assertEqual(hidden['body'], '群聊原消息')
        self.assertIsNone(hidden['avatar_url'])
        self.assertEqual(hidden['display_name'], 'student')
        members = other.get(path).json()['members']
        self.assertIsNone(next(p for p in members if p['user_id'] == uid)['avatar_url'])
        self.client.delete(f'/api/buddy-blocks/{oid}')
        with self.sessions() as db:
            db.add(ModerationAction(user_id=uid, suspended_until=datetime.utcnow()+timedelta(days=1)))
            db.commit()
        hidden = other.get(path+'/messages').json()[0]
        self.assertTrue(hidden['identity_hidden'])
        self.assertIsNone(hidden['avatar_url'])
        self.assertTrue(next(p for p in other.get(path).json()['members'] if p['user_id'] == uid)['identity_hidden'])

    def test_message_identity_queries_are_batched_without_image_bytes(self):
        uid, oid, chat, other = self.pair()
        self.identity(uid, '发起人')
        self.identity(oid, '同伴')
        with self.sessions() as db:
            db.add_all(BuddyMessage(chat_id=chat, sender_id=uid if i % 2 else oid, body=f'消息 {i}')
                       for i in range(40))
            db.commit()
        queries = []
        def record(connection, cursor, statement, parameters, context, executemany):
            queries.append(statement)
        event.listen(self.engine, 'before_cursor_execute', record)
        try:
            response = other.get(f'/api/buddy-chats/{chat}/messages')
        finally:
            event.remove(self.engine, 'before_cursor_execute', record)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 40)
        self.assertLessEqual(len(queries), 8)
        self.assertFalse(any('profile_avatars.content' in q for q in queries))


if __name__ == '__main__':
    unittest.main()
