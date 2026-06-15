#!/usr/bin/env bash
# Deploy ai-investor-assistant to VPS via SSH.
# Config: copy .deploy.env.example → .deploy.env (local only, not committed).
#
# Usage:
#   ./scripts/deploy.sh              # git pull on server + rebuild
#   ./scripts/deploy.sh --push       # push local main, then deploy
#   ./scripts/deploy.sh --local      # rsync local files (skip git pull) + rebuild
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${DEPLOY_ENV:-$ROOT/.deploy.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

: "${DEPLOY_HOST:?Set DEPLOY_HOST in .deploy.env}"
: "${DEPLOY_USER:=dev}"
: "${DEPLOY_REPO:=https://github.com/alferov90/ai-investor-assistant.git}"
: "${DEPLOY_BRANCH:=main}"

# ~/ in .deploy.env expands to Mac home when sourced — use absolute remote path.
DEFAULT_REMOTE_PATH="/home/${DEPLOY_USER}/ai-investor-assistant"
DEPLOY_PATH="${DEPLOY_PATH:-$DEFAULT_REMOTE_PATH}"
if [[ "$DEPLOY_PATH" == /Users/* ]] || [[ "$DEPLOY_PATH" == "$HOME/"* ]]; then
  DEPLOY_PATH="$DEFAULT_REMOTE_PATH"
fi
if [[ "$DEPLOY_PATH" == "~/"* ]]; then
  DEPLOY_PATH="/home/${DEPLOY_USER}/${DEPLOY_PATH#\~/}"
fi

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)
if [[ -n "${DEPLOY_SSH_KEY:-}" ]]; then
  SSH_OPTS+=(-i "$DEPLOY_SSH_KEY")
fi

REMOTE="${DEPLOY_USER}@${DEPLOY_HOST}"
SSH=(ssh "${SSH_OPTS[@]}" "$REMOTE")

echo "→ Deploy to $REMOTE ($DEPLOY_PATH, branch $DEPLOY_BRANCH)"

SKIP_GIT_PULL=0

if [[ "${1:-}" == "--push" ]]; then
  echo "→ git push origin $DEPLOY_BRANCH"
  git -C "$ROOT" push origin "$DEPLOY_BRANCH"
  shift
fi

if [[ "${1:-}" == "--local" ]]; then
  echo "→ rsync local project to $REMOTE:$DEPLOY_PATH"
  rsync -avz --delete \
    --exclude '.git/' \
    --exclude '.env' \
    --exclude '.deploy.env' \
    --exclude '__pycache__/' \
    --exclude '.venv/' \
    --exclude 'node_modules/' \
    "$ROOT/" "$REMOTE:$DEPLOY_PATH/"
  SKIP_GIT_PULL=1
  shift
fi

"${SSH[@]}" \
  DEPLOY_PATH="$DEPLOY_PATH" \
  DEPLOY_REPO="$DEPLOY_REPO" \
  DEPLOY_BRANCH="$DEPLOY_BRANCH" \
  SKIP_GIT_PULL="$SKIP_GIT_PULL" \
  bash -s <<'REMOTE'
set -euo pipefail

if [[ ! -d "$DEPLOY_PATH/.git" ]]; then
  echo "→ Cloning into $DEPLOY_PATH"
  mkdir -p "$(dirname "$DEPLOY_PATH")"
  git clone "$DEPLOY_REPO" "$DEPLOY_PATH"
fi

cd "$DEPLOY_PATH"
if [[ "${SKIP_GIT_PULL}" != "1" ]]; then
  echo "→ git remote & pull"
  git remote set-url origin "$DEPLOY_REPO"
  git fetch origin "$DEPLOY_BRANCH"
  git checkout "$DEPLOY_BRANCH"
  git pull origin "$DEPLOY_BRANCH" --rebase
else
  echo "→ skip git pull (local rsync deploy)"
fi

echo "→ docker compose build & up"
docker compose build --no-cache api
docker compose up -d --wait --wait-timeout 120

echo "→ health check"
curl -sf http://localhost:8000/health | head -c 200
echo ""
docker compose ps
REMOTE

echo "✓ Deploy finished: http://${DEPLOY_HOST}:8000"
