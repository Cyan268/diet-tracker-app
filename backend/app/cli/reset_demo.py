import argparse
import asyncio
import json
from datetime import date

from app.cli.seed_demo import validate_seed_environment
from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.redis import close_redis_client
from app.services.demo_reset import reset_demo_once


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset the NutriPilot demo account using the distributed lock"
    )
    parser.add_argument("--anchor-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--allow-production", action="store_true")
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    settings = get_settings()
    validate_seed_environment(settings.environment, args.allow_production)
    executed = await reset_demo_once(settings, anchor_date=args.anchor_date)
    print(
        json.dumps(
            {"executed": executed, "anchor_date": args.anchor_date.isoformat()},
            ensure_ascii=False,
        )
    )


async def run_with_cleanup() -> None:
    try:
        await run()
    finally:
        await close_redis_client()
        await dispose_engine()


def main() -> None:
    asyncio.run(run_with_cleanup())


if __name__ == "__main__":
    main()
