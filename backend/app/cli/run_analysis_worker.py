import asyncio
import os
import selectors
import signal
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import get_settings
from app.core.logging import configure_logging


async def run() -> None:
    from app.core.database import check_database, dispose_engine, session_factory
    from app.services.analysis_worker_runtime import run_worker_forever

    settings = get_settings()
    configure_logging(settings)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except NotImplementedError:
            signal.signal(signum, lambda *_: loop.call_soon_threadsafe(stop_event.set))
    try:
        await check_database()
        await run_worker_forever(session_factory, settings, stop_event=stop_event)
    finally:
        await dispose_engine()


def _selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def main() -> None:
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    if not head:
        raise RuntimeError("image must contain one Alembic head")
    os.environ["NUTRIPILOT_REQUIRED_SCHEMA_REVISION"] = head
    loop_factory = _selector_loop if sys.platform == "win32" else None
    try:
        asyncio.run(run(), loop_factory=loop_factory)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
