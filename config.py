import os

from dotenv import load_dotenv

# טעינת משתני סביבה מקובץ .env (לפיתוח מקומי)
load_dotenv()


class Config:
    # טוקן הבוט מטלגרם
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    # חיבור ל-MongoDB
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/tefillin_bot")

    # WebApp base URL (for opening device camera via Telegram WebApp)
    # Example for Render: https://<your-service>.onrender.com
    WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "http://localhost:10000")

    # Feature flag: enable/disable WebApp camera button
    ENABLE_WEBAPP_CAMERA = os.getenv("ENABLE_WEBAPP_CAMERA", "false").lower() == "true"

    # הגדרות זמן
    DEFAULT_TIMEZONE = "Asia/Jerusalem"
    DEFAULT_REMINDER_TIME = "07:30"

    # הגדרות תזכורות
    SNOOZE_OPTIONS = {
        "short": 60,
        "medium": 180,
        "long": 360,
    }  # דקות  # 3 שעות  # 6 שעות

    # הגדרות שבת וחגים
    SKIP_SHABBAT = True
    SKIP_HOLIDAYS = True

    # הודעות
    MESSAGES = {
        "welcome": "ברוך הבא! 🙏\nבוט התזכורות לתפילין יעזור לך לא לשכוח.",
        "daily_reminder": (
            "⏰ תזכורת יומית – תפילין\n"
            "הגיע הזמן להניח תפילין.\n"
            "מה תרצה לעשות?"
        ),
        "tefillin_done": "איזה מלך! ✅🙏\nהמשך יום מעולה!",
        "snooze_confirm": "סגור. אזכיר עוד {minutes} דקות ⏰",
    }

    # מנהלים (לפקודות אדמין כמו /usage)
    # ניתן להגדיר ADMIN_IDS כשרשור מזהים מופרדים בפסיקים/רווחים/נקודה־פסיק
    # או ADMIN_ID יחיד (לנוחות), או OWNER_ID (תואם לסביבות מסוימות)
    _ADMIN_IDS_RAW = (
        os.getenv("ADMIN_IDS", "").replace(";", ",").replace(" ", ",").strip()
    )
    _ADMIN_ID_SINGLE = (os.getenv("ADMIN_ID") or os.getenv("OWNER_ID") or "").strip()

    ADMIN_IDS = []  # type: list[int]
    if _ADMIN_ID_SINGLE:
        try:
            ADMIN_IDS = [int(_ADMIN_ID_SINGLE)]
        except ValueError:
            ADMIN_IDS = []
    elif _ADMIN_IDS_RAW:
        ids: list[int] = []
        for part in [p for p in _ADMIN_IDS_RAW.split(",") if p.strip()]:
            try:
                ids.append(int(part))
            except ValueError:
                continue
        ADMIN_IDS = ids
    else:
        ADMIN_IDS = []

    # ולידציה
    @classmethod
    def validate(cls):
        """בדיקה שכל ההגדרות הנדרשות קיימות"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required. Set it in environment variables.")

        if not cls.MONGODB_URI:
            raise ValueError(
                "MONGODB_URI is required. Set it in environment variables."
            )

        return True

    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        """בדיקה האם המשתמש הוא מנהל"""
        try:
            return int(user_id) in cls.ADMIN_IDS
        except Exception:
            return False
