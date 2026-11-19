"""Export the real API contract without connecting to the database."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from learn_api.app import create_app

path = Path(__file__).resolve().parents[2] / "learn_web" / "openapi.json"
value = json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
if "--check" in sys.argv:
    if not path.exists() or path.read_text() != value:
        raise SystemExit("OpenAPI changed: run python scripts/learn_web/export_openapi.py and npm run api:generate")
else:
    path.write_text(value)
