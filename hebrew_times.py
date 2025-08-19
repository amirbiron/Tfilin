import logging
import requests
from datetime import datetime, time, date, timedelta
from typing import Optional, Dict, List
from pytz import timezone
import json

logger = logging.getLogger(__name__)


class HebrewTimes:
    def __init__(self):
        self.timezone = timezone("Asia/Jerusalem")
        self.cache = {}  # קאש לזמני שקיעה
        self.holidays_cache = {}  # קאש לחגים

    def get_sunset_time(self, date_obj: date) -> Optional[time]:
        """קבלת זמן שקיעה לתאריך נתון"""
        date_str = date_obj.isoformat()

        # בדיקה בקאש
        if date_str in self.cache:
            return self.cache[date_str].get("sunset")

        # קריאה ל-API
        try:
            # שימוש ב-Hebcal API לזמני הלכה
            url = "https://www.hebcal.com/zmanim"
            params = {"cfg": "json", "geonameid": "281184", "date": date_str}  # ירושלים

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # חילוץ זמן שקיעה
            sunset_str = data.get("times", {}).get("sunset")
            if sunset_str:
                sunset_time = datetime.fromisoformat(sunset_str.replace("Z", "+00:00"))
                sunset_local = sunset_time.astimezone(self.timezone).time()

                # שמירה בקאש
                self.cache[date_str] = {"sunset": sunset_local, "retrieved_at": datetime.now()}

                return sunset_local

        except Exception as e:
            logger.error(f"Failed to get sunset time for {date_str}: {e}")

        # ברירת מחדל אם API לא עובד
        return self._get_approximate_sunset(date_obj)

    def _get_approximate_sunset(self, date_obj: date) -> time:
        """חישוב מקורב של זמן שקיעה"""
        # זמני שקיעה מקורבים לישראל לפי חודשים
        month_sunsets = {
            1: time(17, 0),  # ינואר
            2: time(17, 30),  # פברואר
            3: time(18, 0),  # מרץ
            4: time(18, 30),  # אפריל
            5: time(19, 0),  # מאי
            6: time(19, 30),  # יוני
            7: time(19, 30),  # יולי
            8: time(19, 0),  # אוגוסט
            9: time(18, 30),  # ספטמבר
            10: time(18, 0),  # אוקטובר
            11: time(17, 30),  # נובמבר
            12: time(17, 0),  # דצמבר
        }

        return month_sunsets.get(date_obj.month, time(18, 0))

    def is_shabbat_or_holiday(self, date_obj: date) -> bool:
        """בדיקה אם התאריך הוא שבת או חג"""
        # בדיקת שבת
        if date_obj.weekday() == 5:  # שבת = 5 (ימי השבוע: 0=ראשון, 5=שבת)
            return True

        # בדיקת חגים
        return self.is_jewish_holiday(date_obj)

    def is_jewish_holiday(self, date_obj: date) -> bool:
        """בדיקה אם התאריך הוא חג יהודי"""
        date_str = date_obj.isoformat()

        # בדיקה בקאש
        if date_str in self.holidays_cache:
            return self.holidays_cache[date_str]

        try:
            # שימוש ב-Hebcal API לחגים
            year = date_obj.year
            url = f"https://www.hebcal.com/hebcal"
            params = {
                "v": "1",
                "cfg": "json",
                "maj": "on",  # חגים מרכזיים
                "min": "on",  # חגים קטנים
                "mod": "on",  # חגים מודרניים
                "nx": "on",  # ראש השנה וכיפור
                "year": year,
                "month": "x",  # כל השנה
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # בדיקה אם התאריך הוא חג
            for event in data.get("items", []):
                if event.get("date") == date_str:
                    category = event.get("category", "")
                    # בדיקה לחגים שבהם לא נוהגים להניח תפילין
                    if category in ["major", "modern", "roshchodesh"]:
                        self.holidays_cache[date_str] = True
                        return True

            # אם לא נמצא חג
            self.holidays_cache[date_str] = False
            return False

        except Exception as e:
            logger.error(f"Failed to check holiday for {date_str}: {e}")
            return False

    def get_next_weekday(self, current_date: date) -> date:
        """קבלת התאריך הבא שאינו שבת או חג"""
        next_date = current_date + timedelta(days=1)
        max_attempts = 10  # מניעת לולאה אינסופית

        for _ in range(max_attempts):
            if not self.is_shabbat_or_holiday(next_date):
                return next_date
            next_date += timedelta(days=1)

        return next_date  # ברירת מחדל

    def update_daily_cache(self, date_obj: date):
        """עדכון יומי של הקאש"""
        # עדכון זמני שקיעה לשבוע הקרוב
        for i in range(7):
            future_date = date_obj + timedelta(days=i)
            self.get_sunset_time(future_date)

        # ניקוי קאש ישן (יותר משבוע)
        cutoff_date = date_obj - timedelta(days=7)
        self.cache = {k: v for k, v in self.cache.items() if datetime.fromisoformat(k).date() >= cutoff_date}

        # ניקוי קאש חגים ישן
        self.holidays_cache = {k: v for k, v in self.holidays_cache.items() if datetime.fromisoformat(k).date() >= cutoff_date}

        logger.info(f"Updated cache for {date_obj}, cache size: {len(self.cache)}")

    def get_weekly_schedule(self, start_date: date) -> List[Dict]:
        """קבלת לוח שבועי עם זמני שקיעה ומידע על שבת/חגים"""
        schedule = []

        for i in range(7):
            current_date = start_date + timedelta(days=i)
            sunset_time = self.get_sunset_time(current_date)
            is_special = self.is_shabbat_or_holiday(current_date)

            day_info = {
                "date": current_date.isoformat(),
                "day_name": self._get_hebrew_day_name(current_date.weekday()),
                "sunset": sunset_time.strftime("%H:%M") if sunset_time else None,
                "is_shabbat_or_holiday": is_special,
                "send_reminders": not is_special,
            }

            schedule.append(day_info)

        return schedule

    def _get_hebrew_day_name(self, weekday: int) -> str:
        """קבלת שם היום בעברית"""
        days = {0: "ראשון", 1: "שני", 2: "שלישי", 3: "רביעי", 4: "חמישי", 5: "שישי", 6: "שבת"}
        return days.get(weekday, "לא ידוע")

    def get_time_until_sunset(self, current_time: datetime) -> Optional[timedelta]:
        """חישוב זמן עד השקיעה"""
        today = current_time.date()
        sunset_time = self.get_sunset_time(today)

        if not sunset_time:
            return None

        sunset_datetime = datetime.combine(today, sunset_time)
        sunset_datetime = self.timezone.localize(sunset_datetime)

        if current_time < sunset_datetime:
            return sunset_datetime - current_time
        else:
            # אם כבר עברה השקיעה, חזור לשקיעה של מחר
            tomorrow = today + timedelta(days=1)
            tomorrow_sunset = self.get_sunset_time(tomorrow)
            if tomorrow_sunset:
                tomorrow_sunset_dt = datetime.combine(tomorrow, tomorrow_sunset)
                tomorrow_sunset_dt = self.timezone.localize(tomorrow_sunset_dt)
                return tomorrow_sunset_dt - current_time

        return None
