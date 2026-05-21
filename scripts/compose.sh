#!/usr/bin/env bash
# Wrapper: picks tunnel profile + optional auth overrides from .env
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — run scripts/setup-bootstrap.py first" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

ARGS=(-f compose.yaml)
if [[ -f compose.auth-overrides.yaml ]]; then
  ARGS+=(-f compose.auth-overrides.yaml)
fi

if [[ "${CF_TUNNEL_MODE:-token}" == "config" ]]; then
  ARGS+=(--profile tunnel-config)
else
  ARGS+=(--profile tunnel-token)
fi

exec docker compose "${ARGS[@]}" "$@"
