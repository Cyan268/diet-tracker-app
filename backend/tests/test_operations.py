from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.runtime_metrics import runtime_metrics
from app.main import app
from app.models import AiCallLog, AnalysisJob
from app.schemas.operations import HostBackupSnapshot, HostContainerSnapshot, HostSnapshot
from app.services.operations import collect_operational_metrics, read_host_snapshot


def _job(*, status: str, created_at: datetime) -> AnalysisJob:
    now = datetime.now(UTC)
    return AnalysisJob(
        id=uuid4(),
        user_id=uuid4(),
        client_request_id=uuid4(),
        request_hash="a" * 64,
        input_type="text",
        input_ciphertext=b"encrypted",
        input_key_version=1,
        input_expires_at=now + timedelta(hours=1),
        status=status,
        provider="rule_based_v1",
        model="deterministic-parser-v1",
        prompt_version="food-text-v1",
        result_schema_version="1.0",
        created_at=created_at,
        updated_at=created_at,
    )


def test_runtime_metrics_have_bounded_labels_and_aggregate_sync() -> None:
    runtime_metrics.reset_for_tests()
    runtime_metrics.record_http("GET", "app.api.routes.diet.read_logs", 200, 17)
    runtime_metrics.record_db_pool_wait(3)
    runtime_metrics.record_sync_page(4)
    runtime_metrics.record_sync_conflict()

    snapshot = runtime_metrics.snapshot()

    assert snapshot["http_requests"] == [
        {
            "method": "GET",
            "endpoint": "app.api.routes.diet.read_logs",
            "status_code": 200,
            "count": 1,
        }
    ]
    assert snapshot["db_pool_wait_ms"]["count"] == 1
    assert snapshot["sync"] == {"pages": 1, "results": 4, "conflicts": 1}


async def test_operational_snapshot_fires_queue_and_unknown_alerts(session_factory) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add_all(
            [
                _job(status="queued", created_at=now - timedelta(minutes=6)),
                _job(status="unknown", created_at=now - timedelta(minutes=1)),
            ]
        )
        await session.commit()
        snapshot = await collect_operational_metrics(
            session,
            Settings(_env_file=None, environment="test"),
            now=now,
        )

    alerts = {alert.code: alert for alert in snapshot.alerts}
    assert alerts["worker-queue-oldest"].state == "firing"
    assert alerts["worker-unknown-result"].state == "firing"
    assert alerts["worker-failure-rate"].state == "unknown"
    assert alerts["host-snapshot-stale"].state == "unknown"
    assert snapshot.privacy_contract["contains_user_ids"] is False
    assert "Host metrics" in " ".join(snapshot.limitations)


async def test_budget_alerts_are_aggregated_without_user_identity(session_factory) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            AiCallLog(
                user_id=uuid4(),
                operation="weekly_report",
                provider="openai",
                model="bounded-model",
                status="success",
                fallback_used=False,
                latency_ms=20,
                attempt_count=1,
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                estimated_cost_usd="9.0",
                input_sha256="b" * 64,
                created_at=now,
            )
        )
        await session.commit()
        snapshot = await collect_operational_metrics(
            session,
            Settings(
                _env_file=None,
                environment="test",
                ai_global_monthly_budget_usd="10",
                ai_per_user_monthly_budget_usd="8",
            ),
            now=now,
        )

    alerts = {alert.code: alert for alert in snapshot.alerts}
    assert alerts["ai-global-budget-warning"].state == "firing"
    assert alerts["ai-global-budget"].state == "ok"
    assert alerts["ai-per-user-budget"].state == "firing"
    assert snapshot.ai["users_at_or_over_budget"] == 1
    assert "user_id" not in str(snapshot.ai)


async def test_host_snapshot_triggers_resource_container_and_backup_alerts(
    session_factory, monkeypatch
) -> None:
    now = datetime.now(UTC)
    host = HostSnapshot(
        schema_version="1.0",
        generated_at=now - timedelta(minutes=2),
        memory_total_bytes=100,
        memory_available_bytes=10,
        disk_total_bytes=100,
        disk_free_bytes=5,
        memory_pressure_active=True,
        consecutive_memory_pressure_samples=2,
        consecutive_memory_recovery_samples=0,
        container_unhealthy_active=True,
        consecutive_container_unhealthy_samples=2,
        consecutive_container_recovery_samples=0,
        containers=[
            HostContainerSnapshot(service="api", running=True, health="unhealthy", restart_count=2)
        ],
        backup=HostBackupSnapshot(status="verified", last_success_at=now - timedelta(hours=40)),
    )
    monkeypatch.setattr("app.services.operations.read_host_snapshot", lambda _: (host, None))
    async with session_factory() as session:
        snapshot = await collect_operational_metrics(
            session,
            Settings(
                _env_file=None,
                environment="test",
                operations_host_snapshot_path=Path("host-snapshot.json"),
            ),
            now=now,
        )

    alerts = {alert.code: alert for alert in snapshot.alerts}
    assert alerts["host-snapshot-stale"].state == "ok"
    assert alerts["host-memory-pressure"].state == "firing"
    assert alerts["host-disk-pressure"].state == "firing"
    assert alerts["container-unhealthy"].state == "firing"
    assert alerts["backup-stale"].state == "firing"
    assert snapshot.host["containers"][0]["restart_count"] == 2


def test_host_snapshot_reader_rejects_extra_or_oversized_content(tmp_path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"secret":"must-not-be-accepted"}', encoding="utf-8")
    assert read_host_snapshot(invalid) == (None, "invalid")

    oversized = tmp_path / "oversized.json"
    oversized.write_text("x" * (64 * 1024 + 1), encoding="utf-8")
    assert read_host_snapshot(oversized) == (None, "file_too_large")


async def test_operations_endpoint_is_hidden_and_requires_constant_time_token(api_client) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        operations_metrics_enabled=True,
        operations_metrics_token="metrics-token-that-is-at-least-32-characters",
    )
    app.dependency_overrides[get_settings] = lambda: settings

    missing = await api_client.get("/api/v1/operations/metrics")
    wrong = await api_client.get(
        "/api/v1/operations/metrics", headers={"X-Operations-Token": "wrong"}
    )
    allowed = await api_client.get(
        "/api/v1/operations/metrics",
        headers={"X-Operations-Token": "metrics-token-that-is-at-least-32-characters"},
    )

    assert missing.status_code == 404
    assert wrong.status_code == 404
    assert allowed.status_code == 200
    assert allowed.json()["privacy_contract"]["contains_credentials"] is False
    assert "/api/v1/operations/metrics" not in app.openapi()["paths"]


async def test_rejected_operations_request_does_not_acquire_database_session(api_client) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        operations_metrics_enabled=True,
        operations_metrics_token="metrics-token-that-is-at-least-32-characters",
    )

    async def forbidden_session():
        raise AssertionError("database dependency must not run before operations authentication")
        yield

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = forbidden_session

    response = await api_client.get("/api/v1/operations/metrics")

    assert response.status_code == 404
