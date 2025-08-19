#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple health check server with integrated Telegram bot
Designed specifically for Render deployment
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime
from threading import Event, Thread

from flask import Flask, jsonify

# Configure logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app for health checks
app = Flask(__name__)
bot_status = {"running": False, "last_update": None, "error": None}
shutdown_event = Event()


@app.route("/health")
def health_check():
    """Health check endpoint for Render"""
    return (
        jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "tefillin-bot",
                "bot_running": bot_status["running"],
                "last_update": bot_status["last_update"],
                "error": bot_status["error"],
            }
        ),
        200,
    )


@app.route("/")
def index():
    """Root endpoint"""
    return jsonify({"service": "Tefillin Bot", "version": "2.0.0", "status": "running", "health_check": "/health"})


def run_telegram_bot():
    """Run the Telegram bot with proper error handling"""
    global bot_status  # noqa: F824

    max_retries = 3
    retry_count = 0

    while retry_count < max_retries and not shutdown_event.is_set():
        try:
            logger.info(f"Starting Telegram bot (attempt {retry_count + 1}/{max_retries})...")

            # Import here to avoid circular imports
            from main_updated import TefillinBot

            # Create bot instance
            bot = TefillinBot()
            bot_status["running"] = True
            bot_status["last_update"] = datetime.now().isoformat()
            bot_status["error"] = None

            logger.info("Bot initialized successfully, starting polling...")

            # Run bot with proper error handling
            bot.app.run_polling(
                drop_pending_updates=True,  # Critical for avoiding conflicts
                allowed_updates=[],  # Accept all update types
                close_loop=False,
                stop_signals=None,  # We handle signals ourselves
            )

        except Exception as e:
            error_msg = f"Bot error: {str(e)}"
            logger.error(error_msg)
            bot_status["running"] = False
            bot_status["error"] = error_msg
            bot_status["last_update"] = datetime.now().isoformat()

            # Check if it's a conflict error
            if "Conflict" in str(e) or "409" in str(e):
                logger.warning("Conflict detected, waiting before retry...")
                time.sleep(10)  # Wait longer for conflict resolution
            else:
                time.sleep(5)

            retry_count += 1

            if retry_count >= max_retries:
                logger.error(f"Failed to start bot after {max_retries} attempts")
                break

    bot_status["running"] = False
    logger.info("Bot thread exiting")


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    shutdown_event.set()
    sys.exit(0)


def main():
    """Main entry point"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Get port from environment
    port = int(os.environ.get("PORT", 10000))

    # Start bot in background thread
    bot_thread = Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    # Give bot time to initialize
    logger.info("Waiting for bot initialization...")
    time.sleep(5)

    # Start Flask server (this blocks)
    logger.info(f"Starting health check server on port {port}...")
    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"Flask server error: {e}")
        shutdown_event.set()


if __name__ == "__main__":
    main()
