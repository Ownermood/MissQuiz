"""Group quiz fixes: names (double-escape, blank fillers), long options, compact history, next part."""

import bson

import src.bot.group_quiz as gq
from src.bot.group_quiz import Session, _short
from src.bot.ui import UI
from tests.test_group_quiz import (App, GROUP, answer_all, ctx, fast, press, questions,  # noqa: F401
                                   user, wait_done)


def test_names_not_double_escaped_and_fillers_removed():
    assert UI.mention(5, "Mimii&gt;&gt;Δ") == '<a href="tg://user?id=5">Mimii&gt;&gt;Δ</a>'
    assert UI.mention(5, "Mimii>>Δ") == '<a href="tg://user?id=5">Mimii&gt;&gt;Δ</a>'
    assert UI.clean_name("🦦" + "ㅤ" * 40) == "🦦"                # Hangul filler made giant rows
    assert UI.clean_name("⠀​ ") == "Player"
    assert UI.clean_name("x" * 60).endswith("…") and len(UI.clean_name("x" * 60)) == 32
    assert UI.clean_name("👨‍👩‍👧 Fam") == "👨‍👩‍👧 Fam"   # emoji ZWJ kept


def test_rich_table_name_escaped_once():
    s = Session(chat_id=GROUP, chat_title="G", title="T", questions=questions(2), secs=10,
                started_by=1, starter_name="H", idx=2)
    s.scores["9"] = {"name": "Mimii>>Δ" + "ㅤ" * 30, "correct": 2, "wrong": 0, "score": 2, "time": 3}
    out = gq.GroupQuizMixin._gq_result_rich_html(App(), s, False)
    assert "Mimii&gt;&gt;Δ</a>" in out and "&amp;gt;" not in out and "ㅤ" not in out


def test_short_cuts_on_word():
    t = _short("A) " + "word " * 40, 100)
    assert len(t) <= 100 and t.endswith("…") and not t.endswith(" …")


async def test_long_options_full_text_card_and_lettered_poll_options():
    app = App()
    c, polls, sent = ctx(admins=(1,))
    long_opt = "The International Cricket Council (ICC) is headquartered in Dubai and represents 108 member countries"
    qs = [{"question": "Which is incorrect?", "options": [long_opt + " worldwide today", "short"],
           "correct_answer": 1}] * 3
    sid = app.real.create_quiz_set(1, "Cricket", qs, 20)
    await press(app, c, user(1), f"gq|set|1|{sid}")
    gq.ACTIVE[GROUP].secs = 0.02
    await wait_done()
    card = next(t for t in sent if t.startswith("❓ <b>Q1/3"))
    assert "member countries worldwide today" in card and "<b>A)</b>" in card
    opts = polls[0][1]["options"]
    assert all(len(o) <= 100 for o in opts) and opts[0].startswith("A) ") and opts[1] == "B) short"
    assert polls[0][1]["question"].endswith("Which is incorrect?")    # short question stays in poll


async def test_short_options_unchanged_no_card():
    app = App()
    c, polls, sent = ctx(admins=(1,))
    await press(app, c, user(1), "gq|bot|1|10")
    gq.ACTIVE[GROUP].secs = 0.01
    await answer_all(app, polls, {7: 0}, 10)
    await wait_done()
    assert polls[0][1]["options"] == ["right", "wrong"] and not any(t.startswith("❓") for t in sent)


def test_history_compact_and_saved_doc_small():
    qs = [{"question": "Q" * 280, "options": ["o" * 100] * 4, "correct_answer": 2,
           "explanation": "e" * 200} for _ in range(200)]
    s = Session(chat_id=GROUP, chat_title="G", title="T", questions=qs, secs=10, started_by=1)
    for i in range(200):
        s.polls[f"p{i}"] = (i, 2, 0.0)
    for uid in range(120):
        for i in range(200):
            s.record(f"p{i}", uid, f"P{uid}", [i % 4])
    size = len(bson.encode(s.to_doc()))
    assert size < 2_000_000, size                     # was ~14 MB → near Mongo's 16 MB limit
    item = s.history_item(s.user_history["3"][1])
    assert item["selected"] == "o" * 100 and item["correct"] == "o" * 100 and item["is_correct"] is False
    assert item["question"] == "Q" * 280 and item["explanation"] == "e" * 200
    old = {"q_num": 1, "question": "old", "selected": "a", "correct": "b", "is_correct": False}
    assert s.history_item(old) is old                 # sessions saved before the update still work


async def test_next_part_after_middle_part_points_after_it():
    app = App()
    c, polls, sent = ctx(admins=(1,))
    sid = app.real.create_quiz_set(1, "Bank", questions(80), 20)
    await press(app, c, user(1), f"gq|part|1|{sid}|25|25")              # Q26–Q50
    s = gq.ACTIVE[GROUP]
    assert s.part_start == 25 and "Q26–Q50" in s.title
    s.secs = 0.01
    await answer_all(app, polls, {7: 0}, 25)
    await wait_done()
    kb = c.bot.send_message.await_args.kwargs["reply_markup"]
    assert kb.inline_keyboard[0][0].text == "▶️ Next part · from Q51"


async def test_plain_start_in_group_admin_gets_picker_member_does_not():
    """'Host in Group' when the bot is already in the group: Telegram sends just /start."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from src.bot.handlers_main import TelegramQuizBot
    from tests.test_group_quiz import group_upd
    b = TelegramQuizBot(MagicMock(), db_manager=MagicMock())
    b.application = MagicMock()
    b.cmd_startquiz = AsyncMock()
    c, _, _ = ctx(admins=(1,))
    upd = group_upd(user(1))
    upd.message = SimpleNamespace(text="/start@MissQuiz_Bot", sender_chat=None)
    await b.cmd_start(upd, c)
    b.cmd_startquiz.assert_awaited_once()
    b.cmd_startquiz.reset_mock()
    upd2 = group_upd(user(2))                                    # normal member → normal /start
    upd2.message = SimpleNamespace(text="/start", sender_chat=None)
    try:
        await b.cmd_start(upd2, c)
    except Exception:
        pass                                                     # welcome card needs more mocks
    b.cmd_startquiz.assert_not_awaited()


async def test_pause_resume_commands_and_quick_resume_does_not_skip():
    from tests.test_group_quiz import group_upd
    app = App()
    c, polls, sent = ctx(admins=(1,))
    await press(app, c, user(1), "gq|bot|1|10")
    s = gq.ACTIVE[GROUP]
    s.secs = 0.3
    for _ in range(200):
        if polls:
            break
        await __import__("asyncio").sleep(0.005)
    await app.cmd_pausequiz(group_upd(user(5)), c)                 # member: no
    assert "Only the quiz host" in app.replies[-1][0] and s.status == "running"
    await app.cmd_pausequiz(group_upd(user(1)), c)
    assert s.status == "paused" and "paused" in app.replies[-1][0]
    await app.cmd_resumequiz(group_upd(user(1)), c)                # quick resume while Q1 is open
    assert s.status == "running" and not s.wake.is_set()            # Q1 not cut short
    await app.cmd_pausequiz(group_upd(user(1)), c)
    await __import__("asyncio").sleep(0.6)                         # loop now waits in pause
    n = len(polls)
    assert s.in_pause_wait
    await __import__("asyncio").sleep(0.4)
    assert len(polls) == n                                          # nothing sent while paused
    await app.cmd_resumequiz(group_upd(user(1)), c)
    await __import__("asyncio").sleep(0.2)
    assert len(polls) == n + 1                                      # continues
    s.status = "stopped"; s.wake.set()
    await wait_done()
    await app.cmd_resumequiz(group_upd(user(1)), c)
    assert "No quiz is running" in app.replies[-1][0]


def test_explanation_cut_on_word():
    t = _short("ICC ka headquarter Dubai mein hai aur iske 108 members " * 6, 200)
    assert len(t) <= 200 and t.endswith("…") and t[-2] != " "


async def test_stopquiz_in_lobby_clears_saved_session(monkeypatch):
    from unittest.mock import AsyncMock
    from tests.test_group_quiz import group_upd
    monkeypatch.setattr(gq, "USE_LOBBY", True)
    monkeypatch.setattr(gq, "LOBBY_TIMEOUT", 0)
    app = App()
    c, polls, sent = ctx(admins=(1,))
    c.bot.pin_chat_message = AsyncMock()
    c.bot.unpin_chat_message = AsyncMock()
    await press(app, c, user(1), "gq|bot|1|10")
    assert app.real.list_quiz_sessions()                         # lobby saved
    await app.cmd_stopquiz(group_upd(user(1)), c)
    assert GROUP not in gq.ACTIVE and app.real.list_quiz_sessions() == []
    c.bot.unpin_chat_message.assert_awaited_once()
    assert "cancelled" in app.replies[-1][0]


async def test_next_part_button_works_after_restart():
    app = App()
    c, polls, sent = ctx(admins=(1,))
    sid = app.real.create_quiz_set(1, "Bank", questions(80), 20)
    assert not getattr(app, "_gq_last", None)                     # fresh process, nothing in memory
    await press(app, c, user(1), f"gq|next|{GROUP}|25|25|{sid}")
    s = gq.ACTIVE[GROUP]
    assert s.part_start == 25 and "Q26–Q50" in s.title


def _app_with_db():
    import mongomock
    app = App()
    client = mongomock.MongoClient()
    real = app.real
    real.quiz_schedules_col = client.db.quiz_schedules
    for fn in ("get_quiz_session", "find_last_quiz_session_of", "save_quiz_schedule",
               "list_quiz_schedules", "delete_quiz_schedule"):
        setattr(app.db, fn, getattr(real, fn))
    return app


async def test_play_again_and_result_work_after_restart():
    from types import SimpleNamespace
    app = _app_with_db()
    c, polls, sent = ctx(admins=(1,))
    await press(app, c, user(1), "gq|bot|1|10")
    gq.ACTIVE[GROUP].secs = 0.01
    await answer_all(app, polls, {7: 1}, 10)                          # P7 answers all wrong
    await wait_done()
    doc = app.real.get_quiz_session(GROUP)
    assert doc and doc["status"] == "done" and "7" in doc["scores"]
    assert app.real.list_quiz_sessions() == []                       # finished quiz is not resumed
    app._gq_last.clear()                                             # ← restart
    last = await app._gq_last_get(GROUP)
    assert last and len(last.questions) == 10
    # /result in DM finds it in the DB
    app._gq_last.clear()
    upd = SimpleNamespace(effective_user=user(7, "P7"), effective_chat=SimpleNamespace(id=7, type="private"),
                          effective_message=SimpleNamespace(sender_chat=None))
    await app.cmd_result(upd, c)
    assert "Questions you missed" in app.replies[-1][0]
    # Play again after restart
    app._gq_last.clear()
    await press(app, c, user(1), f"gq|again|{GROUP}")
    assert gq.is_active(GROUP) and len(gq.ACTIVE[GROUP].questions) == 10


async def test_schedule_uses_ist_saves_and_rearms_after_restart(monkeypatch):
    import asyncio
    from datetime import datetime
    from tests.test_group_quiz import group_upd
    app = _app_with_db()
    c, polls, sent = ctx(admins=(1,))
    c.args = ["21:00", "bot10"]
    await app.cmd_schedule(group_upd(user(1)), c)
    docs = app.real.list_quiz_schedules(GROUP)
    assert len(docs) == 1
    when = datetime.fromtimestamp(docs[0]["at"], gq.SCHED_TZ)
    assert (when.hour, when.minute) == (21, 0) and str(gq.SCHED_TZ) == "Asia/Kolkata"
    c.args = ["cancel"]
    await app.cmd_schedule(group_upd(user(1)), c)
    assert app.real.list_quiz_schedules(GROUP) == [] and "1 scheduled" in app.replies[-1][0]
    # saved schedule due now → re-armed after a restart → quiz opens
    import time as _t
    app.real.save_quiz_schedule({"id": "s1", "chat_id": GROUP, "thread_id": None, "set_id": "bot10",
                                 "at": _t.time() - 5, "by": 1, "by_name": "Admin"})
    app.real.save_quiz_schedule({"id": "old", "chat_id": GROUP, "thread_id": None, "set_id": "bot10",
                                 "at": _t.time() - 7200, "by": 1, "by_name": "Admin"})
    assert await app.gq_resume_schedules(c.bot) == 1
    for _ in range(100):
        if gq.is_active(GROUP):
            break
        await asyncio.sleep(0.01)
    assert gq.is_active(GROUP) and app.real.list_quiz_schedules() == []
    c.args = ["in", "5m"]
    await app.cmd_schedule(group_upd(user(2)), c)                     # member can't
    assert "Only group admins" in app.replies[-1][0]


def test_fit_poll_rules():
    from src.bot.ui import fit_poll
    card, q, o = fit_poll("[1/2] ", "Short?", ["a", "b"])
    assert card is None and q == "[1/2] Short?" and o == ["a", "b"]
    card, q, o = fit_poll("[1/2] ", "W " * 200, ["a", "b"])
    assert card and q.endswith("Read the question above ⬆️") and o == ["a", "b"] and len(q) <= 300
    card, q, o = fit_poll("[1/2] ", "Q?", ["x " * 80, "b"])
    assert "<b>A)</b>" in card and all(len(x) <= 100 for x in o) and o[1] == "B) b"


async def test_battle_long_option_sends_card_then_poll():
    from src.bot.battle import Battle
    app = App()
    c, polls, sent = ctx()
    b = Battle.__new__(Battle)
    b.__dict__.update(id="b1", mode="group", chat_id=GROUP, thread_id=None, n_q=1, secs=10,
                      players=[1, 2], rounds={})
    app._battle_polls = {}
    q = {"question": "Which?", "options": ["long " * 30, "short"], "correct_answer": 1}
    rounds = await app._bt_send_question(b, c, q, 1)
    assert rounds and any("<b>A)</b>" in t for t in sent)
    assert all(len(x) <= 100 for x in polls[0][1]["options"])


async def test_leaderboard_every_n_old_one_deleted_and_lobby_toggle(monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(gq, "LB_EVERY", 5)
    app = App()
    c, polls, sent = ctx(admins=(1,))
    c.bot.delete_message = AsyncMock()
    await press(app, c, user(1), "gq|bot|1|20")
    s = gq.ACTIVE[GROUP]
    assert s.show_board is True                                    # default ON
    s.secs = 0.01
    await answer_all(app, polls, {7: 0}, 20)
    await wait_done()
    boards = [t for t in sent if "After" in t and "questions" in t]
    assert len(boards) == 3                                         # after 5, 10, 15 (not 20 = final)
    # every board deleted when the next came, the last one when the result came
    assert c.bot.delete_message.await_count == 3


async def test_leaderboard_off_in_lobby(monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(gq, "LB_EVERY", 5)
    monkeypatch.setattr(gq, "USE_LOBBY", True)
    monkeypatch.setattr(gq, "LOBBY_TIMEOUT", 0)
    app = App()
    c, polls, sent = ctx(admins=(1,))
    c.bot.pin_chat_message = AsyncMock()
    await press(app, c, user(1), "gq|bot|1|10")
    q = await press(app, c, user(1), f"gq|lset|{GROUP}")
    kb = q.message.edit_text.await_args.kwargs["reply_markup"]
    assert any("Leaderboard every 5 Q" in b.text and b.text.startswith("✅")
               for r in kb.inline_keyboard for b in r)
    await press(app, c, user(1), f"gq|tog_lb|{GROUP}")
    s = gq.ACTIVE[GROUP]
    assert s.show_board is False and Session.from_doc(s.to_doc()).show_board is False
    await press(app, c, user(1), f"gq|launch|{GROUP}")
    s.secs = 0.01
    await answer_all(app, polls, {7: 0}, 10)
    await wait_done()
    assert not any("After" in t and "questions" in t for t in sent)


def test_rich_result_all_113_players_and_emoji_only_name(monkeypatch):
    monkeypatch.setenv("PREMIUM_EMOJI", "1")
    from src.bot.premium import premiumize_html
    s = Session(chat_id=GROUP, chat_title="G", title="T", questions=questions(200), secs=15, started_by=1, idx=200)
    for i in range(113):
        uid = 5000000000 + i * 7919
        s.scores[str(uid)] = {"name": "🎀🖤" if i == 2 else f"Player 🔥 {i}", "correct": 200 - i,
                              "wrong": i, "score": 200 - i, "time": 900}
    out = gq.GroupQuizMixin._gq_result_rich_html(App(), s, False)
    assert "more players" not in out                                  # all 113 listed (was 96)
    assert "113. " in out and len(premiumize_html(out)) < 32768
    third = str(5000000000 + 2 * 7919)[-3:]
    assert f"🎀🖤 #{third}" in out                                     # emoji-only name gets text


async def test_html_report_offline_charts_and_stat_tiles():
    from src.utils.quiz_report import render_analysis_html
    res = [{"user_id": i, "user_name": f"P{i}", "score": 179.0 - i, "total_questions": 200, "time_taken": 60}
           for i in range(15)]
    b, _ = await render_analysis_html(
        {"quiz_name": "Q", "qid": "x", "questions": [{"question": "q", "options": ["a", "b"], "correct_answer": 0}] * 200},
        res)
    page = b.decode()
    assert "<svg" in page and "Chart.js" not in page and "<canvas" not in page     # works offline
    assert ".stat-grid" in page and "179 pts" in page and "179.0 pts" not in page
