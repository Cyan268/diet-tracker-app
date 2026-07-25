import argparse
import asyncio
import json
import os
from datetime import date

from app.core.config import get_settings
from app.core.database import dispose_engine, session_factory
from app.services.demo_data import resolve_demo_anchor_date, seed_demo_account


def validate_seed_environment(environment: str, allow_production: bool) -> None:
    if environment == "production" and not allow_production:
        raise RuntimeError("production demo reset requires --allow-production")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or reset the NutriPilot demo account")
    parser.add_argument(
        "--email",
        default=os.getenv("NUTRIPILOT_DEMO_EMAIL", "demo@nutripilot.example"),
    )
    parser.add_argument("--anchor-date", type=date.fromisoformat)
    parser.add_argument("--reset-existing", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    settings = get_settings()
    validate_seed_environment(settings.environment, args.allow_production)
    password = os.getenv("NUTRIPILOT_DEMO_PASSWORD")
    if password is None:
        raise RuntimeError("NUTRIPILOT_DEMO_PASSWORD must be set")
    anchor_date = args.anchor_date or resolve_demo_anchor_date(settings)
    async with session_factory() as session:
        result = await seed_demo_account(
            session,
            email=args.email,
            password=password,
            anchor_date=anchor_date,
            reset_existing=args.reset_existing,
        )
    print(
        json.dumps(
            {
                "user_id": str(result.user_id),
                "email": result.email,
                "anchor_date": result.anchor_date.isoformat(),
                "log_count": result.log_count,
                "private_food_count": result.private_food_count,
                "reset": result.reset,
            },
            ensure_ascii=False,
        )
    )


async def run_with_cleanup() -> None:
    try:
        await run()
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(run_with_cleanup())


if __name__ == "__main__":
    main()
