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

from flask import Flask, jsonify, make_response

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


@app.route("/webapp/camera")
def webapp_camera():
    """Serve a minimal WebApp page that opens device camera and returns photo to Telegram"""
    html = """
<!doctype html>
<html lang=\"he\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\" />
  <title>צלם תמונה</title>
  <script src=\"https://telegram.org/js/telegram-web-app.js\"></script>
  <style>
    body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; background:#111; color:#fff; }
    .container { padding: 16px; }
    video, canvas { width: 100%; max-height: 60vh; background:#000; border-radius: 12px; }
    .row { display: flex; gap: 12px; margin-top: 12px; }
    button { flex: 1; padding: 14px 16px; font-size: 16px; border-radius: 12px; border: none; cursor: pointer; }
    #snap { background:#2ea043; color:#fff; }
    #retake { background:#444; color:#fff; }
    #send { background:#1d9bf0; color:#fff; }
    .hidden { display: none; }
  </style>
  <meta http-equiv=\"origin-trial\" content=\"\" />
  <meta name=\"referrer\" content=\"no-referrer\" />
  <meta http-equiv=\"Permissions-Policy\" content=\"camera=(self)\" />
  <meta name=\"color-scheme\" content=\"dark light\" />
  <meta name=\"theme-color\" content=\"#111\" />
  <meta name=\"apple-mobile-web-app-capable\" content=\"yes\" />
  <meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\" />
  <meta name=\"mobile-web-app-capable\" content=\"yes\" />
  <meta name=\"format-detection\" content=\"telephone=no\" />
  <meta name=\"HandheldFriendly\" content=\"true\" />
  <meta name=\"apple-mobile-web-app-title\" content=\"Camera\" />
</head>
<body dir=\"rtl\">
  <div class=\"container\">
    <h2>📸 צלם תמונה</h2>
    <video id=\"preview\" autoplay playsinline></video>
    <canvas id=\"photo\" class=\"hidden\"></canvas>
    <div class=\"row\">
      <button id=\"snap\">צלם</button>
      <button id=\"retake\" class=\"hidden\">צלם שוב</button>
      <button id=\"send\" class=\"hidden\">שלח</button>
    </div>
  </div>

  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.expand();
      tg.MainButton.hide();
    }

    const video = document.getElementById('preview');
    const canvas = document.getElementById('photo');
    const snapBtn = document.getElementById('snap');
    const retakeBtn = document.getElementById('retake');
    const sendBtn = document.getElementById('send');

    async function initCamera() {
      try {
        const constraints = { video: { facingMode: 'user' } };
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = stream;
      } catch (e) {
        alert('לא הצלחתי לפתוח מצלמה: ' + e.message);
      }
    }

    function showPreview() {
      canvas.classList.add('hidden');
      video.classList.remove('hidden');
      snapBtn.classList.remove('hidden');
      retakeBtn.classList.add('hidden');
      sendBtn.classList.add('hidden');
    }

    function showCapture() {
      const ctx = canvas.getContext('2d');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.classList.remove('hidden');
      video.classList.add('hidden');
      snapBtn.classList.add('hidden');
      retakeBtn.classList.remove('hidden');
      sendBtn.classList.remove('hidden');
    }

    snapBtn.addEventListener('click', showCapture);
    retakeBtn.addEventListener('click', showPreview);
    sendBtn.addEventListener('click', () => {
      try {
        const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
        const payload = { type: 'photo', dataUrl };
        if (tg) {
          tg.sendData(JSON.stringify(payload));
          tg.close();
        } else {
          alert('Telegram WebApp API לא זמין');
        }
      } catch (e) {
        alert('שגיאה בשליחת התמונה: ' + e.message);
      }
    });

    initCamera();
  </script>
</body>
</html>
    """
    return make_response(html, 200, {"Content-Type": "text/html; charset=utf-8"})


def run_telegram_bot():
    """Run the Telegram bot with proper error handling"""
    global bot_status  # noqa: F824

    # Ensure an asyncio event loop exists in this background thread (Python 3.11+ requirement)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

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
