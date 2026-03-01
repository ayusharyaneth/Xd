import asyncio
import logging
import sys
import uvloop

# Import your modules
from bots.signal_bot import SignalBot
# from bots.alert_bot import AlertBot
# from watch.watch_manager import WatchManager
# from config.settings import SIGNAL_BOT_TOKEN

# Setup standardized logging to match your exact format
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
    level=logging.INFO,
    datefmt="%y-%m-%d %H:%M:%S"
)

async def main():
    logging.info("Using uvloop for optimized performance")
    logging.info("Initializing DexScreener Intelligence System...")
    
    # 1. Initialize your bots and managers
    # Pass your token from config/settings.py here
    signal_bot = SignalBot(token="YOUR_BOT_TOKEN_HERE") 
    
    # alert_bot = AlertBot(token="YOUR_ALERT_TOKEN_HERE")
    # watch_manager = WatchManager(...)

    # 2. Start bots asynchronously (non-blocking)
    await signal_bot.start_bot()
    # await alert_bot.start_bot()
    
    # 3. Start your monitoring loops as background tasks
    # watch_task = asyncio.create_task(watch_manager.start_monitoring())

    logging.info("System successfully initialized. Listening for newly listed tokens...")

    # 4. Keep the main event loop alive forever
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep in 1-hour chunks to keep the thread alive
    except asyncio.CancelledError:
        logging.info("Main loop cancelled. Initiating system shutdown...")
    finally:
        # 5. Graceful shutdown sequence
        logging.info("Shutting down Telegram bots safely...")
        await signal_bot.stop_bot()
        # await alert_bot.stop_bot()
        
        # if watch_task:
        #     watch_task.cancel()

if __name__ == "__main__":
    # Install uvloop globally for speed
    uvloop.install()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received. System shutdown complete.")
        sys.exit(0)
