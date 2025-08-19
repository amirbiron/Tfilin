"""Tests for scheduler module"""

import asyncio
import os
import sys
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduler import TefillinScheduler


class TestTefillinScheduler:
    """Test cases for TefillinScheduler class"""

    @pytest.fixture
    def mock_bot_app(self):
        """Create a mock bot application"""
        mock_app = Mock()
        mock_app.bot = Mock()
        mock_app.bot.send_message = AsyncMock()
        return mock_app

    @pytest.fixture
    def mock_db_client(self):
        """Create a mock database client"""
        mock_client = Mock()
        mock_db = Mock()
        mock_client.tefillin_bot = mock_db
        mock_db.users = Mock()
        mock_db.daily_stats = Mock()
        mock_db.user_logs = Mock()
        return mock_client

    @pytest.fixture
    def scheduler(self, mock_bot_app, mock_db_client):
        """Create a TefillinScheduler instance with mocks"""
        with patch("apscheduler.schedulers.background.BackgroundScheduler") as mock_scheduler_class:
            mock_scheduler_instance = Mock()
            mock_scheduler_class.return_value = mock_scheduler_instance
            scheduler = TefillinScheduler(mock_bot_app, mock_db_client)
            scheduler.scheduler = mock_scheduler_instance
            return scheduler

    def test_start(self, scheduler):
        """Test starting the scheduler"""
        scheduler.start()
        
        assert scheduler.scheduler.start.called
        assert scheduler.scheduler.add_job.called

    def test_stop(self, scheduler):
        """Test stopping the scheduler"""
        scheduler.stop()
        
        scheduler.scheduler.shutdown.assert_called_once_with(wait=False)

    @pytest.mark.asyncio
    async def test_check_daily_reminders(self, scheduler, mock_db_client, mock_bot_app):
        """Test checking and sending daily reminders"""
        # Setup current time
        current_time = datetime.now().strftime("%H:%M")
        
        # Mock users who should receive reminders
        mock_users = [
            {
                "user_id": 123456,
                "username": "user1",
                "daily_time": current_time,
                "is_active": True,
                "skip_next": False
            },
            {
                "user_id": 789012,
                "username": "user2",
                "daily_time": current_time,
                "is_active": True,
                "skip_next": False
            }
        ]
        
        mock_db_client.tefillin_bot.users.find.return_value = mock_users
        
        await scheduler.check_daily_reminders()
        
        # Verify that reminders were sent
        assert mock_bot_app.bot.send_message.call_count == 2
        
        # Check that skip_next was reset
        assert mock_db_client.tefillin_bot.users.update_one.called

    @pytest.mark.asyncio
    async def test_check_daily_reminders_skip(self, scheduler, mock_db_client, mock_bot_app):
        """Test skipping daily reminder when skip_next is True"""
        current_time = datetime.now().strftime("%H:%M")
        
        # Mock user with skip_next = True
        mock_users = [
            {
                "user_id": 123456,
                "username": "user1",
                "daily_time": current_time,
                "is_active": True,
                "skip_next": True
            }
        ]
        
        mock_db_client.tefillin_bot.users.find.return_value = mock_users
        
        await scheduler.check_daily_reminders()
        
        # Verify that no reminder was sent
        mock_bot_app.bot.send_message.assert_not_called()
        
        # Check that skip_next was reset
        mock_db_client.tefillin_bot.users.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_sunset_reminders(self, scheduler, mock_db_client, mock_bot_app):
        """Test checking and sending sunset reminders"""
        # Mock users with sunset reminders
        mock_users = [
            {
                "user_id": 123456,
                "username": "user1",
                "sunset_reminder": True,
                "sunset_offset": -30,
                "location": {"lat": 31.7683, "lng": 35.2137},
                "is_active": True
            }
        ]
        
        mock_db_client.tefillin_bot.users.find.return_value = mock_users
        
        # Mock hebrew_times
        with patch("scheduler.get_hebrew_times") as mock_get_times:
            mock_get_times.return_value = {
                "sunset": time(18, 30)
            }
            
            # Set current time to match reminder time
            with patch("scheduler.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime.now().replace(hour=18, minute=0)
                
                await scheduler.check_sunset_reminders()
                
                # Verify that reminder was sent
                mock_bot_app.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_daily_times(self, scheduler):
        """Test updating daily times cache"""
        with patch("scheduler.update_times_cache") as mock_update:
            await scheduler.update_daily_times()
            
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_daily_reminder(self, scheduler, mock_bot_app):
        """Test sending a daily reminder to a user"""
        user_id = 123456
        
        await scheduler.send_daily_reminder(user_id)
        
        mock_bot_app.bot.send_message.assert_called_once()
        
        # Check the message content
        call_args = mock_bot_app.bot.send_message.call_args
        assert call_args[0][0] == user_id
        assert "תפילין" in call_args[0][1]
        assert "reply_markup" in call_args[1]

    @pytest.mark.asyncio
    async def test_send_daily_reminder_error(self, scheduler, mock_bot_app):
        """Test handling error when sending daily reminder"""
        user_id = 123456
        mock_bot_app.bot.send_message.side_effect = Exception("Send failed")
        
        # Should not raise exception
        await scheduler.send_daily_reminder(user_id)
        
        mock_bot_app.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_sunset_reminder(self, scheduler, mock_bot_app):
        """Test sending a sunset reminder to a user"""
        user_id = 123456
        sunset_time = time(18, 30)
        
        await scheduler.send_sunset_reminder(user_id, sunset_time)
        
        mock_bot_app.bot.send_message.assert_called_once()
        
        # Check the message content
        call_args = mock_bot_app.bot.send_message.call_args
        assert call_args[0][0] == user_id
        assert "18:30" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_schedule_snooze_reminder(self, scheduler):
        """Test scheduling a snooze reminder"""
        user_id = 123456
        minutes = 30
        
        with patch.object(scheduler.scheduler, "add_job") as mock_add_job:
            await scheduler.schedule_snooze_reminder(user_id, minutes)
            
            mock_add_job.assert_called_once()
            
            # Check job configuration
            call_args = mock_add_job.call_args
            assert call_args[1]["trigger"] == "date"
            assert call_args[1]["id"] == f"snooze_{user_id}"

    @pytest.mark.asyncio
    async def test_send_snooze_reminder(self, scheduler, mock_bot_app):
        """Test sending a snooze reminder"""
        user_id = 123456
        
        await scheduler.send_snooze_reminder(user_id)
        
        mock_bot_app.bot.send_message.assert_called_once()
        
        # Check the message content
        call_args = mock_bot_app.bot.send_message.call_args
        assert call_args[0][0] == user_id
        assert "תזכורת נדחית" in call_args[0][1]

    def test_get_active_jobs(self, scheduler):
        """Test getting active jobs"""
        mock_jobs = [Mock(id="job1"), Mock(id="job2")]
        scheduler.scheduler.get_jobs.return_value = mock_jobs
        
        jobs = scheduler.get_active_jobs()
        
        assert jobs == mock_jobs
        scheduler.scheduler.get_jobs.assert_called_once()