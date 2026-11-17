"""Group gets told when auto quiz turns on/off with the bot's admin status."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.bot.tracking import TrackingMixin


class Bot(TrackingMixin):
    def __init__(self):
        self.db = MagicMock()
        self._seen_groups = set()
        self.ensure_group_registered = MagicMock()


def upd(old, new):
    chat = SimpleNamespace(id=-100, type="supergroup", title="G")
    nm = SimpleNamespace(status=new)
    return SimpleNamespace(my_chat_member=SimpleNamespace(
        chat=chat, old_chat_member=SimpleNamespace(status=old), new_chat_member=nm))


@pytest.mark.parametrize("old,new,expect", [
    ("left", "member", "paused"),             # added without admin
    ("member", "administrator", "ON"),        # promoted
    ("left", "administrator", "ON"),          # added directly as admin
    ("administrator", "member", "paused"),    # demoted
    ("member", "restricted", None),           # no note
])
async def test_admin_status_note(old, new, expect):
    bot = Bot()
    ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    await bot.handle_my_chat_member(upd(old, new), ctx)
    bot.db.update_group_admin_status.assert_called_once()
    assert bot.db.update_group_admin_status.call_args.args[1] is (new == "administrator")
    if expect:
        assert expect in ctx.bot.send_message.call_args.args[1]
    else:
        ctx.bot.send_message.assert_not_awaited()


async def test_startup_recovery_remembers_left_groups():
    """A group the bot left is checked once; the next restart doesn't call Telegram for it again."""
    from telegram.error import Forbidden
    from src.bot.tracking import RECOVERY_GONE_KEY
    store = {}
    b = Bot()
    b.db.get_known_group_ids_from_history.return_value = {-1, -2}
    b.db.get_registered_group_ids.return_value = set()
    b.db.get_setting.side_effect = lambda k, d=None: store.get(k, d)
    b.db.set_setting.side_effect = lambda k, v: store.__setitem__(k, v)
    get_chat = AsyncMock(side_effect=Forbidden("bot was kicked"))
    b.application = SimpleNamespace(bot=SimpleNamespace(get_chat=get_chat))
    await b.recover_groups_from_history()
    assert get_chat.await_count == 2 and store[RECOVERY_GONE_KEY] == [-2, -1]
    get_chat.reset_mock()
    await b.recover_groups_from_history()                 # next restart
    get_chat.assert_not_awaited()
