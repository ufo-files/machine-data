#!/usr/bin/env python3
"""Build a compact, static graph catalog from UFO Files transcripts.

The input files remain the source of truth. This script publishes conservative,
evidence-backed entity candidates and relationships for the browser app; it does
not rewrite or copy transcript text.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


SCHEMA = "ufo-files-relationship-catalog/v1"
SKIP_PARTS = {
    ".git", ".state", ".tmp", ".Spotlight-V100", ".Trashes",
    "relationship-graph-builder", "logs", "quarantine",
}
KNOWN = {
    "AARO": ("All-domain Anomaly Resolution Office", "government_agency"),
    "CIA": ("Central Intelligence Agency", "government_agency"),
    "DIA": ("Defense Intelligence Agency", "government_agency"),
    "DOE": ("Department of Energy", "government_agency"),
    "FBI": ("Federal Bureau of Investigation", "government_agency"),
    "NASA": ("NASA", "government_agency"),
    "NSA": ("National Security Agency", "government_agency"),
    "NRO": ("National Reconnaissance Office", "government_agency"),
    "NORAD": ("NORAD", "government_agency"),
    "USAF": ("U.S. Air Force", "government_agency"),
    "U.S. Air Force": ("U.S. Air Force", "government_agency"),
    "United States Air Force": ("U.S. Air Force", "government_agency"),
    "Department of Defense": ("Department of Defense", "government_agency"),
    "Department of War": ("Department of War", "government_agency"),
    "Federal Aviation Administration": ("Federal Aviation Administration", "government_agency"),
    "National Archives": ("National Archives", "government_agency"),
    "Project Blue Book": ("Project Blue Book", "program"),
    "KONA BLUE": ("KONA BLUE", "program"),
    "Majestic 12": ("Majestic 12", "program"),
    "MJ-12": ("Majestic 12", "program"),
    "Area 51": ("Area 51", "location"),
    "Roswell": ("Roswell", "location"),
    "UAP": ("UAP", "subject"),
    "UFO": ("UFO", "subject"),
    "UFOs": ("UFO", "subject"),
    "FOIA": ("FOIA", "subject"),
}
KNOWN_PATTERN = re.compile(
    r"(?<![\w-])(" + "|".join(sorted((re.escape(k) for k in KNOWN), key=len, reverse=True)) + r")(?![\w-])",
    re.IGNORECASE,
)
CAP_PHRASE = re.compile(
    r"\b(?:Dr\.|Mr\.|Mrs\.|Ms\.|Gen\.|General|Colonel|Col\.|Major|Maj\.|Captain|Capt\.|Lt\.|Lieutenant)?"
    r"\s*(?:[A-Z][A-Za-z'’-]{1,25}|[A-Z]{2,})(?:\s+(?:of|the|and|&|for|[A-Z][A-Za-z'’-]{1,25}|[A-Z]{2,})){1,5}\b"
)
DATE_PATTERN = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+(?:19|20)\d{2}\b|\b(?:19|20)\d{2}-\d{2}-\d{2}\b"
)
ORG_WORDS = {
    "agency", "administration", "aerospace", "air force", "army", "bureau", "committee",
    "corporation", "department", "directorate", "division", "foundation", "institute",
    "intelligence", "laboratory", "navy", "office", "organization", "university",
}
LOCATION_WORDS = {
    "air force base", "airport", "area", "base", "county", "desert", "island", "lake",
    "mount", "mountain", "range", "river", "site",
}
PROGRAM_WORDS = {"operation", "program", "project", "task force"}
GENERIC = {
    "air force", "armed forces", "assistant director", "chief of staff", "department",
    "executive officer", "flying object", "general public", "intelligence officer",
    "national security", "press release", "project officer", "public affairs",
    "secretary of defense", "special agent", "the united states", "united states",
    "unidentified aerial phenomena", "unidentified flying object",
}
NON_NAME_WORDS = {
    "act", "additional", "aerial", "all", "asset", "balloon", "balloons", "blue", "book",
    "command", "commands", "commanding", "concerning", "concerns", "congressional", "contained",
    "data", "details", "disclosure", "disc", "discs", "exemption", "field", "flying", "force",
    "code", "form", "general", "government", "group", "hearing", "information", "matter", "memorandum",
    "mission", "number", "object", "objects", "off", "operations", "part", "phenomena", "phone",
    "privacy", "rate", "regarding", "reply", "request", "security", "station", "task", "top",
    "thought", "travel", "type", "unidentified", "war", "working",
}
KNOWN_LOCATIONS = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware",
    "district of columbia", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah",
    "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming", "los alamos",
    "los angeles", "las vegas", "san francisco", "san diego", "kansas city", "white sands",
    "oak ridge", "middle east", "south america", "united kingdom", "soviet union", "milky way",
    "oklahoma city", "new york city", "colorado springs", "mexico city", "fort worth", "new orleans",
}
FIRST_NAMES = {
    "alan", "albert", "alex", "alexander", "allen", "andrew", "anna", "anthony", "arthur",
    "barbara", "ben", "benjamin", "bill", "bob", "brandon", "brian", "bruce", "carl", "carol",
    "charles", "chris", "christopher", "dan", "daniel", "david", "diana", "donald", "dorothy",
    "edgar", "edward", "elizabeth", "eric", "ernest", "eugene", "francis", "frank", "fred",
    "frederick", "gary", "george", "gerald", "glenn", "gordon", "harold", "harry", "helen",
    "henry", "herbert", "howard", "jack", "james", "jane", "jean", "jeremy", "jim", "joe",
    "john", "jose", "joseph", "judith", "karen", "keith", "kelly", "ken", "kenneth", "laura",
    "lee", "linda", "margaret", "mark", "mary", "michael", "mike", "milton", "monica", "nancy",
    "neil", "nikola", "paul", "peter", "philip", "raymond", "richard", "robert", "ronald",
    "russell", "sam", "samuel", "scott", "sidney", "staphen", "stanley", "stanton", "stephen",
    "steven", "susan", "thomas", "tim", "timothy", "walter", "william",
}
ROLE_PREFIX = re.compile(r"^(?:President|Professor|Senator|Congressman|Congresswoman|Secretary|Admiral|General|Colonel|Captain)\s+", re.I)
FIELD_LABELS = {
    "date", "document", "from", "memorandum", "name", "page", "reference", "subject", "to",
}
HONORIFIC = re.compile(r"^(?:Dr\.|Mr\.|Mrs\.|Ms\.|Gen\.|General|Colonel|Col\.|Major|Maj\.|Captain|Capt\.|Lt\.|Lieutenant)\s+", re.I)
RELATIONS = [
    ("affiliated_with", re.compile(r"\b(?:worked|works|served|employed|assigned|member|director|chief|head|affiliated)\b", re.I)),
    ("reported_to", re.compile(r"\b(?:reported to|under the command of|supervised by)\b", re.I)),
    ("investigated", re.compile(r"\b(?:investigated|investigation of|inquired into|examined)\b", re.I)),
    ("located_at", re.compile(r"\b(?:located|stationed|based|at the site|near)\b", re.I)),
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha1(value.encode('utf-8')).hexdigest()[:12]}"


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip(" \t\r\n,;:()[]{}")


def comparison_key(value: str) -> str:
    value = HONORIFIC.sub("", clean_space(value))
    value = value.replace("’", "'").replace("U. S.", "U.S.")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def title_from_path(path: Path) -> str:
    name = path.stem.replace("_", " ").replace("-", " ")
    return clean_space(re.sub(r"\s+", " ", name)).title()


def sentence_segments(text: str) -> Iterable[str]:
    for block in re.split(r"(?:===== PAGE \d+ =====|\n{2,})", text):
        for item in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])|\n", block):
            item = clean_space(item)
            if 24 <= len(item) <= 1600:
                yield item


def read_ocr(path: Path) -> tuple[dict, list[str]] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    first, sep, body = text.partition("\n")
    if not sep:
        return None
    try:
        metadata = json.loads(first)
    except json.JSONDecodeError:
        return None
    if metadata.get("schema") != "ufo-files-archive-ocr/v1":
        return None
    body = re.sub(r"(?m)^\{\"alpha_words\".*?\}\s*$", "", body)
    return metadata, list(sentence_segments(body))


def read_tsv(path: Path) -> tuple[dict, list[str], int] | None:
    sidecar = path.with_suffix(".source.json")
    if not sidecar.exists():
        return None
    try:
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, json.JSONDecodeError):
        return None
    if metadata.get("schema") != "ufo-files-archive-media-transcripts/v1":
        return None
    segments, duration = [], 0
    for line in lines:
        fields = line.split("\t", 2)
        if len(fields) != 3 or fields[0].lower() == "start":
            continue
        try:
            duration = max(duration, int(float(fields[1])))
        except ValueError:
            pass
        value = clean_space(fields[2])
        if value:
            segments.append(value)
    return metadata, segments, duration


def classify_phrase(raw: str) -> tuple[str, float] | None:
    raw = clean_space(raw)
    key = comparison_key(raw)
    if len(key) < 3 or key in GENERIC or key in FIELD_LABELS or key in LOCATION_WORDS:
        return None
    words = key.split()
    if len(words) > 6 or any(len(word) == 1 for word in words[1:-1]):
        return None
    lower = raw.lower()
    if key in KNOWN_LOCATIONS:
        return "location", 0.9
    if key.startswith("uss "):
        return None
    if lower.endswith((" of", " the", " and", " for")):
        return None
    if any(word in lower for word in LOCATION_WORDS):
        return "location", 0.79
    if any(word in NON_NAME_WORDS for word in words):
        return None
    if lower.startswith(("director of ", "chief of ", "commanding ")):
        return None
    if key in {"united nations", "united press", "associated press", "aviation week", "abc news", "big media"}:
        return "organization", 0.88
    if any(word in lower for word in ORG_WORDS):
        category = "government_agency" if any(word in lower for word in ("agency", "bureau", "department", "air force", "army", "navy", "office")) else "organization"
        return category, 0.82
    if any(lower.startswith(word + " ") for word in PROGRAM_WORDS):
        return "program", 0.82
    if raw.isupper() or words[0] in {"mg", "rel", "please", "district"}:
        return None
    role_match = ROLE_PREFIX.match(raw)
    stripped = ROLE_PREFIX.sub("", HONORIFIC.sub("", raw))
    person_words = stripped.split()
    valid_words = all(re.match(r"^(?:[A-Z][A-Za-z'’-]{1,25}|[A-Z]\.)$", word) for word in person_words)
    has_first_name = person_words and person_words[0].rstrip(".").lower() in FIRST_NAMES
    if ((2 <= len(person_words) <= 4 and has_first_name) or (role_match and 1 <= len(person_words) <= 4)) and valid_words:
        if person_words[0].lower() not in {"chapter", "figure", "table", "section", "appendix"}:
            return "person", 0.72 if has_first_name else 0.67
    return None


def load_registry(path: Path) -> dict[str, tuple[str, str]]:
    if not path.exists():
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))
    registry = {}
    for record in records:
        canonical = clean_space(record["name"])
        registry[comparison_key(canonical)] = (canonical, record["category"])
    return registry


@dataclass
class Candidate:
    canonical: str
    category: str
    curated: bool = False
    variants: collections.Counter = field(default_factory=collections.Counter)
    documents: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    segments: set[str] = field(default_factory=set)
    examples: list[dict] = field(default_factory=list)
    mentions: int = 0
    extraction_total: float = 0.0

    def add(self, raw: str, doc_id: str, source: str, segment_id: str, excerpt: str, confidence: float) -> None:
        self.variants[clean_space(raw)] += 1
        self.documents.add(doc_id)
        self.sources.add(source)
        self.segments.add(segment_id)
        self.mentions += 1
        self.extraction_total += confidence
        if len(self.examples) < 4:
            self.examples.append({"documentId": doc_id, "excerpt": excerpt[:280]})


def extract_mentions(segment: str, registry: dict[str, tuple[str, str]]) -> list[tuple[str, str, str, float, bool]]:
    found: dict[str, tuple[str, str, str, float, bool]] = {}
    for match in KNOWN_PATTERN.finditer(segment):
        raw = match.group(0)
        lookup = next((key for key in KNOWN if key.lower() == raw.lower()), raw)
        canonical, category = KNOWN[lookup]
        found[comparison_key(canonical)] = (raw, canonical, category, 0.99, True)
    for match in DATE_PATTERN.finditer(segment):
        raw = match.group(0)
        found[comparison_key(raw)] = (raw, raw, "date", 0.96, False)
    for match in CAP_PHRASE.finditer(segment):
        raw = match.group(0)
        registry_match = registry.get(comparison_key(raw))
        if registry_match:
            canonical, category = registry_match
            found[comparison_key(canonical)] = (raw, canonical, category, 0.98, True)
            continue
        classification = classify_phrase(raw)
        if not classification:
            continue
        category, confidence = classification
        key = comparison_key(raw)
        found.setdefault(key, (raw, HONORIFIC.sub("", clean_space(raw)), category, confidence, False))
    return list(found.values())


def accepted(candidate: Candidate) -> bool:
    if candidate.curated:
        return True
    documents = len(candidate.documents)
    if candidate.category == "person":
        return candidate.mentions >= 3 and documents >= 2
    if candidate.category == "date":
        return candidate.mentions >= 2
    return candidate.mentions >= 2 and documents >= 2


def build(input_root: Path, output: Path, max_entities: int, max_edges: int) -> dict:
    registry = load_registry(Path(__file__).resolve().parents[1] / "data" / "curated_entities.json")
    candidates: dict[str, Candidate] = {}
    documents: list[dict] = []
    segment_entities: dict[str, list[str]] = {}
    segment_text: dict[str, str] = {}
    source_counts: collections.Counter = collections.Counter()
    source_words: collections.Counter = collections.Counter()

    paths = sorted(
        path for path in input_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".txt", ".tsv"} and not (set(path.parts) & SKIP_PARTS)
    )
    for path in paths:
        relative = path.relative_to(input_root).as_posix()
        source = relative.split("/", 1)[0]
        parsed = None
        fmt = ""
        duration = None
        if path.suffix.lower() == ".txt":
            parsed = read_ocr(path)
            if parsed:
                metadata, segments = parsed
                fmt = "ocr"
        else:
            media = read_tsv(path)
            if media:
                metadata, segments, duration = media
                parsed = (metadata, segments)
                fmt = "transcript"
        if not parsed:
            continue
        metadata, segments = parsed
        doc_id = stable_id("doc", relative)
        words = sum(len(segment.split()) for segment in segments)
        title = title_from_path(Path(str(metadata.get("source_file") or path.name)))
        document = {
            "id": doc_id,
            "title": title,
            "source": source,
            "path": relative,
            "format": fmt,
            "words": words,
            "segments": len(segments),
            "bytes": int(metadata.get("source_bytes") or path.stat().st_size),
            "createdAt": metadata.get("created_utc") or metadata.get("created_at"),
            "engine": metadata.get("engine") or metadata.get("backend"),
            "durationMs": duration,
        }
        documents.append(document)
        source_counts[source] += 1
        source_words[source] += words
        for number, segment in enumerate(segments):
            sid = f"{doc_id}:{number}"
            mentions = extract_mentions(segment, registry)
            keys = []
            for raw, canonical, category, confidence, curated in mentions:
                key = f"{category}:{comparison_key(canonical)}"
                candidate = candidates.get(key)
                if candidate is None:
                    candidate = candidates[key] = Candidate(canonical, category, curated)
                else:
                    candidate.curated = candidate.curated or curated
                candidate.add(raw, doc_id, source, sid, segment, confidence)
                keys.append(key)
            if keys:
                segment_entities[sid] = list(dict.fromkeys(keys))
                segment_text[sid] = segment

    accepted_candidates = {key: value for key, value in candidates.items() if accepted(value)}
    ranked = sorted(
        accepted_candidates.items(),
        key=lambda item: (item[1].mentions, len(item[1].documents), item[1].canonical),
        reverse=True,
    )
    published_items = ranked[:max_entities]
    published = dict(published_items)
    entity_ids = {key: stable_id("ent", key) for key in published}
    entities = []
    for key, candidate in published_items:
        extraction = candidate.extraction_total / max(1, candidate.mentions)
        evidence_factor = min(1.0, 0.45 + len(candidate.documents) * 0.08 + candidate.mentions * 0.015)
        classification = 0.99 if candidate.curated else min(0.94, extraction * evidence_factor)
        name = candidate.canonical if candidate.curated else candidate.variants.most_common(1)[0][0]
        entities.append({
            "id": entity_ids[key],
            "name": name,
            "canonicalName": candidate.canonical,
            "category": candidate.category,
            "mentions": candidate.mentions,
            "documentCount": len(candidate.documents),
            "sourceCount": len(candidate.sources),
            "extractionConfidence": round(extraction, 3),
            "classificationConfidence": round(classification, 3),
            "reviewStatus": "curated" if candidate.curated else ("review" if classification < 0.72 else "evidence_backed"),
            "variants": [name for name, _ in candidate.variants.most_common(6)],
            "documentIds": sorted(candidate.documents),
            "evidence": candidate.examples,
        })

    edge_stats: dict[tuple[str, str, str], dict] = {}
    for sid, keys in segment_entities.items():
        usable = sorted(set(key for key in keys if key in published))
        if len(usable) < 2 or len(usable) > 30:
            continue
        text = segment_text[sid]
        relation = next((name for name, pattern in RELATIONS if pattern.search(text)), "co_mentioned")
        for i, left in enumerate(usable):
            for right in usable[i + 1:]:
                if published[left].category == "date" and published[right].category == "date":
                    continue
                edge_key = (left, right, relation)
                stat = edge_stats.setdefault(edge_key, {"segments": set(), "documents": set(), "examples": []})
                stat["segments"].add(sid)
                stat["documents"].add(sid.split(":", 1)[0])
                if len(stat["examples"]) < 3:
                    stat["examples"].append({"documentId": sid.split(":", 1)[0], "excerpt": text[:280]})
    edges = []
    for (left, right, relation), stat in edge_stats.items():
        evidence_count = len(stat["segments"])
        document_count = len(stat["documents"])
        if relation == "co_mentioned" and evidence_count < 2:
            continue
        edges.append({
            "id": stable_id("edge", f"{left}|{right}|{relation}"),
            "source": entity_ids[left],
            "target": entity_ids[right],
            "relationship": relation,
            "evidenceCount": evidence_count,
            "documentCount": document_count,
            "confidence": round(min(0.98, 0.48 + evidence_count * 0.06 + document_count * 0.05 + (0.12 if relation != "co_mentioned" else 0)), 3),
            "evidence": stat["examples"],
        })
    edges.sort(key=lambda edge: (edge["evidenceCount"], edge["documentCount"]), reverse=True)
    all_edge_count = len(edges)
    edges = edges[:max_edges]

    sources = [
        {"id": stable_id("src", source), "name": source, "documents": source_counts[source], "words": source_words[source]}
        for source in sorted(source_counts)
    ]
    catalog = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "input": {"rootName": input_root.name, "transcriptsAreSourceOfTruth": True},
        "publicationPolicy": {
            "personEvidenceFloor": "3 mentions across 2 documents",
            "otherEvidenceFloor": "2 mentions across 2 documents (dates: 2 mentions)",
            "relationshipEvidenceFloor": "2 co-mentions or 1 same-segment typed cue",
            "denseSegmentLimit": 30,
            "maxEntities": max_entities,
            "maxEdges": max_edges,
        },
        "counts": {
            "documents": len(documents),
            "sources": len(sources),
            "candidateEntities": len(candidates),
            "acceptedEntities": len(accepted_candidates),
            "publishedEntities": len(entities),
            "acceptedEdges": all_edge_count,
            "publishedEdges": len(edges),
        },
        "sources": sources,
        "documents": documents,
        "entities": entities,
        "edges": edges,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_input = Path(__file__).resolve().parents[2]
    parser.add_argument("--input", type=Path, default=default_input)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "catalog.json")
    parser.add_argument("--max-entities", type=int, default=1200)
    parser.add_argument("--max-edges", type=int, default=4000)
    args = parser.parse_args()
    catalog = build(args.input.resolve(), args.output.resolve(), args.max_entities, args.max_edges)
    print(json.dumps({"output": str(args.output), **catalog["counts"]}, indent=2))


if __name__ == "__main__":
    main()
