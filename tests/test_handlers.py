"""Tests for bot handlers"""

import asyncio
import os
import sys
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Chat, Message, Update, User

from handlers import TefillinHandlers as Handlers


class TestHandlers:
    """Test cases for Handlers class"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        mock = Mock()
        mock.get_user = Mock(return_value=None)
        mock.create_user = Mock()
        mock.set_reminder = Mock()
        mock.get_reminder = Mock(return_value=None)
        mock.delete_reminder = Mock()
        mock.log_action = Mock()
        return mock

    @pytest.fixture
    def mock_scheduler(self):
        """Create a mock scheduler"""
        mock = Mock()
        mock.add_reminder = Mock()
        mock.remove_reminder = Mock()
        return mock

    @pytest.fixture
    def handlers(self, mock_db, mock_scheduler):
        """Create handlers instance with mocks"""
        return Handlers(mock_db, mock_scheduler)

    @pytest.fixture
    def mock_update(self):
        """Create a mock update object"""
        update = Mock(spec=Update)
        update.effective_user = Mock(spec=User)
        update.effective_user.id = 123456
        update.effective_user.username = "testuser"
        update.effective_user.first_name = "Test"

        update.effective_chat = Mock(spec=Chat)
        update.effective_chat.id = 123456

        update.message = Mock(spec=Message)
        update.message.text = "/start"
        update.message.reply_text = AsyncMock()
        update.message.reply_html = AsyncMock()

        update.callback_query = None

        return update

    @pytest.fixture
    def mock_context(self):
        """Create a mock context object"""
        context = Mock()
        context.bot = Mock()
        context.bot.send_message = AsyncMock()
        context.user_data = {}
        return context

    @pytest.mark.asyncio
    async def test_start_command(self, handlers, mock_update, mock_context, mock_db):
        """Test /start command handler"""
        await handlers.start(mock_update, mock_context)

        # Verify user was created
        mock_db.create_user.assert_called_once_with(123456, "testuser")

        # Verify welcome message was sent
        mock_update.message.reply_html.assert_called_once()
        assert "ברוך הבא" in mock_update.message.reply_html.call_args[0][0]

    @pytest.mark.asyncio
    async def test_help_command(self, handlers, mock_update, mock_context):
        """Test /help command handler"""
        await handlers.help_command(mock_update, mock_context)

        # Verify help message was sent
        mock_update.message.reply_text.assert_called_once()
        assert "פקודות זמינות" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_status_command(self, handlers, mock_update, mock_context, mock_db):
        """Test /status command handler"""
        # Setup mock reminders
        mock_db.get_reminder.side_effect = [{"time": "08:00", "active": True}, None]  # morning reminder  # evening reminder

        await handlers.status(mock_update, mock_context)

        # Verify status message was sent
        mock_update.message.reply_text.assert_called_once()
        status_text = mock_update.message.reply_text.call_args[0][0]
        assert "📊 הסטטוס שלך" in status_text
        assert "08:00" in status_text

    @pytest.mark.asyncio
    async def test_cancel_command(self, handlers, mock_update, mock_context):
        """Test /cancel command handler"""
        from telegram.ext import ConversationHandler

        result = await handlers.cancel(mock_update, mock_context)

        assert result == ConversationHandler.END
        mock_update.message.reply_text.assert_called_once()
        assert "הפעולה בוטלה" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_broadcast_admin_only(self, handlers, mock_update, mock_context):
        """Test broadcast command for non-admin user"""
        mock_update.effective_user.id = 999999  # Non-admin user

        await handlers.broadcast(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "אין לך הרשאה" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_stats_admin_only(self, handlers, mock_update, mock_context):
        """Test stats command for non-admin user"""
        mock_update.effective_user.id = 999999  # Non-admin user

        await handlers.stats(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "אין לך הרשאה" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_validate_time_valid(self, handlers):
        """Test time validation with valid time"""
        assert handlers.validate_time("08:30") == True
        assert handlers.validate_time("23:59") == True
        assert handlers.validate_time("00:00") == True

    @pytest.mark.asyncio
    async def test_validate_time_invalid(self, handlers):
        """Test time validation with invalid time"""
        assert handlers.validate_time("25:00") == False
        assert handlers.validate_time("08:60") == False
        assert handlers.validate_time("8:30") == False
        assert handlers.validate_time("not_a_time") == False

    @pytest.mark.asyncio
    async def test_send_reminder(self, handlers, mock_context):
        """Test sending reminder to user"""
        user_id = 123456
        reminder_type = "morning"

        with patch("handlers.Application") as mock_app:
            mock_app.get_application.return_value.bot = mock_context.bot

            await handlers.send_reminder(user_id, reminder_type)

            mock_context.bot.send_message.assert_called_once()
            call_args = mock_context.bot.send_message.call_args
            assert call_args[1]["chat_id"] == user_id
            assert "תזכורת" in call_args[1]["text"]
