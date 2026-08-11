#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.local/runtime.env"
[[ -f "$ENV_FILE" ]] || {
    printf 'Polyglot n est pas encore initialise. Lancez ./scripts/local-up.sh.\n'
    exit 1
}
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

docker compose --project-directory "$ROOT_DIR" ps
curl --fail --silent --show-error \
    "http://127.0.0.1:${POLYGLOT_HTTP_PORT:-9001}/api/v1/health/ready"
printf '\nInterface: http://127.0.0.1:%s\n' "${POLYGLOT_HTTP_PORT:-9001}"
