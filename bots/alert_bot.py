import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

class AlertBot:
    def __init__(self, token: str):
        """Initialize the alert bot application."""
        self.app = Application.builder().token(token).build()
        self._setup_handlers()

    def _setup_handlers(self):
        """Register all your alert commands and message handlers here."""
        self.app.add_handler(CommandHandler("start", self.start_command))
        # Add your specific handlers (e.g., /status, /rug_check, /whale_alerts) here

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Dexy Alert Bot is online! Ready to broadcast critical intelligence.")

    async def start_bot(self):
        """Asynchronously starts the alert bot without blocking the main event loop."""
        logging.info("Initializing Alert Bot...")
        
        # Manually initialize and start the bot to run concurrently
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES, 
            drop_pending_updates=True
        )
        
        logging.info("Alert Bot is now running in the background.")

    async def stop_bot(self):
        """Gracefully shuts down the bot and cleans up the event loop."""
        logging.info("Stopping Alert Bot...")
        if self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        logging.info("Alert Bot successfully stopped.")

    # ---------------------------------------------------------
    # Custom Broadcast Methods for your Intelligence System
    # ---------------------------------------------------------
    
    async def broadcast_alert(self, chat_id: str, message: str):
        """
        Utility method to push proactive alerts (e.g., Whale Detection, Rug Probability)
        directly to a specific chat or channel.
        """
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to send alert to {chat_id}: {e}")
