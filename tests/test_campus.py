import os
os.environ['DATABASE_URL'] = 'sqlite://'
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from sqlalchemy import select
from app.models import Activity, AdminRole, CampusProfile, Meetup, MeetupMember, UserNotice, PushSubscription, LoginSession
from app.services import campus, push, reminders
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import test_buddies
import test_regressions


class CampusTests(unittest.TestCase):
    tearDown = test_regressions.RegressionTests.tearDown
    login = test_regressions.RegressionTests.login
    another = test_buddies.BuddyTests.another

    def setUp(self):
        test_regressions.RegressionTests.setUp(self)
        # Match the application's session behavior, not SQLAlchemy's default.
        self.sessions.configure(autoflush=False)

    def activity(self, client=None, **changes):
        payload = dict(exercise_type='羽毛球双打', location='南苑体育馆',
                       starts_at=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(), capacity=2)
        payload.update(changes)
        return (client or self.client).post('/api/activities', json=payload)

    def pair(self):
        self.login()
        owner = self.client.get('/api/me').json()['id']
        self.activity()
        other = self.another('partner')
        oid = other.get('/api/me').json()['id']
        chat = other.post(f'/api/buddies/{owner}/chat').json()['id']
        return owner, oid, chat, other

    def invite(self, chat, **changes):
        payload = dict(chat_id=chat, exercise_type='羽毛球', location='体育馆', duration=60,
                       starts_at=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat())
        payload.update(changes)
        return self.client.post('/api/meetups', json=payload)

    def decide(self, client, meeting, action, **changes):
        return client.post(f"/api/meetups/{meeting['id']}/decision",
                           json=dict(action=action, revision=meeting['revision'], **changes))

    def group(self, capacity=3):
        self.login()
        row = self.activity(capacity=capacity).json()
        other = self.another('member')
        joined = other.post(f"/api/activities/{row['id']}/join", json={})
        self.assertEqual(joined.status_code, 200, joined.text)
        return row, other, joined.json()

    def test_school_keyword_level_place_and_three_slots(self):
        self.login()
        first = self.activity(level='新手').json()
        self.assertEqual(first['school'], '湘潭大学')
        self.assertEqual(len(self.client.get('/api/activities?keyword=羽&place=南苑&level=新手').json()), 1)
        self.assertEqual(self.client.get('/api/activities?keyword=%25').json(), [])
        self.assertEqual(self.client.get('/api/activities?level=熟练').json(), [])
        other = self.another('elsewhere')
        other.put('/api/profile', json={'school':'其他大学', 'theme':'ocean'})
        self.assertEqual(other.get('/api/activities').json(), [])
        self.assertEqual(len(other.get('/api/activities?scope=all').json()), 1)
        self.activity(); self.activity()
        self.assertEqual(self.activity().status_code, 409)
        self.client.delete(f"/api/activities/{first['id']}")
        self.assertEqual(self.activity().status_code, 200)
        profile = self.client.get('/api/profile').json()
        self.assertFalse(profile['school_verified'])
        self.assertFalse(profile['is_admin'])
        self.assertEqual(self.client.put('/api/profile', json={'school':' ', 'theme':'forest'}).status_code, 422)

    def test_dates_periods_timezone_and_boundaries(self):
        self.login()
        day = (datetime.now(timezone.utc)+timedelta(hours=8, days=1)).date()
        for hour in (11,12,18):
            self.activity(starts_at=f'{day}T{hour}:00:00+08:00')
        for period,hour in [('morning',11),('afternoon',12),('evening',18)]:
            rows = self.client.get('/api/activities', params={'on_date':str(day), 'period':period, 'utc_offset':480}).json()
            self.assertEqual(len(rows), 1)
            self.assertEqual(datetime.fromisoformat(rows[0]['starts_at'].replace('Z','+00:00')).hour, hour-8)
        self.assertEqual(self.client.get('/api/activities?on_date=2099-01-01').status_code, 422)
        self.assertEqual(self.client.get('/api/activities?period=bad').status_code, 422)
        self.assertEqual(self.client.get('/api/activities?utc_offset=900').status_code, 422)

    def test_invite_privacy_decline_expiry_and_pending_cap(self):
        uid, oid, chat, other = self.pair()
        m = self.invite(chat).json()
        outsider = self.another('outsider')
        self.assertEqual(outsider.get(f"/api/meetups/{m['id']}").status_code,404)
        self.assertEqual(self.decide(self.client,m,'accept').status_code,409)
        self.assertEqual(self.decide(other,m,'decline').json()['state'],'declined')
        for _ in range(3):
            self.assertEqual(self.invite(chat).status_code,200)
        self.assertEqual(self.invite(chat).status_code,409)
        pending=other.get('/api/meetups').json()[0]
        with self.sessions() as db:
            db.get(Meetup,pending['id']).starts_at=datetime.utcnow()-timedelta(minutes=1)
            db.commit()
        self.assertEqual(other.get(f"/api/meetups/{pending['id']}").json()['state'],'expired')
        self.assertEqual(self.decide(other,pending,'accept').status_code,409)

    def test_complete_requires_both_after_end_then_rating(self):
        uid, oid, chat, other = self.pair()
        m=self.invite(chat).json()
        m=self.decide(other,m,'accept').json()
        self.assertEqual(self.decide(self.client,m,'attend').status_code,409)
        self.assertEqual(other.put(f'/api/buddies/{uid}/rating',json={'score':5}).status_code,403)
        with self.sessions() as db:
            db.get(Meetup,m['id']).starts_at=datetime.utcnow()-timedelta(hours=2)
            db.commit()
        m=self.decide(self.client,m,'attend').json()
        self.assertEqual(m['state'],'confirmed')
        self.assertEqual(self.client.get('/api/profile').json()['completed'],0)
        self.assertEqual(other.put(f'/api/buddies/{uid}/rating',json={'score':5}).status_code,403)
        m=self.decide(other,m,'attend').json()
        self.assertEqual(m['state'],'completed')
        self.assertEqual(self.client.get('/api/profile').json()['completed'],1)
        self.assertEqual(other.put(f'/api/buddies/{uid}/rating',json={'score':5}).status_code,200)

    def test_change_waits_for_every_member_and_stale_revision_rejected(self):
        activity, other, m=self.group()
        third=self.another('third')
        m=third.post(f"/api/activities/{activity['id']}/join",json={}).json()
        original=m['starts_at']
        changed=(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()
        proposal=self.client.post(f"/api/meetups/{m['id']}/change",json={'starts_at':changed,'location':'新体育馆','duration':90,'revision':m['revision']})
        self.assertEqual(proposal.status_code,200,proposal.text)
        proposed=proposal.json()
        self.assertEqual(proposed['starts_at'],original)
        self.assertEqual(self.decide(other,m,'accept_change').status_code,409)
        proposed=self.decide(other,proposed,'accept_change').json()
        self.assertEqual(proposed['starts_at'],original)
        final=self.decide(third,proposed,'accept_change').json()
        self.assertEqual(final['location'],'新体育馆')
        self.assertIsNone(final['proposal'])
        self.assertEqual(self.client.get('/api/activities').json()[0]['location'],'新体育馆')

    def test_conflict_warns_and_can_be_overridden(self):
        uid, oid, chat, other=self.pair()
        first=self.invite(chat).json()
        self.decide(other,first,'accept')
        second=self.invite(chat,starts_at=first['starts_at'])
        self.assertEqual(second.status_code,409)
        self.assertIn('conflicts',second.json()['detail'])
        self.assertEqual(self.invite(chat,starts_at=first['starts_at'],allow_conflict=True).status_code,200)

    def test_unjoined_group_change_takes_effect_without_pending_vote(self):
        self.login()
        activity = self.activity(capacity=3).json()
        m = self.client.get('/api/meetups').json()[0]
        changed = (datetime.now(timezone.utc)+timedelta(days=3)).isoformat()
        response = self.client.post(f"/api/meetups/{m['id']}/change", json={
            'starts_at': changed, 'location': '北苑篮球场', 'duration': 90, 'revision': m['revision']})
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        self.assertIsNone(updated['proposal'])
        self.assertIsNone(updated['proposal_by'])
        self.assertEqual(updated['location'], '北苑篮球场')
        other = self.another('new-member')
        self.assertEqual(other.post(f"/api/activities/{activity['id']}/join", json={}).status_code, 200)

    def test_group_capacity_chat_privacy_leave_and_block(self):
        activity,other,m=self.group()
        third=self.another('third')
        fourth=self.another('fourth')
        join=f"/api/activities/{activity['id']}/join"
        self.assertEqual(third.post(join,json={}).status_code,200)
        self.assertEqual(fourth.post(join,json={}).status_code,409)
        base=f"/api/meetups/{m['id']}/messages"
        self.assertEqual(fourth.get(base).status_code,404)
        self.assertEqual(other.post(base,json={'body':'一起练习'}).status_code,200)
        m=other.get(f"/api/meetups/{m['id']}").json()
        left=self.decide(other,m,'cancel',reason='临时有课，提前说明')
        self.assertEqual(left.status_code,200,left.text)
        self.assertEqual(other.post(base,json={'body':'不能发'}).status_code,403)
        self.client.post(base,json={'body':'退出后的新消息'})
        self.assertEqual([r['body'] for r in other.get(base).json()],['一起练习'])
        self.assertEqual(fourth.post(join,json={}).status_code,200)
        self.assertEqual(self.client.delete(f"/api/activities/{activity['id']}").status_code,409)

    def test_cancel_reason_late_classification_private_and_no_rating_penalty(self):
        uid,oid,chat,other=self.pair()
        m=self.invite(chat,starts_at=(datetime.now(timezone.utc)+timedelta(minutes=50)).isoformat()).json()
        m=self.decide(other,m,'accept').json()
        self.assertEqual(self.decide(other,m,'cancel').status_code,422)
        m=self.decide(other,m,'cancel',reason='临时身体不适').json()
        self.assertTrue(m['late_cancel'])
        self.assertEqual(m['cancel_reason'],'临时身体不适')
        public=self.client.get('/api/activities').json()[0]
        self.assertNotIn('cancel_reason',public)
        self.assertIsNone(public['rating'])

    def test_reports_admin_permissions_and_moderation(self):
        uid,oid,chat,other=self.pair()
        report=other.post('/api/reports',json={'target_id':uid,'chat_id':chat,'reason':'对方反复发送骚扰内容'})
        self.assertEqual(report.status_code,200,report.text)
        self.assertEqual(self.client.get('/api/admin/reports').status_code,403)
        self.assertEqual(self.client.get('/api/reports/mine').json(),[])
        admin=self.another('moderator')
        aid=admin.get('/api/me').json()['id']
        with self.sessions() as db:
            db.add(AdminRole(user_id=aid));db.commit()
        self.assertEqual(len(admin.get('/api/admin/reports').json()),1)
        done=admin.post(f"/api/admin/reports/{report.json()['id']}",json={'action':'suspend_7d','resolution':'经核查，暂时限制社交功能七天。'})
        self.assertEqual(done.status_code,200)
        self.assertEqual(self.activity().status_code,403)
        self.assertEqual(self.client.post(f'/api/buddy-chats/{chat}/messages',json={'body':'继续'}).status_code,403)
        self.assertEqual(other.get('/api/reports/mine').json()[0]['state'],'resolved')
        self.assertEqual(self.client.get('/api/records').status_code,200)

    def test_bootstrap_does_not_grant_later_registration(self):
        campus.migrate_legacy(self.engine)
        late=self.another('test02')
        campus.migrate_legacy(self.engine)
        self.assertFalse(late.get('/api/profile').json()['is_admin'])

    def test_reminders_idempotent_private_and_read(self):
        uid,oid,chat,other=self.pair()
        now=datetime.utcnow()
        m=self.invite(chat,starts_at=(now+timedelta(hours=2)).replace(tzinfo=timezone.utc).isoformat()).json()
        m=self.decide(other,m,'accept').json()
        reminders.create_due_reminders(self.engine,now+timedelta(seconds=1))
        reminders.create_due_reminders(self.engine,now+timedelta(seconds=2))
        notices=self.client.get('/api/notices').json()['items']
        reminders_only=[n for n in notices if '2 小时' in n['title']]
        self.assertEqual(len(reminders_only),1)
        outsider=self.another('outsider')
        self.assertEqual(outsider.get('/api/notices').json()['count'],0)
        outsider.post(f"/api/notices/{reminders_only[0]['id']}/read")
        self.assertFalse(self.client.get('/api/notices').json()['items'][0]['is_read'])
        self.client.post(f"/api/meetups/{m['id']}/read")
        self.assertEqual(self.client.get('/api/notices').json()['count'],0)
        self.decide(other,m,'cancel',reason='提前取消这次约定')
        reminders.create_due_reminders(self.engine,now+timedelta(minutes=90,seconds=1))
        self.assertFalse(any('30 分钟' in n['title'] for n in self.client.get('/api/notices').json()['items']))

    def subscription(self, suffix='one'):
        key=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        return {'endpoint':'https://fcm.googleapis.com/fcm/send/'+suffix,
                'keys':{'p256dh':push.b64(key),'auth':push.b64(os.urandom(16))}}

    def due_reminder(self):
        uid, oid, chat, other = self.pair()
        now = datetime.utcnow()
        m = self.invite(chat, starts_at=(now+timedelta(hours=2)).replace(tzinfo=timezone.utc).isoformat()).json()
        m = self.decide(other, m, 'accept').json()
        reminders.create_due_reminders(self.engine, now+timedelta(seconds=1))
        with self.sessions() as db:
            notice = db.scalar(select(UserNotice).where(UserNotice.user_id==uid, UserNotice.dedupe_key.is_not(None)))
            notice_id = notice.id
        self.assertEqual(self.client.put('/api/push/subscriptions', json=self.subscription()).status_code, 200)
        params = {'user_id': uid, 'notice_id': notice_id}
        self.assertTrue(self.client.get('/api/push/check', params=params).json()['show'])
        with patch.object(push, 'webpush') as send:
            self.assertTrue(push.deliver_notice_push(self.engine, notice_id))
            self.assertEqual(send.call_count, 1)
        return m, other, notice_id, params

    def assert_reminder_retired(self, notice_id, params):
        with self.sessions() as db:
            notice = db.get(UserNotice, notice_id)
            self.assertEqual((notice.is_read, notice.push_done), (1, 1))
            # Even a previously queued push must be rejected by the final check.
            notice.is_read, notice.push_done = 0, 0
            db.commit()
        self.assertFalse(self.client.get('/api/push/check', params=params).json()['show'])
        with patch.object(push, 'webpush') as send:
            self.assertTrue(push.deliver_notice_push(self.engine, notice_id))
            send.assert_not_called()

    def test_cancel_suppresses_queued_and_delayed_reminders(self):
        m, other, notice_id, params = self.due_reminder()
        self.assertEqual(self.decide(other, m, 'cancel', reason='课程安排冲突，提前取消').status_code, 200)
        self.assert_reminder_retired(notice_id, params)

    def test_reschedule_keeps_old_reminder_until_everyone_accepts(self):
        m, other, notice_id, params = self.due_reminder()
        proposed = self.client.post(f"/api/meetups/{m['id']}/change", json={
            'starts_at': (datetime.now(timezone.utc)+timedelta(days=3)).isoformat(),
            'location': '新体育馆', 'duration': 90, 'revision': m['revision']})
        self.assertEqual(proposed.status_code, 200, proposed.text)
        self.assertTrue(self.client.get('/api/push/check', params=params).json()['show'])
        self.assertEqual(self.decide(other, proposed.json(), 'accept_change').status_code, 200)
        self.assert_reminder_retired(notice_id, params)

    def test_leaving_group_retires_only_departing_members_reminder(self):
        activity, other, m = self.group()
        third = self.another('third')
        m = third.post(f"/api/activities/{activity['id']}/join", json={}).json()
        now = datetime.utcnow()
        with self.sessions() as db:
            db.get(Meetup, m['id']).starts_at = now + timedelta(hours=2)
            db.commit()
        reminders.create_due_reminders(self.engine, now+timedelta(seconds=1))
        owner_id = self.client.get('/api/me').json()['id']
        other_id = other.get('/api/me').json()['id']
        with self.sessions() as db:
            alarms = {n.user_id: n.id for n in db.scalars(select(UserNotice).where(UserNotice.dedupe_key.is_not(None)))}
        self.assertEqual(self.decide(other, m, 'cancel', reason='临时上课，提前退出组局').status_code, 200)
        self.assertFalse(other.get('/api/push/check', params={'user_id':other_id, 'notice_id':alarms[other_id]}).json()['show'])
        self.assertTrue(self.client.get('/api/push/check', params={'user_id':owner_id, 'notice_id':alarms[owner_id]}).json()['show'])
        with self.sessions() as db:
            self.assertEqual(db.get(UserNotice, alarms[other_id]).is_read, 1)
            self.assertEqual(db.get(UserNotice, alarms[owner_id]).is_read, 0)

    def test_push_validation_logout_ownership_and_durable_delivery(self):
        uid,oid,chat,other=self.pair()
        sub=self.subscription()
        self.assertEqual(self.client.put('/api/push/subscriptions',json=sub).status_code,200)
        key=self.client.get('/api/push/public-key').json()['public_key']
        self.assertEqual(len(push.unb64(key)),65)
        self.assertEqual(key,self.client.get('/api/push/public-key').json()['public_key'])
        for bad in ['http://localhost/','https://127.0.0.1/','https://fcm.googleapis.com.evil.test/','https://fcm.googleapis.com:99/']:
            self.assertEqual(self.client.put('/api/push/subscriptions',json={**sub,'endpoint':bad}).status_code,422)
        evil={**sub,'keys':self.subscription('different')['keys']}
        self.assertEqual(other.put('/api/push/subscriptions',json=evil).status_code,409)
        with patch.object(push,'webpush',side_effect=RuntimeError('temporary')):
            msg=other.post(f'/api/buddy-chats/{chat}/messages',json={'body':'正文不能进推送'}).json()['id']
        with self.sessions() as db:
            queued=db.scalar(select(UserNotice).where(UserNotice.message_id==msg))
            self.assertEqual(queued.push_done,0)
            self.assertEqual(queued.push_attempts,1)
        with patch.object(push,'webpush') as send:
            reminders.deliver_pending(self.engine,datetime.utcnow()+timedelta(minutes=6))
            self.assertEqual(send.call_count,1)
            self.assertNotIn('正文',send.call_args.args[1])
        self.client.post('/api/logout')
        with self.sessions() as db:
            self.assertEqual(list(db.scalars(select(PushSubscription))),[])

    def test_notification_cursor_does_not_replay_history_or_leak_other_chats(self):
        uid,oid,chat,other=self.pair()
        baseline=self.client.get('/api/buddy-notifications').json()['cursor']
        msg=other.post(f'/api/buddy-chats/{chat}/messages',json={'body':'新消息'}).json()['id']
        feed=self.client.get('/api/buddy-notifications',params={'after':baseline}).json()
        self.assertEqual([x['id'] for x in feed['items']],[msg])
        self.assertEqual(self.client.get('/api/buddy-notifications',params={'after':feed['cursor']}).json()['items'],[])
        self.assertEqual(other.get('/api/buddy-notifications?after=0').json()['items'],[])
        self.client.post(f'/api/buddy-chats/{chat}/read',json={'message_id':msg})
        self.assertEqual(self.client.get('/api/buddy-notifications?after=0').json()['items'],[])


if __name__=='__main__':
    unittest.main()
