import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from sqlalchemy import create_engine, text

from scripts.admin_role import main


class AdminCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.url = "sqlite:///" + (Path(self.directory.name) / "admin.db").as_posix()
        self.engine = create_engine(self.url)
        with self.engine.begin() as db:
            # NOCASE exercises the CLI's explicit case-sensitive verification.
            db.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT COLLATE NOCASE UNIQUE)"))
            db.execute(text("CREATE TABLE admin_roles (user_id INTEGER PRIMARY KEY REFERENCES users(id))"))
            db.execute(text("CREATE TABLE migration_stamps (name TEXT PRIMARY KEY)"))
            db.execute(text("INSERT INTO migration_stamps VALUES ('v4-admin-test02')"))
            db.execute(text("INSERT INTO users VALUES (1, 'test02'), (2, 'another')"))

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def run_cli(self, action, username="test02", environ=None):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = main([action, "--username", username],
                          {"DATABASE_URL": self.url} if environ is None else environ)
        return result, output.getvalue(), errors.getvalue()

    def test_grant_revoke_status_are_idempotent_and_targeted(self):
        self.assertIn("administrator=no", self.run_cli("status")[1])
        for _ in range(2):
            self.assertEqual(self.run_cli("grant")[0], 0)
        with self.engine.connect() as db:
            self.assertEqual(db.execute(text("SELECT user_id FROM admin_roles")).all(), [(1,)])
        self.assertIn("administrator=yes", self.run_cli("status")[1])
        for _ in range(2):
            self.assertEqual(self.run_cli("revoke")[0], 0)
        self.assertIn("administrator=no", self.run_cli("status")[1])

    def test_unknown_and_case_mismatched_users_are_rejected(self):
        for username in ("missing", "TEST02", " test02", ""):
            self.assertEqual(self.run_cli("grant", username)[0], 2)
        with self.engine.connect() as db:
            self.assertEqual(db.scalar(text("SELECT count(*) FROM admin_roles")), 0)
            self.assertEqual(db.scalar(text("SELECT count(*) FROM users")), 2)

    def test_requires_explicit_database_and_completed_initialization(self):
        self.assertEqual(self.run_cli("grant", environ={})[0], 2)
        with self.engine.begin() as db:
            db.execute(text("DELETE FROM migration_stamps"))
        self.assertEqual(self.run_cli("grant")[0], 2)

    def test_connection_errors_do_not_echo_secrets(self):
        result, output, errors = self.run_cli("grant", environ={
            "DATABASE_URL": "unknown_driver://user:DO_NOT_ECHO_THIS@invalid.example/database"})
        self.assertEqual(result, 2)
        self.assertNotIn("DO_NOT_ECHO_THIS", output + errors)
        self.assertNotIn("invalid.example", output + errors)


if __name__ == "__main__":
    unittest.main()
