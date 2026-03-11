#!/bin/bash
# ============================================================
# mybuilding.dev — Auto-deploy Hetzner
# Copié depuis theneb_deploy.sh — adapté pour mybuilding
# Cron : */5 * * * * /root/logs/mybuilding_deploy.sh
# ============================================================

LOG="/root/logs/mybuilding_deploy.log"
REPO="https://github.com/Payoss/mybuilding.git"
DIR="/root/mybuilding"
BRANCH="main"
NGINX_CONF="/etc/nginx/sites-available/mybuilding"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"; }

# Check if new commits
cd "$DIR" 2>/dev/null || { log "DIR not found, cloning..."; git clone "$REPO" "$DIR"; }

cd "$DIR"
git fetch origin "$BRANCH" --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0  # Rien de nouveau
fi

log "New commit detected: $REMOTE — deploying..."

git pull origin "$BRANCH" --rebase --autostash >> "$LOG" 2>&1

# Setup nginx conf if not exists
if [ ! -f "$NGINX_CONF" ]; then
    log "Setting up nginx config..."
    cp "$DIR/nginx.conf" "$NGINX_CONF"
    ln -sf "$NGINX_CONF" "/etc/nginx/sites-enabled/mybuilding"
    nginx -t && systemctl reload nginx
    log "Nginx configured."
fi

log "Deploy complete — $(git log -1 --oneline)"
