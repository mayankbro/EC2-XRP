#!/usr/bin/env bash
# ==============================================================================
# 1-Click Server Provisioning Script for Autonomous Trading Bot (Ubuntu/Debian)
# ==============================================================================

set -e

echo "=== Initializing Server Environment for Trading Bot ==="

# 1. Update system packages
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3 python3-pip python3-venv git curl htop ntp

# 2. Synchronize server clock (vital for exchange API nonce security)
sudo systemctl enable systemd-timesyncd
sudo systemctl start systemd-timesyncd
timedatectl set-ntp on

# 3. Create project directory structure
mkdir -p logs data production/ml

# 4. Create virtual environment & install requirements
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

# 5. Initialize environment file if missing
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example. Please populate your CoinDCX & Telegram API keys!"
fi

echo "=== Server Provisioning Complete! ==="
echo "To start with systemd: sudo cp deploy/trading_bot.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable trading_bot && sudo systemctl start trading_bot"
echo "To check live logs:    journalctl -u trading_bot -f"
