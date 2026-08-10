#!/usr/bin/env python3
"""Validate paired Brazil outputs and report manual-review totals."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_PATHS = {
    "document.json", "pt-BR/canonical.json", "pt-BR/canonical.txt",
    "en/translation.json", "en/translation.txt", "entities.json", "events.json",
    "provenance.json", "qa.json", "review.json",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def segments(value: dict) -> list[dict]:
    rows = [segment for page in value.get("pages", []) for segment in page.get("segments", [])]
    rows.extend(value.get("segments", []))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    documents = 0
    reviews = 0
    statuses: dict[str, int] = {}
    for document_path in sorted(args.root.rglob("document.json")):
        documents += 1
        directory = document_path.parent
        try:
            document = json.loads(document_path.read_text(encoding="utf-8"))
            canonical = json.loads((directory / document["canonical_path"]).read_text(encoding="utf-8"))
            translation = json.loads((directory / document["translation_path"]).read_text(encoding="utf-8"))
            qa = json.loads((directory / document["qa_path"]).read_text(encoding="utf-8"))
            review = json.loads((directory / document["review_path"]).read_text(encoding="utf-8"))
            provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
        except (OSError, KeyError, json.JSONDecodeError) as error:
            errors.append(f"{document_path}: {error}")
            continue
        actual_paths = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
        if not EXPECTED_PATHS <= actual_paths:
            errors.append(f"{document_path}: missing artifacts {sorted(EXPECTED_PATHS - actual_paths)}")
        canonical_segments = segments(canonical)
        translation_segments = segments(translation)
        canonical_ids = [segment["segment_id"] for segment in canonical_segments]
        translation_ids = [segment["segment_id"] for segment in translation_segments]
        if canonical_ids != translation_ids:
            errors.append(f"{document_path}: paired segment IDs differ")
        if any(segment.get("source_segment_id") != segment.get("segment_id") for segment in translation_segments):
            errors.append(f"{document_path}: translated source segment IDs differ")
        for segment in canonical_segments:
            expected = hashlib.sha256(segment.get("text", "").encode()).hexdigest()
            if segment.get("text_sha256") != expected:
                errors.append(f"{document_path}: canonical segment hash mismatch {segment.get('segment_id')}")
        for segment in translation_segments:
            expected = hashlib.sha256(segment.get("text", "").encode()).hexdigest()
            if segment.get("translation_text_sha256") != expected:
                errors.append(f"{document_path}: translation segment hash mismatch {segment.get('segment_id')}")
        if not qa.get("page_count_match") or not qa.get("segment_count_match"):
            errors.append(f"{document_path}: paired page/segment count mismatch")
        if document.get("document_id") != canonical.get("document_id") or document.get("document_id") != translation.get("document_id"):
            errors.append(f"{document_path}: document IDs differ")
        if document.get("canonical_language") != "pt-BR" or translation.get("source_language") != "pt-BR" or translation.get("target_language") != "en":
            errors.append(f"{document_path}: language contract mismatch")
        if document.get("source", {}).get("sha256") != provenance.get("source_sha256"):
            errors.append(f"{document_path}: provenance source hash mismatch")
        if document.get("processing_status") != provenance.get("status"):
            errors.append(f"{document_path}: processing status mismatch")
        if provenance.get("canonical_text_sha256") != sha256_file(directory / "pt-BR/canonical.txt"):
            errors.append(f"{document_path}: canonical text artifact hash mismatch")
        if provenance.get("translation_text_sha256") != sha256_file(directory / "en/translation.txt"):
            errors.append(f"{document_path}: translation text artifact hash mismatch")
        status = document.get("translation_review_status", "missing")
        statuses[status] = statuses.get(status, 0) + 1
        reviews += int(review.get("remaining_manual_review_count", 0))
    print(json.dumps({
        "documents": documents,
        "errors": errors,
        "remaining_manual_review_count": reviews,
        "translation_review_statuses": statuses,
    }, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
