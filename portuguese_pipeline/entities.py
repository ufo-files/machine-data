"""Cross-language entity and event extraction without evidence double-counting."""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from .ids import identity_key, stable_id


ALIASES: dict[str, tuple[str, str]] = {
    "ovni": ("UFO", "subject"),
    "ovnis": ("UFO", "subject"),
    "objeto voador não identificado": ("UFO", "subject"),
    "objetos voadores não identificados": ("UFO", "subject"),
    "ufo": ("UFO", "subject"),
    "ufos": ("UFO", "subject"),
    "unidentified flying object": ("UFO", "subject"),
    "unidentified flying objects": ("UFO", "subject"),
    "fenômeno anômalo não identificado": ("UAP", "subject"),
    "fenômenos anômalos não identificados": ("UAP", "subject"),
    "uap": ("UAP", "subject"),
    "câmara dos deputados": ("Câmara dos Deputados", "government_agency"),
    "chamber of deputies": ("Câmara dos Deputados", "government_agency"),
    "arquivo nacional": ("Arquivo Nacional", "government_agency"),
    "national archives of brazil": ("Arquivo Nacional", "government_agency"),
    "comando da aeronáutica": ("Comando da Aeronáutica", "military_organization"),
    "aeronautics command": ("Comando da Aeronáutica", "military_organization"),
    "força aérea brasileira": ("Força Aérea Brasileira", "military_organization"),
    "brazilian air force": ("Força Aérea Brasileira", "military_organization"),
    "fab": ("Força Aérea Brasileira", "military_organization"),
    "ministério da defesa": ("Ministério da Defesa", "government_agency"),
    "ministry of defense": ("Ministério da Defesa", "government_agency"),
    "operação prato": ("Operação Prato", "program"),
    "operation saucer": ("Operação Prato", "program"),
    "varginha": ("Varginha", "location"),
    "colares": ("Colares", "location"),
    "brasil": ("Brazil", "country"),
    "brazil": ("Brazil", "country"),
}
ALIAS_LOOKUP = {identity_key(alias): value for alias, value in ALIASES.items()}

ALIAS_PATTERN = re.compile(
    r"(?<![\w-])(" + "|".join(sorted((re.escape(alias) for alias in ALIASES), key=len, reverse=True)) + r")(?![\w-])",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r"(?<!\d)(?:\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})|(?:19|20)\d{2}-\d{2}-\d{2})(?!\d)"
    r"|\b\d{1,2}\s+de\s+(?:janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(?:19|20)\d{2}\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
EVENT_CONTEXT = re.compile(
    r"\b(?:avist(?:ou|ado|amento)|observ(?:ou|ado|ação)|detect(?:ou|ado)|ocorreu|pous(?:ou|o)|"
    r"encontr(?:ou|o)|sighting|observed|detected|occurred|landed|encountered|hearing|audiência)\b",
    re.IGNORECASE,
)
PT_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _date_or_fallback(year: int, month: int, day: int, raw: str) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return identity_key(raw)


def normalized_date(raw: str, language: str) -> str:
    numeric = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})", raw)
    if numeric:
        first, second, year = (int(value) for value in numeric.groups())
        year = year + (2000 if year < 50 else 1900) if year < 100 else year
        if first > 12:
            day, month = first, second
        elif second > 12:
            month, day = first, second
        elif language == "en":
            month, day = first, second
        else:
            day, month = first, second
        return _date_or_fallback(year, month, day, raw)
    iso = re.fullmatch(r"((?:19|20)\d{2})-(\d{2})-(\d{2})", raw)
    if iso:
        return _date_or_fallback(*(int(value) for value in iso.groups()), raw)
    portuguese = re.fullmatch(r"(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]+)\s+de\s+((?:19|20)\d{2})", raw, re.I)
    if portuguese and portuguese.group(2).casefold() in PT_MONTHS:
        return _date_or_fallback(
            int(portuguese.group(3)), PT_MONTHS[portuguese.group(2).casefold()], int(portuguese.group(1)), raw,
        )
    english = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),?\s+((?:19|20)\d{2})", raw, re.I)
    if english and english.group(1).casefold() in EN_MONTHS:
        return _date_or_fallback(
            int(english.group(3)), EN_MONTHS[english.group(1).casefold()], int(english.group(2)), raw,
        )
    return identity_key(raw)


def _segments(canonical: dict, translation: dict) -> Iterable[tuple[str, str, str]]:
    for page in canonical.get("pages", []):
        for segment in page.get("segments", []):
            yield segment["segment_id"], "pt-BR", segment.get("text", "")
    for segment in canonical.get("segments", []):
        yield segment["segment_id"], "pt-BR", segment.get("text", "")
    for page in translation.get("pages", []):
        for segment in page.get("segments", []):
            if segment.get("status") not in {"failed", "not-required"}:
                yield segment["segment_id"], "en", segment.get("text", "")
    for segment in translation.get("segments", []):
        if segment.get("status") not in {"failed", "not-required"}:
            yield segment["segment_id"], "en", segment.get("text", "")


def extract_entities(canonical: dict, translation: dict) -> dict:
    occurrences: dict[tuple[str, str], dict] = {}
    entities: dict[str, dict] = {}
    for segment_id, language, text in _segments(canonical, translation):
        for match in ALIAS_PATTERN.finditer(text):
            alias = match.group(0)
            canonical_name, category = ALIAS_LOOKUP[identity_key(alias)]
            entity_id = stable_id("ent", f"{category}|{identity_key(canonical_name)}")
            entity = entities.setdefault(entity_id, {
                "entity_id": entity_id,
                "name": canonical_name,
                "category": category,
                "aliases": set(),
                "source_segment_ids": set(),
                "evidence_languages": set(),
            })
            entity["aliases"].add(alias)
            entity["source_segment_ids"].add(segment_id)
            entity["evidence_languages"].add(language)
            key = (entity_id, segment_id)
            occurrence = occurrences.setdefault(key, {
                "entity_id": entity_id,
                "source_segment_id": segment_id,
                "languages": set(),
                "mentions": set(),
            })
            occurrence["languages"].add(language)
            occurrence["mentions"].add(alias)

    entity_rows = []
    for entity in entities.values():
        entity_rows.append({
            **entity,
            "aliases": sorted(entity["aliases"], key=str.casefold),
            "source_segment_ids": sorted(entity["source_segment_ids"]),
            "evidence_languages": sorted(entity["evidence_languages"]),
            "mention_count": len(entity["source_segment_ids"]),
            "counting_policy": "one occurrence per canonical source segment; translation is supplemental",
        })
    occurrence_rows = [
        {
            **row,
            "languages": sorted(row["languages"]),
            "mentions": sorted(row["mentions"], key=str.casefold),
        }
        for row in occurrences.values()
    ]
    return {
        "schema": "ufo-files-cross-language-entities/v1",
        "entities": sorted(entity_rows, key=lambda item: item["entity_id"]),
        "occurrences": sorted(occurrence_rows, key=lambda item: (item["entity_id"], item["source_segment_id"])),
    }


def extract_events(canonical: dict, translation: dict) -> dict:
    evidence: dict[tuple[str, str], dict] = {}
    for segment_id, language, text in _segments(canonical, translation):
        if not EVENT_CONTEXT.search(text):
            continue
        for match in DATE_PATTERN.finditer(text):
            raw_date = match.group(0)
            date_key = normalized_date(raw_date, language)
            key = (segment_id, date_key)
            record = evidence.setdefault(key, {
                "event_id": stable_id("evt", f"{canonical['document_id']}|{segment_id}|{date_key}"),
                "source_segment_id": segment_id,
                "date_as_written": raw_date,
                "normalized_date": date_key,
                "evidence_languages": set(),
                "evidence": {},
                "review_status": "candidate-unreviewed",
                "document_origin_country": canonical.get("source", {}).get("country", "BR"),
                "event_location": None,
            })
            record["evidence_languages"].add(language)
            record["evidence"][language] = text[:500]
            # Country of the record is never inferred as the event location.
            locations = []
            for entity_match in ALIAS_PATTERN.finditer(text):
                name, category = ALIAS_LOOKUP[identity_key(entity_match.group(0))]
                if category == "location":
                    locations.append(name)
            if len(set(locations)) == 1:
                record["event_location"] = locations[0]
    rows = []
    for record in evidence.values():
        rows.append({
            **record,
            "evidence_languages": sorted(record["evidence_languages"]),
            "evidence": dict(sorted(record["evidence"].items())),
        })
    return {
        "schema": "ufo-files-cross-language-events/v1",
        "events": sorted(rows, key=lambda item: item["event_id"]),
        "counting_policy": "one event candidate per canonical source segment and date; translations do not add events",
    }
