"""Post unhandled bot errors to a private Telegram group (LOG_CHAT_ID).

Secrets are scrubbed, the same error is posted at most once per COOLDOWN seconds,
and a failure here never raises (the error handler must not crash)."""
import html
import logging
import os
import time
import traceback
from typing import Dict, Optional

from src.core import config

logger = logging.getLogger(__name__)

COOLDOWN = 300                      # same error (type + place) → once per 5 min
_last_sent: Dict[str, float] = {}
_SECRET_ENVS = ("TELEGRAM_TOKEN", "MONGODB_URL", "ADMIN_API_KEY", "WEBHOOK_SECRET_TOKEN", "SESSION_SECRET")


def _scrub(text: str) -> str:
    for name in _SECRET_ENVS:
        val = os.environ.get(name) or ""
        if len(val) >= 8:
            text = text.replace(val, f"<{name}>")
    return text


def _where(err: BaseException) -> str:
    tb = traceback.extract_tb(err.__traceback__) if err.__traceback__ else []
    for fr in reversed(tb):
        if "/src/" in fr.filename or fr.filename.endswith("main.py"):
            return f"{fr.filename.split('/src/')[-1]}:{fr.lineno} {fr.name}"
    return f"{tb[-1].filename.rsplit('/', 1)[-1]}:{tb[-1].lineno}" if tb else "?"


def _describe(update) -> str:
    parts = []
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    if chat is not None:
        parts.append(f"Chat: {getattr(chat, 'type', '')} {getattr(chat, 'id', '')} "
                     f"{getattr(chat, 'title', '') or ''}".strip())
    if user is not None:
        parts.append(f"User: {getattr(user, 'id', '')}")
    q = getattr(update, "callback_query", None)
    if q is not None and getattr(q, "data", None):
        parts.append(f"Button: {q.data}")
    else:
        msg = getattr(update, "effective_message", None)
        txt = getattr(msg, "text", None) if msg is not None else None
        if isinstance(txt, str) and txt.startswith("/"):
            parts.append(f"Command: {txt[:80]}")
    return "\n".join(parts)


def build_text(update, err: BaseException) -> str:
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    tb = _scrub(tb)
    head = (f"🚨 <b>{html.escape(type(err).__name__)}</b>: {html.escape(_scrub(str(err))[:300])}\n"
            f"📍 <code>{html.escape(_where(err))}</code>\n")
    info = _describe(update)
    if info:
        head += f"<blockquote>{html.escape(_scrub(info))}</blockquote>\n"
    room = max(200, 3900 - len(head))
    return head + f"<pre>{html.escape(tb)[-room:]}</pre>"       # keep the end (where it failed), under 4096


async def post_error(bot, update, err: Optional[BaseException]) -> bool:
    """True if a log message was sent."""
    chat_id = config.LOG_CHAT_ID
    if not chat_id or bot is None or err is None:
        return False
    key = f"{type(err).__name__}|{_where(err)}"
    now = time.monotonic()
    if now - _last_sent.get(key, -COOLDOWN) < COOLDOWN:
        return False
    _last_sent[key] = now
    try:
        await bot.send_message(chat_id, build_text(update, err), parse_mode="HTML",
                               disable_web_page_preview=True)
        return True
    except Exception as e:                           # bad LOG_CHAT_ID / bot not in group: just log locally
        logger.warning(f"[ERRLOG] could not post to log chat: {e}")
        return False
