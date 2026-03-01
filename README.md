# DexScreener Intelligence System

A production-grade Python system for monitoring newly listed tokens from DexScreener with advanced behavioral analysis, intelligence engines, and interactive Telegram features.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Telegram Commands](#telegram-commands)
- [Alert Examples](#alert-examples)
- [Deployment](#deployment)
- [Security](#security)

## Overview

The DexScreener Intelligence System is a comprehensive crypto monitoring solution that:

- Monitors newly listed tokens from DexScreener in real-time
- Applies 15+ intelligence engines for behavioral analysis
- Supports interactive Telegram features with inline buttons
- Implements self-defense mechanisms for operational resilience
- Provides health monitoring and automatic recovery

### Key Capabilities

| Feature | Description |
|---------|-------------|
| Two-Stage Filtering | Basic + advanced criteria for token selection |
| Risk Scoring | Multi-factor risk assessment (0-100) |
| Volume Authenticity | Wash trading and manipulation detection |
| Developer Tracking | Historical reputation analysis |
| Whale Detection | Large holder monitoring and alerts |
| Early Buyer Tracking | First 50 buyers PnL monitoring |
| Wallet Clustering | Sybil attack detection |
| Capital Rotation | Cross-token flow analysis |
| Rug Probability | ML-inspired probability estimation |
| Smart Exit Assistant | Automated exit recommendations |
| Alert Ranking | Composite scoring for prioritization |
| Market Regime | Dynamic threshold adjustment |
| Watch Mode | Interactive token monitoring |
| Self-Defense | Automatic safe mode activation |

## Architecture

```
project-root/
├── main.py                    # Main orchestrator
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
├── strategy.yaml             # Strategy configuration
├── README.md                 # This file
├── config/
│   └── settings.py           # Pydantic configuration models
├── api/
│   ├── dexscreener.py        # DexScreener API client
│   └── rpc.py                # Solana RPC client
├── engines/
│   ├── risk.py               # Risk scoring engine
│   ├── authenticity.py       # Volume authenticity engine
│   ├── developer.py          # Developer reputation engine
│   ├── buy_quality.py        # Buy quality scoring
│   ├── whale.py              # Whale detection engine
│   ├── early_buyer.py        # Early buyer tracking
│   ├── wallet_cluster.py     # Wallet cluster detection
│   ├── capital_rotation.py   # Capital rotation tracker
│   ├── probability.py        # Rug probability estimator
│   ├── exit_engine.py        # Smart exit assistant
│   ├── ranking.py            # Alert ranking engine
│   └── regime.py             # Market regime analyzer
├── watch/
│   └── watch_manager.py      # Watch mode management
├── system/
│   ├── health.py             # Health check system
│   ├── self_defense.py       # Self-defense system
│   └── metrics.py            # Metrics collection
├── bots/
│   ├── signal_bot.py         # Signal Telegram bot
│   └── alert_bot.py          # Alert Telegram bot
└── utils/
    ├── logger.py             # Structured logging
    └── helpers.py            # Utility functions
```

## Features

### Intelligence Engines

#### 1. Risk Scoring Engine
- **Components**: Liquidity risk, volume risk, holder concentration, contract risk, developer risk
- **Output**: 0-100 score with risk level classification
- **Weighting**: Configurable via strategy.yaml

#### 2. Volume Authenticity Engine
- **Detects**: Wash trading, circular trading, matched orders
- **Metrics**: Trade variance, time distribution, buyer-seller overlap
- **Output**: Authenticity score with suspicious patterns

#### 3. Developer Reputation Engine
- **Tracks**: Previous tokens, rug history, liquidity locking
- **Scoring**: +30 for success, -50 per rug
- **Classification**: Trusted, neutral, suspicious, blacklist

#### 4. Buy Quality Engine
- **Wallet Tiers**: Whale ($10k+), Shark ($5k+), Dolphin ($1k+), Fish ($100+), Shrimp
- **Factors**: Diversity, sustainability, entry timing, holding pattern

#### 5. Whale Detection Engine
- **Thresholds**: $50k wallet value, $10k single buy
- **Tracking**: Position updates, movement alerts
- **Alerts**: Large buy/sell with cooldown

#### 6. Early Buyer Tracker
- **Scope**: First 50 buyers
- **Metrics**: Unrealized PnL, sell pressure, distribution
- **Alerts**: Mass selling, early profit taking

#### 7. Wallet Cluster Detector
- **Detection**: Similar funding, timing, trade patterns
- **Suspicion Score**: 0-100 based on indicators
- **Minimum Cluster**: 3 wallets

#### 8. Capital Rotation Tracker
- **Window**: 30-minute detection window
- **Tracking**: Whale exits and entries
- **Boost**: +15 score for detected rotation

#### 9. Rug Probability Estimator
- **Indicators**: Liquidity, holders, contract, developer, volume
- **Output**: 0-1 probability with warning levels
- **Early Warnings**: Liquidity unlock, dev wallet movement

#### 10. Smart Exit Assistant
- **Triggers**: Liquidity drop, whale exit, risk escalation, profit target
- **Features**: Trailing stops, multiple exit conditions
- **Cooldown**: 180 seconds between alerts

#### 11. Alert Ranking Engine
- **Buffer Window**: 5-minute ranking window
- **Composite Score**: Weighted combination of all engines
- **Output**: Top 10 alerts per window

#### 12. Market Regime Analyzer
- **Regimes**: Bull, Bear, Chop, Volatile
- **Adjustments**: Dynamic threshold modification
- **Indicators**: Price trend, volume trend, sentiment

### Watch Mode

Interactive token monitoring with:
- Inline button activation (👁 Watch)
- 30-minute default expiry
- Escalation detection (price, volume, risk)
- Periodic updates

### Self-Defense Mode

Automatic protection when:
- API error rate > 10%
- Latency > 5000ms
- Memory > 1800MB
- CPU > 85%

**Actions**:
- Reduce poll frequency
- Pause non-critical features
- Increase cooldowns
- Alert admins

---

## 📦 Requirements

- Python 3.11+
- Git
- Linux / macOS / WSL (Windows via WSL recommended)

---

## ⚙️ Installation

### 1. Clone Repository

```bash
git clone https://github.com/ayusharyaneth/dexy.git
cd dexy
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Upgrade pip (Recommended)

```bash
pip install --upgrade pip
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 5. Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and configure:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- Any additional required keys

If a value exists in both `.env` and `strategy.yaml`, `.env` takes priority.

---

### 6. Strategy Configuration

Edit:

```
strategy.yaml
```

Modify thresholds, filters, or risk parameters according to your trading logic.

---

### 7. Running Dexy

```bash
python3 main.py
```

Dexy will:

- Poll DexScreener  
- Apply strategy filters  
- Send alerts to configured Telegram chat  

---

### 🔄 Updating

```bash
git pull origin main
pip install -r requirements.txt
```

---

## ⚠️ Notes

- Ensure Python 3.11+ is installed  
- Always validate strategy parameters before running in production  
- Never expose your `.env` file publicly  

---

## Configuration

### Environment Variables (.env)

```bash
# Telegram Bot Tokens (required)
SIGNAL_BOT_TOKEN=your_signal_bot_token_here
ALERT_BOT_TOKEN=your_alert_bot_token_here

# Chat IDs (required)
SIGNAL_CHAT_ID=your_signal_chat_id
ALERT_CHAT_ID=your_alert_chat_id
ADMIN_CHAT_ID=your_admin_chat_id

# API Configuration
DEXSCREENER_API_BASE=https://api.dexscreener.com/latest
RPC_ENDPOINT=https://api.mainnet-beta.solana.com

# Polling Intervals
POLL_INTERVAL_SECONDS=30
WATCH_UPDATE_INTERVAL_SECONDS=60
HEALTH_CHECK_INTERVAL_SECONDS=300

# System Limits
MAX_MEMORY_MB=2048
MAX_CPU_PERCENT=80

# Feature Flags
ENABLE_SELF_DEFENSE=true
ENABLE_WATCH_MODE=true
ENABLE_WHALE_DETECTION=true
```

### Strategy Configuration (strategy.yaml)

```yaml
filters:
  stage1:
    min_liquidity_usd: 10000
    min_volume_24h_usd: 5000
    max_token_age_hours: 72
  
  stage2:
    min_buy_ratio: 0.55
    max_price_change_5m: 100

risk_scoring:
  weights:
    liquidity_risk: 0.25
    volume_risk: 0.20
    holder_concentration: 0.20

whale_detection:
  thresholds:
    min_single_buy_usd: 10000
    min_wallet_value_usd: 50000

self_defense:
  activation_thresholds:
    api_error_rate: 0.1
    avg_latency_ms: 5000
    memory_usage_mb: 1800
```

## Usage

### Running the System

```bash
# Activate virtual environment
source venv/bin/activate

# Run main system
python main.py

# Run with specific config
python main.py --config /path/to/strategy.yaml
```

### Running as Service (systemd)

```bash
# Create service file
sudo nano /etc/systemd/system/dex-intel.service
```

```ini
[Unit]
Description=DexScreener Intelligence System
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/dexscreener-intelligence-system
Environment=PATH=/home/ubuntu/dexscreener-intelligence-system/venv/bin
ExecStart=/home/ubuntu/dexscreener-intelligence-system/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable dex-intel
sudo systemctl start dex-intel

# Check status
sudo systemctl status dex-intel
sudo journalctl -u dex-intel -f
```

## Telegram Commands

### Signal Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and bot info |
| `/ping` | System status and health check |
| `/watchlist` | View all watched tokens |
| `/regime` | Current market regime analysis |

---
