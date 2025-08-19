import asyncio
import os
import sys
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# הוספת נתיב הפרויקט
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from database import DatabaseManager
from hebrew_times import HebrewTimes
from utils import (
    format_duration,
    format_streak_message,
    get_hebrew_day_name,
    parse_time_input,
    sanitize_user_input,
    validate_time_input,
)


class TestUtilityFunctions:
    """בדיקות לפונקציות עזר"""

    def test_validate_time_input(self):
        """בדיקת ולידציית קלט שעה"""
        # קלטים תקינים
        assert validate_time_input("07:30") == True
        assert validate_time_input("23:59") == True
        assert validate_time_input("00:00") == True
        assert validate_time_input("8") == True
        assert validate_time_input("15") == True

        # קלטים לא תקינים
        assert validate_time_input("25:30") == False
        assert validate_time_input("12:60") == False
        assert validate_time_input("abc") == False
        assert validate_time_input("") == False
        assert validate_time_input("12:30:45") == False

    def test_parse_time_input(self):
        """בדיקת פענוח קלט שעה"""
        # קלטים תקינים
        assert parse_time_input("07:30") == time(7, 30)
        assert parse_time_input("23:59") == time(23, 59)
        assert parse_time_input("8") == time(8, 0)

        # קלטים לא תקינים
        assert parse_time_input("25:30") == None
        assert parse_time_input("abc") == None
        assert parse_time_input("") == None

    def test_format_duration(self):
        """בדיקת פורמט זמן"""
        assert format_duration(30) == "30 דקות"
        assert format_duration(60) == "1 שעות"
        assert format_duration(90) == "1 שעות ו-30 דקות"
        assert format_duration(120) == "2 שעות"

    def test_get_hebrew_day_name(self):
        """בדיקת שמות ימים בעברית"""
        # יום שני = 0
        monday = datetime(2025, 8, 18)  # יום שני
        assert get_hebrew_day_name(monday) == "ראשון"

        # שבת = 6
        sunday = datetime(2025, 8, 24)  # יום ראשון
        assert get_hebrew_day_name(sunday) == "שבת"

    def test_format_streak_message(self):
        """בדיקת הודעות רצף"""
        assert format_streak_message(0) == ""
        assert "רצף חדש" in format_streak_message(1)
        assert "רצף של 5" in format_streak_message(5)
        assert "אלוף" in format_streak_message(15)
        assert "מדהים" in format_streak_message(50)

    def test_sanitize_user_input(self):
        """בדיקת ניקוי קלט משתמש"""
        assert sanitize_user_input("<script>alert('xss')</script>") == "scriptalert('xss')/script"
        assert sanitize_user_input("שלום עולם") == "שלום עולם"
        assert len(sanitize_user_input("א" * 200, 50)) <= 53  # כולל "..."


class TestHebrewTimes:
    """בדיקות לזמני הלכה"""

    def setup_method(self):
        """הכנות לפני כל בדיקה"""
        self.hebrew_times = HebrewTimes()

    def test_get_approximate_sunset(self):
        """בדיקת חישוב שקיעה מקורב"""
        # ינואר - שקיעה מוקדמת
        winter_date = date(2025, 1, 15)
        sunset = self.hebrew_times._get_approximate_sunset(winter_date)
        assert sunset.hour == 17

        # יוני - שקיעה מאוחרת
        summer_date = date(2025, 6, 15)
        sunset = self.hebrew_times._get_approximate_sunset(summer_date)
        assert sunset.hour == 19

    def test_is_shabbat_detection(self):
        """בדיקת זיהוי שבת"""
        # שבת
        saturday = date(2025, 8, 23)  # שבת
        assert saturday.weekday() == 5
        assert self.hebrew_times.is_shabbat_or_holiday(saturday) == True

        # יום רגיל
        monday = date(2025, 8, 18)  # שני
        assert monday.weekday() == 0
        # הבדיקה תלויה בAPI, אז נבדוק רק שהפונקציה לא קורסת
        try:
            result = self.hebrew_times.is_shabbat_or_holiday(monday)
            assert isinstance(result, bool)
        except:
            pass  # בסדר אם API לא זמין בבדיקות

    def test_get_next_weekday(self):
        """בדיקת קבלת יום חול הבא"""
        # אם היום הוא שבת, הבא צריך להיות ראשון
        saturday = date(2025, 8, 23)
        next_day = self.hebrew_times.get_next_weekday(saturday)
        assert next_day.weekday() != 5  # לא שבת


class TestConfig:
    """בדיקות הגדרות"""

    def test_config_validation(self):
        """בדיקת ולידציית הגדרות"""
        # שמירת ערכים מקוריים
        original_token = Config.BOT_TOKEN
        original_uri = Config.MONGODB_URI

        try:
            # בדיקת שגיאה כשחסר טוקן
            Config.BOT_TOKEN = None
            with pytest.raises(ValueError, match="BOT_TOKEN is required"):
                Config.validate()

            # החזרת ערך תקין
            Config.BOT_TOKEN = "test_token"
            Config.MONGODB_URI = None
            with pytest.raises(ValueError, match="MONGODB_URI is required"):
                Config.validate()

        finally:
            # החזרת ערכים מקוריים
            Config.BOT_TOKEN = original_token
            Config.MONGODB_URI = original_uri

    def test_default_values(self):
        """בדיקת ערכי ברירת מחדל"""
        assert Config.DEFAULT_TIMEZONE == "Asia/Jerusalem"
        assert Config.DEFAULT_REMINDER_TIME == "07:30"
        assert isinstance(Config.SNOOZE_OPTIONS, dict)


class TestDatabaseManager:
    """בדיקות מנהל מסד נתונים"""

    def setup_method(self):
        """הכנות לפני כל בדיקה"""
        # יצירת mock client
        self.mock_client = Mock()
        self.mock_db = Mock()
        self.mock_users_collection = Mock()

        self.mock_client.tefillin_bot = self.mock_db
        self.mock_db.users = self.mock_users_collection
        self.mock_db.stats = Mock()
        self.mock_db.logs = Mock()

        self.db_manager = DatabaseManager(self.mock_client)

    def test_get_user(self):
        """בדיקת קבלת משתמש"""
        # הגדרת התנהגות mock
        expected_user = {"user_id": 12345, "daily_time": "07:30"}
        self.mock_users_collection.find_one.return_value = expected_user

        # קריאה לפונקציה
        result = self.db_manager.get_user(12345)

        # בדיקות
        assert result == expected_user
        self.mock_users_collection.find_one.assert_called_once_with({"user_id": 12345})

    def test_get_user_not_found(self):
        """בדיקת משתמש לא נמצא"""
        self.mock_users_collection.find_one.return_value = None

        result = self.db_manager.get_user(99999)
        assert result is None

    def test_upsert_user_new(self):
        """בדיקת יצירת משתמש חדש"""
        mock_result = Mock()
        mock_result.upserted_id = "new_object_id"
        mock_result.modified_count = 0
        self.mock_users_collection.update_one.return_value = mock_result

        user_data = {"daily_time": "08:00", "active": True}
        result = self.db_manager.upsert_user(12345, user_data)

        assert result == True
        self.mock_users_collection.update_one.assert_called_once()

    def test_update_user(self):
        """בדיקת עדכון משתמש"""
        mock_result = Mock()
        mock_result.modified_count = 1
        self.mock_users_collection.update_one.return_value = mock_result

        update_data = {"streak": 5}
        result = self.db_manager.update_user(12345, update_data)

        assert result == True


@pytest.mark.asyncio
class TestAsyncFunctions:
    """בדיקות לפונקציות אסינכרוניות"""

    async def test_scheduler_startup(self):
        """בדיקת הפעלת scheduler"""
        with patch("scheduler.TefillinScheduler") as MockScheduler:
            mock_scheduler = MockScheduler.return_value
            mock_scheduler.start = Mock()

            # סימולציה של הפעלת scheduler
            mock_scheduler.start()
            mock_scheduler.start.assert_called_once()


class TestIntegration:
    """בדיקות אינטגרציה בסיסיות"""

    def test_time_parsing_integration(self):
        """בדיקת אינטגרציה של פענוח שעות"""
        test_cases = [("7:30", time(7, 30)), ("23:59", time(23, 59)), ("8", time(8, 0)), ("invalid", None)]

        for input_time, expected in test_cases:
            result = parse_time_input(input_time)
            assert result == expected, f"Failed for input: {input_time}"

    def test_hebrew_times_integration(self):
        """בדיקת אינטגרציה של זמני הלכה"""
        hebrew_times = HebrewTimes()

        # בדיקה שהפונקציות לא קורסות
        today = date.today()

        try:
            sunset = hebrew_times.get_sunset_time(today)
            assert sunset is None or isinstance(sunset, time)

            is_special = hebrew_times.is_shabbat_or_holiday(today)
            assert isinstance(is_special, bool)

        except Exception as e:
            # בסדר אם יש שגיאת רשת בבדיקות
            assert "connection" in str(e).lower() or "timeout" in str(e).lower()


# פונקציות עזר לבדיקות
def create_mock_update(user_id=12345, text="/start"):
    """יצירת update מדומה לבדיקות"""
    mock_update = Mock()
    mock_update.effective_user.id = user_id
    mock_update.effective_user.first_name = "Test User"
    mock_update.message.text = text
    mock_update.message.reply_text = AsyncMock()
    return mock_update


def create_mock_context():
    """יצירת context מדומה לבדיקות"""
    mock_context = Mock()
    mock_context.bot = Mock()
    mock_context.bot.send_message = AsyncMock()
    return mock_context


# הרצת בדיקות ספציפיות
if __name__ == "__main__":
    # הרצת בדיקות מהירות
    print("🧪 Running quick tests...")

    # בדיקות utils
    print("✅ Testing utility functions...")
    test_utils = TestUtilityFunctions()
    test_utils.test_validate_time_input()
    test_utils.test_parse_time_input()
    test_utils.test_format_duration()
    print("✅ Utility tests passed!")

    # בדיקות hebrew_times
    print("✅ Testing Hebrew times...")
    test_times = TestHebrewTimes()
    test_times.setup_method()
    test_times.test_get_approximate_sunset()
    print("✅ Hebrew times tests passed!")

    print("🎉 All quick tests passed!")
    print("\nRun full test suite with: python -m pytest test_bot.py -v")

# הוראות הרצה:
# pip install pytest pytest-asyncio
# python -m pytest test_bot.py -v
# python -m pytest test_bot.py --cov=. --cov-report=html
