import logging
from datetime import datetime, time, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from pymongo import MongoClient
from telegram.ext import Application
from config import Config
from hebrew_times import HebrewTimes

logger = logging.getLogger(__name__)


class TefillinScheduler:
    def __init__(self, bot_app: Application, db_client: MongoClient):
        self.bot_app = bot_app
        self.db = db_client.tefillin_bot
        self.users_collection = self.db.users
        self.scheduler = AsyncIOScheduler(timezone=timezone(Config.DEFAULT_TIMEZONE))
        self.hebrew_times = HebrewTimes()

    def start(self):
        """התחלת הסקדיולר"""
        # הפעלת בדיקת תזכורות יומיות כל דקה
        self.scheduler.add_job(self.check_daily_reminders, CronTrigger(minute="*"), id="daily_check", replace_existing=True)

        # הפעלת בדיקת תזכורות שקיעה כל דקה
        self.scheduler.add_job(self.check_sunset_reminders, CronTrigger(minute="*"), id="sunset_check", replace_existing=True)

        # עדכון זמני שקיעה יומי ב-00:01
        self.scheduler.add_job(
            self.update_daily_times, CronTrigger(hour=0, minute=1), id="daily_update", replace_existing=True
        )

        self.scheduler.start()
        logger.info("Scheduler started successfully")

    def stop(self):
        """עצירת הסקדיולר"""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    async def check_daily_reminders(self):
        """בדיקת תזכורות יומיות"""
        now = datetime.now(timezone(Config.DEFAULT_TIMEZONE))
        current_time = now.time()
        current_date = now.date()

        # בדיקה אם זה שבת או חג
        if self.hebrew_times.is_shabbat_or_holiday(current_date):
            return

        # חיפוש משתמשים שצריכים תזכורת בזמן הנוכחי (±1 דקה)
        users_to_remind = self.users_collection.find(
            {
                "active": True,
                "$expr": {
                    "$and": [
                        {
                            "$eq": [
                                {
                                    "$hour": {
                                        "$dateFromString": {"dateString": {"$concat": ["2000-01-01T", "$daily_time", ":00"]}}
                                    }
                                },
                                current_time.hour,
                            ]
                        },
                        {
                            "$eq": [
                                {
                                    "$minute": {
                                        "$dateFromString": {"dateString": {"$concat": ["2000-01-01T", "$daily_time", ":00"]}}
                                    }
                                },
                                current_time.minute,
                            ]
                        },
                    ]
                },
            }
        )

        for user in users_to_remind:
            # בדיקה שלא נשלחה כבר היום
            last_reminder = user.get("last_reminder_date")
            if last_reminder and last_reminder == current_date.isoformat():
                continue

            await self.send_daily_reminder(user["user_id"])

            # עדכון תאריך תזכורת אחרונה
            self.users_collection.update_one(
                {"user_id": user["user_id"]}, {"$set": {"last_reminder_date": current_date.isoformat()}}
            )

    async def check_sunset_reminders(self):
        """בדיקת תזכורות לפני שקיעה"""
        now = datetime.now(timezone(Config.DEFAULT_TIMEZONE))
        current_date = now.date()

        # בדיקה אם זה שבת או חג
        if self.hebrew_times.is_shabbat_or_holiday(current_date):
            return

        sunset_time = self.hebrew_times.get_sunset_time(current_date)
        if not sunset_time:
            return

        # חיפוש משתמשים שרוצים תזכורת לפני שקיעה
        users_with_sunset = self.users_collection.find({"active": True, "sunset_reminder": {"$exists": True, "$ne": 0}})

        for user in users_with_sunset:
            sunset_offset = user.get("sunset_reminder", 30)  # ברירת מחדל 30 דקות
            reminder_time = datetime.combine(current_date, sunset_time) - timedelta(minutes=sunset_offset)

            # בדיקה אם הגיע הזמן (±2 דקות)
            time_diff = abs((now - reminder_time).total_seconds())
            if time_diff <= 120:  # 2 דקות
                # בדיקה שלא נשלחה כבר היום
                last_sunset_reminder = user.get("last_sunset_reminder_date")
                if last_sunset_reminder and last_sunset_reminder == current_date.isoformat():
                    continue

                # בדיקה שלא הניח כבר היום
                last_done = user.get("last_done")
                if last_done and last_done == current_date.isoformat():
                    continue

                await self.send_sunset_reminder(user["user_id"], sunset_time)

                # עדכון תאריך תזכורת שקיעה אחרונה
                self.users_collection.update_one(
                    {"user_id": user["user_id"]}, {"$set": {"last_sunset_reminder_date": current_date.isoformat()}}
                )

    async def update_daily_times(self):
        """עדכון זמני שקיעה יומי"""
        today = datetime.now(timezone(Config.DEFAULT_TIMEZONE)).date()
        self.hebrew_times.update_daily_cache(today)
        logger.info(f"Updated daily times for {today}")

    async def send_daily_reminder(self, user_id: int):
        """שליחת תזכורת יומית"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [InlineKeyboardButton("הנחתי ✅", callback_data="tefillin_done")],
            [
                InlineKeyboardButton("קריאת שמע 📖", callback_data="show_shema"),
                InlineKeyboardButton("צלם תמונה 📸", callback_data="take_selfie"),
            ],
            [
                InlineKeyboardButton("נודניק 1ש'", callback_data="snooze_60"),
                InlineKeyboardButton("נודניק 3ש'", callback_data="snooze_180"),
            ],
            [
                InlineKeyboardButton("לבחור זמן...", callback_data="snooze_custom"),
                InlineKeyboardButton("עד לפני שקיעה", callback_data="snooze_sunset"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await self.bot_app.bot.send_message(
                chat_id=user_id, text=Config.MESSAGES["daily_reminder"], reply_markup=reply_markup
            )
            logger.info(f"Daily reminder sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send daily reminder to {user_id}: {e}")
            # אם המשתמש חסם את הבוט, סמן כלא פעיל
            if "bot was blocked" in str(e).lower():
                self.users_collection.update_one(
                    {"user_id": user_id}, {"$set": {"active": False, "blocked_date": datetime.now().isoformat()}}
                )

    async def send_sunset_reminder(self, user_id: int, sunset_time: time):
        """שליחת תזכורת לפני שקיעה"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [InlineKeyboardButton("הנחתי ✅", callback_data="tefillin_done")],
            [
                InlineKeyboardButton("קריאת שמע 📖", callback_data="show_shema"),
                InlineKeyboardButton("צלם תמונה 📸", callback_data="take_selfie"),
            ],
            [
                InlineKeyboardButton("דחה 15 דק'", callback_data="snooze_15"),
                InlineKeyboardButton("דחה 30 דק'", callback_data="snooze_30"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        sunset_str = sunset_time.strftime("%H:%M")

        try:
            await self.bot_app.bot.send_message(
                chat_id=user_id,
                text=f"🌇 תזכורת לפני שקיעה\n" f"תזכורת אחרונה להיום להנחת תפילין.\n" f"שקיעה היום ב-{sunset_str}",
                reply_markup=reply_markup,
            )
            logger.info(f"Sunset reminder sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send sunset reminder to {user_id}: {e}")

    async def schedule_snooze_reminder(self, user_id: int, minutes: int):
        """תזמון תזכורת נודניק"""
        run_time = datetime.now(timezone(Config.DEFAULT_TIMEZONE)) + timedelta(minutes=minutes)

        job_id = f"snooze_{user_id}_{int(run_time.timestamp())}"

        self.scheduler.add_job(
            self.send_snooze_reminder, "date", run_date=run_time, args=[user_id], id=job_id, replace_existing=True
        )

        logger.info(f"Scheduled snooze reminder for user {user_id} in {minutes} minutes")

    async def send_snooze_reminder(self, user_id: int):
        """שליחת תזכורת נודניק"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [InlineKeyboardButton("הנחתי ✅", callback_data="tefillin_done")],
            [
                InlineKeyboardButton("קריאת שמע 📖", callback_data="show_shema"),
                InlineKeyboardButton("צלם תמונה 📸", callback_data="take_selfie"),
            ],
            [
                InlineKeyboardButton("עוד נודניק 1ש'", callback_data="snooze_60"),
                InlineKeyboardButton("עוד נודניק 3ש'", callback_data="snooze_180"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await self.bot_app.bot.send_message(
                chat_id=user_id, text="🔔 נודניק – חזרתי להזכיר\n" "הגיע הזמן להניח תפילין.", reply_markup=reply_markup
            )
            logger.info(f"Snooze reminder sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send snooze reminder to {user_id}: {e}")

    def get_active_jobs(self):
        """קבלת רשימת משימות פעילות"""
        return [job.id for job in self.scheduler.get_jobs()]
