import asyncio
import json
import selectors
import sys

from app.core.database import dispose_engine, session_factory
from app.services.catalog_seed import seed_global_catalog


async def run() -> None:
    async with session_factory() as session:
        result = await seed_global_catalog(session)
    print(json.dumps(result.__dict__, ensure_ascii=False))


async def run_with_cleanup() -> None:
    try:
        await run()
    finally:
        await dispose_engine()


def _selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def main() -> None:
    loop_factory = _selector_loop if sys.platform == "win32" else None
    asyncio.run(run_with_cleanup(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
