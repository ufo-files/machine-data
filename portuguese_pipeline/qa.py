"""Cross-language integrity checks for Portuguese-to-English derivatives."""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal, InvalidOperation


REDACTION = re.compile(
    r"\[(?:REDACTED|REDAÇÃO|SUPRIMIDO|ILEG[IÍ]VEL|ILLEGIBLE|INDECI[FS]R[AÁ]VEL)[^\]]*\]"
    r"|<(?:ileg[ií]vel|illegible|redacted)>|█+",
    re.IGNORECASE,
)
FILENAME = re.compile(r"(?<![\w./-])[\w .()&'-]+\.(?:pdf|jpe?g|png|tiff?|mp4|mov|mkv|mp3|wav)(?!\w)", re.I)
IDENTIFIER = re.compile(r"\b(?=[A-Z0-9./-]{4,}\b)(?=[A-Z0-9./-]*\d)[A-Z][A-Z0-9]*(?:[./-][A-Z0-9]+)+\b")
NUMERIC_IDENTIFIER = re.compile(r"(?<![\d/])\d{1,6}/(?:19|20)?\d{2}(?![\d/])")
OFFICIAL_CODE = re.compile(
    r"\b(?:RIC|REQ|NUP|IPM|PROCESSO|OF[IÍ]CIO|PORTARIA|ENVELOPE|COMUNICA[CÇ][AÃ]O)"
    r"[ \t]*(?:N[.º°O][ \t]*)?[A-Z0-9][A-Z0-9./-]*\d[A-Z0-9./-]*\b",
    re.I,
)
ABBREVIATION = re.compile(
    r"\b(?:FAB|COMAER|COMAR|SNI|CISA|CODAR|SINDACTA|COMDABRA|CENDOC|COREG|CBU|CBM|PM|"
    r"EsSA|ESA|NUP|RIC|REQ|IPM|PTB|DF)(?:/[A-Z0-9]{2,})?\b"
)
CALLSIGN = re.compile(r"\b(?:indicativo|callsign)\s+[\"“'‘]([^\"”'’]{1,40})[\"”'’]", re.I)
COORDINATE = re.compile(
    r"(?<!\w)(?:"
    r"[+-]\d{1,3}(?:[.,]\d+)?[ \t]*[°º]"
    r"|\d{1,3}(?:[.,]\d+)?[ \t]*[°º][ \t]*(?:"
    r"\d{1,2}(?:[.,]\d+)?[ \t]*['′](?:[ \t]*\d{1,2}(?:[.,]\d+)?[ \t]*[\"″])?[ \t]*[NSEWO]?"
    r"|[NSEWO]\b))",
)
MEASUREMENT = re.compile(
    r"(?<!\w)\d+(?:[.,]\d+)?(?:"
    r"(?:[ \t]+(?:a|to)[ \t]+|[ \t]*[-–][ \t]*)\d+(?:[.,]\d+)?"
    r")?[ \t]*(?:km/h|m/s|mph|km|cm|mm|kg|ft|m|g|p[eé]s?|metros?|meters?|"
    r"quil[oô]metros?|kilometers?|feet|foot|miles?)(?!\w)",
    re.I,
)
NUMBER = re.compile(
    r"(?<![\w])\d+(?:[.,]\d+)*(?:(?=[º°](?:\W|$))|(?=(?:st|nd|rd|th|h|am|pm)\b)|(?![\w]))",
    re.I,
)
DATE_NUMERIC = re.compile(r"(?<!\d)(?:\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})|(?:19|20)\d{2}-\d{2}-\d{2})(?!\d)")
DATE_NAMED_PT = re.compile(
    r"\b(\d{1,2})\s+de\s+(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+((?:19|20)\d{2})\b",
    re.I,
)
DATE_NAMED_EN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{2})\b",
    re.I,
)
NAME = re.compile(
    r"\b(?:[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][\wÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç.'’-]+)"
    r"(?:\s+(?:d[aeo]s?|e|do|dos|da|das|of|the|[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][\wÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç.'’-]+)){1,5}\b"
)
PT_NEGATIONS = {
    "não": re.compile(
        r"\b(?:not|no|never|without|neither|nor|unidentified|unknown|unconfirmed|unverified|"
        r"undetected|unauthorized|unavailable|impossible|invisible)\b",
        re.I,
    ),
    "nunca": re.compile(r"\bnever\b", re.I),
    "sem": re.compile(r"\b(?:without|lacking|absent|free of)\b", re.I),
    "nenhum": re.compile(r"\b(?:no|none|neither)\b", re.I),
    "nenhuma": re.compile(r"\b(?:no|none|neither)\b", re.I),
}
TRANSLATOR_COMMENTARY = re.compile(
    r"(?im)^\s*(?:translation|translator'?s? note|note)\s*:|^\s*\((?:translation|no context provided|literally)\b"
)
PT_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
UNIT_ALIASES = {
    "metro": "m", "metros": "m", "meter": "m", "meters": "m", "m": "m",
    "quilômetro": "km", "quilômetros": "km", "kilometer": "km", "kilometers": "km", "km": "km",
    "pé": "ft", "pés": "ft", "foot": "ft", "feet": "ft", "ft": "ft",
    "centímetro": "cm", "centímetros": "cm", "centimeter": "cm", "centimeters": "cm", "cm": "cm",
    "milímetro": "mm", "milímetros": "mm", "millimeter": "mm", "millimeters": "mm", "mm": "mm",
    "kg": "kg", "g": "g", "m/s": "m/s", "km/h": "km/h", "mph": "mph",
}
GENERIC_NAME_WORDS = {
    "aérea", "brasileira", "câmara", "comissão", "congresso", "defesa", "departamento",
    "deputados", "diretor", "estado", "federal", "força", "governo", "informações", "ministro",
    "nacional", "oficial", "presidente", "república", "requerimento", "secretaria", "senhor",
}
NAME_PREFIX = re.compile(
    r"^(?:d[ao]s?\s+)?(?:sr\.?|sra\.?|dr\.?|dra\.?|gen\.?|cel\.?|cap\.?|ten\.?)\s+",
    re.I,
)


def protected_tokens(text: str, official_identifiers: list[str] | None = None) -> list[str]:
    tokens: set[str] = set()
    for pattern in (
        REDACTION, FILENAME, OFFICIAL_CODE, IDENTIFIER, NUMERIC_IDENTIFIER, ABBREVIATION, COORDINATE,
    ):
        tokens.update(match.group(0) for match in pattern.finditer(text))
    tokens.update(match.group(1) for match in CALLSIGN.finditer(text))
    for value in official_identifiers or []:
        if value and value in text:
            tokens.add(value)
    return sorted(tokens, key=lambda item: (-len(item), item))


def mask_protected(text: str, official_identifiers: list[str] | None = None) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}
    masked = text
    for index, token in enumerate(protected_tokens(text, official_identifiers)):
        placeholder = f"__UFO_PROTECTED_{index:03d}__"
        if token in masked:
            masked = masked.replace(token, placeholder)
            replacements[placeholder] = token
    return masked, replacements


def restore_protected(text: str, replacements: dict[str, str]) -> tuple[str, list[str]]:
    restored = text
    missing: list[str] = []
    for placeholder, token in replacements.items():
        if placeholder not in restored:
            missing.append(token)
            continue
        restored = restored.replace(placeholder, token)
    return restored, missing


def _counter(pattern: re.Pattern[str], text: str) -> Counter[str]:
    return Counter(match.group(0).casefold() for match in pattern.finditer(text))


def _coordinates(text: str) -> Counter[str]:
    values: Counter[str] = Counter()
    for match in COORDINATE.finditer(text):
        value = match.group(0).upper().replace("º", "°").replace("O", "W").replace(",", ".")
        values[re.sub(r"[ \t]+", "", value)] += 1
    return values


def _names(text: str) -> set[str]:
    values: set[str] = set()
    for match in NAME.finditer(text):
        value = " ".join(match.group(0).split()).strip(".,;:()[]{}")
        if not value or value.isupper():
            continue
        value = NAME_PREFIX.sub("", value).strip(".,;:()[]{}")
        lexical_words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.'’-]*", value)
        significant = [word for word in lexical_words if word.casefold() not in {"da", "das", "de", "do", "dos", "e"}]
        if len(significant) < 2:
            continue
        if any(word.casefold() in GENERIC_NAME_WORDS for word in significant):
            continue
        values.add(value)
    return values


def _dates(text: str, *, language: str) -> Counter[str]:
    values: Counter[str] = Counter()
    for match in DATE_NUMERIC.finditer(text):
        raw = match.group(0)
        if "-" in raw and raw[:4].isdigit():
            year, month, day = raw.split("-")
        else:
            first, second, year = re.split(r"[/-]", raw)
            if int(first) > 12:
                day, month = first, second
            elif int(second) > 12:
                month, day = first, second
            elif language == "en":
                month, day = first, second
            else:
                day, month = first, second
            if len(year) == 2:
                year = "20" + year if int(year) < 50 else "19" + year
        values[f"{int(year):04d}-{int(month):02d}-{int(day):02d}"] += 1
    for day, month, year in DATE_NAMED_PT.findall(text):
        values[f"{int(year):04d}-{PT_MONTHS[month.casefold()]:02d}-{int(day):02d}"] += 1
    for month, day, year in DATE_NAMED_EN.findall(text):
        values[f"{int(year):04d}-{EN_MONTHS[month.casefold()]:02d}-{int(day):02d}"] += 1
    return values


def _number_value(value: str) -> str:
    compact = value.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", compact):
        return compact.replace(".", "").replace(",", "")
    normalized = compact.replace(",", ".")
    try:
        return format(Decimal(normalized).normalize(), "f")
    except InvalidOperation:
        return normalized


def _measurements(text: str) -> Counter[str]:
    values: Counter[str] = Counter()
    for match in MEASUREMENT.finditer(text):
        raw = match.group(0)
        number_match = re.match(r"\d+(?:[.,]\d+)?", raw)
        unit_match = re.search(r"([A-Za-zÀ-ÿ/]+)\s*$", raw)
        if number_match and unit_match:
            unit = UNIT_ALIASES.get(unit_match.group(1).casefold(), unit_match.group(1).casefold())
            values[f"{_number_value(number_match.group(0))} {unit}"] += 1
    return values


def _numbers(text: str) -> Counter[str]:
    return Counter(_number_value(match.group(0)) for match in NUMBER.finditer(text))


def compare_translation(source: str, target: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for name, source_values, target_values, severity in (
        ("dates", _dates(source, language="pt"), _dates(target, language="en"), "error"),
        ("measurements", _measurements(source), _measurements(target), "error"),
        ("coordinates", _coordinates(source), _coordinates(target), "error"),
        ("redactions", _counter(REDACTION, source), _counter(REDACTION, target), "error"),
        ("numbers", _numbers(source), _numbers(target), "warning"),
    ):
        missing = list((source_values - target_values).elements())
        added = list((target_values - source_values).elements())
        if missing or added:
            findings.append({
                "check": name,
                "severity": severity,
                "status": "mismatch",
                "missing_from_translation": sorted(missing),
                "added_in_translation": sorted(added),
            })

    if TRANSLATOR_COMMENTARY.search(target):
        findings.append({
            "check": "translator-commentary",
            "severity": "error",
            "status": "unexpected-derived-commentary",
        })

    source_names = _names(source)
    folded_target = target.casefold()
    missing_names = sorted(name for name in source_names if name.casefold() not in folded_target)
    if missing_names:
        findings.append({
            "check": "names",
            "severity": "warning",
            "status": "mismatch",
            "missing_from_translation": missing_names,
            "added_in_translation": [],
        })

    source_folded = source.casefold()
    for marker, target_pattern in PT_NEGATIONS.items():
        count = len(re.findall(rf"\b{re.escape(marker)}\b", source_folded))
        translated_count = len(target_pattern.findall(target))
        if count and translated_count < count:
            findings.append({
                "check": "negation",
                "severity": "error",
                "status": "mismatch",
                "source_marker": marker,
                "source_count": count,
                "translation_equivalent_count": translated_count,
            })
    return findings


def review_weight(text: str, confidence: float | None = None) -> tuple[int, list[str]]:
    weight = 0
    reasons: list[str] = []
    if REDACTION.search(text):
        weight += 5
        reasons.append("redaction-or-illegibility")
    if re.search(r"\b(?:manuscrit[oa]|handwrit|rubrica|carimbo)\b", text, re.I):
        weight += 5
        reasons.append("handwriting-or-stamp")
    if re.search(r"(?:\t| {3,}|\|).*(?:\t| {3,}|\|)", text):
        weight += 3
        reasons.append("table-or-form")
    if re.search(r"\b(?:FAB|COMAER|SNI|CISA|CODAR|OVNI|NUP|RIC|REQ|CLP)\b", text):
        weight += 3
        reasons.append("military-or-official-abbreviation")
    if re.search(r"\b(?:Opera[cç][aã]o Prato|Colares|Varginha|Noite Oficial)\b", text, re.I):
        weight += 4
        reasons.append("high-importance-case")
    if confidence is not None and confidence < 0.8:
        weight += 4
        reasons.append("low-ocr-confidence")
    return weight, reasons
