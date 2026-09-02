"""Validate resolved Compose JSON without printing secrets or contacting dependencies."""

import argparse
import json
import sys
from ipaddress import ip_address, ip_network


def topology_errors(config: dict, *, local: bool = False) -> list[str]:
    errors = []
    services = config.get("services", {})
    if set(services) != {"api", "maintenance", "postgres", "redis", "proxy"}:
        return ["unexpected or missing services in the VPS topology"]
    for name, service in services.items():
        if name != "proxy" and service.get("ports"):
            errors.append(f"{name} must not publish host ports")
        if service.get("network_mode") or service.get("privileged"):
            errors.append(f"{name} must not use privileged/host networking")
        log = service.get("logging", {})
        if log.get("driver") != "json-file" or log.get("options") != {
            "max-size": "10m",
            "max-file": "3",
        }:
            errors.append(f"{name} must use bounded container logs")
    api, proxy = services["api"], services["proxy"]
    env = api.get("environment", {})
    proxy_env = proxy.get("environment", {})
    if set(api.get("networks", {})) != {"edge", "data"}:
        errors.append("API must join edge and data networks")
    if set(proxy.get("networks", {})) != {"edge"}:
        errors.append("proxy must not join the data network")
    for name in ("postgres", "redis", "maintenance"):
        if set(services[name].get("networks", {})) != {"data"}:
            errors.append(f"{name} must only join the data network")
    if config.get("networks", {}).get("data", {}).get("internal") is not True:
        errors.append("data network must be internal")
    try:
        subnet = ip_network(config["networks"]["edge"]["ipam"]["config"][0]["subnet"])
        proxy_ip = ip_address(proxy["networks"]["edge"]["ipv4_address"])
        api_ip = ip_address(api["networks"]["edge"]["ipv4_address"])
        if (
            subnet.version != 4
            or proxy_ip == api_ip
            or proxy_ip not in subnet
            or api_ip not in subnet
        ):
            raise ValueError
        if env.get("NUTRIPILOT_TRUSTED_PROXY_CIDRS") != json.dumps(
            [f"{proxy_ip}/32"], separators=(",", ":")
        ):
            errors.append("trusted proxy must match the one configured proxy IPv4 address")
        if env.get("NUTRIPILOT_VPS_PROXY_ADDRESS") != str(proxy_ip):
            errors.append("preflight proxy address mismatch")
        if proxy_env.get("NUTRIPILOT_API_UPSTREAM") != f"{api_ip}:8000":
            errors.append("proxy upstream must use the API edge address")
    except (KeyError, ValueError, IndexError):
        errors.append("invalid edge network addressing")
    ports = proxy.get("ports", [])
    if len(ports) != 2 or {item.get("target") for item in ports} != {80, 443}:
        errors.append("proxy must publish only HTTP/HTTPS TCP ports")
    for port in ports:
        if port.get("protocol", "tcp") != "tcp":
            errors.append("only TCP listeners are configured in this release")
        if local and port.get("host_ip") != "127.0.0.1":
            errors.append("local verification must bind all published ports to 127.0.0.1")
        if not local and str(port.get("published")) != str(port.get("target")):
            errors.append("production must publish standard ports 80/443")
    site = proxy_env.get("NUTRIPILOT_SITE_ADDRESS", "")
    try:
        hosts = json.loads(env.get("NUTRIPILOT_ALLOWED_HOSTS", "[]"))
    except ValueError:
        hosts = []
    expected_host = "localhost" if local else site
    if local and site != "http://localhost":
        errors.append("local test entry must be http://localhost (secure loopback context)")
    if not local and (
        not site or any(value in site for value in (":", "/", "*", " ")) or site == "localhost"
    ):
        errors.append("production site must be one bare HTTPS hostname")
    if hosts != [expected_host, "127.0.0.1"]:
        errors.append("Host allowlist must match the site plus internal healthcheck loopback")
    if env.get("NUTRIPILOT_CORS_ORIGINS") != "[]":
        errors.append("same-origin deployment requires empty CORS")
    for key in (
        "NUTRIPILOT_DATABASE_URL",
        "NUTRIPILOT_JWT_SECRET",
        "NUTRIPILOT_CREDENTIAL_ENCRYPTION_KEY",
        "NUTRIPILOT_RATE_LIMIT_HMAC_SECRET",
        "NUTRIPILOT_DEMO_RESET_PASSWORD",
    ):
        if key in env:
            errors.append(f"{key} must be mounted as a secret, not an environment value")
    if api.get("command") != ["python", "-m", "app.cli.serve_vps"]:
        errors.append("API must use the side-effect-free VPS startup command")
    if services["maintenance"].get("profiles") != ["ops"]:
        errors.append("maintenance must require the explicit ops profile")
    if api.get("image") != services["maintenance"].get("image"):
        errors.append("maintenance and API must use the same image")
    image = api.get("image", "")
    if (
        image.endswith(":latest")
        or (":" not in image and "@sha256:" not in image)
        or "REPLACE" in image
    ):
        errors.append("select an explicit tested application image tag/digest")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    try:
        errors = topology_errors(json.load(sys.stdin), local=args.local)
    except (ValueError, TypeError, AttributeError):
        errors = ["invalid Compose JSON input"]
    print(
        json.dumps({"status": "failed" if errors else "ok", "static_only": True, "errors": errors})
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
