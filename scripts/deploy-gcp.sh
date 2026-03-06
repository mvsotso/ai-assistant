#!/bin/bash
# ══════════════════════════════════════════════════════
# AI Personal Assistant — GCP Deployment Script
# Run this on a fresh Google Cloud e2-standard-2 VM
# (Ubuntu 22.04 LTS, Singapore region)
# ══════════════════════════════════════════════════════

set -e

echo "══════════════════════════════════════"
echo "  AI Assistant — GCP Deployment"
echo "══════════════════════════════════════"

# ── Configuration (edit these) ──
DOMAIN="your-domain.com"       # Your domain pointing to this VM
EMAIL="your-email@gmail.com"   # For Let's Encrypt notifications
REPO="https://github.com/mvsotso/ai-assistant.git"

# ── Step 1: System Update ──
echo ""
echo "▶ Step 1: Updating system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw

# ── Step 2: Install Docker ──
echo ""
echo "▶ Step 2: Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "  ✅ Docker installed"
else
    echo "  ✅ Docker already installed"
fi

# Install Docker Compose plugin
echo "  Installing Docker Compose..."
sudo apt install -y docker-compose-plugin
echo "  ✅ Docker Compose installed"

# ── Step 3: Firewall ──
echo ""
echo "▶ Step 3: Configuring firewall..."
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
echo "  ✅ Firewall configured (SSH, HTTP, HTTPS)"

# ── Step 4: Clone Repository ──
echo ""
echo "▶ Step 4: Cloning repository..."
cd /home/$USER
if [ -d "ai-assistant" ]; then
    cd ai-assistant && git pull
    echo "  ✅ Repository updated"
else
    git clone $REPO
    cd ai-assistant
    echo "  ✅ Repository cloned"
fi

# ── Step 5: Configure Environment ──
echo ""
echo "▶ Step 5: Setting up environment..."
if [ ! -f ".env" ]; then
    cp config/.env.example .env
    echo ""
    echo "  ⚠️  IMPORTANT: Edit .env with your actual credentials:"
    echo "     nano .env"
    echo ""
    echo "  Required values:"
    echo "    - TELEGRAM_BOT_TOKEN"
    echo "    - ANTHROPIC_API_KEY"
    echo "    - ADMIN_TELEGRAM_ID"
    echo "    - WEBHOOK_URL=https://$DOMAIN/api/v1/webhook/telegram"
    echo "    - APP_ENV=production"
    echo "    - APP_DEBUG=false"
    echo ""
    read -p "  Press Enter after editing .env to continue..."
fi

# ── Step 6: SSL Certificate ──
echo ""
echo "▶ Step 6: Setting up SSL certificate..."
# Update nginx config with actual domain
sed -i "s/YOUR_DOMAIN.com/$DOMAIN/g" nginx/nginx.conf

# Create SSL directory
mkdir -p nginx/ssl

# First, start nginx without SSL for certbot verification
echo "  Starting temporary HTTP server for verification..."

# Get certificate
sudo docker run --rm \
    -v $(pwd)/nginx/ssl:/etc/letsencrypt \
    -v $(pwd)/certbot-webroot:/var/www/certbot \
    -p 80:80 \
    certbot/certbot certonly \
    --standalone \
    --preferred-challenges http \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    -d $DOMAIN

echo "  ✅ SSL certificate obtained"

# ── Step 7: Build and Deploy ──
echo ""
echo "▶ Step 7: Building and deploying..."
sudo docker compose -f docker-compose.prod.yml build
sudo docker compose -f docker-compose.prod.yml up -d

echo ""
echo "  ⏳ Waiting for services to start..."
sleep 10

# ── Step 8: Verify ──
echo ""
echo "▶ Step 8: Verifying deployment..."
HEALTH=$(curl -s http://localhost:8000/api/v1/health)
echo "  Health check: $HEALTH"

# ── Step 9: Set Telegram Webhook ──
echo ""
echo "▶ Step 9: Registering Telegram webhook..."
source .env
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"https://$DOMAIN/api/v1/webhook/telegram\"}"
echo ""

# ── Step 10: Setup Auto-Renewal ──
echo ""
echo "▶ Step 10: Setting up SSL auto-renewal..."
CRON_CMD="0 3 * * * cd $(pwd) && sudo docker compose -f docker-compose.prod.yml run --rm certbot renew && sudo docker compose -f docker-compose.prod.yml restart nginx"
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
echo "  ✅ SSL auto-renewal configured (daily at 3 AM)"

# ── Step 11: Setup Daily Backup ──
echo ""
echo "▶ Step 11: Setting up daily database backups..."
mkdir -p /home/$USER/backups
BACKUP_CMD="0 2 * * * docker exec ai-assistant-db pg_dump -U assistant ai_assistant | gzip > /home/$USER/backups/db_\$(date +\%Y\%m\%d).sql.gz && find /home/$USER/backups -name '*.gz' -mtime +7 -delete"
(crontab -l 2>/dev/null; echo "$BACKUP_CMD") | crontab -
echo "  ✅ Daily backups configured (2 AM, 7-day retention)"

# ── Done ──
echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ DEPLOYMENT COMPLETE!"
echo "══════════════════════════════════════════════"
echo ""
echo "  🌐 Dashboard: https://$DOMAIN"
echo "  📡 API Docs:  https://$DOMAIN/docs"
echo "  🤖 Telegram:  Open your bot and type /start"
echo ""
echo "  Useful commands:"
echo "    docker compose -f docker-compose.prod.yml logs -f    # View logs"
echo "    docker compose -f docker-compose.prod.yml restart    # Restart all"
echo "    docker compose -f docker-compose.prod.yml down       # Stop all"
echo ""
