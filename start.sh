#!/bin/bash

# סקריפט הפעלה לבוט תפילין ב-Render
# Render יריץ את הסקריפט הזה כפקודת התחלה

set -e  # עצירה בשגיאה

echo "🚀 Starting Tefillin Bot..."

# בדיקת משתני סביבה נדרשים
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ Error: BOT_TOKEN environment variable is required"
    exit 1
fi

if [ -z "$MONGODB_URI" ]; then
    echo "❌ Error: MONGODB_URI environment variable is required"
    exit 1
fi

echo "✅ Environment variables validated"

# בדיקת חיבור למסד נתונים (אופציונלי)
echo "🔍 Testing database connection..."
python3 -c "
import os
from pymongo import MongoClient
try:
    client = MongoClient(os.getenv('MONGODB_URI'), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print('✅ Database connection successful')
    client.close()
except Exception as e:
    print(f'⚠️ Database connection warning: {e}')
    print('Bot will still attempt to start...')
"

# הגדרת משתני סביבה נוספים
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export PYTHONUNBUFFERED=1

# בדיקת קבצי Python
echo "🔍 Checking Python files..."
if [ ! -f "main_updated.py" ]; then
    echo "❌ Error: main_updated.py not found"
    exit 1
fi

echo "✅ Python files found"

# התחלת הבוט
echo "🤖 Starting bot application..."
echo "Bot will run in polling mode"
echo "Press Ctrl+C to stop"

# הרצת הבוט עם הפניית פלט ושגיאות
exec python3 main_updated.py 2>&1

# הערות ל-Render:
# 1. הגדר את הסקריפט הזה כ-Start Command ב-Render
# 2. או השתמש ישירות ב: python main_updated.py
# 3. וודא שמשתני הסביבה BOT_TOKEN ו-MONGODB_URI מוגדרים
# 4. Render יריץ אוטומטית pip install -r requirements.txt
# 5. הבוט יתחיל אוטומטית אחרי deploy מוצלח

# דוגמת הגדרה ב-Render:
# Service Type: Web Service
# Build Command: pip install -r requirements.txt  
# Start Command: bash start.sh
# או פשוט: python main_updated.py

# Environment Variables ב-Render:
# BOT_TOKEN=your_bot_token_here
# MONGODB_URI=your_mongodb_connection_string_here
# LOG_LEVEL=INFO (אופציונלי)
# DEFAULT_TIMEZONE=Asia/Jerusalem (אופציונלי)
