import re
import logging
from datetime import datetime, time, timedelta
from typing import Optional, Union, Dict, List
from telegram import User

logger = logging.getLogger(__name__)

def format_time(time_obj: Union[time, str]) -> str:
    """פורמט זמן לתצוגה ידידותית"""
    if isinstance(time_obj, str):
        return time_obj
    elif isinstance(time_obj, time):
        return time_obj.strftime("%H:%M")
    return "לא זמין"

def validate_time_input(time_string: str) -> bool:
    """ולידציה של קלט שעה"""
    if not time_string:
        return False
    
    # פטרן לזיהוי שעה (HH:MM או HH או H:MM)
    time_patterns = [
        r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$',  # HH:MM
        r'^([01]?[0-9]|2[0-3])$',               # HH
        r'^([0-9]):([0-5][0-9])$'               # H:MM
    ]
    
    for pattern in time_patterns:
        if re.match(pattern, time_string.strip()):
            return True
    
    return False

def parse_time_input(time_string: str) -> Optional[time]:
    """המרת קלט שעה לאובייקט time"""
    if not validate_time_input(time_string):
        return None
    
    time_string = time_string.strip()
    
    try:
        if ':' in time_string:
            hour, minute = map(int, time_string.split(':'))
        else:
            hour = int(time_string)
            minute = 0
        
        # ולידציה של הערכים
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)
    except (ValueError, IndexError):
        pass
    
    return None

def get_user_display_name(user: User) -> str:
    """קבלת שם משתמש לתצוגה"""
    if user.first_name:
        return user.first_name
    elif user.username:
        return user.username
    else:
        return f"משתמש {user.id}"

def format_duration(minutes: int) -> str:
    """פורמט זמן במינוטים לתצוגה נוחה"""
    if minutes < 60:
        return f"{minutes} דקות"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if remaining_minutes == 0:
        return f"{hours} שעות"
    else:
        return f"{hours} שעות ו-{remaining_minutes} דקות"

def get_hebrew_day_name(date_obj: datetime) -> str:
    """קבלת שם יום בעברית"""
    days = {
        0: "ראשון",   # Monday
        1: "שני",     # Tuesday  
        2: "שלישי",   # Wednesday
        3: "רביעי",   # Thursday
        4: "חמישי",   # Friday
        5: "שישי",    # Saturday
        6: "שבת"      # Sunday
    }
    return days.get(date_obj.weekday(), "לא ידוע")

def get_greeting_by_time() -> str:
    """קבלת ברכה לפי שעה"""
    current_hour = datetime.now().hour
    
    if 5 <= current_hour < 12:
        return "בוקר טוב"
    elif 12 <= current_hour < 17:
        return "אחר הצהריים טובים"
    elif 17 <= current_hour < 21:
        return "ערב טוב"
    else:
        return "לילה טוב"

def format_streak_message(streak: int) -> str:
    """פורמט הודעת רצף ימים"""
    if streak == 0:
        return ""
    elif streak == 1:
        return "התחלת רצף חדש! 🌟"
    elif streak < 7:
        return f"רצף של {streak} ימים! 🔥"
    elif streak < 30:
        return f"אלוף! רצף של {streak} ימים! 🏆"
    elif streak < 100:
        return f"מדהים! רצף של {streak} ימים! 🚀"
    else:
        return f"אגדה! רצף של {streak} ימים! 👑"

def is_valid_phone_number(phone: str) -> bool:
    """בדיקת תקינות מספר טלפון ישראלי"""
    if not phone:
        return False
    
    # הסרת רווחים ומקפים
    clean_phone = re.sub(r'[\s-]', '', phone)
    
    # פטרנים למספרי טלפון ישראליים
    patterns = [
        r'^972[1-9]\d{8}$',     # +972 ואז 9 ספרות
        r'^0[1-9]\d{8}$',       # 0 ואז 9 ספרות
        r'^[1-9]\d{8}$'         # 9 ספרות ישירות
    ]
    
    return any(re.match(pattern, clean_phone) for pattern in patterns)

def sanitize_user_input(text: str, max_length: int = 100) -> str:
    """ניקוי קלט משתמש"""
    if not text:
        return ""
    
    # הסרת תווים מיוחדים מסוכנים
    text = re.sub(r'[<>"\']', '', text)
    
    # חיתוך לאורך מקסימלי
    if len(text) > max_length:
        text = text[:max_length] + "..."
    
    return text.strip()

def parse_snooze_input(text: str) -> Optional[int]:
    """פענוח קלט זמן נודניק"""
    if not text:
        return None
    
    text = text.lower().strip()
    
    # פטרנים לזיהוי זמן
    patterns = [
        (r'^(\d+)\s*דק', lambda m: int(m.group(1))),           # X דק'
        (r'^(\d+)\s*ש', lambda m: int(m.group(1)) * 60),       # X שע'
        (r'^(\d+)h?$', lambda m: int(m.group(1)) * 60),        # Xh או X
        (r'^(\d+)m?$', lambda m: int(m.group(1))),             # Xm או X
        (r'^(\d+):(\d+)$', lambda m: int(m.group(1)) * 60 + int(m.group(2)))  # HH:MM
    ]
    
    for pattern, converter in patterns:
        match = re.match(pattern, text)
        if match:
            try:
                minutes = converter(match)
                # ולידציה - מקסימום 12 שעות
                if 1 <= minutes <= 720:
                    return minutes
            except (ValueError, AttributeError):
                continue
    
    return None

def calculate_time_until(target_time: time) -> timedelta:
    """חישוב זמן עד שעה מסוימת"""
    now = datetime.now()
    target_datetime = datetime.combine(now.date(), target_time)
    
    # אם השעה כבר עברה היום, קח את מחר
    if target_datetime <= now:
        target_datetime += timedelta(days=1)
    
    return target_datetime - now

def format_relative_time(dt: datetime) -> str:
    """פורמט זמן יחסי (לפני X זמן)"""
    now = datetime.now()
    diff = now - dt
    
    if diff.days > 0:
        if diff.days == 1:
            return "אתמול"
        else:
            return f"לפני {diff.days} ימים"
    
    hours = diff.seconds // 3600
    if hours > 0:
        if hours == 1:
            return "לפני שעה"
        else:
            return f"לפני {hours} שעות"
    
    minutes = (diff.seconds % 3600) // 60
    if minutes > 0:
        if minutes == 1:
            return "לפני דקה"
        else:
            return f"לפני {minutes} דקות"
    
    return "זה עתה"

def get_next_weekday_date(target_weekday: int) -> datetime:
    """קבלת התאריך הבא של יום שבוע מסוים (0=שני, 6=שבת)"""
    today = datetime.now()
    days_ahead = target_weekday - today.weekday()
    
    if days_ahead <= 0:  # השבוע הבא
        days_ahead += 7
    
    return today + timedelta(days=days_ahead)

def create_progress_bar(current: int, total: int, length: int = 10) -> str:
    """יצירת בר התקדמות טקסטואלי"""
    if total == 0:
        return "▱" * length
    
    filled = int((current / total) * length)
    bar = "▰" * filled + "▱" * (length - filled)
    return f"{bar} {current}/{total}"

def log_user_action(user_id: int, action: str, details: str = ""):
    """רישום פעולת משתמש ללוגים"""
    log_message = f"User {user_id} - {action}"
    if details:
        log_message += f" - {details}"
    
    logger.info(log_message)

def safe_int(value: Union[str, int, None], default: int = 0) -> int:
    """המרה בטוחה למספר שלם"""
    if value is None:
        return default
    
    try:
        if isinstance(value, str):
            return int(value.strip())
        return int(value)
    except (ValueError, TypeError):
        return default

def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """חלוקת רשימה לחלקים קטנים"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def is_business_hours() -> bool:
    """בדיקה אם זה שעות עסקים (06:00-22:00)"""
    current_hour = datetime.now().hour
    return 6 <= current_hour <= 22

def get_random_encouragement() -> str:
    """קבלת הודעת עידוד אקראית"""
    encouragements = [
        "איזה מלך! 👑",
        "כל הכבוד! 🌟", 
        "אלוף! 🏆",
        "מדהים! ✨",
        "יפה מאוד! 👏",
        "המשך כך! 💪",
        "מצוין! 🎉",
        "גאה בך! 🙌"
    ]
    
    import random
    return random.choice(encouragements)

def mask_sensitive_data(text: str, mask_char: str = "*") -> str:
    """הסתרת מידע רגיש בלוגים"""
    # הסתרת טוקנים
    text = re.sub(r'\b\d{10}:[A-Za-z0-9_-]{35}\b', f'{mask_char*8}', text)
    
    # הסתרת מספרי טלפון
    text = re.sub(r'\b\d{9,10}\b', f'{mask_char*4}', text)
    
    return text
