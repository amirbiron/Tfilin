#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import asyncio
from threading import Thread
from flask import Flask, jsonify
from datetime import datetime
import signal

# Import the original bot
from main_updated import TefillinBot

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create Flask app for health checks
app = Flask(__name__)
bot_instance = None
bot_thread = None

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    global bot_instance
    
    status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "tefillin-bot"
    }
    
    # Check if bot is running
    if bot_instance and bot_thread and bot_thread.is_alive():
        status["bot_status"] = "running"
    else:
        status["bot_status"] = "stopped"
        status["status"] = "unhealthy"
    
    # Check database connection
    try:
        if bot_instance and bot_instance.db_client:
            bot_instance.db_client.admin.command('ping')
            status["database"] = "connected"
        else:
            status["database"] = "disconnected"
    except:
        status["database"] = "error"
        status["status"] = "degraded"
    
    return jsonify(status), 200 if status["status"] == "healthy" else 503

@app.route('/')
def index():
    """Root endpoint"""
    return jsonify({
        "service": "Tefillin Bot",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "/": "Service info",
            "/health": "Health check"
        }
    })

def run_bot():
    """Run the bot in a separate thread"""
    global bot_instance
    
    try:
        logger.info("Starting Telegram bot in background thread...")
        bot_instance = TefillinBot()
        
        # Clear any pending updates before starting
        logger.info("Clearing pending updates...")
        
        # Override the run method to prevent blocking
        bot_instance.app.run_polling(
            drop_pending_updates=True,  # Critical: drop all pending updates
            close_loop=False,  # Don't close the event loop
            allowed_updates=[]  # Accept all update types
        )
    except Exception as e:
        logger.error(f"Bot thread error: {e}")
        raise

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    logger.info("Received shutdown signal, cleaning up...")
    
    global bot_instance
    if bot_instance:
        try:
            # Stop the bot gracefully
            if bot_instance.app:
                bot_instance.app.stop()
            if bot_instance.scheduler:
                bot_instance.scheduler.stop()
            if bot_instance.db_client:
                bot_instance.db_client.close()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    sys.exit(0)

def main():
    """Main entry point"""
    global bot_thread
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start bot in background thread
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Wait a bit for bot to initialize
    logger.info("Waiting for bot to initialize...")
    asyncio.run(asyncio.sleep(3))
    
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 10000))
    
    # Start Flask server
    logger.info(f"Starting health check server on port {port}...")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        use_reloader=False  # Important: prevent duplicate bot instances
    )

if __name__ == "__main__":
    main()