#!/bin/zsh
set -euo pipefail

# 备份平台库（账户）和每个用户的账本库，写到 <CFO_HOME>/backups/<时间戳>/，目录结构与原来一致。
# 截图和 OCR 文本是只增不改的文件，不在这里重复拷；整机备份时连同 tenants/ 目录一起带走即可。

cd "$(dirname "$0")/.."

if [[ -f cfo_agent_poc/.env ]]; then
  set -a
  source cfo_agent_poc/.env
  set +a
fi

HOME_DIR="${CFO_HOME:-cfo_agent_poc/data}"
STAMP="$(date '+%Y%m%d_%H%M%S')"
BACKUP_DIR="${HOME_DIR}/backups/${STAMP}"

if [[ ! -f "${HOME_DIR}/platform.sqlite" ]]; then
  echo "Platform database not found: ${HOME_DIR}/platform.sqlite" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
# sqlite3 .backup 是在线备份，服务开着也能拿到一致的快照
sqlite3 "${HOME_DIR}/platform.sqlite" ".backup '${BACKUP_DIR}/platform.sqlite'"

count=0
for db in "${HOME_DIR}"/tenants/*/data/cfo.sqlite(N); do
  relative="${db#${HOME_DIR}/}"
  mkdir -p "${BACKUP_DIR}/$(dirname "${relative}")"
  sqlite3 "${db}" ".backup '${BACKUP_DIR}/${relative}'"
  count=$((count + 1))
done

echo "Backup written: ${BACKUP_DIR} (platform + ${count} ledgers)"
