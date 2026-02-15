#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Push local changes to the running EC2 instance
#
# Usage:
#   ./infra/deploy-update.sh infra            # sync .env.prod, compose file, nginx config
#   ./infra/deploy-update.sh frontend
#   ./infra/deploy-update.sh backend
#   ./infra/deploy-update.sh backend --migrate
#   ./infra/deploy-update.sh all
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${DEPLOY_HOST:-3.74.70.149}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/meeple-deploy.pem}"
SSH="ssh -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@$HOST"
RSYNC="rsync -azP -e 'ssh -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'"
COMPOSE="sudo docker compose -f docker-compose.prod.yml --env-file .env.prod"

TARGET="${1:-}"
MIGRATE=false
[[ "${2:-}" == "--migrate" ]] && MIGRATE=true

GREEN='\033[0;32m'; NC='\033[0m'
info() { echo -e "${GREEN}>>>${NC} $1"; }
SCP="scp -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

sync_infra() {
    info "Syncing .env.prod and infra files..."
    $SCP infra/.env.prod "ubuntu@$HOST:/opt/meeple/.env.prod"
    $SCP docker-compose.prod.yml "ubuntu@$HOST:/opt/meeple/docker-compose.prod.yml"
    eval $RSYNC infra/ "ubuntu@$HOST:/opt/meeple/infra/"
}

sync_frontend() {
    info "Syncing frontend..."
    eval $RSYNC --exclude node_modules --exclude .next \
        frontend/ "ubuntu@$HOST:/opt/meeple/frontend/"
    info "Rebuilding frontend container..."
    $SSH "cd /opt/meeple && $COMPOSE up -d --build frontend"
}

sync_backend() {
    info "Syncing backend..."
    eval $RSYNC --exclude __pycache__ --exclude .venv --exclude '*.pyc' \
        backend/ "ubuntu@$HOST:/opt/meeple/backend/"
    info "Rebuilding backend container..."
    $SSH "cd /opt/meeple && $COMPOSE up -d --build backend"
    if $MIGRATE; then
        info "Running migrations..."
        $SSH "cd /opt/meeple && $COMPOSE exec -T backend uv run alembic upgrade head"
    fi
}

case "$TARGET" in
    infra)
        sync_infra
        ;;
    frontend)
        sync_infra
        sync_frontend
        ;;
    backend)
        sync_infra
        sync_backend
        ;;
    all)
        sync_infra
        sync_frontend
        sync_backend
        ;;
    *)
        echo "Usage: deploy-update.sh <infra|frontend|backend|all> [--migrate]"
        exit 1
        ;;
esac

info "Done!"
