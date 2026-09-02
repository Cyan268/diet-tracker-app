#!/usr/bin/env bash
set -euo pipefail

# Usage: bash scripts/deploy/preflight.sh /absolute/path/config.env [--local]
# Static-only: does not migrate, seed, start dependencies, or publish ports.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:?Pass an explicit non-secret configuration file}"
MODE="${2:-}"
[[ -f "$ENV_FILE" ]] || { echo 'Configuration file not found' >&2; exit 1; }
[[ -z "$MODE" || "$MODE" == '--local' ]] || { echo 'Unknown preflight mode' >&2; exit 1; }
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/compose.prod.yml" --profile ops)
"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" config --format json | "${COMPOSE[@]}" run --rm --no-deps -T maintenance \
  python -m app.cli.vps_topology ${MODE:+"$MODE"}
"${COMPOSE[@]}" run --rm --no-deps -T maintenance \
  python -m app.cli.production_preflight --portfolio --behind-proxy --single-origin-web --vps
# Git Bash otherwise rewrites this Linux container path to C:/Program Files/Git/...
# Keep normal host-path conversion for the Compose file and exclude only this argument.
if [[ "${OSTYPE:-}" == msys* ]]; then
  export MSYS2_ARG_CONV_EXCL="/etc/caddy/Caddyfile"
fi
if "${COMPOSE[@]}" ps --status running --services proxy | grep -Fxq proxy; then
  # A one-off proxy inherits the service's fixed edge IP and would collide with
  # the live proxy. Validate in the running container instead.
  "${COMPOSE[@]}" exec -T proxy caddy validate --config /etc/caddy/Caddyfile
else
  "${COMPOSE[@]}" run --rm --no-deps -T proxy caddy validate --config /etc/caddy/Caddyfile
fi
echo 'Static preflight passed; dependency readiness and browser checks are separate.'
