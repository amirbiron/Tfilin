#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple health check server with integrated Telegram bot
Designed specifically for Render deployment
"""

import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime
from threading import Event, Thread

from flask import Flask, jsonify, make_response, request, send_file
import uuid

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
    """Serve a minimal WebApp page that opens device camera and allows sharing the photo"""
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
    <video id=\"preview\" autoplay playsinline muted></video>
    <canvas id=\"photo\" class=\"hidden\"></canvas>
    <div class=\"row\">
      <button id=\"snap\">צלם</button>
      <button id=\"retake\" class=\"hidden\">צלם שוב</button>
      <button id=\"share\" class=\"hidden\">שלח לאנשי קשר</button>
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
    const shareBtn = document.getElementById('share');

    async function initCamera() {
      try {
        const constraints = { video: { facingMode: 'user' } };
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = stream;
        // Ensure autoplay works across mobile webviews (Telegram/iOS/Android)
        video.muted = true;
        await video.play();
      } catch (e) {
        alert('לא הצלחתי לפתוח מצלמה: ' + e.message);
      }
    }

    function showPreview() {
      canvas.classList.add('hidden');
      video.classList.remove('hidden');
      snapBtn.classList.remove('hidden');
      retakeBtn.classList.add('hidden');
      shareBtn.classList.add('hidden');
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
      shareBtn.classList.remove('hidden');
    }

    snapBtn.addEventListener('click', showCapture);
    retakeBtn.addEventListener('click', showPreview);

    // Share to contacts: prefer Web Share, otherwise upload and open Telegram share link
    shareBtn.addEventListener('click', async () => {
      try {
        const dataUrl = canvas.toDataURL('image/jpeg', 0.92);
        const res = await fetch(dataUrl);
        const blob = await res.blob();
        const file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
          await navigator.share({ files: [file], title: 'צילום', text: 'תמונה' });
          return;
        }
        // Fallback: upload and open Telegram share chooser
        const form = new FormData();
        form.append('photo', blob, 'photo.jpg');
        const resp = await fetch('/share_photo', { method: 'POST', body: form });
        if (!resp.ok) throw new Error('שגיאה בהעלאה לשיתוף');
        const data = await resp.json();
        const url = data && data.url;
        if (!url) throw new Error('קישור שיתוף חסר');
        const shareLink = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent('תמונה')}`;
        if (tg && tg.openTelegramLink) tg.openTelegramLink(shareLink);
        else window.open(shareLink, '_blank');
      } catch (e) {
        alert('שגיאה בשיתוף: ' + (e && e.message ? e.message : e));
      }
    });

    initCamera();
  </script>
</body>
</html>
    """
    return make_response(html, 200, {"Content-Type": "text/html; charset=utf-8"})


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
  <div class=\"box\">\n    <button id=\"snap\" onclick=\"snapAndUpload()\" disabled>צלם ושלח</button>\n  </div>
  <div id=\"status\" class=\"box hint\"></div>
  <div id=\"fileRow\" class=\"box\" style=\"display:none\">או בחר תמונה: <input id=\"file\" type=\"file\" accept=\"image/*\" onchange=\"onFileChosen(event)\" /></div>
  <div class=\"box hint\">\n    לאחר צילום, פתח את טלגרם ושלח את התמונה לבוט.
  </div>
  <div class=\"box\">\n    <a class=\"button\" href=\"{bot_link}\">פתח את טלגרם</a>\n  </div>
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


@app.route("/share_photo", methods=["POST"])
def share_photo():
    """Receive uploaded photo and return a temporary public URL for sharing"""
    try:
        file = request.files.get("photo")
        if not file:
            return ("missing photo", 400)
        token = uuid.uuid4().hex
        path = f"/tmp/shared_{token}.jpg"
        file.save(path)
        base_url = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or ""
        url = f"{base_url.rstrip('/')}/shared/{token}.jpg" if base_url else f"/shared/{token}.jpg"
        return jsonify({"url": url}), 200
    except Exception as e:
        logger.error(f"share_photo error: {e}")
        return ("error", 500)


@app.route("/shared/<token>.jpg")
def get_shared_photo(token: str):
    try:
        path = f"/tmp/shared_{token}.jpg"
        if not os.path.exists(path):
            return ("not found", 404)
        return send_file(path, mimetype="image/jpeg")
    except Exception as e:
        logger.error(f"get_shared_photo error: {e}")
        return ("error", 500)


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

            # Clean environment issues on Render containers
            os.environ.pop("PYTHONWARNINGS", None)

            # Create bot instance
            bot = TefillinBot()
            bot_status["running"] = True
            bot_status["last_update"] = datetime.now().isoformat()
            bot_status["error"] = None

            # Run bot with proper error handling
            bot.app.run_polling(
                drop_pending_updates=True,  # Critical for avoiding conflicts
                close_loop=False,
                allowed_updates=None,
                stop_signals=None,
            )

            logger.info("Bot stopped gracefully")
            break
        except Exception as e:
            retry_count += 1
            error_msg = f"Telegram bot failed to start/run (attempt {retry_count}): {e}"
            logger.error(error_msg)
            bot_status["running"] = False
            bot_status["error"] = error_msg
            bot_status["last_update"] = datetime.now().isoformat()

            # Backoff before retrying
            if retry_count < max_retries:
                time.sleep(min(10 * retry_count, 30))
                continue

            if retry_count >= max_retries:
                logger.error(f"Failed to start bot after {max_retries} attempts")
                break

    bot_status["running"] = False
    logger.info("Bot thread exiting")


if __name__ == "__main__":
    # Import the original bot
    from main_updated import TefillinBot

    # Start bot in background thread (do not delay HTTP server startup)
    bot_thread = Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    # Start Flask server
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting health check server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
