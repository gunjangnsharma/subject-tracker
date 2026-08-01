"""Additive schema reconciliation for databases created by an older version.

There is no migration tool (see BUILD_CONTEXT §12.7) and `create_all` only
creates **missing tables** — it never alters a table that already exists. So a
database written before a new column was introduced keeps its old shape, and
every query mentioning that column fails with "no such column". The same is true
of **indexes**: adding one to a model does nothing for a table that already
exists, which is how a live database ends up doing full scans.

This module closes those two gaps: it adds **missing nullable/defaulted columns**
and **missing indexes** to existing tables, and nothing else. Deliberately narrow —

* it only ever runs ``ALTER TABLE ... ADD COLUMN`` (safe and instant in SQLite)
  and ``CREATE INDEX IF NOT EXISTS``,
* it never drops, renames, retypes or reorders anything,
* it is idempotent: already-present columns and indexes are skipped,
* it is not a migration framework. Anything beyond adding a defaulted column
  still means recreating the database (or adopting Alembic).

Called by ``Database.create_all`` so both fresh and existing databases end up
with a schema the current models can query efficiently.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, inspect, text


@dataclass(frozen=True)
class AddedColumn:
    """One column this reconciliation added to an existing table."""

    table: str
    column: str


#: Columns introduced after the initial schema, with the DDL to add them.
#: Each entry must be safe to apply to a populated table — i.e. nullable, or
#: NOT NULL with a server default so existing rows get a value.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    # Chapter display order within its module (feature: reorder chapters).
    # Existing rows get 0; `maintenance.backfill_chapter_positions` then assigns
    # real per-module positions from the current id order.
    "chapters": {"position": "INTEGER NOT NULL DEFAULT 0"},
}


def ensure_columns(engine: Engine) -> list[AddedColumn]:
    """Add any known-missing columns to tables that already exist.

    Returns the columns actually added (empty on a fresh or up-to-date
    database), so callers can log or report the change.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: list[AddedColumn] = []

    for table, columns in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue  # create_all will build it complete; nothing to patch.
        present = {c["name"] for c in inspector.get_columns(table)}
        for column, ddl in columns.items():
            if column in present:
                continue
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            added.append(AddedColumn(table=table, column=column))

    return added


def ensure_indexes(engine: Engine) -> list[str]:
    """Create every index the models declare that the database is missing.

    ``create_all`` builds indexes only alongside a table it creates, so a
    database that predates an index never gets it — the table just keeps
    scanning. This walks the model metadata and issues ``CREATE INDEX IF NOT
    EXISTS`` for each index on an existing table.

    Returns the index names created (empty when already up to date). Safe to run
    on every startup: SQLite skips indexes that exist, and creating one on the
    small tables this app uses is effectively instant.
    """
    from tracker.database import Base

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    created: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all built it with its indexes already.
        present = {index["name"] for index in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name in present:
                continue
            columns = ", ".join(column.name for column in index.columns)
            with engine.begin() as connection:
                connection.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {index.name} ON {table.name} ({columns})")
                )
            created.append(index.name)

    return created
