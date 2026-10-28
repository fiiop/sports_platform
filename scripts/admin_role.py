"""Manage an existing account's administrator role using server-side database access.

Run from the repository root: python scripts/admin_role.py grant --username test02
DATABASE_URL must be set explicitly. This command neither creates users nor runs migrations.
"""
import argparse
import os
import sys

from sqlalchemy import MetaData, Table, create_engine, inspect, select, update


class AdminCommandError(Exception):
    pass


def change_role(engine, action, username):
    """Return the final role, changing only the exact existing username requested."""
    if not username or username != username.strip():
        raise AdminCommandError("Username must be nonempty and have no surrounding whitespace.")
    with engine.begin() as connection:
        required = {"users", "admin_roles", "migration_stamps"}
        if not required.issubset(set(inspect(connection).get_table_names())):
            raise AdminCommandError("Version 4 database is not initialized. Start the application once first.")
        metadata = MetaData()
        users = Table("users", metadata, autoload_with=connection)
        roles = Table("admin_roles", metadata, autoload_with=connection)
        stamps = Table("migration_stamps", metadata, autoload_with=connection)
        if connection.scalar(select(stamps.c.name).where(stamps.c.name == "v4-admin-test02")) is None:
            raise AdminCommandError("Version 4 initialization is incomplete. Start the application once first.")
        account = connection.execute(select(users.c.id, users.c.username).where(
            users.c.username == username)).first()
        # Check again in Python: a database with case-insensitive collation must not
        # turn a typo into an administrator grant for a different username.
        if account is None or account.username != username:
            raise AdminCommandError("Exact username was not found; no account was created or changed.")
        if action != "status":
            connection.execute(update(users).where(users.c.id == account.id).values(username=users.c.username))
        present = connection.scalar(select(roles.c.user_id).where(roles.c.user_id == account.id)) is not None
        if action == "grant" and not present:
            connection.execute(roles.insert().values(user_id=account.id))
            present = True
        elif action == "revoke" and present:
            connection.execute(roles.delete().where(roles.c.user_id == account.id))
            present = False
        elif action not in {"grant", "revoke", "status"}:
            raise AdminCommandError("Unsupported action.")
        return present


def main(argv=None, environ=None):
    parser = argparse.ArgumentParser(description="Grant, revoke or check an existing user's administrator role.")
    parser.add_argument("action", choices=("grant", "revoke", "status"))
    parser.add_argument("--username", required=True, help="Exact, case-sensitive existing username")
    args = parser.parse_args(argv)
    source = os.environ if environ is None else environ
    url = source.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL must be explicitly configured for the intended database.", file=sys.stderr)
        return 2
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
            break
    engine = None
    try:
        engine = create_engine(url, future=True, pool_pre_ping=True)
        present = change_role(engine, args.action, args.username)
    except AdminCommandError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        # Database exceptions may contain credentials, hostnames and connection
        # strings. Do not print the exception or a traceback in this operator CLI.
        print("Database operation failed; verify server access and database initialization. No credentials are shown.", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()
    print(f"{args.username}: administrator={'yes' if present else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
