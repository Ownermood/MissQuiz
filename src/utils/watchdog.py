"""
Freeze watchdog. If the asyncio loop doesn't tick for WATCHDOG_SECS (default 120),
the bot is stuck (it stops answering everyone). Then: write every thread's stack
to the log (so we can see the exact line it was stuck on), and exit so systemd
(Restart=always) / Docker brings it back in seconds. WATCHDOG_SECS=0 turns it off.
"""

import asyncio
import faulthandler
import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

_state = {"beat": time.monotonic(), "task": None}


def limit_secs() -> int:
    try:
        return max(0, int(os.getenv("WATCHDOG_SECS", "120")))
    except ValueError:
        return 120


async def _heartbeat(every: float) -> None:
    while True:
        _state["beat"] = time.monotonic()
        await asyncio.sleep(every)


def _guard(limit: int, check_every: float, on_stuck) -> None:
    while True:
        time.sleep(check_every)
        stuck_for = time.monotonic() - _state["beat"]
        if stuck_for > limit:
            on_stuck(stuck_for)
            return


def _die(stuck_for: float) -> None:
    logger.critical(f"🧊 [WATCHDOG] bot frozen for {int(stuck_for)}s — stack of every thread below, then restart")
    try:
        sys.stderr.flush()
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        sys.stderr.flush()
    finally:
        os._exit(3)


def start(limit: int = None, beat_every: float = 5.0, check_every: float = 10.0, on_stuck=_die) -> bool:
    """Call once from inside the running loop. False = disabled."""
    limit = limit_secs() if limit is None else limit
    if limit <= 0:
        logger.info("[WATCHDOG] off (WATCHDOG_SECS=0)")
        return False
    _state["beat"] = time.monotonic()
    _state["task"] = asyncio.get_running_loop().create_task(_heartbeat(beat_every))   # strong ref kept
    threading.Thread(target=_guard, args=(limit, check_every, on_stuck),
                     name="freeze-watchdog", daemon=True).start()
    logger.info(f"🐶 [WATCHDOG] on — restarts the bot if it freezes for {limit}s")
    return True
