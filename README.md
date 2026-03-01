# DexScreener Intelligence System

A production-grade Python system that monitors newly listed tokens, applies advanced behavioral and intelligence engines, and pushes interactive alerts to Telegram.

## Architecture Explanation
The system operates asynchronously using `asyncio` and `aiohttp`. 
- **API Layer**: Polls DexScreener periodically.
- **Engines Layer**: Runs tokens through a two-stage filter. First, basic risk (liquidity/FDV). Second, deep intelligence (authenticity, rug probability, whales).
- **Ranking**: Buffers alerts and only sends the highest-scoring tokens to reduce noise.
- **Bot Layer**: 
  - *Signal Bot*: Interacts with users, sends alpha, handles inline buttons (Watch/Refresh), and the `/ping` command.
  - *Alert Bot*: Dedicated to critical system failures and Safe Mode escalation.
- **System Layer**: Monitors CPU, RAM, and API latency, triggering Self-Defense mode if thresholds are breached.

## Features
- **Two-Stage Configurable Filters**: Fast rejection of low-liquidity scams.
- **Rug Probability Estimator**: Combines clustering, risk, and dev rep into a 0-100% score.
- **Watch Mode**: Clicking '👁 Watch' tracks the token and utilizes the Exit Assistant.
- **Self-Defense Mode**: Auto-pauses polling if error rates exceed limits defined in `strategy.yaml`.

## Examples

**Example Alert Message**
🚀 **NEW ALPHA DETECTED** 🚀
**Symbol:** PEPE2
**Address:** `0x123...abc`
**Price:** 0.000045 USD
**Score:** 85.50/100
[🔄 Refresh] [👁 Watch]

**Example Watch Message**
⚠️ **WATCH ESCALATION** ⚠️
Token: `0x123...abc`
Reason: Price dropped > 30% in 1h
Action: Consider Exit.

**Example /ping Output**
🏓 **System Status**
Status: 🟢 Healthy
Latency: 45.20ms
CPU: 12.5%
Memory: 45.0%
Market Regime: NORMAL
Safe Mode: 🟢 INACTIVE
Active Watches: 3

## Setup Guide
1. `git clone <repo>`
2. `python -m venv venv && source venv/bin/activate`
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in Bot tokens and Chat IDs.
5. Modify `strategy.yaml` to adjust thresholds.
6. `python main.py`

## Ubuntu VPS Deployment (systemd)

Create `/etc/systemd/system/dexscreener-bot.service`:

```ini
[Unit]
Description=DexScreener Intelligence Bot
After=network.target

[Service]
User=root
WorkingDirectory=/path/to/project-root
Environment="PATH=/path/to/project-root/venv/bin"
ExecStart=/path/to/project-root/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
