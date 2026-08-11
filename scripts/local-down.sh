#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.local/runtime.env"
[[ -f "$ENV_FILE" ]] || { printf 'Aucun environnement local Polyglot.\n'; exit 0; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
docker compose --project-directory "$ROOT_DIR" down
