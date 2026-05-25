import logging
import os
from datetime import datetime, time, timedelta

from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.ext import CallbackQueryHandler, ContextTypes, ConversationHandler

from activity_reporter import create_reporter
from config import Config
from hebrew_times import HebrewTimes

logger = logging.getLogger(__name__)

reporter = create_reporter(
    mongodb_uri="mongodb+srv://mumin:M43M2TFgLfGvhBwY@muminai.tm6x81b.mongodb.net/?retryWrites=true&w=majority&appName=muminAI",
    service_id="srv-d2i9hfm3jp1c7397v9jg",
    service_name="Tfilin",
)

# מצבי שיחה
WAITING_CUSTOM_TIME, WAITING_CUSTOM_SNOOZE = range(2)


class TefillinHandlers:
    def __init__(self, db_client: MongoClient, scheduler):
        self.db = db_client.tefillin_bot
        self.users_collection = self.db.users
        self.scheduler = scheduler
        self.hebrew_times = HebrewTimes()

    async def handle_snooze_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בכפתורי נודניק"""
        reporter.report_activity(update.effective_user.id)
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data

        if data == "snooze_custom":
            await self.handle_custom_snooze_request(query)
        elif data == "snooze_sunset":
            await self.handle_snooze_until_sunset(query, user_id)
        elif data.startswith("snooze_"):
            # נודניק רגיל עם מספר דקות
            minutes = int(data.replace("snooze_", ""))
            await self.handle_regular_snooze(query, user_id, minutes)

    async def handle_regular_snooze(self, query, user_id: int, minutes: int):
        """טיפול בנודניק רגיל"""
        await self.scheduler.schedule_snooze_reminder(user_id, minutes)

        hours = minutes // 60
        remaining_minutes = minutes % 60

        if hours > 0:
            time_text = f"{hours} שעות"
            if remaining_minutes > 0:
                time_text += f" ו-{remaining_minutes} דקות"
        else:
            time_text = f"{minutes} דקות"

        await query.edit_message_text(f"סגור. אזכיר עוד {time_text} ⏰")

    async def handle_custom_snooze_request(self, query):
        """בקשה לנודניק מותאם אישית"""
        keyboard = [
            [
                InlineKeyboardButton("15 דק'", callback_data="snooze_15"),
                InlineKeyboardButton("30 דק'", callback_data="snooze_30"),
            ],
            [
                InlineKeyboardButton("45 דק'", callback_data="snooze_45"),
                InlineKeyboardButton("90 דק'", callback_data="snooze_90"),
            ],
            [InlineKeyboardButton("אחר...", callback_data="snooze_other")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text("בחר דחייה:", reply_markup=reply_markup)

    async def handle_snooze_until_sunset(self, query, user_id: int):
        """נודניק עד לפני שקיעה"""
        today = datetime.now().date()
        sunset_time = self.hebrew_times.get_sunset_time(today)

        if not sunset_time:
            await query.edit_message_text("מצטער, לא הצלחתי לחשב זמן שקיעה היום.\nנסה דחייה רגילה.")
            return

        # חישוב זמן לתזכורת (30 דקות לפני שקיעה)
        sunset_datetime = datetime.combine(today, sunset_time)
        reminder_time = sunset_datetime - timedelta(minutes=30)
        now = datetime.now()

        if reminder_time <= now:
            await query.edit_message_text("השקיעה קרובה מדי.\nבחר דחייה אחרת.")
            return

        minutes_until_reminder = int((reminder_time - now).total_seconds() / 60)
        await self.scheduler.schedule_snooze_reminder(user_id, minutes_until_reminder)

        sunset_str = sunset_time.strftime("%H:%M")
        reminder_str = reminder_time.strftime("%H:%M")

        await query.edit_message_text(f"מעולה! 🌇\nאזכיר ב-{reminder_str} (30 דק' לפני השקיעה ב-{sunset_str})")

    async def handle_settings_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בהגדרות"""
        reporter.report_activity(update.effective_user.id)
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data

        if data == "change_time":
            await self.show_time_selection(query)
        elif data == "stats":
            await self.show_user_stats(query, user_id)
        elif data == "sunset_settings":
            await self.show_sunset_settings(query, user_id)
        elif data.startswith("sunset_"):
            await self.handle_sunset_setting(query, user_id, data)

    async def show_time_selection(self, query):
        """הצגת בחירת שעה"""
        keyboard = [
            [
                InlineKeyboardButton("06:30", callback_data="time_06:30"),
                InlineKeyboardButton("07:00", callback_data="time_07:00"),
            ],
            [
                InlineKeyboardButton("07:30", callback_data="time_07:30"),
                InlineKeyboardButton("08:00", callback_data="time_08:00"),
            ],
            [
                InlineKeyboardButton("08:30", callback_data="time_08:30"),
                InlineKeyboardButton("09:00", callback_data="time_09:00"),
            ],
            [InlineKeyboardButton("שעה אחרת...", callback_data="time_custom")],
            [InlineKeyboardButton("⬅️ חזור", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text("בחר שעה חדשה לתזכורת יומית:", reply_markup=reply_markup)

    async def show_sunset_settings(self, query, user_id: int):
        """הצגת הגדרות תזכורת שקיעה"""
        user = self.users_collection.find_one({"user_id": user_id})
        current_setting = user.get("sunset_reminder", 0)

        keyboard = [
            [InlineKeyboardButton("כיבוי תזכורת", callback_data="sunset_0")],
            [
                InlineKeyboardButton("30 דק' לפני", callback_data="sunset_30"),
                InlineKeyboardButton("45 דק' לפני", callback_data="sunset_45"),
            ],
            [
                InlineKeyboardButton("60 דק' לפני", callback_data="sunset_60"),
                InlineKeyboardButton("90 דק' לפני", callback_data="sunset_90"),
            ],
            [InlineKeyboardButton("⬅️ חזור", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        status_text = "כיבוי תזכורת" if current_setting == 0 else f"{current_setting} דקות לפני שקיעה"

        await query.edit_message_text(
            f"תזכורת לפני שקיעה\nמצב נוכחי: {status_text}\n\nבחר הגדרה חדשה:",
            reply_markup=reply_markup,
        )

    async def handle_sunset_setting(self, query, user_id: int, data: str):
        """עדכון הגדרת תזכורת שקיעה"""
        minutes = int(data.replace("sunset_", ""))

        # עדכון לא הורס נתונים אחרים
        update_data = {"sunset_reminder": minutes}
        self.users_collection.update_one({"user_id": user_id}, {"$set": update_data})

        if minutes == 0:
            text = "תזכורת לפני שקיעה בוטלה ✅"
        else:
            text = f"תזכורת לפני שקיעה עודכנה ל-{minutes} דקות ✅"

        await query.edit_message_text(text)

    async def show_user_stats(self, query, user_id: int):
        """הצגת סטטיסטיקות משתמש"""
        user = self.users_collection.find_one({"user_id": user_id})

        if not user:
            await query.edit_message_text("לא נמצאו נתונים")
            return

        streak = user.get("streak", 0)
        daily_time = user.get("daily_time", "לא נקבע")
        sunset_reminder = user.get("sunset_reminder", 0)
        created_at = user.get("created_at")
        last_done = user.get("last_done")

        # חישוב ימים מההרשמה
        days_since_signup = 0
        if created_at:
            days_since_signup = (datetime.now() - created_at).days

        sunset_text = "כיבוי תזכורת" if sunset_reminder == 0 else f"{sunset_reminder} דק' לפני שקיעה"
        last_done_text = last_done if last_done else "לא נרשם"

        # קבלת זמן שקיעה היום
        today = datetime.now().date()
        sunset_today = self.hebrew_times.get_sunset_time(today)
        sunset_today_text = sunset_today.strftime("%H:%M") if sunset_today else "לא זמין"

        stats_text = (
            f"📊 הסטטיסטיקות שלך:\n\n"
            f"🔥 רצף נוכחי: {streak} ימים\n"
            f"🕐 שעה יומית: {daily_time}\n"
            f"🌇 תזכורת שקיעה: {sunset_text}\n"
            f"📅 תאריך הרשמה: {created_at.strftime('%d/%m/%Y') if created_at else 'לא זמין'}\n"
            f"📈 ימים מההרשמה: {days_since_signup}\n"
            f"✅ הנחה אחרונה: {last_done_text}\n\n"
            f"🌅 שקיעה היום: {sunset_today_text}"
        )

        keyboard = [[InlineKeyboardButton("חזרה להגדרות", callback_data="back_to_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(stats_text, reply_markup=reply_markup)

    async def handle_custom_time_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בקלט שעה מותאמת אישית"""
        reporter.report_activity(update.effective_user.id)
        user_id = update.effective_user.id
        time_text = update.message.text.strip()

        try:
            # ניסיון לפרס את השעה
            if ":" in time_text:
                hour, minute = map(int, time_text.split(":"))
            else:
                hour = int(time_text)
                minute = 0

            # ולידציה
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time")

            time_str = f"{hour:02d}:{minute:02d}"

            # עדכון במסד הנתונים
            self.users_collection.update_one({"user_id": user_id}, {"$set": {"daily_time": time_str}})

            await update.message.reply_text(f"מעולה! ✅\n" f"השעה עודכנה ל-{time_str}")

            return ConversationHandler.END

        except (ValueError, IndexError):
            await update.message.reply_text("פורמט לא תקין. אנא שלח שעה בפורמט HH:MM (למשל: 08:15)")
            return WAITING_CUSTOM_TIME

    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול שיחה"""
        reporter.report_activity(update.effective_user.id)
        await update.message.reply_text("בוטל.")
        return ConversationHandler.END

    async def handle_skip_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """דילוג על היום"""
        reporter.report_activity(update.effective_user.id)
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        today = datetime.now().date().isoformat()

        # סימון שדולג היום
        self.users_collection.update_one({"user_id": user_id}, {"$set": {"skipped_date": today}})

        await query.edit_message_text("הבנתי. לא אזכיר יותר היום.\nנתראה מחר! 👋")

    def get_conversation_handler(self):
        """יצירת ConversationHandler לזמן מותאם אישית"""
        from telegram.ext import CommandHandler, MessageHandler, filters

        return ConversationHandler(
            entry_points=[CallbackQueryHandler(self.handle_custom_time_callback, pattern="time_custom")],
            states={WAITING_CUSTOM_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_custom_time_input)]},
            fallbacks=[
                CommandHandler("cancel", self.cancel_conversation),
                CallbackQueryHandler(self._back_to_menu_from_conversation, pattern="^back_to_menu$"),
            ],
        )

    async def handle_custom_time_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """התחלת תהליך בחירת שעה מותאמת"""
        reporter.report_activity(update.effective_user.id)
        query = update.callback_query
        await query.answer()

        await query.edit_message_text("שלח לי שעה בפורמט HH:MM\nלמשל: 08:15 או 07:45\n\nאו שלח /cancel לביטול")

        return WAITING_CUSTOM_TIME

    async def _back_to_menu_from_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """יציאה מהשיחה וחזרה לתפריט הראשי (מטופל כאן כדי לא לחסום את הכפתור בתוך שיחה)"""
        reporter.report_activity(update.effective_user.id)
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        user = self.users_collection.find_one({"user_id": user_id}) or {}

        # בניית תפריט ראשי כמו ב-show_main_menu
        base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:10000"
        camera_url = f"{base_url.rstrip('/')}/webapp/camera"

        reply_keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton("הנחתי ✅")],
                [KeyboardButton("קריאת שמע 📖"), KeyboardButton("צלם תמונה 📸")],
                [KeyboardButton("🕐 שינוי שעה"), KeyboardButton("🌇 תזכורת שקיעה")],
                [KeyboardButton("📊 סטטיסטיקות"), KeyboardButton("⚙️ הגדרות")],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            selective=False,
        )

        inline_keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("הנחתי ✅", callback_data="tefillin_done")],
                [
                    InlineKeyboardButton("קריאת שמע 📖", callback_data="show_shema"),
                    InlineKeyboardButton("צלם תמונה 📸", web_app=WebAppInfo(camera_url)),
                ],
                [
                    InlineKeyboardButton("🕐 שינוי שעה", callback_data="change_time"),
                    InlineKeyboardButton("🌇 תזכורת שקיעה", callback_data="sunset_settings"),
                ],
                [
                    InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats"),
                    InlineKeyboardButton("⚙️ הגדרות", callback_data="show_settings"),
                ],
            ]
        )

        current_time = user.get("daily_time", "07:30")
        streak = user.get("streak", 0)
        header = f"🕐 שעה יומית: {current_time}\n🔥 רצף: {streak} ימים\n\n"
        text_for_reply_keyboard = header if header.strip() else "תפריט ראשי"

        await query.message.reply_text(text_for_reply_keyboard, reply_markup=reply_keyboard)
        await query.message.reply_text("תפריט פעולות:", reply_markup=inline_keyboard)

        return ConversationHandler.END
