#!/usr/bin/env python3
"""Record an auditable human review decision for one English segment."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portuguese_pipeline.ids import sha256_text  # noqa: E402
from portuguese_pipeline.pipeline import render_text, write_json_atomic, write_text_atomic  # noqa: E402


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def segments(value: dict) -> list[dict]:
    return [segment for page in value.get("pages", []) for segment in page.get("segments", [])] + list(value.get("segments", []))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_dir", type=Path)
    parser.add_argument("--segment-id", required=True)
    parser.add_argument("--decision", choices=("reviewed", "needs-review", "rejected"), required=True)
    parser.add_argument("--reviewer", required=True, help="Stable reviewer name or team identifier.")
    parser.add_argument("--note", required=True)
    parser.add_argument("--replacement-text", type=Path, help="Optional reviewed English replacement text.")
    args = parser.parse_args()
    root = args.document_dir.resolve()
    translation_path = root / "en" / "translation.json"
    translation = json.loads(translation_path.read_text(encoding="utf-8"))
    match = next((segment for segment in segments(translation) if segment.get("segment_id") == args.segment_id), None)
    if not match:
        parser.error(f"segment does not exist: {args.segment_id}")
    reviewed_at = now_iso()
    previous_hash = match.get("translation_text_sha256", "")
    if args.replacement_text:
        replacement = args.replacement_text.read_text(encoding="utf-8").strip()
        if not replacement:
            parser.error("replacement text cannot be empty")
        match["text"] = replacement
        match["translation_text_sha256"] = sha256_text(replacement)
        match["status"] = "human-corrected"
    match["review_status"] = args.decision
    match["review"] = {
        "reviewer": args.reviewer,
        "reviewed_at": reviewed_at,
        "decision": args.decision,
        "note": args.note,
        "source_text_sha256": match["source_text_sha256"],
        "previous_translation_text_sha256": previous_hash,
        "reviewed_translation_text_sha256": match["translation_text_sha256"],
    }
    all_segments = segments(translation)
    review_states = [segment.get("review_status") for segment in all_segments if segment.get("status") != "not-required"]
    failure_states = {"failed", "failed-protected-token-check"}
    segment_states = [segment.get("status") for segment in all_segments]
    if any(state in failure_states for state in segment_states):
        overall = "partial" if any(state not in failure_states | {"not-required"} for state in segment_states) else "failed"
    elif review_states and all(state == "reviewed" for state in review_states):
        overall = "reviewed"
    else:
        overall = "needs-review"
    translation["translation"]["review_status"] = overall
    write_json_atomic(translation_path, translation)
    write_text_atomic(root / "en" / "translation.txt", render_text(translation, language="en"))

    document_path = root / "document.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["translation_review_status"] = overall
    document["processing_status"] = "complete" if overall not in {"partial", "failed"} else overall
    write_json_atomic(document_path, document)

    review_path = root / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    for item in review.get("segments", []):
        if item.get("segment_id") == args.segment_id:
            item["review_status"] = args.decision
    remaining = sum(segment.get("review_status") != "reviewed" for segment in all_segments if segment.get("status") != "not-required")
    review["remaining_manual_review_count"] = remaining
    write_json_atomic(review_path, review)

    provenance_path = root / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["translation"]["review_status"] = overall
    provenance["status"] = "complete" if overall not in {"partial", "failed"} else overall
    provenance["remaining_manual_review_count"] = remaining
    write_json_atomic(provenance_path, provenance)

    audit_path = root / "translation-reviews.json"
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        audit = {"schema": "ufo-files-portuguese-translation-reviews/v1", "reviews": []}
    audit["reviews"].append({"segment_id": args.segment_id, **match["review"]})
    write_json_atomic(audit_path, audit)
    print(json.dumps({"document_id": translation["document_id"], "segment_id": args.segment_id, "decision": args.decision, "remaining_manual_review_count": remaining}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
