#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")/.."

# --demo: run with a fictional seeded ledger, no mail/LLM config required
DEMO_MODE=0
SERVER_ARGS=()
for arg in "$@"; do
  if [[ "${arg}" == "--demo" ]]; then
    DEMO_MODE=1
  else
    SERVER_ARGS+=("${arg}")
  fi
done

if [[ -f cfo_agent_poc/.env ]]; then
  set -a
  source cfo_agent_poc/.env
  set +a
fi

if [[ "${DEMO_MODE}" == "1" ]]; then
  export CFO_DEMO=1
  export CFO_DB_PATH="${PWD}/cfo_agent_poc/data/cfo-demo.sqlite"
  if [[ ! -f "${CFO_DB_PATH}" ]]; then
    (cd cfo_agent_poc && python3 demo_seed.py)
  fi
  echo "Demo mode: serving fictional data from ${CFO_DB_PATH}"
fi

if [[ -f cfo_agent_poc/web_app/package.json ]]; then
  needs_build=0
  if [[ ! -f cfo_agent_poc/web_app/dist/index.html ]]; then
    needs_build=1
  elif find cfo_agent_poc/web_app/src cfo_agent_poc/web_app/index.html cfo_agent_poc/web_app/styles.css -newer cfo_agent_poc/web_app/dist/index.html | grep -q .; then
    needs_build=1
  fi

  if [[ "${needs_build}" == "1" ]]; then
    LOCAL_NODE_BIN="cfo_agent_poc/bin/node/bin"
    if [[ -x "${LOCAL_NODE_BIN}/npm" ]]; then
      export PATH="${PWD}/${LOCAL_NODE_BIN}:${PATH}"
      NPM_BIN="${NPM_BIN:-${PWD}/${LOCAL_NODE_BIN}/npm}"
    else
      NPM_BIN="${NPM_BIN:-$(command -v npm || true)}"
    fi
    if [[ -z "${NPM_BIN}" ]]; then
      echo "npm is required to build the React/Vite frontend." >&2
      echo "Install Node.js/npm, or set NPM_BIN to your npm executable." >&2
      exit 1
    fi
    if [[ ! -d cfo_agent_poc/web_app/node_modules ]]; then
      "${NPM_BIN}" --prefix cfo_agent_poc/web_app install
    fi
    "${NPM_BIN}" --prefix cfo_agent_poc/web_app run build
  fi
fi

HOST="${CFO_WEB_HOST:-127.0.0.1}"
PORT="${CFO_WEB_PORT:-8091}"

# ${arr[@]+...} 写法兼容 bash 3.2（macOS /bin/sh）在 set -u 下的空数组展开
python3 cfo_agent_poc/web_app/server.py --host "${HOST}" --port "${PORT}" ${SERVER_ARGS[@]+"${SERVER_ARGS[@]}"}
