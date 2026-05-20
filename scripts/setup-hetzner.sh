#!/usr/bin/env bash
# Initial server setup for Hetzner CPX41 (Ubuntu 22.04)
# Run once as root: bash setup-hetzner.sh <deploy_user> <dockerhub_username>
set -euo pipefail

DEPLOY_USER="${1:-deploy}"
DOCKERHUB_USERNAME="${2:-}"

# ── system ────────────────────────────────────────────────────────────────────
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl git ufw fail2ban

# ── deploy user ───────────────────────────────────────────────────────────────
if ! id "$DEPLOY_USER" &>/dev/null; then
  useradd -m -s /bin/bash "$DEPLOY_USER"
  usermod -aG sudo "$DEPLOY_USER"
  echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy
fi

# ── Docker ────────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  usermod -aG docker "$DEPLOY_USER"
fi

# Docker Compose v2 is bundled with Docker Engine >= 23 — no separate install needed

# ── firewall ──────────────────────────────────────────────────────────────────
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ── app directory ─────────────────────────────────────────────────────────────
APP_DIR=/opt/audio-app
mkdir -p "$APP_DIR"
chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

# ── .env ──────────────────────────────────────────────────────────────────────
if [[ -n "$DOCKERHUB_USERNAME" && ! -f "$APP_DIR/.env" ]]; then
  cat > "$APP_DIR/.env" <<EOF
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
UPLOAD_DIR=/app/uploads
OUTPUT_DIR=/app/outputs
MODELS_CACHE_DIR=/app/models_cache
DOCKERHUB_USERNAME=${DOCKERHUB_USERNAME}
ALLOWED_ORIGINS=https://your-app.vercel.app
EOF
  chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "Created $APP_DIR/.env — edit ALLOWED_ORIGINS before deploying"
fi

# ── nginx conf dir ────────────────────────────────────────────────────────────
mkdir -p "$APP_DIR/nginx"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/nginx"

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Copy docker-compose.yml and nginx/default.conf to $APP_DIR"
echo "  2. Edit $APP_DIR/.env (set ALLOWED_ORIGINS to your Vercel URL)"
echo "  3. Add GitHub Actions secrets:"
echo "       HETZNER_IP, DEPLOY_USER, DEPLOY_SSH_KEY"
echo "       DOCKERHUB_USERNAME, DOCKERHUB_TOKEN"
echo "  4. Generate SSH key for CI: ssh-keygen -t ed25519 -C ci@audio-app"
echo "       Add public key to ~/.ssh/authorized_keys on this server"
echo "       Add private key as DEPLOY_SSH_KEY secret in GitHub"
