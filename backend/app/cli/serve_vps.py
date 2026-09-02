"""VPS-only start: static validation, schema readiness contract, then one API process.

Never migrates or seeds. Legacy Render retains its existing CMD.
"""

import os

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.cli.production_preflight import main as preflight


def main() -> int:
    if preflight(["--portfolio", "--behind-proxy", "--single-origin-web", "--vps"]):
        return 1
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    if not head:
        raise RuntimeError("image must contain one Alembic head")
    os.environ["NUTRIPILOT_REQUIRED_SCHEMA_REVISION"] = head
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--workers",
            "1",
            "--no-proxy-headers",
            "--no-access-log",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
