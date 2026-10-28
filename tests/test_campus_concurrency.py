"""Exercise real independent SQLite connections racing for bounded resources."""
import os
os.environ['DATABASE_URL'] = 'sqlite://'

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.models import Activity, Meetup, MeetupMember
from app.services import campus


class CampusConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='campus-race-')
        self.engine = create_engine('sqlite:///' + (Path(self.directory.name)/'race.db').as_posix(),
                                    connect_args={'check_same_thread': False, 'timeout': 10})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        def database():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.clients = []
        self.owner = self.account('owner')

    def tearDown(self):
        for client in self.clients:
            client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.directory.cleanup()

    def account(self, username):
        client = TestClient(app)
        self.clients.append(client)
        credentials = {'username': username, 'password': 'test-pass-123'}
        self.assertEqual(client.post('/api/register', json=credentials).status_code, 200)
        self.assertEqual(client.post('/api/login', json=credentials).status_code, 200)
        return client

    def activity(self, **changes):
        return {'exercise_type': '篮球', 'location': '北苑球场', 'capacity': 3,
                'starts_at': (datetime.now(timezone.utc)+timedelta(days=2)).isoformat(), **changes}

    def race(self, callbacks):
        barrier = Barrier(2)
        original_lock = campus.lock_user
        def synchronized_lock(db, user_id):
            barrier.wait(timeout=5)
            return original_lock(db, user_id)
        with patch.object(campus, 'lock_user', side_effect=synchronized_lock), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(callback) for callback in callbacks]
            return [future.result(timeout=15) for future in futures]

    def test_only_one_person_can_claim_the_last_group_seat(self):
        activity = self.owner.post('/api/activities', json=self.activity()).json()
        seed, first, second = [self.account(name) for name in ('seed', 'first', 'second')]
        path = f"/api/activities/{activity['id']}/join"
        self.assertEqual(seed.post(path, json={}).status_code, 200)
        responses = self.race([lambda: first.post(path, json={}), lambda: second.post(path, json={})])
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409],
                         [response.text for response in responses])
        with self.sessions() as db:
            meeting = db.scalar(select(Meetup).where(Meetup.activity_id==activity['id']))
            count = db.scalar(select(func.count()).select_from(MeetupMember).where(
                MeetupMember.meetup_id==meeting.id, MeetupMember.status=='accepted'))
            self.assertEqual(count, 3)

    def test_same_user_cannot_publish_a_fourth_status_concurrently(self):
        for _ in range(2):
            self.assertEqual(self.owner.post('/api/activities', json=self.activity(capacity=2)).status_code, 200)
        second = TestClient(app)
        self.clients.append(second)
        second.cookies.set('session', self.owner.cookies.get('session'))
        payload = self.activity(capacity=2)
        responses = self.race([lambda: self.owner.post('/api/activities', json=payload),
                               lambda: second.post('/api/activities', json=payload)])
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409],
                         [response.text for response in responses])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Activity)), 3)


if __name__ == '__main__':
    unittest.main()
