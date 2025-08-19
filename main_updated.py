import asyncio
import logging
import os
from datetime import datetime
import uuid

from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.error import Conflict

from config import Config
from database import DatabaseManager
from handlers import TefillinHandlers
from hebrew_times import HebrewTimes
from scheduler import TefillinScheduler
from utils import format_time, get_user_display_name, validate_time_input

# הגדרת לוגים
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=getattr(logging, os.getenv("LOG_LEVEL", "INFO"))
)
logger = logging.getLogger(__name__)


class TefillinBot:
    def __init__(self):
        # ולידציית הגדרות
        Config.validate()

        # חיבור למסד נתונים
        self.db_client = MongoClient(Config.MONGODB_URI)
        self.db_manager = DatabaseManager(self.db_client)
        self.db_manager.setup_database()

        # הגדרות נעילה מבוזרת (leader lock)
        self.leader_owner_id = str(uuid.uuid4())
        self.lock_ttl_seconds = int(os.getenv("LEADER_LOCK_TTL", "60"))
        self._lock_refresh_task = None

        # יצירת אפליקציית בוט
        self.app = Application.builder().token(Config.BOT_TOKEN).build()

        # יצירת מודולים
        self.scheduler = TefillinScheduler(self.app, self.db_client)
        self.handlers = TefillinHandlers(self.db_client, self.scheduler)
        self.hebrew_times = HebrewTimes()

        # הגדרת handlers
        self.setup_handlers()

    def setup_handlers(self):
        """הגדרת כל ה-handlers לבוט"""
        # פקודות בסיסיות
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("settings", self.settings_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("skip", self.skip_today_command))

        # Conversation handler לזמן מותאם אישית
        self.app.add_handler(self.handlers.get_conversation_handler())

        # Callback handlers
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

        # Message handlers
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

        # Error handler
        self.app.add_error_handler(self.error_handler)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת /start - הרשמה ראשונית"""
        user_id = update.effective_user.id
        user_name = get_user_display_name(update.effective_user)

        # בדיקה אם המשתמש כבר קיים
        existing_user = self.db_manager.get_user(user_id)

        if existing_user:
            current_time = existing_user.get("daily_time", "07:30")
            streak = existing_user.get("streak", 0)

            # כפתור להגדרות
            keyboard = [[InlineKeyboardButton("⚙️ הגדרות", callback_data="show_settings")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"שלום שוב {user_name}! 👋\n\n"
                f"🕐 השעה הנוכחית שלך: {current_time}\n"
                f"🔥 רצף נוכחי: {streak} ימים\n\n"
                f"הבוט פעיל ושולח תזכורות יומיות.\n"
                f"משתמש ב-/help לעזרה נוספת.",
                reply_markup=reply_markup,
            )
            return

        # משתמש חדש - הצגת בחירת שעות
        await self.show_time_selection_for_new_user(update, user_name)

    async def show_time_selection_for_new_user(self, update, user_name):
        """הצגת בחירת שעה למשתמש חדש"""
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
            [InlineKeyboardButton("⏰ שעה אחרת...", callback_data="time_custom")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # קבלת זמן שקיעה היום להדגמה
        today = datetime.now().date()
        sunset_time = self.hebrew_times.get_sunset_time(today)
        sunset_text = f" (שקיעה היום: {sunset_time.strftime('%H:%M')})" if sunset_time else ""

        await update.message.reply_text(
            f"ברוך הבא {user_name}! 🙏\n\n"
            f"בוט התזכורות לתפילין יעזור לך לא לשכוח.\n"
            f"הבוט לא ישלח תזכורות בשבת ובחגים{sunset_text}\n\n"
            f"🕐 בחר שעה יומית לתזכורת:",
            reply_markup=reply_markup,
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ניתוב כפתורים למטפלים המתאימים"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id

        try:
            if data.startswith("time_"):
                await self.handle_time_selection(query, user_id, data)
            elif data == "tefillin_done":
                await self.handle_tefillin_done(query, user_id)
            elif data.startswith("snooze_"):
                await self.handlers.handle_snooze_callback(update, context)
            elif data in ["show_settings", "change_time", "stats", "sunset_settings", "back_to_settings"]:
                await self.handlers.handle_settings_callback(update, context)
            elif data.startswith("sunset_"):
                await self.handlers.handle_settings_callback(update, context)
            elif data == "skip_today":
                await self.handlers.handle_skip_today(update, context)
            elif data == "show_shema":
                await self.handle_show_shema(query)
            elif data == "take_selfie":
                await self.handle_take_selfie(query)
            else:
                await query.answer("פעולה לא מזוהה")

        except Exception as e:
            logger.error(f"Error in button callback: {e}")
            await query.answer("אירעה שגיאה, נסה שוב")

    async def handle_time_selection(self, query, user_id, data):
        """טיפול בבחירת שעה"""
        if data == "time_custom":
            # זה ייטופל ב-conversation handler
            return

        # חילוץ השעה
        time_str = data.replace("time_", "")

        # שמירת המשתמש
        user_data = {
            "user_id": user_id,
            "daily_time": time_str,
            "timezone": Config.DEFAULT_TIMEZONE,
            "created_at": datetime.now(),
            "active": True,
            "streak": 0,
            "sunset_reminder": 0,  # כבוי כברירת מחדל
            "skip_shabbat": Config.SKIP_SHABBAT,
            "skip_holidays": Config.SKIP_HOLIDAYS,
        }

        self.db_manager.upsert_user(user_id, user_data)

        # כפתורי המשך
        keyboard = [
            [InlineKeyboardButton("🌇 הגדרת תזכורת שקיעה", callback_data="sunset_settings")],
            [InlineKeyboardButton("⚙️ הגדרות נוספות", callback_data="show_settings")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"מעולה! ✅\n"
            f"תזכורת יומית נקבעה לשעה {time_str}.\n\n"
            f"📅 תקבל תזכורת כל יום (חוץ משבת וחגים)\n"
            f"🔔 אפשר להגדיר תזכורת נוספת לפני שקיעה\n\n"
            f"הבוט מוכן לפעולה! 🚀",
            reply_markup=reply_markup,
        )

    async def handle_tefillin_done(self, query, user_id):
        """טיפול בלחיצה על 'הנחתי'"""
        today = datetime.now().date().isoformat()
        user = self.db_manager.get_user(user_id)

        if not user:
            await query.edit_message_text("שגיאה: משתמש לא נמצא")
            return

        # בדיקה שלא סומן כבר היום
        last_done = user.get("last_done")
        if last_done == today:
            await query.edit_message_text("כבר סימנת שהנחת תפילין היום! ✅\n" "המשך יום מעולה! 🙏")
            return

        # עדכון רצף
        current_streak = user.get("streak", 0)
        yesterday = (datetime.now().date() - datetime.timedelta(days=1)).isoformat()

        # בדיקה אם הרצף נמשך (הנחה אתמול או התחלת רצף חדש)
        if last_done == yesterday:
            new_streak = current_streak + 1
        else:
            new_streak = 1  # רצף חדש

        # עדכון במסד נתונים
        update_data = {"streak": new_streak, "last_done": today, "last_done_time": datetime.now().isoformat()}
        self.db_manager.update_user(user_id, update_data)

        # הודעת אישור
        streak_text = ""
        if new_streak > 1:
            if new_streak >= 7:
                streak_text = f"\n🔥 אלוף! רצף של {new_streak} ימים!"
            elif new_streak >= 3:
                streak_text = f"\n🔥 כל הכבוד! רצף של {new_streak} ימים!"
            else:
                streak_text = f"\n🔥 רצף: {new_streak} ימים"

        await query.edit_message_text(f"איזה מלך! ✅🙏\n" f"המשך יום מעולה!{streak_text}")

    async def handle_show_shema(self, query):
        """הצגת נוסח קריאת שמע"""
        shema_text = """📖 קריאת שמע

**פרשה ראשונה:**
שְׁמַע יִשְׂרָאֵל, ה' אֱלֹהֵינוּ, ה' אֶחָד.
בָּרוּךְ שֵׁם כְּבוֹד מַלְכוּתוֹ לְעוֹלָם וָעֶד.

וְאָהַבְתָּ אֵת ה' אֱלֹהֶיךָ בְּכָל לְבָבְךָ וּבְכָל נַפְשְׁךָ וּבְכָל מְאֹדֶךָ.
וְהָיוּ הַדְּבָרִים הָאֵלֶּה אֲשֶׁר אָנֹכִי מְצַוְּךָ הַיּוֹם עַל לְבָבֶךָ.
וְשִׁנַּנְתָּם לְבָנֶיךָ וְדִבַּרְתָּ בָּם בְּשִׁבְתְּךָ בְּבֵיתֶךָ וּבְלֶכְתְּךָ בַדֶּרֶךְ וּבְשָׁכְבְּךָ וּבְקוּמֶךָ.
וּקְשַׁרְתָּם לְאוֹת עַל יָדֶךָ וְהָיוּ לְטֹטָפֹת בֵּין עֵינֶיךָ.
וּכְתַבְתָּם עַל מְזוּזֹת בֵּיתֶךָ וּבִשְׁעָרֶיךָ.

**פרשה שניה:**
וְהָיָה אִם שָׁמֹעַ תִּשְׁמְעוּ אֶל מִצְוֹתַי אֲשֶׁר אָנֹכִי מְצַוֶּה אֶתְכֶם הַיּוֹם
לְאַהֲבָה אֶת ה' אֱלֹהֵיכֶם וּלְעָבְדוֹ בְּכָל לְבַבְכֶם וּבְכָל נַפְשְׁכֶם.
וְנָתַתִּי מְטַר אַרְצְכֶם בְּעִתּוֹ יוֹרֶה וּמַלְקוֹשׁ וְאָסַפְתָּ דְגָנֶךָ וְתִירֹשְׁךָ וְיִצְהָרֶךָ.
וְנָתַתִּי עֵשֶׂב בְּשָׂדְךָ לִבְהֶמְתֶּךָ וְאָכַלְתָּ וְשָׂבָעְתָּ.

(להמשך הקריאה המלאה, ראה סידור תפילה)

🙏 יהי רצון שתהיה קריאתך מקובלת לפני הקב"ה"""

        await query.edit_message_text(shema_text, parse_mode="Markdown")

    async def handle_take_selfie(self, query):
        """הנחיה לצילום תמונה עם תפילין"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        selfie_text = """📸 צילום עם תפילין

**איך לצלם תמונה מושלמת עם תפילין:**

1️⃣ **תאורה** - עמוד ליד חלון או במקום מואר
2️⃣ **זווית** - החזק את הטלפון בגובה העיניים או מעט למעלה
3️⃣ **רקע** - בחר רקע נקי ומסודר
4️⃣ **חיוך** - חייך! אתה מקיים מצווה חשובה 😊

**טיפים נוספים:**
• ודא שהתפילין של ראש ושל יד נראים בתמונה
• התפילין של ראש צריך להיות במרכז המצח
• הרצועות צריכות להיות מסודרות

📱 **לצילום:** 
פתח את אפליקציית המצלמה בטלפון שלך
או שלח לי תמונה ישירות כאן בצ'אט!

שתזכה למצוות! 🙏"""

        keyboard = [[InlineKeyboardButton("חזרה לתפריט ⬅️", callback_data="tefillin_done")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(selfie_text, parse_mode="Markdown", reply_markup=reply_markup)

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת הגדרות מפורטת"""
        user_id = update.effective_user.id
        user = self.db_manager.get_user(user_id)

        if not user:
            await update.message.reply_text("לא נמצאת במערכת. הקש /start להרשמה.")
            return

        await self.show_main_settings(update.message, user)

    async def show_main_settings(self, message, user):
        """הצגת תפריט הגדרות ראשי"""
        keyboard = [
            [
                InlineKeyboardButton("🕐 שינוי שעה", callback_data="change_time"),
                InlineKeyboardButton("🌇 תזכורת שקיעה", callback_data="sunset_settings"),
            ],
            [
                InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats"),
                InlineKeyboardButton("ℹ️ עזרה", callback_data="show_help"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        current_time = user.get("daily_time", "לא נקבע")
        streak = user.get("streak", 0)
        sunset_reminder = user.get("sunset_reminder", 0)
        sunset_text = "כבוי" if sunset_reminder == 0 else f"{sunset_reminder} דק' לפני"

        settings_text = (
            f"⚙️ ההגדרות שלך:\n\n"
            f"🕐 שעה יומית: {current_time}\n"
            f"🌇 תזכורת שקיעה: {sunset_text}\n"
            f"🔥 רצף נוכחי: {streak} ימים\n\n"
            f"מה תרצה לשנות?"
        )

        await message.reply_text(settings_text, reply_markup=reply_markup)

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת סטטיסטיקות מפורטת"""
        user_id = update.effective_user.id
        await self.handlers.show_user_stats(type("Query", (), {"edit_message_text": update.message.reply_text})(), user_id)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת עזרה"""
        help_text = (
            f"🤖 בוט תזכורות תפילין\n\n"
            f"📋 פקודות זמינות:\n"
            f"/start - הרשמה או חזרה לבוט\n"
            f"/settings - הגדרות מתקדמות\n"
            f"/stats - סטטיסטיקות מפורטות\n"
            f"/skip - דלג על התזכורת היום\n"
            f"/help - הצגת הודעה זו\n\n"
            f"🔔 התזכורות:\n"
            f"• תזכורת יומית בשעה שבחרת\n"
            f"• תזכורת לפני שקיעה (אופציונלי)\n"
            f"• לא שולח בשבת ובחגים\n\n"
            f"⭐ תכונות:\n"
            f"• מעקב רצף ימים\n"
            f"• נודניק חכם\n"
            f"• זמני שקיעה מדויקים\n"
            f"• הגדרות אישיות\n\n"
            f"💡 טיפ: אפשר תמיד לשנות הגדרות עם /settings"
        )

        await update.message.reply_text(help_text)

    async def skip_today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת דילוג על היום"""
        user_id = update.effective_user.id
        today = datetime.now().date().isoformat()

        self.db_manager.update_user(user_id, {"skipped_date": today})

        await update.message.reply_text("✅ דילגתי על התזכורת להיום.\n" "נתראה מחר עם תזכורת חדשה! 👋")

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בהודעות טקסט רגילות"""
        # בדיקה אם זה נראה כמו שעה
        text = update.message.text.strip()
        if validate_time_input(text):
            await update.message.reply_text(f"נראה שרצית לקבוע שעה: {text}\n" f"השתמש ב-/settings כדי לשנות את השעה היומית.")
        else:
            await update.message.reply_text(f"שלום! 👋\n" f"השתמש ב-/help לרשימת פקודות זמינות.")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בשגיאות"""
        # טיפול רך ב-409 Conflict
        if isinstance(getattr(context, "error", None), Conflict):
            logger.warning("Conflict detected (409) – another polling process may be active. Ignoring temporarily.")
            return
        logger.error(f"Exception while handling an update: {context.error}")

        # אם יש update, נסה לשלוח הודעת שגיאה למשתמש
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text("מצטער, אירעה שגיאה. אנא נסה שוב מאוחר יותר.")
            except Exception:
                pass

    async def startup(self, application):
        """פעולות אתחול"""
        logger.info("Starting Tefillin Bot...")

        # ניסיון קבלת leader lock לפני תחילת polling
        got_lock = self.db_manager.acquire_leader_lock(self.leader_owner_id, ttl_seconds=self.lock_ttl_seconds)
        if not got_lock:
            logger.warning("Leader lock is held by another instance. Standing by without polling.")
            # זריקה כדי לעצור את run_polling לפני תחילת getUpdates
            raise RuntimeError("Not leader - another instance is running")

        # בדיקת חיבור למסד נתונים
        try:
            self.db_client.admin.command("ping")
            logger.info("Database connection successful")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

        # התחלת הסקדיולר
        self.scheduler.start()

        # הפעלת משימת רענון לוק כדי לשמור בעלות
        self._lock_refresh_task = asyncio.create_task(self._refresh_leader_lock_task())

        # עדכון זמני שקיעה
        await self.scheduler.update_daily_times()

        logger.info("Bot startup completed successfully")

    async def shutdown(self, application):
        """פעולות סגירה"""
        logger.info("Shutting down Tefillin Bot...")

        # עצירת הסקדיולר
        self.scheduler.stop()

        # עצירת משימת רענון הלוק
        try:
            if self._lock_refresh_task:
                self._lock_refresh_task.cancel()
        except Exception:
            pass

        # שחרור ה-leader lock
        try:
            self.db_manager.release_leader_lock(self.leader_owner_id)
        except Exception:
            pass

        # סגירת חיבור למסד נתונים
        self.db_client.close()

        logger.info("Bot shutdown completed")

    def run(self):
        """הרצת הבוט"""
        try:
            # הוספת פעולות startup ו-shutdown
            self.app.post_init = self.startup
            self.app.post_shutdown = self.shutdown

            # הרצת הבוט
            logger.info("Starting bot polling...")
            self.app.run_polling(drop_pending_updates=True)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Critical error: {e}")
            raise

    async def _refresh_leader_lock_task(self):
        """משימה שומרת-חיים לרענון ה-leader lock באופן מחזורי"""
        try:
            while True:
                # רענון חצי מה-TTL כדי לשמור מרווח ביטחון
                await asyncio.sleep(max(5, self.lock_ttl_seconds // 2))
                ok = self.db_manager.refresh_leader_lock(self.leader_owner_id, ttl_seconds=self.lock_ttl_seconds)
                if not ok:
                    logger.error("Lost leader lock. Stopping application to avoid duplicate polling.")
                    # עצירה מסודרת של האפליקציה
                    await self.app.stop()
                    break
        except asyncio.CancelledError:
            # סיום רגיל בעת כיבוי
            return


if __name__ == "__main__":
    bot = TefillinBot()
    bot.run()