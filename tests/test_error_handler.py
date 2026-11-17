"""Global error handler: a failed button press never posts 'Something went wrong' in the group."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update
from telegram.error import BadRequest

from src.bot.handlers_main import TelegramQuizBot

pytestmark = pytest.mark.asyncio


def _upd(callback: bool):
    u = MagicMock(spec=Update)
    msg = SimpleNamespace(reply_text=AsyncMock())
    u.effective_message = msg
    u.callback_query = SimpleNamespace(answer=AsyncMock()) if callback else None
    return u, msg


async def test_callback_error_is_popup_not_group_message():
    u, msg = _upd(True)
    await TelegramQuizBot._global_error_handler(None, u, SimpleNamespace(error=RuntimeError("boom")))
    msg.reply_text.assert_not_awaited()
    assert u.callback_query.answer.await_args.kwargs.get("show_alert") is True


async def test_old_query_is_silent():
    u, msg = _upd(True)
    await TelegramQuizBot._global_error_handler(None, u, SimpleNamespace(error=BadRequest("Query is too old and response timeout expired")))
    msg.reply_text.assert_not_awaited()
    u.callback_query.answer.assert_not_awaited()


async def test_command_error_still_replies():
    u, msg = _upd(False)
    await TelegramQuizBot._global_error_handler(None, u, SimpleNamespace(error=RuntimeError("boom")))
    msg.reply_text.assert_awaited()
