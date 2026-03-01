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


## Setup Guide
1. `git clone <repo>`
2. `python -m venv venv && source venv/bin/activate`
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in Bot tokens and Chat IDs.
5. Modify `strategy.yaml` to adjust thresholds.
6. `python main.py`
