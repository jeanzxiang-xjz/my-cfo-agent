#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")/.."

DB_PATH="cfo_agent_poc/data/cfo.sqlite"
BACKUP_DIR="cfo_agent_poc/data/backups"
STAMP="$(date '+%Y%m%d_%H%M%S')"
BACKUP_PATH="${BACKUP_DIR}/cfo_${STAMP}.sqlite"

if [[ ! -f "${DB_PATH}" ]]; then
  echo "Database not found: ${DB_PATH}" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
sqlite3 "${DB_PATH}" ".backup '${BACKUP_PATH}'"
echo "Backup written: ${BACKUP_PATH}"
