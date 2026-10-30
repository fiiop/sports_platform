"""Identity, upload validation, private media access and database persistence."""
import os
os.environ['DATABASE_URL'] = 'sqlite://'
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Activity, ActivityCover, ModerationAction, ProfileAvatar, PublicIdentity, User
from app.services import media
import test_buddies
import test_regressions


def picture(size=(900, 600), fmt='PNG', **save_options):
    output = BytesIO()
    Image.new('RGB', size, (25, 105, 70)).save(output, format=fmt, **save_options)
    return output.getvalue()


class MediaTests(unittest.TestCase):
    tearDown = test_regressions.RegressionTests.tearDown
    login = test_regressions.RegressionTests.login
    another = test_buddies.BuddyTests.another

    def setUp(self):
        test_regressions.RegressionTests.setUp(self)
        self.sessions.configure(autoflush=False)

    def activity(self, capacity=2):
        return self.client.post('/api/activities', json={
            'exercise_type': '羽毛球', 'location': '体育馆', 'capacity': capacity,
            'starts_at': (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}).json()

    def upload(self, path='/api/profile/avatar', content=None, client=None):
        return (client or self.client).post(path, files={
            'file': ('photo.png', picture() if content is None else content, 'image/png')})

    def test_identity_optional_trimmed_and_activities_show_real_participants(self):
        self.assertEqual(self.client.put('/api/profile/identity', json={'nickname':'test'}).status_code,401)
        self.login()
        result = self.client.put('/api/profile/identity', json={'nickname':' 小林 ', 'bio':' 新手也欢迎 '})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['display_name'],'小林')
        self.assertEqual(result.json()['bio'],'新手也欢迎')
        self.assertEqual(self.client.get('/api/me').json()['username'],'student')
        group=self.activity(3)
        self.assertEqual(len(group['participants']),1)
        self.assertEqual(group['participants'][0]['display_name'],'小林')
        member=self.another('teammate')
        member.put('/api/profile/identity',json={'nickname':'小陈'})
        self.assertEqual(member.post(f"/api/activities/{group['id']}/join",json={}).status_code,200)
        activity=self.client.get('/api/activities/mine').json()[0]
        self.assertEqual(activity['joined'],2)
        self.assertEqual([p['display_name'] for p in activity['participants']],['小林','小陈'])
        self.assertEqual(self.client.put('/api/profile/identity',json={'nickname':'x'*31}).status_code,422)
        self.assertEqual(self.client.put('/api/profile/identity',json={'bio':'x'*161}).status_code,422)
        profile=self.client.get('/api/profile').json()
        self.assertEqual(profile['nickname'],'小林')
        self.assertIn('theme',profile)
        cleared=self.client.put('/api/profile/identity',json={'nickname':' ', 'bio':''}).json()
        self.assertEqual(cleared['display_name'],'student')

    def test_avatar_is_compressed_rotated_without_metadata_and_can_be_removed(self):
        self.assertEqual(self.upload().status_code,401)
        self.login()
        exif=Image.Exif()
        exif[274]=6
        exif[315]='private-camera-owner'
        result=self.upload(content=picture((800,400),'JPEG',exif=exif))
        self.assertEqual(result.status_code,200,result.text)
        url=result.json()['avatar_url']
        image_response=self.client.get(url)
        self.assertEqual(image_response.headers['content-type'],'image/jpeg')
        self.assertIn('no-store',image_response.headers['cache-control'])
        self.assertEqual(image_response.headers['x-content-type-options'],'nosniff')
        with Image.open(BytesIO(image_response.content)) as output:
            self.assertEqual(output.size,(256,512))
            self.assertFalse(output.getexif())
            self.assertEqual(output.mode,'RGB')
        self.assertNotIn(b'private-camera-owner',image_response.content)
        replacement=self.upload(content=picture((200,200))).json()['avatar_url']
        self.assertNotEqual(replacement,url)
        self.assertEqual(self.client.delete('/api/profile/avatar').json()['avatar_url'],None)
        self.assertEqual(self.client.get(url).status_code,404)

    def test_invalid_uploads_do_not_replace_existing_image(self):
        self.login()
        url=self.upload().json()['avatar_url']
        original=self.client.get(url).content
        invalid=[b'', b'<svg onload="alert(1)"></svg>', b'not-an-image', picture(fmt='GIF'), picture()[:60]]
        for raw in invalid:
            result=self.upload(content=raw)
            self.assertEqual(result.status_code,422,result.text)
        self.assertEqual(self.upload(content=b'x'*(media.MAX_UPLOAD_BYTES+1)).status_code,413)
        self.assertEqual(self.client.get(url).content,original)
        self.assertEqual(self.client.get('/api/profile').json()['avatar_url'],url)

    def test_pixel_limit_is_checked_before_decoding(self):
        self.login()
        from unittest.mock import patch
        with patch.object(media,'MAX_PIXELS',100):
            self.assertEqual(self.upload(content=picture((11,10))).status_code,413)

    def test_cover_is_owned_compressed_and_blacklist_protects_both_image_types(self):
        self.login()
        uid=self.client.get('/api/me').json()['id']
        activity=self.activity()
        path=f"/api/activities/{activity['id']}/cover"
        self.assertEqual(self.upload(path, picture((2400,1600))).status_code,200)
        avatar_url=self.upload().json()['avatar_url']
        other=self.another('other')
        cover=other.get(path)
        self.assertEqual(cover.status_code,200)
        with Image.open(BytesIO(cover.content)) as output:
            self.assertEqual(max(output.size),1280)
        self.assertEqual(self.upload(path,client=other).status_code,404)
        self.assertEqual(other.delete(path).status_code,404)
        other.put(f'/api/buddy-blocks/{uid}')
        self.assertEqual(other.get(path).status_code,404)
        self.assertEqual(other.get(avatar_url).status_code,404)
        self.assertEqual(self.client.get(path).status_code,200)
        other.delete(f'/api/buddy-blocks/{uid}')
        self.assertEqual(other.get(avatar_url).status_code,200)
        self.assertEqual(self.client.delete(path).json()['cover_url'],None)
        self.assertEqual(self.client.get(path).status_code,404)

    def test_inactive_cover_visible_only_to_owner_and_existing_participant(self):
        self.login()
        activity=self.activity(3)
        path=f"/api/activities/{activity['id']}/cover"
        self.upload(path)
        member=self.another('member')
        member.post(f"/api/activities/{activity['id']}/join",json={})
        outsider=self.another('outsider')
        with self.sessions() as db:
            db.get(Activity,activity['id']).active=0
            db.commit()
        self.assertEqual(outsider.get(path).status_code,404)
        self.assertEqual(member.get(path).status_code,200)
        self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.upload(path).status_code,409)

    def test_image_and_identity_survive_engine_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            database_url='sqlite:///'+(Path(directory)/'persistent.db').as_posix()
            engine=create_engine(database_url)
            try:
                Base.metadata.create_all(engine)
                with Session(engine) as db:
                    user=User(username='persisted',password_hash='unused-test-value')
                    db.add(user);db.flush()
                    uid=user.id
                    db.add(PublicIdentity(user_id=uid,nickname='小周',bio='爱运动'))
                    content=picture((80,60),'JPEG')
                    db.add(ProfileAvatar(user_id=uid,version='v1',content=content))
                    activity=Activity(user_id=uid,exercise_type='跑步',location='操场',
                                      starts_at=datetime.utcnow()+timedelta(days=1))
                    db.add(activity);db.flush()
                    activity_id=activity.id
                    db.add(ActivityCover(activity_id=activity_id,version='v2',content=content))
                    db.commit()
            finally:
                engine.dispose()
            reopened=create_engine(database_url)
            try:
                with Session(reopened) as db:
                    self.assertEqual(media.identity_dict(db,uid)['display_name'],'小周')
                    avatar=db.get(ProfileAvatar,uid)
                    cover=db.get(ActivityCover,activity_id)
                    self.assertIn('content',inspect(avatar).unloaded)
                    self.assertIn('content',inspect(cover).unloaded)
                    self.assertEqual(avatar.content,content)
                    self.assertEqual(cover.content,content)
            finally:
                reopened.dispose()

    def test_group_preview_hides_blocked_and_suspended_people_without_faking_count(self):
        self.login()
        group=self.activity(4)
        first=self.another('first')
        first_id=first.get('/api/me').json()['id']
        second=self.another('second')
        second_id=second.get('/api/me').json()['id']
        for client in (first,second):
            self.assertEqual(client.post(f"/api/activities/{group['id']}/join",json={}).status_code,200)
        viewer=self.another('viewer')
        # Either direction of blocking hides the participant's identity preview.
        viewer_id=viewer.get('/api/me').json()['id']
        first.put(f'/api/buddy-blocks/{viewer_id}')
        with self.sessions() as db:
            db.add(ModerationAction(user_id=second_id,suspended_until=datetime.utcnow()+timedelta(days=1)))
            db.commit()
        row=viewer.get('/api/activities').json()[0]
        self.assertEqual(row['joined'],3)
        self.assertEqual([p['user_id'] for p in row['participants']],[group['user_id']])
        self.assertNotIn(first_id,[p['user_id'] for p in row['participants']])

    def test_listing_does_not_select_image_binaries_and_media_requires_login(self):
        self.login()
        group=self.activity(3)
        avatar=self.upload().json()['avatar_url']
        cover=f"/api/activities/{group['id']}/cover"
        self.assertEqual(self.upload(cover).status_code,200)
        statements=[]
        def record_query(connection,cursor,statement,parameters,context,executemany):
            statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',record_query)
        try:
            self.assertEqual(self.client.get('/api/activities').status_code,200)
        finally:
            event.remove(self.engine,'before_cursor_execute',record_query)
        self.assertTrue(statements)
        self.assertFalse(any('profile_avatars.content' in q or 'activity_covers.content' in q for q in statements))
        self.client.post('/api/logout')
        self.assertEqual(self.client.get(avatar).status_code,401)
        self.assertEqual(self.client.get(cover).status_code,401)


if __name__=='__main__':
    unittest.main()
