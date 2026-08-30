#!/usr/bin/env python3
"""Emit reviewable, claim-adjacent epistemic qualifier annotations from TSV transcripts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    category: str
    confidence: float
    evidence_weight: float
    pattern: re.Pattern[str]


def load_rules(path: Path) -> tuple[tuple[Rule, ...], re.Pattern[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "ufo-files-epistemic-qualifier-rules/v1":
        raise ValueError(f"unsupported epistemic qualifier rules: {path}")
    rules = tuple(Rule(item["category"], float(item["confidence"]), float(item.get("evidenceWeight", 1)), re.compile(item["pattern"], re.IGNORECASE)) for item in payload["rules"])
    return rules, re.compile(payload["nonClaimFollowupPattern"], re.IGNORECASE)


def read_segments(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = []
        for line_number, row in enumerate(csv.DictReader(handle, delimiter="\t"), 2):
            try:
                rows.append({"line": line_number, "start": int(row["start"]), "end": int(row["end"]), "text": row["text"].strip()})
            except (KeyError, TypeError, ValueError):
                continue
        return rows


def annotations(path: Path, root: Path, rules: tuple[Rule, ...], non_claim_followups: re.Pattern[str]) -> list[dict]:
    rows = read_segments(path)
    results = []
    for index, row in enumerate(rows):
        for rule in rules:
            for match in rule.pattern.finditer(row["text"]):
                preceding = row["text"][:match.start()].rstrip(" ,:;—-.")
                remainder = row["text"][match.end():].lstrip(" ,:;—-.")
                scope = "same_segment"
                claim_text = remainder
                claim_row = row
                confidence = rule.confidence
                if len(claim_text.split()) < 5 and len(preceding.split()) >= 5:
                    claim_text = preceding
                    scope = "preceding_clause"
                elif len(claim_text.split()) < 5 and index + 1 < len(rows) and rows[index + 1]["start"] - row["end"] <= 2500:
                    claim_text = " ".join(part for part in (claim_text, rows[index + 1]["text"]) if part)
                    scope = "next_segment_candidate"
                    claim_row = rows[index + 1]
                    confidence = min(confidence, .82)
                if not claim_text or non_claim_followups.match(claim_text):
                    scope = "unresolved"
                    confidence = min(confidence, .55)
                relative = path.relative_to(root).as_posix()
                identity = f"{relative}:{row['line']}:{match.start()}:{match.group(0).lower()}"
                results.append({
                    "id": "eq-" + hashlib.sha256(identity.encode()).hexdigest()[:16],
                    "source_path": relative,
                    "line": row["line"],
                    "start_ms": row["start"],
                    "end_ms": row["end"],
                    "claim_line": claim_row["line"],
                    "claim_start_ms": claim_row["start"],
                    "claim_end_ms": claim_row["end"],
                    "category": rule.category,
                    "qualifier": match.group(0),
                    "claim_text": claim_text,
                    "scope": scope,
                    "confidence": round(confidence, 2),
                    "evidence_weight": round(1 - confidence * (1 - rule.evidence_weight), 3),
                    "speaker_attribution": "unresolved",
                    "review_status": "candidate",
                    "evidence_text": row["text"],
                })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path, help="Transcript files or directories")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository_root = args.repository_root.resolve()
    missing = [str(path) for path in args.roots if not path.exists()]
    if missing:
        parser.error("transcript root does not exist: " + ", ".join(missing))
    rules, non_claim_followups = load_rules(args.rules or repository_root / "config" / "epistemic_qualifiers.json")
    paths = sorted({path.resolve() for item in args.roots for path in ([item] if item.is_file() else item.rglob("*.tsv"))})
    output = args.output.resolve()
    if output in paths:
        parser.error("--output must not overwrite an input transcript")
    rows = [item for path in paths for item in annotations(path, repository_root, rules, non_claim_followups)]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"schema": "ufo-files-epistemic-qualifiers/v1", "files": len(paths), "candidates": len(rows), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
