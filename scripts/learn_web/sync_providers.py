"""Snapshot legacy provider metadata for the independent React frontend."""

import argparse
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "learn_web/src/models/provider-catalog.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    platforms = runpy.run_path(str(ROOT / "learning_ext/model_platforms.py"))["PLATFORMS"]
    catalog = [
        {
            "id": key,
            "name": item["name"],
            "mark": item["mark"],
            "subtitle": item["tag"],
            "group": item["group"],
            "baseUrl": next(iter(item["profiles"].values())),
            "profiles": [{"label": label, "value": url} for label, url in item["profiles"].items()],
            "models": item["models"],
            "note": item["note"],
            "website": item.get("key_url") or item.get("docs", ""),
            "docs": item.get("docs", ""),
        }
        for key, item in {"custom": platforms["custom"], **platforms}.items()
    ]
    output = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not TARGET.exists() or json.loads(TARGET.read_text()) != catalog:
            raise SystemExit("Provider catalog is stale. Run scripts/learn_web/sync_providers.py")
        print(f"Provider catalog matches all {len(catalog)} legacy entries.")
    else:
        TARGET.write_text(output)
        print(f"Wrote {len(catalog)} provider entries to {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
