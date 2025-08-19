#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Manager - מנהל הרצת הבוט עם מניעת instances כפולים
"""

import asyncio
import fcntl
import logging
import os
import signal
import sys
import time
from pathlib import Path

# Configure logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


class SingletonBot:
    """מבטיח שרק instance אחד של הבוט רץ"""

    LOCK_FILE = "/tmp/tefillin_bot.lock"

    def __init__(self):
        self.lock_file = None
        self.bot_instance = None

    def acquire_lock(self):
        """נסה לקבל lock - אם כבר יש instance רץ, יכשל"""
        try:
            self.lock_file = open(self.LOCK_FILE, "w")
            fcntl.lockf(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file.write(str(os.getpid()))
            self.lock_file.flush()
            logger.info(f"Lock acquired successfully (PID: {os.getpid()})")
            return True
        except IOError:
            logger.error("Another instance is already running!")
            if self.lock_file:
                self.lock_file.close()
            return False

    def release_lock(self):
        """שחרר את ה-lock"""
        if self.lock_file:
            try:
                fcntl.lockf(self.lock_file, fcntl.LOCK_UN)
                self.lock_file.close()
                os.remove(self.LOCK_FILE)
                logger.info("Lock released successfully")
            except Exception as e:
                logger.error(f"Error releasing lock: {e}")

    def cleanup_stale_lock(self):
        """נקה lock ישן אם התהליך הקודם קרס"""
        if os.path.exists(self.LOCK_FILE):
            try:
                with open(self.LOCK_FILE, "r") as f:
                    old_pid = int(f.read().strip())

                # בדוק אם התהליך עדיין חי
                try:
                    os.kill(old_pid, 0)
                    logger.warning(f"Process {old_pid} is still running")
                    return False
                except ProcessLookupError:
                    # התהליך לא קיים, נקה את הlock
                    os.remove(self.LOCK_FILE)
                    logger.info(f"Cleaned up stale lock from PID {old_pid}")
                    return True
            except Exception as e:
                logger.error(f"Error checking stale lock: {e}")
                return False
        return True

    def run(self):
        """הרץ את הבוט עם הגנה מפני instances כפולים"""
        # נקה locks ישנים
        self.cleanup_stale_lock()

        # נסה לקבל lock
        if not self.acquire_lock():
            logger.error("Failed to acquire lock. Exiting...")
            sys.exit(1)

        try:
            # Import and run the bot
            from main_with_healthcheck import main

            logger.info("Starting bot with singleton protection...")
            main()

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            raise
        finally:
            self.release_lock()


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Received shutdown signal")
    sys.exit(0)


if __name__ == "__main__":
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run bot with singleton protection
    manager = SingletonBot()
    manager.run()
