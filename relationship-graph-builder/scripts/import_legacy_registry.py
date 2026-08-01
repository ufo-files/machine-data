#!/usr/bin/env python3
"""Import only the reviewed identity registry from the legacy graph build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CATEGORY_MAP = {
    "people": "person",
    "locations": "location",
    "government_agencies": "government_agency",
    "organizations": "organization",
    "programs_projects": "program",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy", type=Path, help="Legacy relationship-graph checkout")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "curated_entities.json")
    args = parser.parse_args()
    records = {}
    for path in sorted((args.legacy / "data" / "entities").glob("chunk-*.json")):
        for entity in json.loads(path.read_text(encoding="utf-8")):
            category = CATEGORY_MAP.get(entity.get("category"))
            if not category or entity.get("review_status") != "reviewed":
                continue
            if float(entity.get("classification_confidence") or 0) < 0.9:
                continue
            name = str(entity.get("canonical_name") or entity.get("name") or "").strip()
            if len(name) < 3:
                continue
            key = " ".join("".join(char.lower() if char.isalnum() else " " for char in name).split())
            current = records.get(key)
            count = int(entity.get("count") or 0)
            if current is None or count > current["legacyCount"]:
                records[key] = {"name": name, "category": category, "legacyCount": count}
    output = sorted(records.values(), key=lambda item: (-item["legacyCount"], item["name"]))
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "reviewedEntities": len(output)}, indent=2))


if __name__ == "__main__":
    main()
