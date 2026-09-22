#!/usr/bin/env bash
# voiceDeck one-shot deploy helper for a fresh Ubuntu/Debian VPS.
# Idempotent: safe to re-run.
#
# What it does:
#   1) Ensures Docker is installed (installs docker.io + compose plugin if absent).
#   2) Ensures a non-root `deploy` user exists, with passwordless sudo for docker.
#   3) Creates /opt/voicedeck (owned by deploy:deploy).
#   4) Writes compose.yaml + .env (IMAGE and APP_PORT overridable via env).
#   5) Appends the GitHub Actions deploy public key to ~deploy/.ssh/authorized_keys
#      (idempotent — duplicates are fine).
#
# Usage (as root on the new VPS):
#   curl -fsSL https://raw.githubusercontent.com/stashash/voiceDeck/main/scripts/deploy/server-setup.sh \
#     | sudo IMAGE=ghcr.io/stashash/voicedeck:latest APP_PORT=8088 \
#           DEPLOY_PUBKEY='ssh-rsa AAAA... voicedeck-deploy@github-actions' \
#           bash

set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/stashash/voicedeck:latest}"
APP_PORT="${APP_PORT:-8088}"
DEPLOY_PUBKEY="${DEPLOY_PUBKEY:-}"
APP_USER="deploy"
APP_DIR="/opt/voicedeck"

log() { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[setup][ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root (or with sudo) on the target host."

# 1) Docker
if ! command -v docker >/dev/null 2>&1; then
  log "Installing docker.io..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# 2) deploy user
if ! id "$APP_USER" >/dev/null 2>&1; then
  log "Creating user $APP_USER"
  adduser --disabled-password --gecos "" "$APP_USER"
fi
usermod -aG docker "$APP_USER"
echo "$APP_USER ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/bin/docker compose" > /etc/sudoers.d/90-deploy-docker
chmod 440 /etc/sudoers.d/90-deploy-docker

# 3) app directory
install -d -o "$APP_USER" -g "$APP_USER" -m 0755 "$APP_DIR"

# 4) compose.yaml + .env
cat > "$APP_DIR/compose.yaml" <<YAML
services:
  app:
    image: \${IMAGE:-ghcr.io/stashash/voicedeck:latest}
    pull_policy: always
    ports:
      - "127.0.0.1:\${APP_PORT:-8088}:8080"
    restart: unless-stopped
    environment:
      APP_PORT: "\${APP_PORT:-8088}"
      MODE: "\${MODE:-demo}"
YAML
chown "$APP_USER:$APP_USER" "$APP_DIR/compose.yaml"

cat > "$APP_DIR/.env" <<ENV
IMAGE=$IMAGE
APP_PORT=$APP_PORT
MODE=demo
ENV
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 0640 "$APP_DIR/.env"

# 5) SSH public key for GitHub Actions
if [[ -n "$DEPLOY_PUBKEY" ]]; then
  install -d -o "$APP_USER" -g "$APP_USER" -m 0700 "/home/$APP_USER/.ssh"
  AUTH_FILE="/home/$APP_USER/.ssh/authorized_keys"
  touch "$AUTH_FILE"
  chown "$APP_USER:$APP_USER" "$AUTH_FILE"
  chmod 0600 "$AUTH_FILE"
  if ! grep -Fq "$DEPLOY_PUBKEY" "$AUTH_FILE"; then
    echo "$DEPLOY_PUBKEY" >> "$AUTH_FILE"
    log "Deploy public key appended to $AUTH_FILE"
  else
    log "Deploy public key already present in $AUTH_FILE"
  fi
else
  log "DEPLOY_PUBKEY not provided — skipping authorized_keys update"
fi

log "Done."
log "Next: trigger GitHub Actions workflow_dispatch with image_tag=latest and dry_run=false."
