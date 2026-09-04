# XRP/USDT 4H Autonomous Liquidity-Hunting Trading Bot

An institutional-grade, 24/7 automated cryptocurrency futures trading system. It utilizes real-time global order-flow intelligence and liquidation feeds from **Binance Futures** to forecast high-probability liquidity sweeps, and executes risk-managed bracket trades directly on **CoinDCX Futures**.

---

## 🌟 Core Strategy & Edge

* **Asset**: XRP/USDT Futures (4H Timeframe).
* **Core Phenomenon**: Market makers and order flow hunt clustered retail leverage liquidations (50x–60x) before mean-reverting.
* **Dual-Limit OCO Bracket**: Places Limit Sell at the upper sweep band ($+1.8\%$) and Limit Buy at the lower sweep band ($-1.8\%$) at candle open ($t=0$). The first fill automatically cancels the opposite order.
* **Dynamic Sizing & Risk Regimes**:
  - **Tier 1 (A+ Setup, ATR $\le 1.8\%$)**: Low volatility consolidation $\rightarrow$ 20x Leverage, 15% Margin.
  - **Tier 2 (Standard Setup, ATR $1.8\% - 3.2\%$)**: Standard regime $\rightarrow$ 15x Leverage, 10% Margin.
  - **Tier 3 (Danger Zone, ATR $> 3.2\%$)**: Violent momentum breakout $\rightarrow$ **NO TRADE** (Preserves capital).
* **Strict Discipline**: Maximum **1 trade per day**, **no weekend trading (Mon–Fri only)**.
* **Empirical Validation**: Backtested across **6.66 years (2020–2026, 14,598 candles)** with a **71.0% Win Rate**, **2.27 Profit Factor**, and **99.9% 6-month profitability**.

---

## 📁 Repository Architecture

```
My Trading Bot/
├── production/
│   ├── config.py                 # Central configuration and environment loader
│   ├── bot.py                    # Master 24/7 autonomous async trading daemon
│   ├── data_feed/
│   │   ├── binance_ws.py         # Async WebSocket for 4H klines & live @forceOrder liquidations
│   │   └── feature_pipeline.py   # Real-time streaming ATR, RVOL, and setup classifier
│   ├── execution/
│   │   ├── coindcx_client.py     # Authenticated CoinDCX REST API client (HMAC SHA-256)
│   │   ├── mock_broker.py        # Paper trading engine for zero-risk testing
│   │   └── order_manager.py      # OCO bracket lifecycle manager (cancel-on-fill, TP/SL)
│   ├── ml/
│   │   ├── model.py              # Calibrated LightGBM reversion probability classifier
│   │   ├── trainer.py            # Automated training & walk-forward retraining module
│   │   ├── feature_store.py      # SQLite database for live trade outcomes & drift tracking
│   │   └── model_weights.pkl     # Pre-trained production model weights (77.7% accuracy)
│   ├── risk/
│   │   └── circuit_breakers.py   # 3-strike daily loss kill switch & drawdown lock
│   └── notifications/
│       └── telegram_bot.py       # Instant Telegram trade alerts, heartbeat, & kill switch
├── deploy/
│   ├── Dockerfile                # Production Docker container image
│   ├── docker-compose.yml        # Docker Compose configuration
│   ├── trading_bot.service       # Systemd service unit for Linux VPS deployment
│   └── setup_server.sh           # 1-click VPS provisioning shell script
├── data/
│   ├── xrp_4h_futures_all.parquet # 6.66 years of historical 4H candles (14,598 rows)
│   └── live_trading.db           # SQLite database storing live trades and feature history
├── dashboard/
│   └── dashboard.html            # Standalone visual PnL and analytics dashboard
├── tests/
│   └── test_strategy.py          # Automated unit tests for math and execution logic
├── .env.example                  # Environment configuration template
└── requirements.txt              # Production Python package dependencies
```

---

## 🚀 Quick Start (Local Paper Trading)

The bot defaults to **`EXECUTION_MODE=MOCK`**, allowing you to test real-time WebSocket feeds, ML predictions, and simulated fills with zero financial risk.

1. **Activate Virtual Environment**:
   ```bash
   source .venv/bin/activate
   ```

2. **Verify Pre-Trained ML Weights**:
   ```bash
   python production/ml/trainer.py
   ```

3. **Launch the Autonomous Daemon**:
   ```bash
   python production/bot.py
   ```

You will see the bot connect to the live Binance Futures WebSocket, pre-seed historical features, monitor XRP price ticks, and wait for 4H candle opens.

---

## ⚙️ Switching to Live CoinDCX Trading

1. Open `.env` in your project root:
   ```bash
   nano .env
   ```
2. Update the following credentials:
   ```env
   # Switch from MOCK to LIVE
   EXECUTION_MODE=LIVE

   # CoinDCX API Keys (from CoinDCX -> API Management)
   COINDCX_API_KEY=your_real_api_key
   COINDCX_API_SECRET=your_real_api_secret
   COINDCX_SYMBOL=B-XRP_USDT

   # Your Starting Capital & Telegram
   INITIAL_CAPITAL_INR=10000.0
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   ```
3. Restart the bot:
   ```bash
   python production/bot.py
   ```

---

## ☁️ 24/7 Cloud Deployment (AWS EC2 / DigitalOcean)

### Option A: Using Docker Compose (Recommended)
```bash
# 1. Clone repository to server
git clone <your-repo-url> My-Trading-Bot
cd My-Trading-Bot

# 2. Configure .env with your credentials
cp .env.example .env
nano .env

# 3. Build and launch container in background
docker compose -f deploy/docker-compose.yml up -d --build

# 4. View real-time logs
docker logs -f xrp_liquidity_bot
```

### Option B: Using Systemd (Native Linux Service)
```bash
# 1. Run automated server setup
chmod +x deploy/setup_server.sh
./deploy/setup_server.sh

# 2. Install and enable systemd service
sudo cp deploy/trading_bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading_bot
sudo systemctl start trading_bot

# 3. Check service status & live logs
sudo systemctl status trading_bot
journalctl -u trading_bot -f
```

---

## 🛡️ Circuit Breakers & Safety Features

* **3-Strike Kill Switch**: Automatically halts trading for the day if 2 stop losses occur.
* **15% Max Drawdown Lock**: Permanently pauses the bot and alerts Telegram if portfolio drawdown exceeds 15%.
* **Emergency Remote Kill Switch**: Send `/kill` to your Telegram bot to cancel all active orders and exit immediately.
* **Time Drift Protection**: Server NTP sync ensures timestamps never fail exchange signature validation.
