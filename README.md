# 🙏 בוט תזכורות תפילין

בוט טלגרם חכם לתזכורות יומיות להנחת תפילין, עם תמיכה בזמני הלכה, זיהוי שבת וחגים, ומעקב רצף ימים.

## ✨ תכונות

### 🔔 תזכורות חכמות
- **תזכורת יומית** בשעה לבחירת המשתמש
- **תזכורת לפני שקיעה** (אופציונלי)
- **נודניק חכם** עם אפשרויות דחייה שונות
- **לא שולח בשבת וחגים** - זיהוי אוטומטי

### 📊 מעקב אישי
- **מעקב רצף ימים** עם הודעות עידוד
- **סטטיסטיקות מפורטות** - אחוזי הצלחה, ימי פעילות
- **הגדרות אישיות** - שעה, תזכורת שקיעה

### 🕒 זמני הלכה מדויקים
- **זמני שקיעה** מ-API מדויק (Hebcal)
- **זיהוי חגים יהודיים** אוטומטי
- **תמיכה באזורי זמן** שונים

## 🚀 התקנה מהירה

### דרישות מוקדמות
- Python 3.11+
- MongoDB (מומלץ MongoDB Atlas)
- טוקן בוט מ-@BotFather בטלגרם

### 1. הכנת הבוט בטלגרם
```
1. פתח שיחה עם @BotFather
2. שלח /newbot
3. בחר שם לבוט (למשל: "תזכורת תפילין")
4. בחר username (למשל: my_tefillin_bot)
5. שמור את הטוקן שתקבל!
```

### 2. הכנת מסד נתונים MongoDB
**אופציה א: MongoDB Atlas (מומלץ - חינמי)**
```
1. הירשם ל-https://mongodb.com/atlas
2. צור cluster חינמי
3. צור משתמש במסד הנתונים
4. הוסף את כתובת IP שלך (או 0.0.0.0/0 לכל מקום)
5. קבל את connection string
```

**אופציה ב: MongoDB מקומי**
```bash
# Ubuntu/Debian
sudo apt-get install mongodb

# macOS
brew install mongodb/brew/mongodb-community
```

### 3. הורדת הקוד
```bash
git clone https://github.com/yourusername/tefillin-bot.git
cd tefillin-bot
```

### 4. הגדרת סביבה
```bash
# יצירת סביבה וירטואלית
python -m venv venv
source venv/bin/activate  # Linux/Mac
# או: venv\Scripts\activate  # Windows

# התקנת תלויות
pip install -r requirements.txt

# יצירת קובץ הגדרות
cp .env.example .env
```

### 5. הגדרת משתני סביבה
ערוך את קובץ `.env`:
```bash
# טוקן הבוט (חובה!)
BOT_TOKEN=1234567890:ABCDEFghijklmnopqrstuvwxyz123456

# כתובת MongoDB (חובה!)
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/tefillin_bot

# הגדרות אופציונליות
LOG_LEVEL=INFO
DEFAULT_TIMEZONE=Asia/Jerusalem
```

### 6. הרצה מקומית
```bash
python main_updated.py
```

הבוט צריך להציג:
```
✅ Database connection successful
🤖 Starting bot application...
INFO - Bot startup completed successfully
```

## 🌐 פריסה ב-Render

### הכנות
1. העלה את הקוד ל-GitHub (ללא קובץ .env!)
2. הירשם ל-https://render.com

### שלבי פריסה
1. **צור שירות חדש** ב-Render
2. **בחר Web Service** וחבר את ה-repository
3. **הגדר את השירות:**
   ```
   Name: tefillin-bot
   Environment: Docker
   Build Command: (השאר ריק)
   Start Command: python main_updated.py
   ```

4. **הוסף משתני סביבה:**
   ```
   BOT_TOKEN = הטוקן שלך
   MONGODB_URI = connection string של MongoDB
   LOG_LEVEL = INFO
   ```

5. **לחץ Deploy** וחכה לסיום

## 📱 שימוש בבוט

### פקודות בסיסיות
- `/start` - הרשמה ובחירת שעה
- `/settings` - שינוי הגדרות
- `/stats` - סטטיסטיקות אישיות
- `/skip` - דילוג על היום
- `/help` - עזרה

### זרימת משתמש
1. **הרשמה:** המשתמש שולח `/start` ובוחר שעה יומית
2. **תזכורת:** הבוט שולח תזכורת בשעה שנקבעה
3. **תגובה:** המשתמש לוחץ "הנחתי ✅" או בוחר נודניק
4. **מעקב:** הבוט מעדכן רצף ימים ושולח עידוד

## 🔧 מבנה הפרויקט

```
tefillin-bot/
├── main_updated.py      # בוט ראשי
├── config.py           # הגדרות
├── scheduler.py        # תזמון תזכורות
├── handlers.py         # טיפול בכפתורים
├── hebrew_times.py     # זמני הלכה
├── database.py         # ניהול MongoDB
├── utils.py           # פונקציות עזר
├── requirements.txt    # תלויות Python
├── Dockerfile         # עבור deployment
├── start.sh          # סקריפט הפעלה
├── .env.example      # דוגמה למשתני סביבה
├── .gitignore        # קבצים להתעלמות
└── tests/           # בדיקות אוטומטיות
```

## ⚙️ הגדרות מתקדמות

### זמני שקיעה מותאמים
הבוט משתמש ב-Hebcal API. אפשר לשנות:
```python
# בקובץ hebrew_times.py
params = {
    'geonameid': '281184'  # ירושלים - שנה לעיר אחרת
}
```

### הוספת חגים מותאמים
```python
# בקובץ hebrew_times.py
def is_custom_holiday(self, date_obj):
    # הוסף לוגיקה לחגים מיוחדים
    pass
```

### שינוי הודעות
```python
# בקובץ config.py
MESSAGES = {
    'daily_reminder': "ההודעה שלך כאן...",
    'tefillin_done': "הודעת אישור מותאמת..."
}
```

## 🧪 בדיקות

```bash
# הרצת כל הבדיקות
python -m pytest tests/

# בדיקת קובץ ספציפי
python -m pytest tests/test_scheduler.py

# בדיקה עם כיסוי
python -m pytest --cov=. tests/
```

## 📊 ניטור ולוגים

### לוגים ב-Render
```bash
# צפייה בלוגים בזמן אמת
render logs --service your-service-id --tail

# הורדת לוגים
render logs --service your-service-id > logs.txt
```

### מדדי ביצועים
הבוט שומר סטטיסטיקות יומיות:
- מספר משתמשים פעילים
- אחוז השלמת תזכורות
- מספר תזכורות שנשלחו

## 🔒 אבטחה

### משתני סביבה
- **לעולם** אל תשמור טוקנים בקוד
- השתמש במשתני סביבה של Render
- בדוק שה-.env ב-.gitignore

### MongoDB
- השתמש במשתמש ייעודי עם הרשאות מוגבלות
- הפעל SSL/TLS
- הגבל גישה לכתובות IP נדרשות

### בוט טלגרם
- שמור את הטוקן במקום בטוח
- אל תשתף את הטוקן עם אף אחד
- במקרה של חשיפה - צור טוקן חדש מיד

## 🐛 פתרון בעיות נפוצות

### "Database connection failed"
```bash
# בדוק connection string
python -c "from pymongo import MongoClient; MongoClient('your-uri').admin.command('ping')"
```

### "Bot was blocked by user"
הבוט מטפל בזה אוטומטית - המשתמש יסומן כלא פעיל.

### זמני שקיעה לא מדויקים
```python
# בדוק geonameid בקובץ hebrew_times.py
# חפש עיר ב: http://www.geonames.org/
```

### תזכורות לא נשלחות
1. בדוק שהמשתמש active במסד הנתונים
2. וודא שה-scheduler רץ
3. בדוק לוגים לשגיאות

## 🤝 תרומה לפרויקט

### דיווח על בעיות
פתח [issue חדש](https://github.com/yourusername/tefillin-bot/issues) עם:
- תיאור הבעיה
- צעדים לשחזור
- לוגים רלוונטיים

### הוספת תכונות
1. Fork את הפרויקט
2. צור branch חדש (`git checkout -b feature/amazing-feature`)
3. Commit השינויים (`git commit -m 'Add amazing feature'`)
4. Push ל-branch (`git push origin feature/amazing-feature`)
5. פתח Pull Request

## 📄 רישיון

פרויקט זה מופץ תחת רישיון MIT. ראה `LICENSE` לפרטים.

## 📞 יצירת קשר

- 📧 Email: your.email@example.com
- 💬 Telegram: @yourusername
- 🐙 GitHub: [@yourusername](https://github.com/yourusername)

## 🙏 תודות

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - ספריית בוט מעולה
- [Hebcal](https://www.hebcal.com/) - זמני הלכה מדויקים
- [MongoDB Atlas](https://www.mongodb.com/atlas) - מסד נתונים בענן
- [Render](https://render.com/) - פלטפורמת deployment נוחה

---

**⭐ אם הפרויקט עזר לך, אל תשכח לתת כוכב ב-GitHub!**

**💡 רעיון? בעיה? פתח issue ונעזור לך!**
תזכורת להניח
