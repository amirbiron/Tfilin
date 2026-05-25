import asyncio
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from io import BytesIO

from pymongo import MongoClient
from telegram import (
    BotCommand,
    BotCommandScopeChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.error import Conflict
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from activity_reporter import create_reporter
from config import Config
from database import DatabaseManager
from handlers import TefillinHandlers
from hebrew_times import HebrewTimes
from scheduler import TefillinScheduler
from utils import get_user_display_name, validate_time_input

# הגדרת לוגים
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
)
logger = logging.getLogger(__name__)

reporter = create_reporter(
    mongodb_uri="mongodb+srv://mumin:M43M2TFgLfGvhBwY@muminai.tm6x81b.mongodb.net/?retryWrites=true&w=majority&appName=muminAI",
    service_id="srv-d2i9hfm3jp1c7397v9jg",
    service_name="Tfilin",
)


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
        # אפשרות לעקוף נעילה כדי לשחזר במהירות תפקוד
        # הוסף ב-Render: DISABLE_LEADER_LOCK=1 כדי לנטרל זמנית
        self.leader_lock_enabled = os.getenv("DISABLE_LEADER_LOCK", "0").lower() not in ("1", "true", "yes")
        self._lock_refresh_task = None

        # יצירת אפליקציית בוט
        self.app = Application.builder().token(Config.BOT_TOKEN).build()
        # חיבור פעולות אתחול/סגירה כך שיפעלו גם כאשר מפעילים run_polling ישירות
        self.app.post_init = self.startup
        self.app.post_shutdown = self.shutdown

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
        # פקודות
        self.app.add_handler(CommandHandler("settings", self.settings_command))
        self.app.add_handler(CommandHandler("stats", lambda u, c: self.stats_command(u, c)))
        self.app.add_handler(CommandHandler("help", lambda u, c: self.help_command(u, c)))
        self.app.add_handler(CommandHandler("skip", lambda u, c: self.skip_today_command(u, c)))
        self.app.add_handler(CommandHandler("usage", self.usage_command))

        # Conversation handler לזמן מותאם אישית
        self.app.add_handler(self.handlers.get_conversation_handler())

        # Callback handlers
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

        # Message handlers
        self.app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, self.handle_web_app_data))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

        # Error handler
        self.app.add_error_handler(self.error_handler)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת /start - הרשמה ראשונית"""
        reporter.report_activity(update.effective_user.id)
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
        reporter.report_activity(update.effective_user.id)
        user_id = update.effective_user.id
        user = self.db_manager.get_user(user_id)
        await self.show_main_menu(update.message, user)

    async def show_main_menu(self, message, user, greeting: str | None = None):
        """הצגת תפריט ראשי עם כפתורי פעולה בתחתית ההקלדה (ReplyKeyboard)"""
        base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:10000"
        camera_url = f"{base_url.rstrip('/')}/webapp/camera"

        # ReplyKeyboard בתחתית שורת ההקלדה
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

        # InlineKeyboard עם פעולות (WebApp מצלמה בתוך טלגרם)
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

        header = ""
        if greeting is not None:
            current_time = (user or {}).get("daily_time", "07:30")
            streak = (user or {}).get("streak", 0)
            header = f"שלום שוב {greeting}! 👋\n\n" f"🕐 שעה יומית: {current_time}\n" f"🔥 רצף: {streak} ימים\n\n"

        # ודא שהטקסט לא ריק כדי לא לשבור שליחת הודעה
        text_for_reply_keyboard = header if header.strip() else "תפריט ראשי"
        await message.reply_text(text_for_reply_keyboard, reply_markup=reply_keyboard)
        await message.reply_text("תפריט פעולות:", reply_markup=inline_keyboard)

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
        reporter.report_activity(update.effective_user.id)
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id

        try:
            # תשובה מהירה כדי למנוע "טוען..." אינסופי בכפתור
            await query.answer()
            if data.startswith("time_"):
                await self.handle_time_selection(query, user_id, data)
            elif data == "tefillin_done":
                await self.handle_tefillin_done(query, user_id)
            elif data.startswith("snooze_"):
                await self.handlers.handle_snooze_callback(update, context)
            elif data == "back_to_settings":
                user = self.db_manager.get_user(user_id)
                await self.show_main_settings(query.message, user)
            elif data in ["show_settings", "change_time", "stats", "sunset_settings"]:
                await self.handlers.handle_settings_callback(update, context)
            elif data.startswith("sunset_"):
                await self.handlers.handle_settings_callback(update, context)
            elif data == "skip_today":
                await self.handlers.handle_skip_today(update, context)
            elif data == "show_shema":
                await self.handle_show_shema(query)
            elif data == "take_selfie":
                await self.handle_take_selfie(query)
            elif data == "show_help":
                # שליחת טקסט העזרה כמו ב-/help
                dummy_update = type(
                    "U",
                    (),
                    {"message": query.message, "effective_user": update.effective_user},
                )()
                await self.help_command(dummy_update, context)
            elif data == "back_to_menu":
                user = self.db_manager.get_user(user_id)
                await self.show_main_menu(query.message, user)
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

        # עדכון לא הורס הגדרות קיימות:
        # אם המשתמש קיים, עדכן רק את השעה; אחרת צור חדש
        existing = self.db_manager.get_user(user_id)
        if existing:
            self.db_manager.update_user(user_id, {"daily_time": time_str})
        else:
            user_data = {
                "user_id": user_id,
                "daily_time": time_str,
                "timezone": Config.DEFAULT_TIMEZONE,
                "created_at": datetime.now(),
                "active": True,
                "streak": 0,
                "sunset_reminder": 0,
                "skip_shabbat": Config.SKIP_SHABBAT,
                "skip_holidays": Config.SKIP_HOLIDAYS,
            }
            self.db_manager.upsert_user(user_id, user_data)

        # כפתורי המשך / תפריט ראשי
        base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:10000"
        camera_url = f"{base_url.rstrip('/')}/webapp/camera"
        keyboard = [
            [InlineKeyboardButton("🌇 הגדרת תזכורת שקיעה", callback_data="sunset_settings")],
            [
                InlineKeyboardButton("קריאת שמע 📖", callback_data="show_shema"),
                InlineKeyboardButton("צלם תמונה 📸", web_app=WebAppInfo(camera_url)),
            ],
            # הוסר כפתור "הגדרות נוספות"
            [InlineKeyboardButton("⬅️ חזור", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            (
                f"מעולה! ✅\n"
                f"תזכורת יומית נקבעה לשעה {time_str}.\n\n"
                f"📅 תקבל תזכורת כל יום (חוץ משבת וחגים)\n"
                f"🔔 אפשר להגדיר תזכורת נוספת לפני שקיעה\n\n"
                f"הבוט מוכן לפעולה! 🚀"
            ),
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
            await query.edit_message_text("כבר סימנת שהנחת תפילין היום! ✅\nהמשך יום מעולה! 🙏")
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
        # רישום שימוש
        self.db_manager.log_user_action(user_id, "tefillin_done")

        # הודעת אישור
        streak_text = ""
        if new_streak > 1:
            if new_streak >= 7:
                streak_text = f"\n🔥 אלוף! רצף של {new_streak} ימים!"
            elif new_streak >= 3:
                streak_text = f"\n🔥 כל הכבוד! רצף של {new_streak} ימים!"
            else:
                streak_text = f"\n🔥 רצף: {new_streak} ימים"

        await query.edit_message_text(f"איזה מלך! ✅🙏\nהמשך יום מעולה!{streak_text}")

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
הִשָּׁמְרוּ לָכֶם פֶּן יִפְתֶּה לְבַבְכֶם וְסַרְתֶּם וַעֲבַדְתֶּם אֱלֹהִים אֲחֵרִים וְהִשְׁתַּחֲוִיתֶם לָהֶם.
וְחָרָה אַף ה' בָּכֶם וְעָצַר אֶת הַשָּׁמַיִם וְלֹא יִהְיֶה מָטָר וְהָאֲדָמָה לֹא תִתֵּן אֶת יְבוּלָהּ, 
וַאֲבַדְתֶּם מְהֵרָה מֵעַל הָאָרֶץ הַטּוֹבָה אֲשֶׁר ה' נֹתֵן לָכֶם.
וְשַׂמְתֶּם אֶת דְּבָרַי אֵלֶּה עַל לְבַבְכֶם וְעַל נַפְשְׁכֶם; 
וּקְשַׁרְתֶּם אֹתָם לְאוֹת עַל יֶדְכֶם וְהָיוּ לְטוֹטָפֹת בֵּין עֵינֵיכֶם.
וְלִמַּדְתֶּם אֹתָם אֶת בְּנֵיכֶם לְדַבֵּר בָּם בְּשִׁבְתְּךָ בְּבֵיתֶךָ וּבְלֶכְתְּךָ בַדֶּרֶךְ וּבְשָׁכְבְּךָ וּבְקוּמֶךָ.
וּכְתַבְתָּם עַל מְזוּזֹת בֵּיתֶךָ וּבִשְׁעָרֶיךָ.
לְמַעַן יִרְבּוּ יְמֵיכֶם וִימֵי בְּנֵיכֶם עַל הָאֲדָמָה אֲשֶׁר נִשְׁבַּע ה' לַאֲבֹתֵיכֶם לָתֵת לָהֶם, 
כִּימֵי הַשָּׁמַיִם עַל הָאָרֶץ.

🙏 יהי רצון שתהיה קריאתך מקובלת לפני הקב"ה"""

        keyboard = [[InlineKeyboardButton("⬅️ חזור", callback_data="back_to_menu")]]
        await query.edit_message_text(
            shema_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def handle_take_selfie(self, query):
        """פתיחת מצלמה באמצעות Web App"""
        base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:10000"
        camera_url = f"{base_url.rstrip('/')}/webapp/camera"

        text = "📸 צילום עם תפילין\n\n" "לחץ על הכפתור כדי לפתוח את המצלמה בתוך Telegram, צלם ושלח אליי."

        keyboard = [
            [InlineKeyboardButton("פתח מצלמה 📷", web_app=WebAppInfo(camera_url))],
            [InlineKeyboardButton("⬅️ חזור", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """מיפוי כפתורי ReplyKeyboard לפעולות"""
        reporter.report_activity(update.effective_user.id)
        text = (update.message.text or "").strip()
        user_id = update.effective_user.id
        user = self.db_manager.get_user(user_id)

        try:
            if text == "הנחתי ✅":
                # עיבוד כמו handle_tefillin_done אך בהודעת טקסט
                today = datetime.now().date().isoformat()
                if user:
                    last_done = user.get("last_done")
                    if last_done == today:
                        await update.message.reply_text("כבר סימנת שהנחת היום ✅")
                        return
                    current_streak = user.get("streak", 0)
                    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
                    new_streak = current_streak + 1 if last_done == yesterday else 1
                    self.db_manager.update_user(
                        user_id,
                        {"streak": new_streak, "last_done": today, "last_done_time": datetime.now().isoformat()},
                    )
                    # רישום שימוש
                    self.db_manager.log_user_action(user_id, "tefillin_done")
                    streak_text = ""
                    if new_streak > 1:
                        if new_streak >= 7:
                            streak_text = f"\n🔥 אלוף! רצף של {new_streak} ימים!"
                        elif new_streak >= 3:
                            streak_text = f"\n🔥 כל הכבוד! רצף של {new_streak} ימים!"
                        else:
                            streak_text = f"\n🔥 רצף: {new_streak} ימים"
                    await update.message.reply_text(f"איזה מלך! ✅🙏\nהמשך יום מעולה!{streak_text}")
                else:
                    await update.message.reply_text("לא נמצאת במערכת. הקש /start להרשמה.")
                return

            if text == "קריאת שמע 📖":
                await self.handle_show_shema(type("Q", (), {"edit_message_text": update.message.reply_text})())
                return

            if text == "צלם תמונה 📸":
                # שלח הודעה עם Inline כפתור WebApp למצלמה
                base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:10000"
                camera_url = f"{base_url.rstrip('/')}/webapp/camera"
                keyboard = InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("פתח מצלמה 📷", web_app=WebAppInfo(camera_url))],
                        [InlineKeyboardButton("⬅️ חזור", callback_data="back_to_menu")],
                    ]
                )
                await update.message.reply_text("פתח את המצלמה מתוך Telegram:", reply_markup=keyboard)
                return

            if text == "🕐 שינוי שעה":
                await self.handlers.show_time_selection(type("Q", (), {"edit_message_text": update.message.reply_text})())
                return

            if text == "🌇 תזכורת שקיעה":
                await self.handlers.show_sunset_settings(
                    type("Q", (), {"edit_message_text": update.message.reply_text})(),
                    user_id,
                )
                return

            if text == "📊 סטטיסטיקות":
                await self.stats_command(update, context)
                return

            if text == "⚙️ הגדרות":
                await self.settings_command(update, context)
                return

            # ברירת מחדל: זיהוי שעה ידנית
            if validate_time_input(text):
                await update.message.reply_text(
                    f"נראה שרצית לקבוע שעה: {text}\n" f"השתמש ב-/settings כדי לשנות את השעה היומית."
                )
            else:
                await update.message.reply_text("שלום! 👋\nהשתמש ב-/menu או ב-/help לעזרה.")
        except Exception as e:
            logger.error(f"Error in text handler: {e}")
            await update.message.reply_text("אירעה שגיאה, נסה שוב.")

    async def handle_web_app_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """קליטת נתונים מ-WebApp (למשל תמונה ממצלמה) ושליחתם לצ'אט."""
        reporter.report_activity(update.effective_user.id)
        try:
            msg = update.effective_message
            web_app_data = getattr(msg, "web_app_data", None)
            if not web_app_data or not web_app_data.data:
                return
            data = json.loads(web_app_data.data)
            if data.get("type") != "photo" or not data.get("dataUrl"):
                return
            data_url = data["dataUrl"]
            header, b64data = data_url.split(",", 1)
            image_bytes = base64.b64decode(b64data)
            bio = BytesIO(image_bytes)
            bio.name = "photo.jpg"
            await msg.reply_photo(photo=bio)
        except Exception as e:
            logger.error(f"Error handling web_app_data: {e}")
            try:
                await update.effective_message.reply_text("שגיאה בעיבוד התמונה שנשלחה מהמצלמה.")
            except Exception:
                pass

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת הגדרות מפורטת"""
        reporter.report_activity(update.effective_user.id)
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
            [InlineKeyboardButton("⬅️ חזור", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        current_time = user.get("daily_time", "לא נקבע")
        streak = user.get("streak", 0)
        sunset_reminder = user.get("sunset_reminder", 0)
        sunset_text = "כיבוי תזכורת" if sunset_reminder == 0 else f"{sunset_reminder} דק' לפני"

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
        reporter.report_activity(update.effective_user.id)
        user_id = update.effective_user.id
        await self.handlers.show_user_stats(type("Query", (), {"edit_message_text": update.message.reply_text})(), user_id)

    async def usage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת אדמין: מי השתמש בשבוע האחרון, באילו שעות, וכמה ימים"""
        reporter.report_activity(update.effective_user.id)
        user_id = update.effective_user.id
        if not Config.is_admin(user_id):
            await update.message.reply_text("פקודה זו למנהלים בלבד")
            return

        # פרמטר אופציונלי: מספר ימים (ברירת מחדל 7)
        days = 7
        try:
            if context.args and len(context.args) > 0:
                days = max(1, min(30, int(context.args[0])))
        except Exception:
            days = 7

        results = self.db_manager.get_usage_last_days(days)

        if not results:
            summary = self.db_manager.get_usage_summary(days)
            total_active = summary.get("total_active_users", 0)
            users_done = summary.get("users_marked_done", 0)
            total_marks = summary.get("total_marks", 0)
            await update.message.reply_text(
                "\n".join(
                    [
                        f"📊 סיכום שימוש {days} ימים אחרונים:",
                        f"משתמשים פעילים: {total_active}",
                        f"משתמשים שסימנו הנחה לפחות פעם אחת: {users_done}",
                        f"מספר סימונים כולל (tefillin_done): {total_marks}",
                        "(אין פירוט לפי משתמשים כי לא נמצאו לוגים מתאימים)",
                    ]
                )
            )
            return

        total_users = len(results)
        header = f'📊 שימוש ב-{days} ימים אחרונים\nסה"כ משתמשים פעילים (עם לוגים): {total_users}\n\n'

        # בניית שורות תצוגה; הגבלת שעות לתצוגה עד 5 ראשונות
        lines = []
        for idx, r in enumerate(results, start=1):
            uid = r.get("user_id")
            days_count = r.get("days_count", 0)
            hours = r.get("hours", [])
            # ייחוד והגבלה בוצעו כבר בשכבת DB, אך נגן גם כאן למקרה חריג
            unique_hours = sorted({h for h in hours})
            hours_preview = ", ".join(unique_hours[:5]) + ("…" if len(unique_hours) > 5 else "")
            lines.append(f"{idx}. ID {uid} — {days_count} ימים — שעות: {hours_preview}")

        # טלגרם מגביל הודעה ~4096 תווים; נחלק במידת הצורך
        text = header + "\n".join(lines)
        if len(text) <= 4000:
            await update.message.reply_text(text)
        else:
            # שליחה בקבצים
            chunk = ""
            for line in [header] + lines:
                if len(chunk) + len(line) + 1 > 3900:
                    await update.message.reply_text(chunk)
                    chunk = ""
                chunk += ("\n" if chunk else "") + line
            if chunk:
                await update.message.reply_text(chunk)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת עזרה"""
        reporter.report_activity(update.effective_user.id)
        help_text = (
            f"🤖 בוט תזכורות תפילין\n\n"
            f"📋 פקודות זמינות:\n"
            f"/start - הרשמה או חזרה לבוט\n"
            f"/menu - תפריט ראשי\n"
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
        reporter.report_activity(update.effective_user.id)
        user_id = update.effective_user.id
        today = datetime.now().date().isoformat()

        self.db_manager.update_user(user_id, {"skipped_date": today})

        await update.message.reply_text("✅ דילגתי על התזכורת להיום.\nנתראה מחר עם תזכורת חדשה! 👋")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בשגיאות"""
        if isinstance(getattr(context, "error", None), Conflict):
            logger.warning("Conflict detected (409) – another polling process may be active. Ignoring temporarily.")
            return
        logger.error(f"Exception while handling an update: {context.error}")
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text("מצטער, אירעה שגיאה. אנא נסה שוב מאוחר יותר.")
            except Exception:
                pass

    async def startup(self, application):
        """פעולות אתחול"""
        logger.info("Starting Tefillin Bot...")

        # ניסיון קבלת leader lock לפני תחילת polling (אם לא מנוטרל)
        if self.leader_lock_enabled:
            got_lock = self.db_manager.acquire_leader_lock(self.leader_owner_id, ttl_seconds=self.lock_ttl_seconds)
            if not got_lock:
                logger.warning("Leader lock is held by another instance. Standing by without polling.")
                raise RuntimeError("Not leader - another instance is running")
        else:
            logger.warning("Leader lock disabled via env. Starting without distributed lock (temporary recovery mode).")

        # בדיקת חיבור למסד נתונים
        try:
            self.db_client.admin.command("ping")
            logger.info("Database connection successful")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

        # התחלת הסקדיולר
        self.scheduler.start()

        # הפעלת משימת רענון לוק כדי לשמור בעלות (רק אם נעילה פעילה)
        if self.leader_lock_enabled:
            self._lock_refresh_task = asyncio.create_task(self._refresh_leader_lock_task())

        # עדכון זמני שקיעה
        await self.scheduler.update_daily_times()

        # הגדרת תפריט פקודות ייעודי למנהלים בלבד (רק /usage) בצ'אט הפרטי שלהם
        try:
            admin_ids = getattr(Config, "ADMIN_IDS", []) or []
            if admin_ids:
                commands = [BotCommand("usage", "דוח שימוש אחרון")]
                for admin_id in admin_ids:
                    try:
                        await self.app.bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=admin_id))
                        logger.info(f"Admin commands set for chat {admin_id}")
                    except Exception as e:
                        logger.warning(f"Failed to set admin commands for chat {admin_id}: {e}")
        except Exception as e:
            logger.warning(f"Skipping admin commands configuration: {e}")

        logger.info("Bot startup completed successfully")

    async def shutdown(self, application):
        """פעולות סגירה"""
        logger.info("Shutting down Tefillin Bot...")

        # עצירת הסקדיולר
        try:
            if hasattr(self, "scheduler") and self.scheduler and self.scheduler.is_running():
                self.scheduler.stop()
        except Exception as e:
            logger.warning(f"Scheduler stop skipped: {e}")

        # עצירת משימת רענון הלוק
        try:
            if self._lock_refresh_task:
                self._lock_refresh_task.cancel()
        except Exception:
            pass

        # שחרור ה-leader lock (רק אם נעילה פעילה)
        if self.leader_lock_enabled:
            try:
                self.db_manager.release_leader_lock(self.leader_owner_id)
            except Exception:
                pass

        # סגירת חיבור למסד נתונים
        self.db_client.close()

        logger.info("Bot shutdown completed")

    async def _refresh_leader_lock_task(self):
        """משימה שומרת-חיים לרענון ה-leader lock באופן מחזורי"""
        # אם נעילה מנוטרלת אין מה לרענן
        if not self.leader_lock_enabled:
            return
        try:
            while True:
                await asyncio.sleep(max(5, self.lock_ttl_seconds // 2))
                ok = self.db_manager.refresh_leader_lock(self.leader_owner_id, ttl_seconds=self.lock_ttl_seconds)
                if not ok:
                    logger.error("Lost leader lock. Stopping application to avoid duplicate polling.")
                    await self.app.stop()
                    break
        except asyncio.CancelledError:
            return
