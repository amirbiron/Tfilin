import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, ConnectionFailure
from config import Config

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, client: MongoClient):
        self.client = client
        self.db = client.tefillin_bot
        self.users_collection = self.db.users
        self.stats_collection = self.db.stats
        self.logs_collection = self.db.logs

    def setup_database(self):
        """הגדרת מסד הנתונים ואינדקסים"""
        try:
            # יצירת אינדקסים למשתמשים
            self.users_collection.create_index([("user_id", ASCENDING)], unique=True)
            self.users_collection.create_index([("daily_time", ASCENDING)])
            self.users_collection.create_index([("active", ASCENDING)])
            self.users_collection.create_index([("created_at", DESCENDING)])

            # אינדקס מורכב למשתמשים פעילים עם זמן יומי
            self.users_collection.create_index([("active", ASCENDING), ("daily_time", ASCENDING)])

            # יצירת אינדקסים לסטטיסטיקות
            self.stats_collection.create_index([("date", DESCENDING)])
            self.stats_collection.create_index([("type", ASCENDING)])

            # יצירת אינדקסים ללוגים
            self.logs_collection.create_index([("timestamp", DESCENDING)])
            self.logs_collection.create_index([("user_id", ASCENDING)])
            self.logs_collection.create_index([("action", ASCENDING)])

            # אינדקס TTL ללוגים (מחיקה אוטומטית אחרי 30 יום)
            self.logs_collection.create_index([("timestamp", ASCENDING)], expireAfterSeconds=30 * 24 * 60 * 60)  # 30 יום

            logger.info("Database indexes created successfully")

        except Exception as e:
            logger.error(f"Failed to setup database: {e}")
            raise

    def get_user(self, user_id: int) -> Optional[Dict]:
        """קבלת משתמש לפי ID"""
        try:
            return self.users_collection.find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None

    def upsert_user(self, user_id: int, user_data: Dict) -> bool:
        """יצירה או עדכון משתמש"""
        try:
            user_data["user_id"] = user_id
            user_data["updated_at"] = datetime.now()

            result = self.users_collection.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)

            if result.upserted_id:
                logger.info(f"Created new user {user_id}")
                self.log_user_action(user_id, "user_created")
            else:
                logger.info(f"Updated user {user_id}")
                self.log_user_action(user_id, "user_updated")

            return True

        except Exception as e:
            logger.error(f"Failed to upsert user {user_id}: {e}")
            return False

    def update_user(self, user_id: int, update_data: Dict) -> bool:
        """עדכון נתוני משתמש"""
        try:
            update_data["updated_at"] = datetime.now()

            result = self.users_collection.update_one({"user_id": user_id}, {"$set": update_data})

            if result.modified_count > 0:
                logger.info(f"Updated user {user_id} data")
                return True
            else:
                logger.warning(f"No changes made to user {user_id}")
                return False

        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {e}")
            return False

    def get_active_users(self) -> List[Dict]:
        """קבלת כל המשתמשים הפעילים"""
        try:
            return list(
                self.users_collection.find(
                    {"active": True},
                    {"user_id": 1, "daily_time": 1, "timezone": 1, "sunset_reminder": 1, "last_reminder_date": 1},
                )
            )
        except Exception as e:
            logger.error(f"Failed to get active users: {e}")
            return []

    def get_users_by_time(self, time_str: str) -> List[Dict]:
        """קבלת משתמשים לפי שעה יומית"""
        try:
            return list(self.users_collection.find({"active": True, "daily_time": time_str}))
        except Exception as e:
            logger.error(f"Failed to get users by time {time_str}: {e}")
            return []

    def get_users_with_sunset_reminder(self) -> List[Dict]:
        """קבלת משתמשים עם תזכורת שקיעה"""
        try:
            return list(self.users_collection.find({"active": True, "sunset_reminder": {"$gt": 0}}))
        except Exception as e:
            logger.error(f"Failed to get users with sunset reminder: {e}")
            return []

    def deactivate_user(self, user_id: int, reason: str = "blocked") -> bool:
        """השבתת משתמש"""
        try:
            result = self.users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"active": False, "deactivated_at": datetime.now(), "deactivation_reason": reason}},
            )

            if result.modified_count > 0:
                logger.info(f"Deactivated user {user_id} - reason: {reason}")
                self.log_user_action(user_id, "user_deactivated", reason)
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to deactivate user {user_id}: {e}")
            return False

    def reactivate_user(self, user_id: int) -> bool:
        """הפעלת משתמש מחדש"""
        try:
            result = self.users_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {"active": True, "reactivated_at": datetime.now()},
                    "$unset": {"deactivated_at": "", "deactivation_reason": ""},
                },
            )

            if result.modified_count > 0:
                logger.info(f"Reactivated user {user_id}")
                self.log_user_action(user_id, "user_reactivated")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to reactivate user {user_id}: {e}")
            return False

    def log_user_action(self, user_id: int, action: str, details: str = "") -> bool:
        """רישום פעולת משתמש"""
        try:
            log_entry = {"user_id": user_id, "action": action, "details": details, "timestamp": datetime.now()}

            self.logs_collection.insert_one(log_entry)
            return True

        except Exception as e:
            logger.error(f"Failed to log action for user {user_id}: {e}")
            return False

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """קבלת סטטיסטיקות משתמש"""
        try:
            user = self.get_user(user_id)
            if not user:
                return {}

            # חישוב ימים מההרשמה
            created_at = user.get("created_at")
            days_since_signup = 0
            if created_at:
                days_since_signup = (datetime.now() - created_at).days

            # חישוב אחוז הצלחה (רצף / ימים מההרשמה)
            streak = user.get("streak", 0)
            success_rate = 0
            if days_since_signup > 0:
                success_rate = min(100, (streak / days_since_signup) * 100)

            # קבלת מספר פעולות מהלוגים
            total_actions = self.logs_collection.count_documents({"user_id": user_id})
            tefillin_done_count = self.logs_collection.count_documents({"user_id": user_id, "action": "tefillin_done"})

            return {
                "streak": streak,
                "days_since_signup": days_since_signup,
                "success_rate": round(success_rate, 1),
                "total_actions": total_actions,
                "tefillin_done_count": tefillin_done_count,
                "last_done": user.get("last_done"),
                "daily_time": user.get("daily_time"),
                "sunset_reminder": user.get("sunset_reminder", 0),
            }

        except Exception as e:
            logger.error(f"Failed to get stats for user {user_id}: {e}")
            return {}

    def save_daily_stats(self, date: datetime) -> bool:
        """שמירת סטטיסטיקות יומיות"""
        try:
            date_str = date.date().isoformat()

            # ספירת משתמשים פעילים
            total_users = self.users_collection.count_documents({"active": True})

            # ספירת משתמשים שהניחו תפילין היום
            users_done_today = self.users_collection.count_documents({"last_done": date_str})

            # ספירת תזכורות שנשלחו היום
            reminders_sent = self.logs_collection.count_documents(
                {
                    "action": "reminder_sent",
                    "timestamp": {
                        "$gte": datetime.combine(date.date(), datetime.min.time()),
                        "$lt": datetime.combine(date.date(), datetime.max.time()),
                    },
                }
            )

            stats_entry = {
                "date": date_str,
                "type": "daily",
                "total_users": total_users,
                "users_done_today": users_done_today,
                "reminders_sent": reminders_sent,
                "completion_rate": (users_done_today / total_users * 100) if total_users > 0 else 0,
                "timestamp": datetime.now(),
            }

            # עדכון או יצירה
            self.stats_collection.update_one({"date": date_str, "type": "daily"}, {"$set": stats_entry}, upsert=True)

            logger.info(f"Saved daily stats for {date_str}")
            return True

        except Exception as e:
            logger.error(f"Failed to save daily stats: {e}")
            return False

    def get_daily_stats(self, days: int = 7) -> List[Dict]:
        """קבלת סטטיסטיקות יומיות של X ימים אחרונים"""
        try:
            start_date = datetime.now() - timedelta(days=days)
            start_date_str = start_date.date().isoformat()

            return list(
                self.stats_collection.find({"type": "daily", "date": {"$gte": start_date_str}}, sort=[("date", DESCENDING)])
            )

        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return []

    def cleanup_old_data(self, days_to_keep: int = 90) -> bool:
        """ניקוי נתונים ישנים"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)

            # מחיקת סטטיסטיקות ישנות
            result_stats = self.stats_collection.delete_many({"timestamp": {"$lt": cutoff_date}})

            # לוגים נמחקים אוטומטית באמצעות TTL index

            logger.info(f"Cleaned up {result_stats.deleted_count} old stats entries")
            return True

        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            return False

    def get_database_info(self) -> Dict[str, Any]:
        """קבלת מידע על מסד הנתונים"""
        try:
            db_stats = self.db.command("dbstats")

            collections_info = {}
            for collection_name in self.db.list_collection_names():
                collection = self.db[collection_name]
                collections_info[collection_name] = {
                    "count": collection.count_documents({}),
                    "indexes": len(list(collection.list_indexes())),
                }

            return {
                "database_size": db_stats.get("dataSize", 0),
                "collections": collections_info,
                "indexes_total": sum(info["indexes"] for info in collections_info.values()),
            }

        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {}

    def backup_user_data(self, user_id: int) -> Optional[Dict]:
        """גיבוי נתוני משתמש"""
        try:
            user_data = self.get_user(user_id)
            if not user_data:
                return None

            # הוספת לוגים אחרונים
            recent_logs = list(self.logs_collection.find({"user_id": user_id}, sort=[("timestamp", DESCENDING)], limit=50))

            backup_data = {"user_data": user_data, "recent_logs": recent_logs, "backup_timestamp": datetime.now().isoformat()}

            return backup_data

        except Exception as e:
            logger.error(f"Failed to backup user {user_id}: {e}")
            return None

    def test_connection(self) -> bool:
        """בדיקת חיבור למסד הנתונים"""
        try:
            # פינג פשוט
            self.client.admin.command("ping")

            # בדיקת כתיבה וקריאה
            test_doc = {"test": True, "timestamp": datetime.now()}
            result = self.db.test_collection.insert_one(test_doc)

            # מחיקת המסמך הבדיקה
            self.db.test_collection.delete_one({"_id": result.inserted_id})

            logger.info("Database connection test successful")
            return True

        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
