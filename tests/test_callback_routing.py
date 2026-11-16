"""Every callback prefix reaches its own handler (PTB runs only the first match per group)."""
from unittest.mock import MagicMock

from telegram import CallbackQuery, Update, User
from telegram.ext import CallbackQueryHandler

from src.bot.handlers_main import TelegramQuizBot


def first_match(data):
    b = TelegramQuizBot(MagicMock(), db_manager=MagicMock())
    added = []
    b.application = MagicMock()
    b.application.add_handler.side_effect = lambda h, group=0: added.append((group, h))
    b._register_handlers()
    u = Update(1, callback_query=CallbackQuery("1", User(1, "a", False), "i", data=data))
    for g, h in added:
        if g == 0 and isinstance(h, CallbackQueryHandler) and h.check_update(u):
            return h.callback.__name__


def test_edit_quiz_buttons_reach_the_editor():
    assert first_match("edit_quiz_list_2") == "handle_edit_quiz_callback"
    assert first_match("edit_quiz_cancel") == "handle_edit_quiz_callback"


def test_other_buttons_unchanged():
    assert first_match("play_quiz") == "handle_callback"
    assert first_match("nav_home") == "handle_callback"
    assert first_match("gq|pause|-1") == "handle_group_quiz_callback"
    assert first_match("ap:open") == "handle_admin_panel_callback"
