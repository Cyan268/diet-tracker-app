import argparse
import asyncio
import logging
import selectors
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.upload_storage import LocalPrivateUploadStore
from app.services.uploads import cleanup_expired_uploads

logger = logging.getLogger("nutripilot.upload_cleanup")


async def run(limit: int) -> None:
    from app.core.database import check_database, dispose_engine, session_factory

    settings = get_settings()
    configure_logging(settings)
    try:
        await check_database()
        async with session_factory() as session:
            result = await cleanup_expired_uploads(
                session,
                LocalPrivateUploadStore(settings.upload_root),
                limit=limit,
            )
        logger.info(
            "upload_cleanup_completed selected=%s deleted=%s failed=%s",
            result.selected,
            result.deleted,
            result.failed,
        )
        if result.failed:
            raise RuntimeError("one or more upload objects could not be deleted")
    finally:
        await dispose_engine()


def _selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete expired private upload objects")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 1000:
        parser.error("--limit must be between 1 and 1000")
    loop_factory = _selector_loop if sys.platform == "win32" else None
    asyncio.run(run(args.limit), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
