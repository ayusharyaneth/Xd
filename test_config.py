#!/usr/bin/env python3
"""Test configuration loading"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Testing configuration loading...")
    print("-" * 50)
    
    from config.settings import get_config
    
    config = get_config()
    settings = config.settings
    
    print("✅ Configuration loaded successfully!")
    print()
    print("Settings loaded:")
    print(f"  LOG_LEVEL: {settings.LOG_LEVEL}")
    print(f"  POLL_INTERVAL_SECONDS: {settings.POLL_INTERVAL_SECONDS}")
    print(f"  RPC_ENDPOINT: {settings.RPC_ENDPOINT}")
    print(f"  SIGNAL_BOT_TOKEN: {'✅ Set' if settings.SIGNAL_BOT_TOKEN else '❌ Not set'}")
    print(f"  ALERT_BOT_TOKEN: {'✅ Set' if settings.ALERT_BOT_TOKEN else '❌ Not set'}")
    print(f"  SIGNAL_CHAT_ID: {'✅ Set' if settings.SIGNAL_CHAT_ID else '❌ Not set'}")
    print()
    
    # Check if alternative fields were loaded
    if settings.rpc_base_url:
        print(f"  rpc_base_url (alternative): {settings.rpc_base_url}")
    if settings.poll_interval:
        print(f"  poll_interval (alternative): {settings.poll_interval}")
    
    print()
    print("Strategy config:")
    print(f"  Filters stage1 min_liquidity: {config.strategy.filters.stage1.min_liquidity_usd}")
    print(f"  Risk scoring weights: {config.strategy.risk_scoring.weights}")
    print()
    print("✅ All configurations loaded successfully!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
