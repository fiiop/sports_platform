"""Small, idempotent schema upgrade for databases created before place-only statuses.

SQLite cannot drop NOT NULL in place. Rebuild only this leaf table inside an
explicit transaction, retaining its actual columns, constraints, indexes and
triggers. PostgreSQL can alter the two columns directly. No user data is reset.
"""
from sqlalchemy import MetaData, Table, inspect, select, text


def allow_place_only_statuses(engine):
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            # Serializes concurrent startup upgrades; explicitly includes SQLite DDL.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            connection.begin()
            if engine.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(1742102101)"))
        try:
            schema = inspect(connection)
            if "buddy_statuses" not in schema.get_table_names():
                connection.commit()
                return
            columns = {column["name"]: column for column in schema.get_columns("buddy_statuses")}
            if all(columns[name]["nullable"] for name in ("latitude", "longitude")):
                connection.commit()
                return
            if engine.dialect.name == "postgresql":
                connection.exec_driver_sql("ALTER TABLE buddy_statuses ALTER COLUMN latitude DROP NOT NULL")
                connection.exec_driver_sql("ALTER TABLE buddy_statuses ALTER COLUMN longitude DROP NOT NULL")
            elif engine.dialect.name == "sqlite":
                # The shipped schema has no incoming FK. Refuse unexpected custom
                # schemas instead of risking cascade deletion during the rebuild.
                for name in schema.get_table_names():
                    if any(key["referred_table"] == "buddy_statuses" for key in schema.get_foreign_keys(name)):
                        raise RuntimeError("buddy_statuses has incoming foreign keys; manual migration required")
                dependent_sql = connection.execute(text(
                    "SELECT sql FROM sqlite_master WHERE tbl_name = 'buddy_statuses' "
                    "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
                )).scalars().all()
                metadata = MetaData()
                old = Table("buddy_statuses", metadata, autoload_with=connection)
                replacement = old.to_metadata(metadata, name="buddy_statuses_nullable_v1")
                replacement.c.latitude.nullable = True
                replacement.c.longitude.nullable = True
                # Original named indexes still exist until the old table is dropped.
                replacement.indexes.clear()
                replacement.create(connection)
                names = [column.name for column in old.columns]
                connection.execute(replacement.insert().from_select(names, select(*old.columns)))
                old.drop(connection)
                connection.exec_driver_sql("ALTER TABLE buddy_statuses_nullable_v1 RENAME TO buddy_statuses")
                for statement in dependent_sql:
                    connection.exec_driver_sql(statement)
            else:
                raise RuntimeError("Place-only status migration supports SQLite and PostgreSQL")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
