"""Repeat invitations preserve history, consent, privacy and retry identity."""
import os
os.environ['DATABASE_URL'] = 'sqlite://'
from datetime import datetime, timedelta, timezone
import unittest
from uuid import uuid4

from sqlalchemy import func, select
from app.models import Activity, Meetup, MeetupMember, ModerationAction, UserNotice
from app.services import campus, push
import test_campus
import test_regressions


class RepeatMeetupTests(unittest.TestCase):
    setUp = test_campus.CampusTests.setUp
    tearDown = test_regressions.RegressionTests.tearDown
    login = test_regressions.RegressionTests.login
    another = test_campus.CampusTests.another
    activity = test_campus.CampusTests.activity
    pair = test_campus.CampusTests.pair
    invite = test_campus.CampusTests.invite
    decide = test_campus.CampusTests.decide

    def finish(self, meeting, clients):
        with self.sessions() as db:
            db.get(Meetup, meeting['id']).starts_at = datetime.utcnow() - timedelta(hours=3)
            db.commit()
        for client in clients:
            result = self.decide(client, meeting, 'attend')
            self.assertEqual(result.status_code, 200, result.text)
            meeting = result.json()
        self.assertEqual(meeting['state'], 'completed')
        return meeting

    def completed_pair(self):
        uid, oid, chat, other = self.pair()
        meeting = self.invite(chat).json()
        meeting = self.decide(other, meeting, 'accept').json()
        return self.finish(meeting, [self.client, other]), other

    def completed_group(self):
        self.login()
        activity = self.activity(capacity=4).json()
        second, third = self.another('second'), self.another('third')
        meeting = second.post(f"/api/activities/{activity['id']}/join", json={}).json()
        meeting = third.post(f"/api/activities/{activity['id']}/join", json={}).json()
        return self.finish(meeting, [self.client, second, third]), second, third

    def payload(self, **changes):
        data = dict(starts_at=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                    duration=90, location='体育馆 2 号场', request_id=uuid4().hex)
        data.update(changes)
        return data

    def repeat(self, meeting, client=None, payload=None):
        return (client or self.client).post(f"/api/meetups/{meeting['id']}/repeat", json=payload or self.payload())

    def test_pair_repeats_original_people_without_changing_history_and_retries_once(self):
        original, other = self.completed_pair()
        payload = self.payload()
        result = self.repeat(original, payload=payload)
        self.assertEqual(result.status_code, 200, result.text)
        new = result.json()
        self.assertNotEqual(new['id'], original['id'])
        self.assertEqual(new['chat_id'], original['chat_id'])
        self.assertEqual(new['exercise_type'], original['exercise_type'])
        self.assertEqual(new['state'], 'pending')
        self.assertEqual(sorted(p['status'] for p in new['members']), ['accepted', 'pending'])
        self.assertFalse(any(p['attended'] for p in new['members']))
        self.assertEqual(self.repeat(original, payload=payload).json()['id'], new['id'])
        self.assertEqual(self.repeat(original, payload={**payload, 'location': '另一个场地'}).status_code, 409)
        self.assertEqual(self.client.get(f"/api/meetups/{original['id']}").json(), original)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Meetup)), 2)
        accepted = self.decide(other, new, 'accept')
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()['state'], 'confirmed')

    def test_group_invites_are_private_and_one_decline_does_not_cancel_everyone(self):
        original, second, third = self.completed_group()
        with self.sessions() as db:
            old_activities = db.scalar(select(func.count()).select_from(Activity))
        result = self.repeat(original)
        self.assertEqual(result.status_code, 200, result.text)
        new = result.json()
        self.assertEqual(new['kind'], 'group')
        self.assertEqual(new['capacity'], 3)
        self.assertEqual([p['status'] for p in new['members']].count('pending'), 2)
        self.assertEqual(second.get(f"/api/meetups/{new['id']}/messages").status_code, 403)
        with self.sessions() as db:
            self.assertIsNone(db.get(Meetup, new['id']).activity_id)
            self.assertEqual(db.scalar(select(func.count()).select_from(Activity)), old_activities)
            notices = db.scalars(select(UserNotice).where(UserNotice.meetup_id == new['id'])).all()
            self.assertEqual(len(notices), 2)
            self.assertTrue(all(push.reminder_is_current(db, n) for n in notices))
        declined = self.decide(second, new, 'decline').json()
        self.assertEqual(declined['state'], 'pending')
        accepted = self.decide(third, declined, 'accept')
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()['state'], 'confirmed')
        self.assertEqual(third.get(f"/api/meetups/{new['id']}/messages").status_code, 200)
        self.assertEqual(second.get(f"/api/meetups/{new['id']}/messages").status_code, 403)
        self.assertEqual(self.client.get(f"/api/meetups/{original['id']}").json(), original)
        with self.sessions() as db:
            notices = db.scalars(select(UserNotice).where(UserNotice.meetup_id == new['id'], UserNotice.dedupe_key.startswith('repeat:'))).all()
            self.assertFalse(any(push.reminder_is_current(db, n) for n in notices))

    def test_later_group_replies_still_work_after_first_acceptance(self):
        original, second, third = self.completed_group()
        new = self.repeat(original).json()
        new = self.decide(second, new, 'accept').json()
        self.assertEqual(new['state'], 'confirmed')
        response = self.decide(third, new, 'accept')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([p['status'] for p in response.json()['members']].count('accepted'), 3)

    def test_pending_member_cannot_gain_chat_history_by_cancelling(self):
        original, second, third = self.completed_group()
        new = self.repeat(original).json()
        new = self.decide(second, new, 'accept').json()
        messages = f"/api/meetups/{new['id']}/messages"
        self.assertEqual(self.client.post(messages, json={'body': '已参加成员的群消息'}).status_code, 200)
        self.assertEqual(third.get(messages).status_code, 403)
        self.assertEqual(third.post(messages, json={'body': '尚未接受'}).status_code, 403)
        cancelled = self.decide(third, new, 'cancel', reason='本次不参加')
        self.assertEqual(cancelled.status_code, 409, cancelled.text)
        self.assertEqual(third.get(messages).status_code, 403)
        unchanged = third.get(f"/api/meetups/{new['id']}").json()
        self.assertEqual(unchanged['revision'], new['revision'])
        declined = self.decide(third, new, 'decline')
        self.assertEqual(declined.status_code, 200, declined.text)
        self.assertEqual(declined.json()['state'], 'confirmed')
        self.assertEqual(third.get(messages).status_code, 403)
        self.assertEqual(third.post(messages, json={'body': '拒绝后不能发言'}).status_code, 403)
        # An actual participant still keeps the history from before they left.
        left = self.decide(second, declined.json(), 'cancel', reason='临时有课，提前说明')
        self.assertEqual(left.status_code, 200, left.text)
        self.assertEqual(self.client.post(messages, json={'body': '退出后的消息'}).status_code, 200)
        self.assertEqual([m['body'] for m in second.get(messages).json()], ['已参加成员的群消息'])
        self.assertEqual(second.post(messages, json={'body': '退出后不能发言'}).status_code, 403)

    def test_pending_invitee_accepts_only_after_rescheduling_finishes(self):
        original, second, third = self.completed_group()
        new = self.repeat(original).json()
        new = self.decide(second, new, 'accept').json()
        changed = self.client.post(f"/api/meetups/{new['id']}/change", json={
            'revision': new['revision'], 'starts_at': self.payload()['starts_at'],
            'duration': 120, 'location': '改到北苑体育馆'} )
        self.assertEqual(changed.status_code, 200, changed.text)
        proposal = changed.json()
        self.assertEqual(self.decide(third, proposal, 'accept').status_code, 409)
        self.assertEqual(self.decide(third, proposal, 'accept_change').status_code, 409)
        agreed = self.decide(second, proposal, 'accept_change')
        self.assertEqual(agreed.status_code, 200, agreed.text)
        self.assertEqual(self.decide(third, proposal, 'accept').status_code, 409)
        accepted = self.decide(third, agreed.json(), 'accept')
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()['location'], '改到北苑体育馆')
        self.assertEqual(accepted.json()['duration'], 120)

    def test_repeat_push_stops_after_owner_cancel_without_losing_retry_identity(self):
        original, other = self.completed_pair()
        payload = self.payload()
        new = self.repeat(original, payload=payload).json()
        with self.sessions() as db:
            notice = db.scalar(select(UserNotice).where(UserNotice.meetup_id == new['id']))
            self.assertTrue(push.reminder_is_current(db, notice))
            notice_id, recipient = notice.id, notice.user_id
        check = {'notice_id': notice_id, 'user_id': recipient}
        self.assertTrue(other.get('/api/push/check', params=check).json()['show'])
        cancelled = self.decide(self.client, new, 'cancel', reason='临时调整，提前说明')
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertFalse(other.get('/api/push/check', params=check).json()['show'])
        retry = self.repeat(original, payload=payload)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()['id'], new['id'])
        self.assertEqual(retry.json()['state'], 'cancelled')

    def test_permissions_blocks_restrictions_and_completion_are_enforced(self):
        original, other = self.completed_pair()
        outsider = self.another('outsider')
        self.assertEqual(self.repeat(original, client=outsider).status_code, 404)
        uid = self.client.get('/api/me').json()['id']
        oid = other.get('/api/me').json()['id']
        other.put(f'/api/buddy-blocks/{uid}')
        self.assertEqual(self.repeat(original).status_code, 403)
        other.delete(f'/api/buddy-blocks/{uid}')
        with self.sessions() as db:
            db.add(ModerationAction(user_id=oid, suspended_until=datetime.utcnow()+timedelta(days=1)))
            db.commit()
        self.assertEqual(self.repeat(original).status_code, 403)
        with self.sessions() as db:
            db.delete(db.get(ModerationAction, oid))
            db.get(MeetupMember, (original['id'], uid)).attended = 0
            db.commit()
        self.assertEqual(self.repeat(original).status_code, 409)
        with self.sessions() as db:
            db.get(MeetupMember, (original['id'], uid)).attended = 1
            db.get(Meetup, original['id']).state = 'confirmed'
            db.commit()
        self.assertEqual(self.repeat(original).status_code, 409)

    def test_future_time_conflicts_and_pending_limit(self):
        original, other = self.completed_pair()
        self.assertEqual(self.repeat(original, payload=self.payload(starts_at=datetime.now(timezone.utc).isoformat())).status_code, 422)
        self.assertEqual(self.repeat(original, payload=self.payload(request_id='invalid')).status_code, 422)
        first = self.repeat(original).json()
        first = self.decide(other, first, 'accept').json()
        conflict = self.repeat(original, payload=self.payload(starts_at=first['starts_at']))
        self.assertEqual(conflict.status_code, 409)
        self.assertIn('conflicts', conflict.json()['detail'])
        for index in range(3):
            result = self.repeat(original, payload=self.payload(starts_at=first['starts_at'], allow_conflict=True))
            self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.repeat(original, payload=self.payload(allow_conflict=True)).status_code, 409)

    def test_all_group_declines_end_invitation_and_reminder_retirement_keeps_repeat_key(self):
        original, second, third = self.completed_group()
        payload = self.payload()
        new = self.repeat(original, payload=payload).json()
        with self.sessions() as db:
            notice = db.scalar(select(UserNotice).where(UserNotice.meetup_id == new['id']))
            campus.retire_reminders(db, new['id'])
            db.commit()
            db.refresh(notice)
            self.assertEqual(notice.is_read, 0)
            self.assertTrue(push.reminder_is_current(db, notice))
        new = self.decide(second, new, 'decline').json()
        new = self.decide(third, new, 'decline').json()
        self.assertEqual(new['state'], 'declined')
        self.assertEqual(self.repeat(original, payload=payload).json()['id'], new['id'])
        with self.sessions() as db:
            notices = db.scalars(select(UserNotice).where(UserNotice.meetup_id == new['id'], UserNotice.dedupe_key.startswith('repeat:'))).all()
            self.assertFalse(any(push.reminder_is_current(db, n) for n in notices))


if __name__ == '__main__':
    unittest.main()
