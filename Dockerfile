# שימוש בתמונת Python רשמית
FROM python:3.11-slim

# הגדרת תיקיית עבודה
WORKDIR /app

# העתקת קובץ requirements לפני השאר (לנצול cache של Docker)
COPY requirements.txt .

# עדכון מנהל החבילות והתקנת תלויות מערכת
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# התקנת תלויות Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# העתקת כל קבצי הפרויקט
COPY . .

# הפוך את הסקריפט להרצה
RUN chmod +x /app/start.sh

# יצירת משתמש לא-root לאבטחה
RUN useradd --create-home --shell /bin/bash tefillin && \
    chown -R tefillin:tefillin /app
USER tefillin

# הגדרת משתני סביבה
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# חשיפת פורט לhealth check endpoint (ברירת מחדל)
EXPOSE 10000

# בדיקת תקינות הקונטיינר (משתמש ב-$PORT אם קיים)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD sh -c 'PORT=${PORT:-10000}; curl -fsS http://localhost:${PORT}/health >/dev/null || exit 1'

# פקודת הפעלה עם health check server
CMD ["/app/start.sh"]

# הערות לbuild ו-deployment:
# 
# Build מקומי:
# docker build -t tefillin-bot .
# 
# הרצה מקומית:
# docker run --env-file .env tefillin-bot
#
# עבור Render:
# 1. הגדר את משתני הסביבה (BOT_TOKEN, MONGODB_URI) בממשק Render
# 2. Render יבנה אוטומטית מהDockerfile הזה
# 3. הקונטיינר יתחיל אוטומטית עם CMD

# טיפים ל-Render:
# - השתמש ב-Environment Variables במקום .env
# - וודא שה-MongoDB URI נכון (לרוב MongoDB Atlas)
# - בדוק שהטוקן של הבוט תקין
# - ה-bot צריך לרוץ במצב polling (לא webhook) עבור Render
