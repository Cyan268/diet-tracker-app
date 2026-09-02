from importlib import import_module
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models import Base


async def test_v8_to_v9_preserves_global_ids_and_backfills_per_user(pg_session_factory):
    schema = f"u4_migration_{uuid4().hex}"
    assert schema.startswith("u4_migration_") and schema.replace("_", "").isalnum()
    async with pg_session_factory() as session:
        connection = await session.connection()
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))

        def upgrade_old(sync_connection):
            context = MigrationContext.configure(
                sync_connection, opts={"target_metadata": Base.metadata}
            )
            with Operations.context(context):
                for name in [
                    "20260715_0001_create_users",
                    "20260715_0002_create_refresh_tokens",
                    "20260715_0003_create_diet_domain",
                    "20260715_0004_create_sync_changes",
                    "20260717_0005_create_ai_call_logs",
                    "20260718_0006_create_ai_credentials",
                    "20260720_0007_create_assistant_conversations",
                    "20260722_0008_add_demo_account_flag",
                ]:
                    import_module(f"migrations.versions.{name}").upgrade()

        await connection.run_sync(upgrade_old)
        first, second = uuid4(), uuid4()
        for owner in [first, second]:
            await connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'test-only')"
                ),
                {"id": owner, "email": f"{owner}@example.test"},
            )
        for event_id, owner in [(5, first), (20, second), (31, first)]:
            await connection.execute(
                text(
                    "INSERT INTO sync_changes "
                    "(id, user_id, aggregate_id, client_id, operation, version) "
                    "VALUES (:id, :owner, :aggregate, :client, 'delete', 1)"
                ),
                {"id": event_id, "owner": owner, "aggregate": uuid4(), "client": uuid4()},
            )

        def upgrade_new(sync_connection):
            context = MigrationContext.configure(
                sync_connection, opts={"target_metadata": Base.metadata}
            )
            with Operations.context(context):
                import_module("migrations.versions.20260831_0009_order_user_sync").upgrade()

        await connection.run_sync(upgrade_new)
        rows = (
            await connection.execute(text("SELECT id, user_seq FROM sync_changes ORDER BY id"))
        ).all()
        assert rows == [(5, 1), (20, 1), (31, 2)]
        states = dict(
            (await connection.execute(text("SELECT user_id, last_seq FROM user_sync_state"))).all()
        )
        assert states == {first: 2, second: 1}
        assert (
            await connection.scalar(text("SELECT COUNT(DISTINCT epoch) FROM user_sync_state")) == 2
        )
        # The temporary schema/data never become persistent, including on assertion failure.
        await session.rollback()
