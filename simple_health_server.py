#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple health check server with integrated Telegram bot
Designed specifically for Render deployment
"""

import logging
import asyncio
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

@app.route("/favicon.ico")
def favicon():
    return ("", 204)

@app.route("/camera")
def camera_page():
    """A minimal camera page to open in external browser"""
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    bot_username = os.environ.get("BOT_USERNAME", "")
    bot_link = f"tg://resolve?domain={bot_username}" if bot_username else "https://t.me"

    html = f"""
<!DOCTYPE html>
<html lang=\"he\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>מצלמה - בוט תפילין</title>
  <style>
    body {{ font-family: sans-serif; margin: 16px; }}
    .box {{ margin: 12px 0; }}
    button, a.button {{ display: inline-block; padding: 12px 16px; background:#0b74de; color:#fff; text-decoration:none; border:none; border-radius:8px; }}
    .hint {{ color:#555; font-size:14px; }}
  </style>
  <script>
    function openFileCapture() {{
      const input = document.getElementById('capture');
      input.click();
    }}
    function onFileChosen(e) {{
      const file = e.target.files && e.target.files[0];
      const status = document.getElementById('status');
      if (file) {{
        status.textContent = 'נבחרה תמונה. כעת פתח את טלגרם ושלח אותה לבוט';
      }} else {{
        status.textContent = '';
      }}
    }}
  </script>
  </head>
<body>
  <h2>📸 צילום ושליחה לבוט</h2>
  <div class=\"box\">
    <input id=\"capture\" type=\"file\" accept=\"image/*\" capture=\"environment\" style=\"display:none\" onchange=\"onFileChosen(event)\" />
    <button onclick=\"openFileCapture()\">פתח מצלמה</button>
  </div>
  <div id=\"status\" class=\"box hint\"></div>
  <div class=\"box hint\">
    לאחר צילום, פתח את טלגרם ושלח את התמונה לבוט.
  </div>
  <div class=\"box\">
    <a class=\"button\" href=\"{bot_link}\">פתח את טלגרם</a>
  </div>
  <div class=\"box hint\">URL שירות: {base_url}</div>
</body>
</html>
"""
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}

def run_telegram_bot():
    """Run the Telegram bot with proper error handling"""
    global bot_status  # noqa: F824

    max_retries = 3
    retry_count = 0

    while retry_count < max_retries and not shutdown_event.is_set():
        try:
            logger.info(f"Starting Telegram bot (attempt {retry_count + 1}/{max_retries})...")

            # Ensure an event loop exists in this thread (Python 3.11+ doesn't create one by default)
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

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

            # Standby (not leader)
            if "Not leader" in str(e) or "leader lock" in str(e):
                logger.info("Not leader. Standing by and retrying to acquire leader lock later...")
                time.sleep(15)
                continue

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

    # Start bot in background thread (do not delay HTTP server startup)
    bot_thread = Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    # Start Flask server (this blocks)
    logger.info(f"Starting health check server on port {port}...")
    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"Flask server error: {e}")
        shutdown_event.set()


if __name__ == "__main__":
    main()
