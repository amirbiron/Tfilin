import logging
import os
from datetime import datetime, timedelta

from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from activity_reporter import create_reporter

from config import Config

# הגדרת לוגים
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# התחברות ל-MongoDB
client = MongoClient(Config.MONGODB_URI)
db = client.tefillin_bot
users_collection = db.users

reporter = create_reporter(
    mongodb_uri="mongodb+srv://mumin:M43M2TFgLfGvhBwY@muminai.tm6x81b.mongodb.net/?retryWrites=true&w=majority&appName=muminAI",
    service_id="srv-d2i9hfm3jp1c7397v9jg",
    service_name="Tfilin"
)


class TefillinBot:
    def __init__(self):
        self.app = Application.builder().token(Config.BOT_TOKEN).build()
        self.setup_handlers()

    def setup_handlers(self):
        """הגדרת handlers לבוט"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("settings", self.settings_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת /start - הרשמה ראשונית"""
        reporter.report_activity(update.effective_user.id)
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "ידידי"

        # בדיקה אם המשתמש כבר קיים
        existing_user = users_collection.find_one({"user_id": user_id})

        if existing_user:
            await update.message.reply_text(
                f"שלום {user_name}! 👋\n"
                f"אתה כבר רשום לתזכורות תפילין.\n"
                f"השעה הנוכחית שלך: {existing_user.get('daily_time', '07:30')}\n\n"
                f"אפשר לשנות הגדרות עם /settings"
            )
            return

        # יצירת כפתורי שעות
        keyboard = [
            [
                InlineKeyboardButton("06:30", callback_data="time_06:30"),
                InlineKeyboardButton("07:00", callback_data="time_07:00"),
            ],
            [
                InlineKeyboardButton("07:30", callback_data="time_07:30"),
                InlineKeyboardButton("08:00", callback_data="time_08:00"),
            ],
            [InlineKeyboardButton("שעה אחרת...", callback_data="time_custom")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"ברוך הבא {user_name}! 🙏\n\n" f"בוט התזכורות לתפילין יעזור לך לא לשכוח.\n" f"בחר שעה יומית לתזכורת:",
            reply_markup=reply_markup,
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בלחיצות כפתורים"""
        reporter.report_activity(update.effective_user.id)
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data

        if data.startswith("time_"):
            await self.handle_time_selection(query, user_id, data)
        elif data == "tefillin_done":
            await self.handle_tefillin_done(query, user_id)
        elif data.startswith("snooze_"):
            await self.handle_snooze(query, user_id, data)

    async def handle_time_selection(self, query, user_id, data):
        """טיפול בבחירת שעה"""
        if data == "time_custom":
            await query.edit_message_text("שלח לי שעה בפורמט HH:MM (למשל: 08:15)")
            return

        # חילוץ השעה
        time_str = data.replace("time_", "")

        # שמירת המשתמש במסד הנתונים
        user_data = {
            "user_id": user_id,
            "daily_time": time_str,
            "timezone": "Asia/Jerusalem",
            "created_at": datetime.now(),
            "active": True,
            "streak": 0,
        }

        users_collection.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)

        await query.edit_message_text(
            f"מעולה! ✅\n"
            f"תזכורת יומית נקבעה לשעה {time_str}.\n\n"
            f"תקבל תזכורת כל יום (חוץ משבת וחגים).\n"
            f"אפשר לשנות בכל עת עם /settings"
        )

    async def handle_tefillin_done(self, query, user_id):
        """טיפול בלחיצה על 'הנחתי'"""
        # עדכון רצף
        user = users_collection.find_one({"user_id": user_id})
        if user:
            new_streak = user.get("streak", 0) + 1
            users_collection.update_one(
                {"user_id": user_id}, {"$set": {"streak": new_streak, "last_done": datetime.now().date().isoformat()}}
            )

            streak_text = f"\n🔥 רצף נוכחי: {new_streak} ימים!" if new_streak > 1 else ""

            await query.edit_message_text(f"איזה מלך! ✅🙏\n" f"המשך יום מעולה!{streak_text}")

    async def handle_snooze(self, query, user_id, data):
        """טיפול בנודניק"""
        snooze_minutes = {"snooze_60": 60, "snooze_180": 180}.get(data, 60)

        await query.edit_message_text(f"סגור. אזכיר עוד {snooze_minutes // 60} שעות ⏰")

        # כאן נוסיף את לוגיקת התזמון בהמשך

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת הגדרות"""
        reporter.report_activity(update.effective_user.id)
        user_id = update.effective_user.id
        user = users_collection.find_one({"user_id": user_id})

        if not user:
            await update.message.reply_text("לא נמצאת במערכת. הקש /start להרשמה.")
            return

        keyboard = [
            [InlineKeyboardButton("שינוי שעה יומית", callback_data="change_time")],
            [InlineKeyboardButton("סטטיסטיקות", callback_data="stats")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        current_time = user.get("daily_time", "לא נקבע")
        streak = user.get("streak", 0)

        await update.message.reply_text(
            f"⚙️ ההגדרות שלך:\n\n" f"🕐 שעה יומית: {current_time}\n" f"🔥 רצף נוכחי: {streak} ימים\n\n" f"מה תרצה לשנות?",
            reply_markup=reply_markup,
        )

    async def send_daily_reminder(self, user_id: int):
        """שליחת תזכורת יומית"""
        keyboard = [
            [InlineKeyboardButton("הנחתי ✅", callback_data="tefillin_done")],
            [
                InlineKeyboardButton("נודניק 1ש'", callback_data="snooze_60"),
                InlineKeyboardButton("נודניק 3ש'", callback_data="snooze_180"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await self.app.bot.send_message(
                chat_id=user_id,
                text="⏰ תזכורת יומית – תפילין\nהגיע הזמן להניח תפילין.\nמה תרצה לעשות?",
                reply_markup=reply_markup,
            )
        except Exception as e:
            logger.error(f"Failed to send reminder to {user_id}: {e}")

    def run(self):
        """הרצת הבוט"""
        logger.info("Starting Tefillin Bot...")
        self.app.run_polling()


if __name__ == "__main__":
    bot = TefillinBot()
    bot.run()
