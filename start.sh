#!/bin/bash

# Tefillin Bot Startup Script
# מבטיח הרצה נקייה ללא instances כפולים

echo "🚀 Starting Tefillin Bot..."

# Kill any existing bot processes
echo "Checking for existing bot processes..."
pkill -f "python.*main" 2>/dev/null
pkill -f "python.*bot" 2>/dev/null

# Wait for processes to die
sleep 3

# Clean up any lock files
rm -f /tmp/tefillin_bot.lock 2>/dev/null
rm -f /tmp/bot.lock 2>/dev/null

# Export environment variables
export PYTHONUNBUFFERED=1
export PYTHONPATH=/app:$PYTHONPATH
export PORT=${PORT:-10000}

# Clear Telegram webhook (if any)
if [ ! -z "$BOT_TOKEN" ]; then
    echo "Clearing any existing webhook..."
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/deleteWebhook" > /dev/null 2>&1
    sleep 2
fi

# On Render, PORT is always set, so we need the health check server
echo "Starting with health check server on port ${PORT}..."
exec python simple_health_server.py