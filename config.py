import os
from dotenv import load_dotenv

# טעינת משתני סביבה מקובץ .env (לפיתוח מקומי)
load_dotenv()


class Config:
    # טוקן הבוט מטלגרם
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    # חיבור ל-MongoDB
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/tefillin_bot")

    # הגדרות זמן
    DEFAULT_TIMEZONE = "Asia/Jerusalem"
    DEFAULT_REMINDER_TIME = "07:30"

    # הגדרות תזכורות
    SNOOZE_OPTIONS = {"short": 60, "medium": 180, "long": 360}  # דקות  # 3 שעות  # 6 שעות

    # הגדרות שבת וחגים
    SKIP_SHABBAT = True
    SKIP_HOLIDAYS = True

    # הודעות
    MESSAGES = {
        "welcome": "ברוך הבא! 🙏\nבוט התזכורות לתפילין יעזור לך לא לשכוח.",
        "daily_reminder": "⏰ תזכורת יומית – תפילין\nהגיע הזמן להניח תפילין.\nמה תרצה לעשות?",
        "tefillin_done": "איזה מלך! ✅🙏\nהמשך יום מעולה!",
        "snooze_confirm": "סגור. אזכיר עוד {minutes} דקות ⏰",
    }

    # ולידציה
    @classmethod
    def validate(cls):
        """בדיקה שכל ההגדרות הנדרשות קיימות"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required. Set it in environment variables.")

        if not cls.MONGODB_URI:
            raise ValueError("MONGODB_URI is required. Set it in environment variables.")

        return True
