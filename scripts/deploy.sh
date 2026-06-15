#!/usr/bin/env bash
# Deploy ai-investor-assistant to VPS via SSH.
# Config: copy .deploy.env.example → .deploy.env (local only, not committed).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${DEPLOY_ENV:-$ROOT/.deploy.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

: "${DEPLOY_HOST:?Set DEPLOY_HOST in .deploy.env}"
: "${DEPLOY_USER:=dev}"
: "${DEPLOY_REPO:=git@github.com:alferov90/ai-investor-assistant.git}"
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

if [[ "${1:-}" == "--push" ]]; then
  echo "→ git push origin $DEPLOY_BRANCH"
  git -C "$ROOT" push origin "$DEPLOY_BRANCH"
fi

"${SSH[@]}" \
  DEPLOY_PATH="$DEPLOY_PATH" \
  DEPLOY_REPO="$DEPLOY_REPO" \
  DEPLOY_BRANCH="$DEPLOY_BRANCH" \
  bash -s <<'REMOTE'
set -euo pipefail

if [[ ! -d "$DEPLOY_PATH/.git" ]]; then
  echo "→ Cloning into $DEPLOY_PATH"
  mkdir -p "$(dirname "$DEPLOY_PATH")"
  git clone "$DEPLOY_REPO" "$DEPLOY_PATH"
fi

cd "$DEPLOY_PATH"
echo "→ git fetch && pull"
git fetch origin "$DEPLOY_BRANCH"
git checkout "$DEPLOY_BRANCH"
git pull origin "$DEPLOY_BRANCH" --rebase

echo "→ docker compose build & up"
docker compose build --no-cache api
docker compose up -d
docker compose exec -T api alembic upgrade head

echo "→ health check"
curl -sf http://localhost:8000/health | head -c 200
echo ""
docker compose ps
REMOTE

echo "✓ Deploy finished: http://${DEPLOY_HOST}:8000"
