"""End-to-end Portuguese canonical text and paired English derivative pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .entities import extract_entities, extract_events
from .extract import Extraction, ExtractedUnit, extract_source
from .ids import sha256_text, stable_id
from .language import detect_language
from .qa import compare_translation, review_weight
from .translation import Backend, PROMPT_SHA256, WORKFLOW_VERSION, translate_text


PIPELINE_VERSION = "ufo-files-portuguese-pipeline/1.0.11"
DOCUMENT_SCHEMA = "ufo-files-portuguese-document/v1"
CANONICAL_SCHEMA = "ufo-files-portuguese-canonical/v1"
TRANSLATION_SCHEMA = "ufo-files-portuguese-translation/v1"
PROVENANCE_SCHEMA = "ufo-files-portuguese-provenance/v1"


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _manifest_items(manifest: dict) -> list[dict]:
    items = manifest.get("items", [])
    if not isinstance(items, list):
        raise RuntimeError("source manifest 'items' must be a list")
    return [item for item in items if isinstance(item, dict)]


def source_record(manifest: dict, relative_path: str) -> dict:
    matches = [item for item in _manifest_items(manifest) if item.get("relative_path") == relative_path]
    if not matches:
        raise RuntimeError(f"source is absent from authoritative manifest: {relative_path}")
    # Duplicate manifest references can intentionally point to the same immutable file.
    # Prefer a primary record, then use canonical identifier as a deterministic tiebreaker.
    matches.sort(key=lambda item: (bool(item.get("duplicate_of")), str(item.get("canonical_source_identifier", ""))))
    return matches[0]


def output_relative_path(relative_path: str) -> Path:
    source = Path(relative_path)
    return Path("Brazil-Government-UAP") / "paired" / source.parent / source.stem


def _source_metadata(record: dict, relative_path: str, source_sha256: str, source_bytes: int) -> dict:
    expected_hash = record.get("sha256")
    if expected_hash and expected_hash != source_sha256:
        raise RuntimeError(f"source SHA-256 does not match manifest for {relative_path}")
    expected_bytes = record.get("bytes")
    if expected_bytes not in (None, "") and int(expected_bytes) != source_bytes:
        raise RuntimeError(f"source byte size does not match manifest for {relative_path}")
    return {
        "archived_original_path": f"originals/Brazil-Government-UAP/{relative_path}",
        "relative_path": relative_path,
        "sha256": source_sha256,
        "bytes": source_bytes,
        "canonical_source_identifier": record.get("canonical_source_identifier", ""),
        "official_identifier": record.get("official_identifier", ""),
        "original_title": record.get("original_title", ""),
        "original_language": record.get("original_language") or "pt-BR",
        "institution": record.get("institution", ""),
        "collection_fonds": record.get("collection_fonds", ""),
        "country": record.get("country") or "BR",
        "jurisdiction": record.get("jurisdiction", ""),
        "document_date": record.get("document_date") or record.get("issue_date") or "",
        "landing_page_url": record.get("landing_page_url", ""),
        "direct_file_url": record.get("direct_file_url", ""),
        "source_urls": record.get("source_urls", []),
        "rights_access_note": record.get("rights_access_note", ""),
        "media_type": record.get("media_type", ""),
    }


def _split_segments(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return [""]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
    if len(paragraphs) == 1 and len(paragraphs[0]) > 3000:
        paragraphs = [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ])", paragraphs[0]) if part.strip()]
    return paragraphs or [normalized]


def _canonical_segment(document_id: str, unit: ExtractedUnit, index: int, text: str, *, page_id: str | None) -> dict:
    location = f"page:{unit.index}:segment:{index}" if page_id else f"time:{unit.start_ms}:{unit.end_ms}:segment:{index}"
    return {
        "segment_id": stable_id("seg", f"{document_id}|{location}"),
        "segment_index": index,
        "page_id": page_id,
        "start_ms": unit.start_ms,
        "end_ms": unit.end_ms,
        "text": text,
        "text_sha256": sha256_text(text),
        "language": detect_language(text),
        "ocr_confidence": round(unit.confidence, 4) if unit.confidence is not None else None,
    }


def build_canonical(document_id: str, source: dict, extraction: Extraction, generated_at: str) -> dict:
    common = {
        "schema": CANONICAL_SCHEMA,
        "document_id": document_id,
        "canonical_language": "pt-BR",
        "source": source,
        "medium": extraction.medium,
        "extraction": {
            "engine": extraction.engine,
            "mode": extraction.mode,
            "tools": extraction.tools or {},
            "generated_at": generated_at,
        },
    }
    if extraction.medium in {"document", "image"}:
        pages = []
        for unit in extraction.units:
            page_id = stable_id("page", f"{document_id}|page:{unit.index}")
            segments = [
                _canonical_segment(document_id, unit, index, text, page_id=page_id)
                for index, text in enumerate(_split_segments(unit.text), 1)
            ]
            pages.append({
                "page_id": page_id,
                "page_index": unit.index,
                "language": detect_language(unit.text),
                "segments": segments,
            })
        all_text = "\n".join(unit.text for unit in extraction.units)
        return {**common, "detected_language": detect_language(all_text), "pages": pages, "segments": []}
    segments = [
        _canonical_segment(document_id, unit, unit.index, unit.text, page_id=None)
        for unit in extraction.units
    ]
    return {**common, "detected_language": detect_language("\n".join(unit.text for unit in extraction.units)), "pages": [], "segments": segments}


def _translate_segment(segment: dict, backend: Backend, identifiers: list[str]) -> tuple[dict, list[dict]]:
    result = translate_text(backend, segment["text"], official_identifiers=identifiers)
    findings = compare_translation(segment["text"], result.text) if result.text else []
    if result.missing_protected_tokens:
        findings.append({
            "check": "protected-tokens",
            "severity": "error",
            "status": "mismatch",
            "missing_from_translation": list(result.missing_protected_tokens),
        })
    status = result.status
    if findings and status == "machine-unreviewed":
        status = "needs-review"
    translated = {
        "segment_id": segment["segment_id"],
        "source_segment_id": segment["segment_id"],
        "segment_index": segment["segment_index"],
        "page_id": segment.get("page_id"),
        "start_ms": segment.get("start_ms"),
        "end_ms": segment.get("end_ms"),
        "source_text_sha256": segment["text_sha256"],
        "text": result.text,
        "translation_text_sha256": sha256_text(result.text),
        "status": status,
        "review_status": status,
        "error": result.error,
        "qa_findings": findings,
    }
    return translated, findings


def build_translation(canonical: dict, backend: Backend, generated_at: str) -> tuple[dict, dict]:
    source = canonical["source"]
    identifiers = [
        source.get("official_identifier", ""),
        source.get("canonical_source_identifier", ""),
        Path(source.get("relative_path", "")).name,
    ]
    all_findings: list[dict] = []
    total_segments = count_segments(canonical)
    completed_segments = 0
    translation_started = time.monotonic()

    def report_progress() -> None:
        if total_segments < 25:
            return
        if completed_segments % 25 == 0 or completed_segments == total_segments:
            elapsed = int(time.monotonic() - translation_started)
            print(
                f"+ translation working: {completed_segments}/{total_segments} segment(s); elapsed {elapsed}s",
                flush=True,
            )

    pages = []
    for page in canonical.get("pages", []):
        segments = []
        for segment in page["segments"]:
            translated, findings = _translate_segment(segment, backend, identifiers)
            segments.append(translated)
            all_findings.extend({"segment_id": segment["segment_id"], **finding} for finding in findings)
            completed_segments += 1
            report_progress()
        pages.append({
            "page_id": page["page_id"],
            "source_page_id": page["page_id"],
            "page_index": page["page_index"],
            "segments": segments,
        })
    segments = []
    for segment in canonical.get("segments", []):
        translated, findings = _translate_segment(segment, backend, identifiers)
        segments.append(translated)
        all_findings.extend({"segment_id": segment["segment_id"], **finding} for finding in findings)
        completed_segments += 1
        report_progress()
    states = [segment["status"] for page in pages for segment in page["segments"]] + [segment["status"] for segment in segments]
    failure_states = {"failed", "failed-protected-token-check"}
    if any(status in failure_states for status in states):
        status = "partial" if any(status not in failure_states | {"not-required"} for status in states) else "failed"
    elif any(status == "needs-review" for status in states):
        status = "needs-review"
    else:
        status = "machine-unreviewed"
    translation = {
        "schema": TRANSLATION_SCHEMA,
        "document_id": canonical["document_id"],
        "source_language": "pt-BR",
        "target_language": "en",
        "translation": {
            "method": backend.method,
            "model": backend.model,
            "model_revision": backend.model_revision,
            "workflow_version": WORKFLOW_VERSION,
            "prompt_sha256": PROMPT_SHA256,
            "runtime_version": backend.runtime_version,
            "generated_at": generated_at,
            "review_status": status,
        },
        "pages": pages,
        "segments": segments,
    }
    qa = {
        "schema": "ufo-files-portuguese-translation-qa/v1",
        "document_id": canonical["document_id"],
        "source_language": "pt-BR",
        "target_language": "en",
        "page_count_match": len(canonical.get("pages", [])) == len(pages),
        "segment_count_match": count_segments(canonical) == count_segments(translation),
        "findings": all_findings,
        "status": "pass" if not all_findings else "needs-review",
    }
    return translation, qa


def count_segments(value: dict) -> int:
    return sum(len(page.get("segments", [])) for page in value.get("pages", [])) + len(value.get("segments", []))


def review_sample(canonical: dict, translation: dict, limit: int = 25) -> dict:
    translated_by_id = {
        segment["segment_id"]: segment
        for page in translation.get("pages", []) for segment in page.get("segments", [])
    }
    translated_by_id.update({segment["segment_id"]: segment for segment in translation.get("segments", [])})
    candidates = []
    source_segments = [segment for page in canonical.get("pages", []) for segment in page.get("segments", [])]
    source_segments.extend(canonical.get("segments", []))
    for segment in source_segments:
        translated = translated_by_id[segment["segment_id"]]
        weight, reasons = review_weight(segment["text"], segment.get("ocr_confidence"))
        if translated["status"] in {"failed", "needs-review", "failed-protected-token-check"}:
            weight += 10
            reasons.append("translation-failure-or-qa")
        candidates.append({
            "segment_id": segment["segment_id"],
            "weight": weight,
            "reasons": sorted(set(reasons)),
            "review_status": translated["review_status"],
        })
    candidates.sort(key=lambda item: (-item["weight"], item["segment_id"]))
    selected = candidates[:limit]
    return {
        "schema": "ufo-files-portuguese-review-queue/v1",
        "document_id": canonical["document_id"],
        "selection_method": "deterministic weighted sample: failures, handwriting/stamps, low OCR confidence, forms, abbreviations, important cases",
        "segments": selected,
        "remaining_manual_review_count": sum(item["review_status"] != "reviewed" for item in candidates),
    }


def render_text(value: dict, *, language: str) -> str:
    metadata = {
        "schema": "ufo-files-portuguese-search-text/v1",
        "document_id": value["document_id"],
        "language": language,
        "canonical": language == "pt-BR",
        "translation_review_status": value.get("translation", {}).get("review_status"),
    }
    lines = [json.dumps(metadata, ensure_ascii=False, sort_keys=True), ""]
    for page in value.get("pages", []):
        lines.append(f"===== PAGE {page['page_index']} [{page['page_id']}] =====")
        for segment in page.get("segments", []):
            status = f" [{segment['status']}]" if language == "en" else ""
            lines.append(f"--- {segment['segment_id']}{status} ---")
            lines.append(segment.get("text", ""))
        lines.append("")
    for segment in value.get("segments", []):
        timing = f" {segment.get('start_ms')}–{segment.get('end_ms')}ms"
        status = f" [{segment['status']}]" if language == "en" else ""
        lines.append(f"--- {segment['segment_id']}{timing}{status} ---")
        lines.append(segment.get("text", ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def expected_complete(output_dir: Path, source_sha256: str, backend: Backend) -> bool:
    path = output_dir / "provenance.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        data.get("status") == "complete"
        and data.get("source_sha256") == source_sha256
        and data.get("pipeline_version") == PIPELINE_VERSION
        and data.get("translation", {}).get("model") == backend.model
        and data.get("translation", {}).get("model_revision") == backend.model_revision
        and all((output_dir / name).is_file() for name in (
            "document.json", "pt-BR/canonical.json", "pt-BR/canonical.txt",
            "en/translation.json", "en/translation.txt", "qa.json",
            "entities.json", "events.json", "review.json",
        ))
    )


def process_source(
    source_path: Path,
    *,
    relative_path: str,
    manifest: dict,
    output_root: Path,
    work_root: Path,
    backend: Backend,
    workers: int = 2,
    dpi: int = 300,
    embedded_word_floor: int = 80,
    whisper_model: str = "mlx-community/whisper-large-v3-mlx",
    whisper_model_revision: str = "main",
    force: bool = False,
) -> dict:
    source_path = source_path.resolve()
    source_bytes = source_path.stat().st_size
    source_hash = sha256_file(source_path)
    record = source_record(manifest, relative_path)
    source = _source_metadata(record, relative_path, source_hash, source_bytes)
    identity = source.get("canonical_source_identifier") or f"Brazil-Government-UAP/{relative_path}"
    document_id = stable_id("doc", identity)
    output_dir = output_root / output_relative_path(relative_path)
    if not force and expected_complete(output_dir, source_hash, backend):
        return {"status": "skipped-complete", "document_id": document_id, "output_dir": str(output_dir)}

    generated_at = now_iso()
    work_root.mkdir(parents=True, exist_ok=True)
    job_work = Path(tempfile.mkdtemp(prefix=f"pt-{document_id}-", dir=work_root))
    staging = output_dir.with_name(f".{output_dir.name}.staging-{os.getpid()}")
    prior_review_audit: bytes | None = None
    prior_review_path = output_dir / "translation-reviews.json"
    try:
        candidate_audit = prior_review_path.read_bytes()
        parsed_audit = json.loads(candidate_audit)
        if parsed_audit.get("schema") == "ufo-files-portuguese-translation-reviews/v1":
            prior_review_audit = candidate_audit
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        extraction = extract_source(
            source_path,
            work_dir=job_work,
            workers=workers,
            dpi=dpi,
            embedded_word_floor=embedded_word_floor,
            whisper_model=whisper_model,
            whisper_model_revision=whisper_model_revision,
        )
        canonical = build_canonical(document_id, source, extraction, generated_at)
        translation, qa = build_translation(canonical, backend, generated_at)
        translation_status = translation["translation"]["review_status"]
        processing_status = "complete" if translation_status not in {"partial", "failed"} else translation_status
        entities = extract_entities(canonical, translation)
        events = extract_events(canonical, translation)
        review = review_sample(canonical, translation)
        document = {
            "schema": DOCUMENT_SCHEMA,
            "document_id": document_id,
            "source": source,
            "medium": canonical["medium"],
            "canonical_language": "pt-BR",
            "available_languages": ["pt-BR", "en"],
            "translation_available": translation["translation"]["review_status"] != "failed",
            "translation_review_status": translation["translation"]["review_status"],
            "processing_status": processing_status,
            "canonical_path": "pt-BR/canonical.json",
            "translation_path": "en/translation.json",
            "entity_path": "entities.json",
            "event_path": "events.json",
            "qa_path": "qa.json",
            "review_path": "review.json",
        }
        provenance = {
            "schema": PROVENANCE_SCHEMA,
            "status": processing_status,
            "document_id": document_id,
            "source_sha256": source_hash,
            "source_bytes": source_bytes,
            "pipeline_version": PIPELINE_VERSION,
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
            },
            "generated_at": generated_at,
            "extraction": canonical["extraction"],
            "translation": translation["translation"],
            "canonical_text_sha256": sha256_text(render_text(canonical, language="pt-BR")),
            "translation_text_sha256": sha256_text(render_text(translation, language="en")),
            "page_count": len(canonical.get("pages", [])),
            "segment_count": count_segments(canonical),
            "qa_status": qa["status"],
            "remaining_manual_review_count": review["remaining_manual_review_count"],
        }
        write_json_atomic(staging / "document.json", document)
        write_json_atomic(staging / "pt-BR" / "canonical.json", canonical)
        write_text_atomic(staging / "pt-BR" / "canonical.txt", render_text(canonical, language="pt-BR"))
        write_json_atomic(staging / "en" / "translation.json", translation)
        write_text_atomic(staging / "en" / "translation.txt", render_text(translation, language="en"))
        write_json_atomic(staging / "qa.json", qa)
        write_json_atomic(staging / "entities.json", entities)
        write_json_atomic(staging / "events.json", events)
        write_json_atomic(staging / "review.json", review)
        write_json_atomic(staging / "provenance.json", provenance)
        if prior_review_audit is not None:
            (staging / "translation-reviews.json").write_bytes(prior_review_audit)
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        if output_dir.exists():
            old = output_dir.with_name(f".{output_dir.name}.old-{os.getpid()}")
            os.replace(output_dir, old)
            os.replace(staging, output_dir)
            shutil.rmtree(old)
        else:
            os.replace(staging, output_dir)
        return {
            "status": processing_status,
            "document_id": document_id,
            "output_dir": str(output_dir),
            "page_count": provenance["page_count"],
            "segment_count": provenance["segment_count"],
            "translation_review_status": translation["translation"]["review_status"],
            "qa_status": qa["status"],
            "remaining_manual_review_count": review["remaining_manual_review_count"],
        }
    except Exception as error:
        failure_path = output_dir.parent / f"{output_dir.name}.failure.json"
        write_json_atomic(failure_path, {
            "schema": PROVENANCE_SCHEMA,
            "status": "failed",
            "document_id": document_id,
            "source_sha256": source_hash,
            "pipeline_version": PIPELINE_VERSION,
            "failed_at": now_iso(),
            "error": f"{type(error).__name__}: {error}",
        })
        raise
    finally:
        shutil.rmtree(job_work, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)


def retranslate_existing(output_dir: Path, backend: Backend) -> dict:
    """Regenerate only derived artifacts from an existing canonical transcript."""
    output_dir = output_dir.resolve()
    canonical_path = output_dir / "pt-BR" / "canonical.json"
    canonical_bytes_before = canonical_path.read_bytes()
    canonical = json.loads(canonical_bytes_before)
    generated_at = now_iso()
    translation, qa = build_translation(canonical, backend, generated_at)
    entities = extract_entities(canonical, translation)
    events = extract_events(canonical, translation)
    review = review_sample(canonical, translation)

    document_path = output_dir / "document.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["translation_available"] = translation["translation"]["review_status"] != "failed"
    document["translation_review_status"] = translation["translation"]["review_status"]

    provenance_path = output_dir / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["pipeline_version"] = PIPELINE_VERSION
    provenance["translation"] = translation["translation"]
    translation_status = translation["translation"]["review_status"]
    processing_status = "complete" if translation_status not in {"partial", "failed"} else translation_status
    provenance["status"] = processing_status
    provenance["translation_text_sha256"] = sha256_text(render_text(translation, language="en"))
    provenance["qa_status"] = qa["status"]
    provenance["remaining_manual_review_count"] = review["remaining_manual_review_count"]
    provenance["retranslated_at"] = generated_at
    document["processing_status"] = processing_status

    write_json_atomic(output_dir / "en" / "translation.json", translation)
    write_text_atomic(output_dir / "en" / "translation.txt", render_text(translation, language="en"))
    write_json_atomic(output_dir / "qa.json", qa)
    write_json_atomic(output_dir / "entities.json", entities)
    write_json_atomic(output_dir / "events.json", events)
    write_json_atomic(output_dir / "review.json", review)
    write_json_atomic(document_path, document)
    write_json_atomic(provenance_path, provenance)
    if canonical_path.read_bytes() != canonical_bytes_before:
        raise RuntimeError("canonical Portuguese changed during translation-only update")
    return {
        "status": processing_status,
        "document_id": canonical["document_id"],
        "translation_review_status": translation["translation"]["review_status"],
        "qa_status": qa["status"],
        "remaining_manual_review_count": review["remaining_manual_review_count"],
    }
