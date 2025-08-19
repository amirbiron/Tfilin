#!/bin/bash

# Tefillin Bot Startup Script
# מבטיח הרצה נקייה ללא instances כפולים

echo "🚀 Starting Tefillin Bot..."

# Kill any existing bot processes
echo "Checking for existing bot processes..."
pkill -f "python.*main_updated.py" 2>/dev/null
pkill -f "python.*main_with_healthcheck.py" 2>/dev/null
pkill -f "python.*bot_manager.py" 2>/dev/null

# Wait a bit for processes to die
sleep 2

# Clean up lock files
rm -f /tmp/tefillin_bot.lock 2>/dev/null

# Export environment variables
export PYTHONUNBUFFERED=1
export PYTHONPATH=/app:$PYTHONPATH

# Check if we should use health check version
if [ "$USE_HEALTHCHECK" = "true" ] || [ "$PORT" != "" ]; then
    echo "Starting with health check server on port ${PORT:-10000}..."
    exec python main_with_healthcheck.py
else
    echo "Starting in standalone mode..."
    exec python bot_manager.py
fi