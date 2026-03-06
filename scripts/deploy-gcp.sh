#!/bin/bash
# ══════════════════════════════════════════════════════
# AI Personal Assistant — GCP Deployment Script (v2)
# Fixed version with all deployment issues resolved
# ══════════════════════════════════════════════════════

set -e

echo "══════════════════════════════════════"
echo "  AI Assistant — GCP Deployment v2"
echo "══════════════════════════════════════"

# ── Configuration (edit these) ──
DOMAIN="${1:-your-domain.duckdns.org}"
EMAIL="${2:-your-email@gmail.com}"

if [ "$DOMAIN" = "your-domain.duckdns.org" ]; then
    echo ""
    echo "Usage: bash scripts/deploy-gcp.sh <domain> <email>"
    echo "Example: bash scripts/deploy-gcp.sh sotso-assistant.duckdns.org mvsotso@gmail.com"
    echo ""
    exit 1
fi

echo "  Domain: $DOMAIN"
echo "  Email: $EMAIL"
echo ""

# ── Step 1: Install Docker ──
echo "▶ Step 1: Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    echo "  ✅ Docker installed"
    echo "  ⚠️  Run 'newgrp docker' after this script, or log out and back in"
else
    echo "  ✅ Docker already installed"
fi

# ── Step 2: Install Docker Compose ──
echo ""
echo "▶ Step 2: Installing Docker Compose..."
if ! docker compose version &> /dev/null; then
    sudo apt install -y docker-compose-plugin
    echo "  ✅ Docker Compose installed"
else
    echo "  ✅ Docker Compose already installed"
fi

# ── Step 3: Configure .env ──
echo ""
echo "▶ Step 3: Checking .env configuration..."
if [ ! -f ".env" ]; then
    cp config/.env.example .env
    # Auto-generate secret key
    SECRET=$(openssl rand -hex 32)
    sed -i "s|APP_SECRET_KEY=.*|APP_SECRET_KEY=$SECRET|" .env
    # Set domain in URLs
    sed -i "s|YOUR_DOMAIN|$DOMAIN|g" .env
    echo ""
    echo "  ⚠️  .env created with domain=$DOMAIN"
    echo "  ⚠️  You MUST edit .env to add your API keys:"
    echo "     vim .env"
    echo ""
    echo "  Required values to fill in:"
    echo "    - TELEGRAM_BOT_TOKEN (from @BotFather)"
    echo "    - ADMIN_TELEGRAM_ID (from @userinfobot)"
    echo "    - ANTHROPIC_API_KEY (from console.anthropic.com)"
    echo "    - GOOGLE_CLIENT_ID (from GCP Console)"
    echo "    - GOOGLE_CLIENT_SECRET (from GCP Console)"
    echo ""
    read -p "  Edit .env now, then press Enter to continue..."
else
    echo "  ✅ .env already exists"
fi

# ── Step 4: Update nginx config ──
echo ""
echo "▶ Step 4: Configuring nginx..."
sed -i "s/YOUR_DOMAIN.com/$DOMAIN/g" nginx/nginx.conf 2>/dev/null || true
sed -i "s/YOUR_DOMAIN/$DOMAIN/g" nginx/nginx.conf 2>/dev/null || true
echo "  ✅ Nginx configured for $DOMAIN"

# ── Step 5: SSL Certificate ──
echo ""
echo "▶ Step 5: Getting SSL certificate..."
mkdir -p nginx/ssl
if [ -d "nginx/ssl/live/$DOMAIN" ]; then
    echo "  ✅ SSL certificate already exists"
else
    sudo docker run --rm -p 80:80 \
        -v $(pwd)/nginx/ssl:/etc/letsencrypt \
        certbot/certbot certonly \
        --standalone --preferred-challenges http \
        --email $EMAIL --agree-tos --no-eff-email \
        -d $DOMAIN
    # Fix permissions (common issue!)
    sudo chmod -R 755 nginx/ssl
    sudo chown -R $USER:$USER nginx/ssl
    echo "  ✅ SSL certificate obtained"
fi

# ── Step 6: Build and Deploy ──
echo ""
echo "▶ Step 6: Building and deploying..."
docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo "  ⏳ Waiting for services to start..."
sleep 15

# ── Step 7: Run Database Migrations ──
echo ""
echo "▶ Step 7: Running database migrations..."
docker exec ai-assistant python scripts/migrate_db.py 2>/dev/null || echo "  ⚠️  Migration skipped (will run on next restart)"

# ── Step 8: Verify ──
echo ""
echo "▶ Step 8: Verifying deployment..."
echo "  Services:"
docker compose -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || docker compose -f docker-compose.prod.yml ps
echo ""
HEALTH=$(curl -s -k https://$DOMAIN/api/v1/health 2>/dev/null || curl -s http://localhost:8000/api/v1/health 2>/dev/null || echo "FAILED")
echo "  Health check: $HEALTH"

# ── Step 9: Set Telegram Webhook ──
echo ""
echo "▶ Step 9: Registering Telegram webhook..."
source .env
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ "$TELEGRAM_BOT_TOKEN" != "your-bot-token-from-botfather" ]; then
    RESULT=$(curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
        -H "Content-Type: application/json" \
        -d "{\"url\": \"https://$DOMAIN/api/v1/webhook/telegram\"}")
    echo "  Webhook: $RESULT"
else
    echo "  ⚠️  Skipped — set TELEGRAM_BOT_TOKEN in .env first"
fi

# ── Step 10: Setup Cron Jobs ──
echo ""
echo "▶ Step 10: Setting up automated tasks..."
# SSL auto-renewal
CRON_SSL="0 3 * * * cd $(pwd) && sudo docker run --rm -v $(pwd)/nginx/ssl:/etc/letsencrypt certbot/certbot renew --quiet && docker compose -f docker-compose.prod.yml restart nginx"
# Daily database backup
CRON_BACKUP="0 2 * * * docker exec ai-assistant-db pg_dump -U assistant ai_assistant | gzip > /home/$USER/backups/db_\$(date +\%Y\%m\%d).sql.gz && find /home/$USER/backups -name '*.gz' -mtime +7 -delete"
mkdir -p /home/$USER/backups
(crontab -l 2>/dev/null | grep -v "certbot\|pg_dump"; echo "$CRON_SSL"; echo "$CRON_BACKUP") | crontab -
echo "  ✅ SSL auto-renewal + daily backups configured"

# ── Done ──
echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ DEPLOYMENT COMPLETE!"
echo "══════════════════════════════════════════════"
echo ""
echo "  🌐 Website: https://$DOMAIN"
echo "  📡 Health:  https://$DOMAIN/api/v1/health"
echo "  🤖 Bot:     Open @sotso_assistant_bot on Telegram"
echo ""
echo "  Useful commands:"
echo "    docker compose -f docker-compose.prod.yml logs -f app    # App logs"
echo "    docker compose -f docker-compose.prod.yml restart        # Restart all"
echo "    docker compose -f docker-compose.prod.yml down           # Stop all"
echo "    docker exec -it ai-assistant-db psql -U assistant -d ai_assistant  # Database"
echo ""
