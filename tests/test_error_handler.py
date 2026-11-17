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


def _boom():
    try:
        raise RuntimeError("db at mongodb://user:supersecret@host failed")
    except RuntimeError as e:
        return e


async def test_error_posted_to_log_chat_scrubbed_and_rate_limited(monkeypatch):
    from src.bot import error_log
    from src.core import config
    monkeypatch.setattr(config, "LOG_CHAT_ID", -100123)
    monkeypatch.setenv("MONGODB_URL", "mongodb://user:supersecret@host")
    error_log._last_sent.clear()
    bot = SimpleNamespace(send_message=AsyncMock())
    u = SimpleNamespace(effective_chat=SimpleNamespace(type="supergroup", id=-1005, title="QV"),
                        effective_user=SimpleNamespace(id=42),
                        callback_query=SimpleNamespace(data="gq|launch|-1005"), effective_message=None)
    err = _boom()
    assert await error_log.post_error(bot, u, err) is True
    chat, text = bot.send_message.await_args.args
    assert chat == -100123 and "supersecret" not in text and "&lt;MONGODB_URL&gt;" in text
    assert "gq|launch|-1005" in text and "RuntimeError" in text and len(text) < 4096
    assert await error_log.post_error(bot, u, err) is False            # same error again → skipped
    assert bot.send_message.await_count == 1


async def test_no_log_chat_or_send_failure_never_raises(monkeypatch):
    from src.bot import error_log
    from src.core import config
    error_log._last_sent.clear()
    monkeypatch.setattr(config, "LOG_CHAT_ID", None)
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("chat not found")))
    assert await error_log.post_error(bot, None, _boom()) is False
    monkeypatch.setattr(config, "LOG_CHAT_ID", -100123)
    assert await error_log.post_error(bot, None, _boom()) is False
