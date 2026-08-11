#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.local/runtime.env"
mkdir -p "$(dirname "$ENV_FILE")"

random_secret() {
    python3 -c 'import secrets; print(secrets.token_urlsafe(36))'
}

if [[ ! -f "$ENV_FILE" ]]; then
    umask 077
    cat >"$ENV_FILE" <<EOF
POLYGLOT_POSTGRES_PASSWORD=$(random_secret)
POLYGLOT_MIGRATION_DB_PASSWORD=$(random_secret)
POLYGLOT_RUNTIME_DB_PASSWORD=$(random_secret)
POLYGLOT_RETENTION_DB_PASSWORD=$(random_secret)
POLYGLOT_SESSION_SECRET=$(random_secret)
POLYGLOT_MEDIA_SIGNING_SECRET=$(random_secret)
EOF
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

docker compose --project-directory "$ROOT_DIR" up --build --detach --wait
printf 'Polyglot est disponible sur http://127.0.0.1:9001\n'
