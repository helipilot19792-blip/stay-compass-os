#!/bin/bash
set -euo pipefail

MODE="${1:-apply}"
CONFIG_FILE="/opt/stay-compass/device/config.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Device config not found."
    exit 1
fi

mapfile -t CONFIG_VALUES < <(python3 - "$CONFIG_FILE" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(config.get("update_repo_dir", ""))
print(config.get("update_remote", "origin"))
print(config.get("update_branch", "main"))
PY
)

REPO_DIR="${CONFIG_VALUES[0]:-}"
REMOTE="${CONFIG_VALUES[1]:-origin}"
BRANCH="${CONFIG_VALUES[2]:-main}"

if [ -z "$REPO_DIR" ] || [ ! -d "$REPO_DIR/.git" ]; then
    echo "Update repository is not configured or is not a Git checkout."
    exit 1
fi

if [ "$MODE" != "check" ] && [ "$MODE" != "apply" ]; then
    echo "Unsupported update mode: $MODE"
    exit 1
fi

cd "$REPO_DIR"

git config --global --add safe.directory "$REPO_DIR" >/dev/null 2>&1 || true
git fetch --quiet "$REMOTE" "$BRANCH"

LOCAL_REVISION="$(git rev-parse HEAD)"
REMOTE_REVISION="$(git rev-parse FETCH_HEAD)"

if [ "$LOCAL_REVISION" = "$REMOTE_REVISION" ]; then
    echo "Already up to date."
    if [ "$MODE" = "check" ]; then
        exit 20
    fi

    exit 0
fi

if [ "$MODE" = "check" ]; then
    echo "Update available: $LOCAL_REVISION -> $REMOTE_REVISION"
    exit 0
fi

git pull --ff-only "$REMOTE" "$BRANCH"
bash "$REPO_DIR/install.sh"
