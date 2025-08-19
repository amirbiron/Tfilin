import asyncio
import logging
import os
from datetime import datetime, timedelta
import uuid

from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
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
        self.app.add_handler(CommandHandler("menu", self.menu_command))
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
            await self.show_main_menu(update.message, existing_user, greeting=user_name)
            return

        # משתמש חדש - הצגת בחירת שעות
        await self.show_time_selection_for_new_user(update, user_name)

    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת /menu - הצגת תפריט ראשי"""
        user_id = update.effective_user.id
        user = self.db_manager.get_user(user_id)
        await self.show_main_menu(update.message, user)

    async def show_main_menu(self, message, user, greeting: str | None = None):
        """הצגת תפריט ראשי עם כפתורי פעולה"""
        base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:10000"
        camera_url = f"{base_url.rstrip('/')}/camera?chat_id={message.chat_id}"

        keyboard = [
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
        reply_markup = InlineKeyboardMarkup(keyboard)

        header = ""
        if greeting is not None:
            current_time = (user or {}).get("daily_time", "07:30")
            streak = (user or {}).get("streak", 0)
            header = (
                f"שלום שוב {greeting}! 👋\n\n"
                f"🕐 שעה יומית: {current_time}\n"
                f"🔥 רצף: {streak} ימים\n\n"
            )

        await message.reply_text(
            header + "מה תרצה לעשות עכשיו?", reply_markup=reply_markup
        )

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

        # כפתורי המשך / תפריט ראשי
        base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:10000"
        camera_url = f"{base_url.rstrip('/')}/camera?chat_id={query.message.chat_id}"
        keyboard = [
            [InlineKeyboardButton("🌇 הגדרת תזכורת שקיעה", callback_data="sunset_settings")],
            [
                InlineKeyboardButton("קריאת שמע 📖", callback_data="show_shema"),
                InlineKeyboardButton("צלם תמונה 📸", web_app=WebAppInfo(camera_url)),
            ],
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
        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()

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
        """פתיחת מצלמה באמצעות Web App"""
        base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:10000"
        camera_url = f"{base_url.rstrip('/')}/camera?chat_id={query.message.chat_id}"

        text = (
            "📸 צילום עם תפילין\n\n"
            "לחץ על הכפתור כדי לפתוח את המצלמה בתוך Telegram, צלם ושלח אליי."
        )

        keyboard = [
            [InlineKeyboardButton("פתח מצלמה 📷", web_app=WebAppInfo(camera_url))],
            [InlineKeyboardButton("חזרה לתפריט ⬅️", callback_data="tefillin_done")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup)