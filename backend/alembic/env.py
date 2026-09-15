"""Alembic environment.

The database URL comes from application Settings rather than alembic.ini, so migrations
cannot be run against a different database than the application uses, and no credential
is ever written into a tracked file.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importing the models package registers every table on Base.metadata.
import app.models  # noqa: F401  (side-effect import)
from alembic import context
from app.core.config import get_settings
from app.core.db import SCHEMAS, Base

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False, which fileConfig does NOT default to.
    #
    # The default silently sets .disabled on every logger that already exists. The test
    # suite runs these migrations at session start, after the application modules are
    # imported, so it was switching off the app's own loggers for the rest of the run -
    # and any test asserting on a log line would have passed while checking nothing.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", str(get_settings().database_url))


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Restrict autogenerate to schemas this application owns."""
    return not (type_ == "table" and obj.schema not in SCHEMAS)


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
        # Detect column type changes, which are otherwise silently missed.
        compare_type=True,
        compare_server_default=True,
        version_table_schema="public",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
