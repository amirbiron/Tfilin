"""Tests for database operations"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager


class TestDatabaseManager:
    """Test cases for DatabaseManager class"""

    @pytest.fixture
    def mock_client(self):
        """Create a mock MongoDB client"""
        with patch("database.MongoClient") as mock_client:
            # Setup mock database and collections
            mock_db = Mock()
            mock_users = Mock()
            mock_stats = Mock()
            mock_logs = Mock()
            
            # Configure the mock client
            mock_client_instance = Mock()
            mock_client_instance.tefillin_bot = mock_db
            mock_db.users = mock_users
            mock_db.daily_stats = mock_stats
            mock_db.user_logs = mock_logs
            
            yield mock_client_instance

    @pytest.fixture
    def db_manager(self, mock_client):
        """Create a DatabaseManager instance with mock client"""
        return DatabaseManager(mock_client)

    def test_setup_database(self, db_manager, mock_client):
        """Test database setup and index creation"""
        db_manager.setup_database()
        
        # Check that indexes were created
        assert mock_client.tefillin_bot.users.create_index.called
        assert mock_client.tefillin_bot.daily_stats.create_index.called

    def test_get_user(self, db_manager, mock_client):
        """Test getting a user from database"""
        # Setup mock response
        mock_user = {
            "user_id": 123456,
            "username": "testuser",
            "daily_time": "08:00",
            "is_active": True
        }
        mock_client.tefillin_bot.users.find_one.return_value = mock_user
        
        # Test
        result = db_manager.get_user(123456)
        
        # Verify
        assert result == mock_user
        mock_client.tefillin_bot.users.find_one.assert_called_once_with({"user_id": 123456})

    def test_get_user_not_found(self, db_manager, mock_client):
        """Test getting a non-existent user"""
        mock_client.tefillin_bot.users.find_one.return_value = None
        
        result = db_manager.get_user(999999)
        
        assert result is None

    def test_upsert_user_new(self, db_manager, mock_client):
        """Test creating a new user"""
        mock_client.tefillin_bot.users.update_one.return_value = Mock(
            upserted_id="new_id", modified_count=0
        )
        
        user_data = {
            "username": "newuser",
            "daily_time": "09:00",
            "timezone": "Asia/Jerusalem"
        }
        
        result = db_manager.upsert_user(123456, user_data)
        
        assert result is True
        mock_client.tefillin_bot.users.update_one.assert_called_once()
        
        # Check the call arguments
        call_args = mock_client.tefillin_bot.users.update_one.call_args
        assert call_args[0][0] == {"user_id": 123456}  # filter
        assert "$set" in call_args[0][1]  # update
        assert call_args[1]["upsert"] is True  # options

    def test_upsert_user_existing(self, db_manager, mock_client):
        """Test updating an existing user"""
        mock_client.tefillin_bot.users.update_one.return_value = Mock(
            upserted_id=None, modified_count=1
        )
        
        user_data = {
            "daily_time": "10:00"
        }
        
        result = db_manager.upsert_user(123456, user_data)
        
        assert result is True

    def test_update_user(self, db_manager, mock_client):
        """Test updating user data"""
        mock_client.tefillin_bot.users.update_one.return_value = Mock(modified_count=1)
        
        update_data = {
            "daily_time": "11:00",
            "sunset_reminder": True
        }
        
        result = db_manager.update_user(123456, update_data)
        
        assert result is True
        mock_client.tefillin_bot.users.update_one.assert_called_once()

    def test_get_active_users(self, db_manager, mock_client):
        """Test getting all active users"""
        mock_users = [
            {"user_id": 1, "is_active": True},
            {"user_id": 2, "is_active": True}
        ]
        mock_client.tefillin_bot.users.find.return_value = mock_users
        
        result = db_manager.get_active_users()
        
        assert result == mock_users
        mock_client.tefillin_bot.users.find.assert_called_once_with({"is_active": True})

    def test_get_users_by_time(self, db_manager, mock_client):
        """Test getting users by specific time"""
        mock_users = [
            {"user_id": 1, "daily_time": "08:00"},
            {"user_id": 2, "daily_time": "08:00"}
        ]
        mock_client.tefillin_bot.users.find.return_value = mock_users
        
        result = db_manager.get_users_by_time("08:00")
        
        assert result == mock_users
        mock_client.tefillin_bot.users.find.assert_called_once_with({
            "daily_time": "08:00",
            "is_active": True
        })

    def test_deactivate_user(self, db_manager, mock_client):
        """Test deactivating a user"""
        mock_client.tefillin_bot.users.update_one.return_value = Mock(modified_count=1)
        
        result = db_manager.deactivate_user(123456, "user_request")
        
        assert result is True
        
        # Check the update call
        call_args = mock_client.tefillin_bot.users.update_one.call_args
        assert call_args[0][0] == {"user_id": 123456}
        assert "$set" in call_args[0][1]
        assert call_args[0][1]["$set"]["is_active"] is False

    def test_reactivate_user(self, db_manager, mock_client):
        """Test reactivating a user"""
        mock_client.tefillin_bot.users.update_one.return_value = Mock(modified_count=1)
        
        result = db_manager.reactivate_user(123456)
        
        assert result is True
        
        # Check the update call
        call_args = mock_client.tefillin_bot.users.update_one.call_args
        assert call_args[0][0] == {"user_id": 123456}
        assert "$set" in call_args[0][1]
        assert call_args[0][1]["$set"]["is_active"] is True

    def test_log_user_action(self, db_manager, mock_client):
        """Test logging user action"""
        mock_client.tefillin_bot.user_logs.insert_one.return_value = Mock(inserted_id="log_id")
        
        result = db_manager.log_user_action(123456, "test_action", "test details")
        
        assert result is True
        mock_client.tefillin_bot.user_logs.insert_one.assert_called_once()

    def test_test_connection(self, db_manager, mock_client):
        """Test database connection check"""
        mock_client.admin.command.return_value = {"ok": 1}
        
        result = db_manager.test_connection()
        
        assert result is True
        mock_client.admin.command.assert_called_once_with("ping")

    def test_test_connection_failure(self, db_manager, mock_client):
        """Test database connection check failure"""
        mock_client.admin.command.side_effect = Exception("Connection failed")
        
        result = db_manager.test_connection()
        
        assert result is False