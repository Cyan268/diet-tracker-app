#!/usr/bin/env bash
set -euo pipefail
BASE="${1:?Pass the deployment HTTPS URL}"
BASE="${BASE%/}"
case "$BASE" in
  https://*) ;;
  http://localhost:*|http://127.0.0.1:*) [[ "${2:-}" == '--local' ]] || exit 1 ;;
  *) echo 'Only HTTPS or explicitly opted-in loopback HTTP is supported' >&2; exit 1 ;;
esac
for path in / /auth /api/v1/health/live /api/v1/health/ready /api/v1/meta/config; do
  curl --fail --silent --show-error --max-time 15 "$BASE$path" > /dev/null
done
headers="$(curl --fail --silent --show-error --max-time 15 --head "$BASE/")"
grep -qi '^cross-origin-opener-policy: same-origin' <<< "$headers"
grep -qi '^cross-origin-embedder-policy: credentialless' <<< "$headers"
status="$(curl --silent --show-error --max-time 15 -o /dev/null -w '%{http_code}' "$BASE/assets/not-found.wasm")"
[[ "$status" == '404' ]]
echo 'Read-only HTTP smoke passed. Authentication, writes and browser SQLite are separate checks.'
