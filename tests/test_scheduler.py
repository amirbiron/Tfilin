"""Tests for scheduler module"""

import asyncio
import os
import sys
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduler import Scheduler


class TestScheduler:
    """Test cases for Scheduler class"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        mock = Mock()
        mock.get_active_reminders = Mock(return_value=[])
        mock.update_daily_times = Mock()
        mock.get_daily_times = Mock(return_value=None)
        return mock

    @pytest.fixture
    def mock_handlers(self):
        """Create mock handlers"""
        mock = Mock()
        mock.send_reminder = AsyncMock()
        return mock

    @pytest.fixture
    def scheduler(self, mock_db, mock_handlers):
        """Create scheduler instance with mocks"""
        with patch("scheduler.AsyncIOScheduler"):
            scheduler = Scheduler(mock_db, mock_handlers)
            scheduler.scheduler = Mock()
            scheduler.scheduler.add_job = Mock()
            scheduler.scheduler.remove_job = Mock()
            scheduler.scheduler.get_job = Mock(return_value=None)
            scheduler.scheduler.start = Mock()
            scheduler.scheduler.shutdown = Mock()
            return scheduler

    def test_start(self, scheduler):
        """Test starting the scheduler"""
        scheduler.start()
        scheduler.scheduler.start.assert_called_once()

    def test_stop(self, scheduler):
        """Test stopping the scheduler"""
        scheduler.stop()
        scheduler.scheduler.shutdown.assert_called_once_with(wait=False)

    def test_add_reminder(self, scheduler):
        """Test adding a reminder"""
        user_id = 123456
        reminder_type = "morning"
        time_str = "08:30"

        scheduler.add_reminder(user_id, reminder_type, time_str)

        scheduler.scheduler.add_job.assert_called_once()
        call_args = scheduler.scheduler.add_job.call_args
        assert call_args[1]["trigger"] == "cron"
        assert call_args[1]["hour"] == 8
        assert call_args[1]["minute"] == 30
        assert call_args[1]["id"] == f"reminder_{user_id}_{reminder_type}"

    def test_remove_reminder_existing(self, scheduler):
        """Test removing an existing reminder"""
        user_id = 123456
        reminder_type = "morning"
        job_id = f"reminder_{user_id}_{reminder_type}"

        # Mock that job exists
        mock_job = Mock()
        scheduler.scheduler.get_job.return_value = mock_job

        scheduler.remove_reminder(user_id, reminder_type)

        scheduler.scheduler.get_job.assert_called_once_with(job_id)
        scheduler.scheduler.remove_job.assert_called_once_with(job_id)

    def test_remove_reminder_not_existing(self, scheduler):
        """Test removing a non-existing reminder"""
        user_id = 123456
        reminder_type = "morning"
        job_id = f"reminder_{user_id}_{reminder_type}"

        # Mock that job doesn't exist
        scheduler.scheduler.get_job.return_value = None

        scheduler.remove_reminder(user_id, reminder_type)

        scheduler.scheduler.get_job.assert_called_once_with(job_id)
        scheduler.scheduler.remove_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_daily_times(self, scheduler, mock_db):
        """Test updating daily times"""
        with patch("scheduler.requests.get") as mock_get:
            # Mock API response
            mock_response = Mock()
            mock_response.json.return_value = {"times": {"Sunrise": "06:30:00", "Sunset": "18:45:00"}}
            mock_get.return_value = mock_response

            await scheduler.update_daily_times()

            # Verify API was called
            mock_get.assert_called_once()

            # Verify times were saved to database
            mock_db.update_daily_times.assert_called_once()
            call_args = mock_db.update_daily_times.call_args[0][0]
            assert "sunrise" in call_args
            assert "sunset" in call_args

    @pytest.mark.asyncio
    async def test_update_daily_times_api_error(self, scheduler, mock_db):
        """Test handling API error when updating daily times"""
        with patch("scheduler.requests.get") as mock_get:
            # Mock API error
            mock_get.side_effect = Exception("API Error")

            await scheduler.update_daily_times()

            # Verify error was handled gracefully
            mock_db.update_daily_times.assert_not_called()

    def test_load_reminders(self, scheduler, mock_db):
        """Test loading reminders from database"""
        # Mock active reminders
        mock_reminders = [
            {"user_id": 1, "type": "morning", "time": "08:00"},
            {"user_id": 2, "type": "evening", "time": "18:00"},
        ]
        mock_db.get_active_reminders.return_value = mock_reminders

        scheduler.load_reminders()

        # Verify reminders were loaded
        mock_db.get_active_reminders.assert_called_once()
        assert scheduler.scheduler.add_job.call_count == 2

    @pytest.mark.asyncio
    async def test_check_reminders(self, scheduler, mock_db, mock_handlers):
        """Test checking and sending reminders"""
        # Mock active reminders
        mock_reminders = [
            {"user_id": 1, "type": "morning", "time": "08:00"},
            {"user_id": 2, "type": "evening", "time": "18:00"},
        ]
        mock_db.get_active_reminders.return_value = mock_reminders

        # Mock current time to match one reminder
        with patch("scheduler.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "08:00"

            await scheduler.check_reminders()

            # Verify only matching reminder was sent
            mock_handlers.send_reminder.assert_called_once_with(1, "morning")
