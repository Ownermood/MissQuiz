import asyncio
import time

from src.utils import watchdog


async def test_watchdog_fires_only_when_loop_is_blocked():
    fired = []
    assert watchdog.start(limit=1, beat_every=0.1, check_every=0.1, on_stuck=fired.append)
    await asyncio.sleep(1.5)                    # loop healthy → heartbeat keeps going
    assert fired == []
    time.sleep(1.6)                             # block the loop like a stuck handler
    await asyncio.sleep(0.3)
    assert fired and fired[0] > 1
    watchdog._state["task"].cancel()


def test_watchdog_off_with_zero(monkeypatch):
    monkeypatch.setenv("WATCHDOG_SECS", "0")
    assert watchdog.limit_secs() == 0
    monkeypatch.setenv("WATCHDOG_SECS", "abc")
    assert watchdog.limit_secs() == 120
