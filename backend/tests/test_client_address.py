from starlette.types import Scope

from app.core.client_address import MAX_FORWARDED_HOPS, resolve_client_address


def scope(peer: str | None, forwarded_for: str | None = None) -> Scope:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return {
        "type": "http",
        "client": None if peer is None else (peer, 12345),
        "headers": headers,
    }


def test_untrusted_peer_cannot_spoof_forwarded_address() -> None:
    resolved = resolve_client_address(
        scope("198.51.100.10", "203.0.113.99"),
        ["10.0.0.0/8"],
    )

    assert resolved == "198.51.100.10"


def test_trusted_proxy_chain_is_walked_from_the_right() -> None:
    resolved = resolve_client_address(
        scope("10.0.0.5", "203.0.113.99, 198.51.100.10, 10.1.0.8"),
        ["10.0.0.0/8"],
    )

    assert resolved == "198.51.100.10"


def test_invalid_or_oversized_forwarded_chain_falls_back_to_peer() -> None:
    trusted = ["10.0.0.0/8"]
    assert resolve_client_address(scope("10.0.0.5", "not-an-ip"), trusted) == "10.0.0.5"
    oversized = ", ".join(["198.51.100.10"] * (MAX_FORWARDED_HOPS + 1))
    assert resolve_client_address(scope("10.0.0.5", oversized), trusted) == "10.0.0.5"


def test_ipv6_is_canonicalized_and_missing_peer_is_bounded() -> None:
    assert resolve_client_address(scope("2001:0db8::0001"), []) == "2001:db8::1"
    assert resolve_client_address(scope(None, "198.51.100.10"), ["10.0.0.0/8"]) == "unknown"
