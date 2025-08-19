"""Tests for handlers module"""

import asyncio
import os
import sys
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from telegram import Chat, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, User

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handlers import TefillinHandlers


class TestTefillinHandlers:
    """Test cases for TefillinHandlers class"""

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
    def mock_scheduler(self):
        """Create a mock scheduler"""
        return Mock()

    @pytest.fixture
    def handlers(self, mock_db_client, mock_scheduler):
        """Create a TefillinHandlers instance with mocks"""
        return TefillinHandlers(mock_db_client, mock_scheduler)

    @pytest.fixture
    def mock_update(self):
        """Create a mock update object"""
        update = Mock(spec=Update)
        update.effective_user = Mock(spec=User)
        update.effective_user.id = 123456
        update.effective_user.first_name = "Test"
        update.effective_user.username = "testuser"
        
        update.message = Mock(spec=Message)
        update.message.chat = Mock(spec=Chat)
        update.message.chat.id = 123456
        update.message.reply_text = AsyncMock()
        
        update.callback_query = Mock()
        update.callback_query.data = "test_data"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.callback_query.message = update.message
        
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
    async def test_handle_snooze_callback_regular(self, handlers, mock_update, mock_context):
        """Test handling regular snooze callback"""
        mock_update.callback_query.data = "snooze_30"
        
        await handlers.handle_snooze_callback(mock_update, mock_context)
        
        mock_update.callback_query.answer.assert_called_once()
        assert "30 דקות" in mock_update.callback_query.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_snooze_callback_custom(self, handlers, mock_update, mock_context):
        """Test handling custom snooze callback"""
        mock_update.callback_query.data = "snooze_custom"
        
        await handlers.handle_snooze_callback(mock_update, mock_context)
        
        mock_update.callback_query.edit_message_text.assert_called_once()
        assert "כמה דקות" in mock_update.callback_query.edit_message_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_snooze_callback_sunset(self, handlers, mock_update, mock_context, mock_db_client):
        """Test handling snooze until sunset callback"""
        mock_update.callback_query.data = "snooze_sunset"
        
        # Mock database response
        mock_db_client.tefillin_bot.users.find_one.return_value = {
            "user_id": 123456,
            "location": {"lat": 31.7683, "lng": 35.2137}
        }
        
        # Mock hebrew_times module
        with patch("handlers.get_hebrew_times") as mock_get_times:
            mock_get_times.return_value = {
                "sunset": time(18, 30)
            }
            
            await handlers.handle_snooze_callback(mock_update, mock_context)
            
            mock_update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_settings_callback_time(self, handlers, mock_update, mock_context):
        """Test handling time settings callback"""
        mock_update.callback_query.data = "settings_time"
        
        await handlers.handle_settings_callback(mock_update, mock_context)
        
        mock_update.callback_query.edit_message_text.assert_called_once()
        # Check that time buttons are shown
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert "בחר שעה" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_settings_callback_sunset(self, handlers, mock_update, mock_context, mock_db_client):
        """Test handling sunset settings callback"""
        mock_update.callback_query.data = "settings_sunset"
        
        # Mock database response
        mock_db_client.tefillin_bot.users.find_one.return_value = {
            "user_id": 123456,
            "sunset_reminder": False
        }
        
        await handlers.handle_settings_callback(mock_update, mock_context)
        
        mock_update.callback_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_settings_callback_stats(self, handlers, mock_update, mock_context, mock_db_client):
        """Test handling stats callback"""
        mock_update.callback_query.data = "settings_stats"
        
        # Mock database response
        mock_db_client.tefillin_bot.users.find_one.return_value = {
            "user_id": 123456,
            "username": "testuser",
            "daily_time": "08:00",
            "created_at": datetime.now(),
            "total_reminders_sent": 10,
            "last_reminder_sent": datetime.now()
        }
        
        await handlers.handle_settings_callback(mock_update, mock_context)
        
        mock_update.callback_query.edit_message_text.assert_called_once()
        # Check that stats are shown
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert "📊" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_custom_time_input_valid(self, handlers, mock_update, mock_context, mock_db_client):
        """Test handling valid custom time input"""
        mock_update.message.text = "09:30"
        mock_context.user_data = {"awaiting_time": True}
        
        # Mock database update
        mock_db_client.tefillin_bot.users.update_one.return_value = Mock(modified_count=1)
        
        result = await handlers.handle_custom_time_input(mock_update, mock_context)
        
        assert result == -1  # ConversationHandler.END
        mock_update.message.reply_text.assert_called()
        assert "09:30" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_custom_time_input_invalid(self, handlers, mock_update, mock_context):
        """Test handling invalid custom time input"""
        mock_update.message.text = "25:99"
        mock_context.user_data = {"awaiting_time": True}
        
        result = await handlers.handle_custom_time_input(mock_update, mock_context)
        
        assert result == 0  # Stay in same state
        mock_update.message.reply_text.assert_called()
        assert "לא תקינה" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_cancel_conversation(self, handlers, mock_update, mock_context):
        """Test canceling conversation"""
        result = await handlers.cancel_conversation(mock_update, mock_context)
        
        assert result == -1  # ConversationHandler.END
        mock_update.message.reply_text.assert_called()

    @pytest.mark.asyncio
    async def test_handle_skip_today(self, handlers, mock_update, mock_context, mock_db_client):
        """Test handling skip today command"""
        # Mock database update
        mock_db_client.tefillin_bot.users.update_one.return_value = Mock(modified_count=1)
        
        await handlers.handle_skip_today(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called()
        assert "דילגנו" in mock_update.message.reply_text.call_args[0][0]

    def test_get_conversation_handler(self, handlers):
        """Test getting conversation handler"""
        conv_handler = handlers.get_conversation_handler()
        
        assert conv_handler is not None
        assert len(conv_handler.entry_points) > 0
        assert len(conv_handler.states) > 0
        assert len(conv_handler.fallbacks) > 0

    @pytest.mark.asyncio
    async def test_handle_custom_time_callback(self, handlers, mock_update, mock_context):
        """Test handling custom time callback"""
        mock_update.callback_query.data = "custom_time"
        mock_context.user_data = {}
        
        result = await handlers.handle_custom_time_callback(mock_update, mock_context)
        
        assert result == 0  # AWAITING_TIME state
        assert mock_context.user_data["awaiting_time"] is True
        mock_update.callback_query.edit_message_text.assert_called_once()