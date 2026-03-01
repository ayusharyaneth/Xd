import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

class SignalBot:
    def __init__(self, token: str):
        """Initialize the bot application."""
        self.app = Application.builder().token(token).build()
        self._setup_handlers()

    def _setup_handlers(self):
        """Register all your bot commands and message handlers here."""
        self.app.add_handler(CommandHandler("start", self.start_command))
        # Add your other custom handlers (e.g., /status, /whale_alerts) here

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Dexy Signal Bot is online and monitoring!")

    async def start_bot(self):
        """Asynchronously starts the bot without blocking the main event loop."""
        logging.info("Initializing Signal Bot...")
        
        # Manually initialize and start the bot to run concurrently
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES, 
            drop_pending_updates=True
        )
        
        logging.info("Signal Bot is now running in the background.")

    async def stop_bot(self):
        """Gracefully shuts down the bot and cleans up the event loop."""
        logging.info("Stopping Signal Bot...")
        if self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        logging.info("Signal Bot successfully stopped.")
