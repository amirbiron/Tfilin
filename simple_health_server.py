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

from flask import Flask, jsonify, request

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
    """Camera page using getUserMedia with fallback file upload"""
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
    async function startCamera() {{
      try {{
        const stream = await navigator.mediaDevices.getUserMedia({{ video: {{ facingMode: 'environment' }} }});
        const video = document.getElementById('video');
        video.srcObject = stream;
        video.play();
        document.getElementById('snap').disabled = false;
      }} catch (e) {{
        document.getElementById('status').textContent = 'לא הצלחתי לפתוח מצלמה בדפדפן. אפשר לבחור תמונה מקבצים ולהעלות.';
        document.getElementById('fileRow').style.display = 'block';
      }}
    }}
    function dataURLToBlob(dataURL) {{
      const parts = dataURL.split(',');
      const mime = parts[0].match(/:(.*?);/)[1];
      const bstr = atob(parts[1]);
      let n = bstr.length;
      const u8arr = new Uint8Array(n);
      while (n--) u8arr[n] = bstr.charCodeAt(n);
      return new Blob([u8arr], {{ type: mime }});
    }}
    async function snapAndUpload() {{
      const video = document.getElementById('video');
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 720;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const dataURL = canvas.toDataURL('image/jpeg', 0.9);
      const blob = dataURLToBlob(dataURL);
      await uploadBlob(blob);
    }}
    async function onFileChosen(e) {{
      const file = e.target.files && e.target.files[0];
      if (file) await uploadBlob(file);
    }}
    async function uploadBlob(blob) {{
      const status = document.getElementById('status');
      status.textContent = 'מעלה...';
      const form = new FormData();
      form.append('photo', blob, 'photo.jpg');
      const params = new URLSearchParams(window.location.search);
      const chatId = params.get('chat_id') || '';
      if (chatId) form.append('chat_id', chatId);
      const res = await fetch('/upload_photo', {{ method: 'POST', body: form }});
      status.textContent = res.ok ? 'הועלה ונשלח לבוט! פתח את טלגרם כדי לצפות.' : 'שגיאה בשליחה לבוט.';
    }}
  </script>
  </head>
<body>
  <h2>📸 צילום ושליחה לבוט</h2>
  <video id=\"video\" style=\"width:100%;max-width:480px;background:#000\" playsinline muted></video>
  <div class=\"box\">
    <button id=\"snap\" onclick=\"snapAndUpload()\" disabled>צלם ושלח</button>
  </div>
  <div id=\"status\" class=\"box hint\"></div>
  <div id=\"fileRow\" class=\"box\" style=\"display:none\">או בחר תמונה: <input id=\"file\" type=\"file\" accept=\"image/*\" onchange=\"onFileChosen(event)\" /></div>
  <div class=\"box hint\">
    לאחר צילום, פתח את טלגרם ושלח את התמונה לבוט.
  </div>
  <div class=\"box\">
    <a class=\"button\" href=\"{bot_link}\">פתח את טלגרם</a>
  </div>
  <div class=\"box hint\">URL שירות: {base_url}</div>
  <script>startCamera();</script>
</body>
</html>
"""
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/upload_photo", methods=["POST"])
def upload_photo():
    """Receive uploaded photo and forward to Telegram bot chat_id"""
    try:
        from main_updated import TefillinBot  # local import

        chat_id = request.form.get("chat_id")
        file = request.files.get("photo")
        if not file:
            return ("missing photo", 400)
        path = "/tmp/upload.jpg"
        file.save(path)
        bot = TefillinBot()
        if chat_id:
            bot.app.bot.send_photo(chat_id=chat_id, photo=open(path, "rb"))
        return ("ok", 200)
    except Exception as e:
        logger.error(f"upload_photo error: {e}")
        return ("error", 500)


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

            # Standby (not leader), unless lock disabled
            if ("Not leader" in str(e) or "leader lock" in str(e)) and os.environ.get(
                "DISABLE_LEADER_LOCK", "0"
            ).lower() not in ("1", "true", "yes"):
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
