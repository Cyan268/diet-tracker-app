import pytest
from fastapi import HTTPException, Request
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.services.auth_guard import AuthGuard


class FakeRedis:
    def __init__(self, result=(1, 60_000), error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.eval_calls: list[tuple] = []
        self.delete_calls: list[str] = []

    async def eval(self, *args):
        self.eval_calls.append(args)
        if self.error is not None:
            raise self.error
        return self.result

    async def delete(self, key: str):
        self.delete_calls.append(key)
        if self.error is not None:
            raise self.error
        return 1


def make_request(peer: str = "198.51.100.10", forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request({"type": "http", "client": (peer, 12345), "headers": headers})


async def test_auth_rate_key_is_normalized_private_and_action_scoped() -> None:
    redis = FakeRedis()
    guard = AuthGuard(Settings(_env_file=None), redis)  # type: ignore[arg-type]

    request = make_request()
    await guard.enforce_rate("login", "Student@Example.com", request)
    first_key = redis.eval_calls[-1][2]
    first_visitor_key = redis.eval_calls[-2][2]
    await guard.enforce_rate("login", "student@example.com", request)
    second_key = redis.eval_calls[-1][2]
    await guard.enforce_rate("register", "student@example.com", request)
    register_key = redis.eval_calls[-1][2]

    assert first_key == second_key
    assert first_key != register_key
    assert first_visitor_key == redis.eval_calls[-2][2]
    assert "student@example.com" not in first_key.lower()
    assert "198.51.100.10" not in first_visitor_key
    assert len(first_key.rsplit(":", 1)[-1]) == 64


async def test_auth_rate_limit_returns_retry_after() -> None:
    redis = FakeRedis(result=(11, 45_001))
    guard = AuthGuard(
        Settings(_env_file=None, auth_login_attempts_per_window=10),
        redis,  # type: ignore[arg-type]
    )

    with pytest.raises(HTTPException) as raised:
        await guard.enforce_rate("login", "target@example.com", make_request())

    assert raised.value.status_code == 429
    assert raised.value.headers == {"Retry-After": "46"}


async def test_visitor_bucket_blocks_email_rotation_and_ignores_spoofed_header() -> None:
    redis = FakeRedis(result=(3, 30_001))
    guard = AuthGuard(
        Settings(
            _env_file=None,
            auth_visitor_requests_per_window=2,
            trusted_proxy_cidrs=["10.0.0.0/8"],
        ),
        redis,  # type: ignore[arg-type]
    )

    with pytest.raises(HTTPException) as raised:
        await guard.enforce_rate(
            "login",
            "rotated@example.com",
            make_request("198.51.100.10", "203.0.113.99"),
        )

    assert raised.value.status_code == 429
    assert raised.value.detail == "authentication visitor limit reached; retry later"
    assert len(redis.eval_calls) == 1
    assert "198.51.100.10" not in redis.eval_calls[0][2]
    assert "203.0.113.99" not in redis.eval_calls[0][2]


async def test_successful_login_clear_uses_same_private_key() -> None:
    redis = FakeRedis()
    guard = AuthGuard(Settings(_env_file=None), redis)  # type: ignore[arg-type]

    await guard.enforce_rate("login", "Student@Example.com", make_request())
    await guard.clear_login_rate("student@example.com")

    assert redis.delete_calls == [redis.eval_calls[1][2]]


async def test_auth_rate_limit_has_explicit_redis_failure_policy() -> None:
    unavailable = FakeRedis(error=RedisConnectionError("redis unavailable"))

    await AuthGuard(
        Settings(_env_file=None, auth_protection_fail_closed=False),
        unavailable,  # type: ignore[arg-type]
    ).enforce_rate("login", "student@example.com", make_request())

    with pytest.raises(HTTPException) as raised:
        await AuthGuard(
            Settings(_env_file=None, auth_protection_fail_closed=True),
            unavailable,  # type: ignore[arg-type]
        ).enforce_rate("login", "student@example.com", make_request())

    assert raised.value.status_code == 503
    assert raised.value.headers == {"Retry-After": "30"}


async def test_success_cleanup_failure_does_not_orphan_committed_login_response() -> None:
    unavailable = FakeRedis(error=RedisConnectionError("redis unavailable"))
    guard = AuthGuard(
        Settings(_env_file=None, auth_protection_fail_closed=True),
        unavailable,  # type: ignore[arg-type]
    )

    await guard.clear_login_rate("student@example.com")
