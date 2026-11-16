"""
Separate worker pool for heavy CPU work (reading PDFs/DOCX, parsing 1000-question files).

asyncio.to_thread() uses ONE shared pool (min(32, CPUs + 4) threads; 6 on a 2-core VPS) for
everything, including the quick MongoDB writes of poll answers and the group-quiz save.
A few big files parsed at once filled that pool, so answers and the running quiz had to
wait: the bot looked frozen. Heavy jobs now queue here (2 at a time) instead.
"""

import asyncio
import functools
import os
from concurrent.futures import ThreadPoolExecutor

_POOL = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("HEAVY_WORKERS", "2") or 2)),
                           thread_name_prefix="heavy")


async def run_heavy(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_POOL, functools.partial(fn, *args, **kwargs))
