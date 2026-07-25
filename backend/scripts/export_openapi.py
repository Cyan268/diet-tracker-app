import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND_DIR / "openapi.json"
    output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote OpenAPI schema to {output}")


if __name__ == "__main__":
    main()
