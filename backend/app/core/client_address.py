from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from typing import Final

from starlette.types import Scope

FORWARDED_FOR_HEADER: Final = b"x-forwarded-for"
MAX_FORWARDED_HOPS: Final = 20

IPAddress = IPv4Address | IPv6Address


def _is_trusted(address: IPAddress, trusted_proxy_cidrs: list[str]) -> bool:
    return any(address in ip_network(cidr, strict=False) for cidr in trusted_proxy_cidrs)


def _peer_address(scope: Scope) -> IPAddress | None:
    client = scope.get("client")
    if client is None:
        return None
    try:
        return ip_address(client[0])
    except ValueError:
        return None


def _forwarded_chain(scope: Scope) -> list[IPAddress] | None:
    raw_values: list[str] = []
    for key, value in scope.get("headers", []):
        if key.lower() != FORWARDED_FOR_HEADER:
            continue
        try:
            raw_values.append(value.decode("ascii"))
        except UnicodeDecodeError:
            return None
    if not raw_values:
        return []
    parts = [part.strip() for value in raw_values for part in value.split(",")]
    if not parts or len(parts) > MAX_FORWARDED_HOPS or any(not part for part in parts):
        return None
    try:
        return [ip_address(part) for part in parts]
    except ValueError:
        return None


def resolve_client_address(scope: Scope, trusted_proxy_cidrs: list[str]) -> str:
    peer = _peer_address(scope)
    if peer is None:
        return "unknown"
    if not trusted_proxy_cidrs or not _is_trusted(peer, trusted_proxy_cidrs):
        return peer.compressed

    forwarded = _forwarded_chain(scope)
    if not forwarded:
        return peer.compressed

    for address in reversed([*forwarded, peer]):
        if not _is_trusted(address, trusted_proxy_cidrs):
            return address.compressed
    return forwarded[0].compressed
