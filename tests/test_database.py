"""Tests for database operations"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager as Database


class TestDatabase:
    """Test cases for Database class"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database instance"""
        with patch("database.MongoClient") as mock_client:
            mock_db_instance = Mock()
            mock_client.return_value.__getitem__.return_value = mock_db_instance

            db = Database("mongodb://test:test@localhost:27017/test")
            db.db = mock_db_instance

            # Setup mock collections
            db.users = Mock()
            db.reminders = Mock()
            db.daily_times = Mock()
            db.system_logs = Mock()

            return db

    def test_create_indexes(self, mock_db):
        """Test index creation"""
        mock_db.create_indexes()

        # Verify indexes were created on all collections
        assert mock_db.users.create_index.called
        assert mock_db.reminders.create_index.called
        assert mock_db.daily_times.create_index.called
        assert mock_db.system_logs.create_index.called

    def test_get_user(self, mock_db):
        """Test getting user from database"""
        mock_user = {"user_id": 123456, "username": "testuser", "registered_at": datetime.now()}
        mock_db.users.find_one.return_value = mock_user

        result = mock_db.get_user(123456)

        mock_db.users.find_one.assert_called_once_with({"user_id": 123456})
        assert result == mock_user

    def test_create_user(self, mock_db):
        """Test creating a new user"""
        user_id = 123456
        username = "testuser"

        # Mock that user doesn't exist
        mock_db.users.find_one.return_value = None

        mock_db.create_user(user_id, username)

        # Verify user was created
        mock_db.users.update_one.assert_called_once()
        call_args = mock_db.users.update_one.call_args
        assert call_args[0][0] == {"user_id": user_id}
        assert call_args[1]["upsert"] == True

    def test_set_reminder(self, mock_db):
        """Test setting a reminder"""
        user_id = 123456
        reminder_type = "morning"
        time = "08:00"

        mock_db.set_reminder(user_id, reminder_type, time)

        # Verify reminder was updated
        mock_db.reminders.update_one.assert_called_once()
        call_args = mock_db.reminders.update_one.call_args
        assert call_args[0][0] == {"user_id": user_id}

    def test_get_reminder(self, mock_db):
        """Test getting a reminder"""
        user_id = 123456
        reminder_type = "morning"

        mock_reminder = {"user_id": user_id, "type": reminder_type, "time": "08:00", "active": True}
        mock_db.reminders.find_one.return_value = mock_reminder

        result = mock_db.get_reminder(user_id, reminder_type)

        mock_db.reminders.find_one.assert_called_once_with({"user_id": user_id, "type": reminder_type})
        assert result == mock_reminder

    def test_delete_reminder(self, mock_db):
        """Test deleting a reminder"""
        user_id = 123456
        reminder_type = "morning"

        mock_db.delete_reminder(user_id, reminder_type)

        mock_db.reminders.delete_one.assert_called_once_with({"user_id": user_id, "type": reminder_type})

    def test_get_active_reminders(self, mock_db):
        """Test getting active reminders"""
        mock_reminders = [
            {"user_id": 1, "type": "morning", "time": "08:00"},
            {"user_id": 2, "type": "evening", "time": "18:00"},
        ]
        mock_db.reminders.find.return_value = mock_reminders

        result = mock_db.get_active_reminders()

        mock_db.reminders.find.assert_called_once_with({"active": True})
        assert result == mock_reminders

    def test_update_daily_times(self, mock_db):
        """Test updating daily times"""
        times = {"sunrise": "06:30", "sunset": "18:45"}

        mock_db.update_daily_times(times)

        mock_db.daily_times.update_one.assert_called_once()
        call_args = mock_db.daily_times.update_one.call_args
        assert call_args[1]["upsert"] == True

    def test_log_action(self, mock_db):
        """Test logging an action"""
        user_id = 123456
        action = "test_action"
        details = {"test": "data"}

        mock_db.log_action(user_id, action, details)

        mock_db.system_logs.insert_one.assert_called_once()
        call_args = mock_db.system_logs.insert_one.call_args[0][0]
        assert call_args["user_id"] == user_id
        assert call_args["action"] == action
        assert call_args["details"] == details
        assert "timestamp" in call_args
