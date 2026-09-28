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
FILENAME = re.compile(r"(?<![\w./-])[\w()&'-]+(?:[ .][\w()&'-]+)*\.(?:pdf|jpe?g|png|tiff?|mp4|mov|mkv|mp3|wav)(?!\w)", re.I)
URL = re.compile(r"\b(?:https?://|www\.)[^\s<>\"'“”‘’]+", re.I)
IDENTIFIER = re.compile(r"\b(?=[A-Z0-9./-]{4,}\b)(?=[A-Z0-9./-]*\d)[A-Z][A-Z0-9]*(?:[./-][A-Z0-9]+)+\b")
NUMERIC_IDENTIFIER = re.compile(r"(?<![\w/])\d{1,6}/(?:19|20)?\d{2}(?![\w/])")
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
    r"(?:\s+(?:a|to|e|and)\s+|\s*[-–]\s*)\d+(?:[.,]\d+)?"
    r")?\s*(?:km/h|m/s|mph|km|cm|mm|kg|ft|m|g|p[eéê]s?|metros?|meters?|"
    r"quil[oô]metros?|kilometers?|feet|foot|milhas?|miles?|minutos?|minutes?)(?!\w)",
    re.I,
)
NUMBER = re.compile(
    r"(?<![\w])\d+(?:[.,]\d+)*(?:(?=[º°](?:\W|$))|(?=(?:st|nd|rd|th|h|am|pm)\b)|(?![\w]))",
    re.I,
)
DATE_NUMERIC = re.compile(r"(?<!\d)(?:\d{1,2}[/.\-]\d{1,2}[/.\-](?:\d{2}|\d{4})|(?:1\d|20)\d{2}-\d{2}-\d{2})(?!\d)")
DATE_NAMED_PT = re.compile(
    r"\b(\d{1,2})[º°o]?\s+(?:(?:dias?\s+)?do\s+m[eê]s\s+)?de\s+(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+(?:do\s+ano\s+)?de:?\s+((?:1\d|20)\d{2})\b",
    re.I,
)
DATE_NAMED_EN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?[,.]?\s+((?:1\d|20)\d{2})\b",
    re.I,
)
NAME = re.compile(
    r"\b(?:[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][\wÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç.'’-]+)"
    r"(?:\s+(?:d[aeo]s?|e|do|dos|da|das|of|the|[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][\wÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç.'’-]+)){1,5}\b"
)
PT_NEGATIONS = {
    "não": re.compile(
        r"\b(?:not|no|never|cannot|without|neither|nor|unidentified|unknown|unconfirmed|unverified|"
        r"undetected|unauthorized|unavailable|impossible|invisible|unmanned|non[- ]monetary)\b",
        re.I,
    ),
    "nunca": re.compile(r"\b(?:never|nothing\s+ever|not\s+ever)\b", re.I),
    "sem": re.compile(r"\b(?:without|lacking|absent|free of|no|not|unconfirmed|unidentified)\b", re.I),
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
FR_MONTHS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}
IT_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
UNIT_ALIASES = {
    "metro": "m", "metros": "m", "meter": "m", "meters": "m", "m": "m",
    "quilômetro": "km", "quilômetros": "km", "kilometer": "km", "kilometers": "km", "km": "km",
    "pé": "ft", "pés": "ft", "pe": "ft", "pes": "ft", "pê": "ft", "pês": "ft",
    "foot": "ft", "feet": "ft", "ft": "ft",
    "centímetro": "cm", "centímetros": "cm", "centimeter": "cm", "centimeters": "cm", "cm": "cm",
    "milímetro": "mm", "milímetros": "mm", "millimeter": "mm", "millimeters": "mm", "mm": "mm",
    "milha": "mi", "milhas": "mi", "mile": "mi", "miles": "mi",
    "minuto": "min", "minutos": "min", "minute": "min", "minutes": "min",
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


def _urls(text: str) -> Counter[str]:
    values = []
    for match in URL.finditer(text):
        value = match.group(0).rstrip(".,;")
        for closing, opening in ((")", "("), ("]", "[")):
            while value.endswith(closing) and value.count(closing) > value.count(opening):
                value = value[:-1]
        values.append(value)
    return Counter(values)


def protected_tokens(text: str, official_identifiers: list[str] | None = None) -> list[str]:
    tokens: set[str] = set()
    for pattern in (
        REDACTION, FILENAME, OFFICIAL_CODE, IDENTIFIER, NUMERIC_IDENTIFIER, ABBREVIATION, COORDINATE,
    ):
        tokens.update(match.group(0) for match in pattern.finditer(text))
    tokens.update(match.group(1) for match in CALLSIGN.finditer(text))
    tokens.update(_urls(text))
    for value in official_identifiers or []:
        if value and value in text:
            tokens.add(value)
    return sorted(tokens, key=lambda item: (-len(item), item))


def mask_protected(text: str, official_identifiers: list[str] | None = None) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}
    tokens = protected_tokens(text, official_identifiers)
    if not tokens:
        return text, replacements
    placeholders: dict[str, str] = {}
    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token not in placeholders:
            placeholder = f"__UFO_PROTECTED_{len(placeholders):03d}__"
            placeholders[token] = placeholder
            replacements[placeholder] = token
        return placeholders[token]
    # One pass avoids inventing a missing placeholder for an abbreviation
    # already covered by a longer filename or identifier.
    masked = re.sub("|".join(re.escape(token) for token in tokens), replace, text)
    return masked, replacements


def restore_protected(text: str, replacements: dict[str, str]) -> tuple[str, list[str]]:
    # Models sometimes change underscores to spaces/dashes or omit leading underscores.
    # Match only a complete, numbered marker present in this request's mapping.
    marker = re.compile(r"(?<![\w])_*UFO[ _-]*PROTECTED[ _-]*(\d{1,3})_*(?![\w])", re.I)
    seen: set[str] = set()
    def replace(match: re.Match[str]) -> str:
        key = f"__UFO_PROTECTED_{int(match.group(1)):03d}__"
        if key not in replacements:
            return match.group(0)
        seen.add(key)
        return replacements[key]
    restored = marker.sub(replace, text)
    missing = []
    for key, token in replacements.items():
        if key in seen:
            continue
        # A model may preserve the original literal instead of its marker.
        # Word boundaries prevent PAN being mistaken for the suffix of GEIPAN.
        left = r"(?<!\w)" if token and token[0].isalnum() else ""
        right = r"(?!\w)" if token and token[-1].isalnum() else ""
        if not re.search(left + re.escape(token) + right, restored):
            missing.append(token)
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


def _date_spacing(text: str) -> str:
    # OCR sometimes separates characters within an otherwise explicit date.
    # Normalize only full dates and known month names, never ambiguous fragments.
    text = re.sub(r"\bagôsto\b", "agosto", text, flags=re.I)
    text = re.sub(r"(\b\d{1,2}\s+de\s+)margo(?=\s+de\s+(?:19|20)\d{2}\b)",
                  r"\1março", text, flags=re.I)
    spaced_months = "|".join(r"\s*".join(re.escape(letter) for letter in month) for month in PT_MONTHS)
    full_date = re.compile(
        r"(?<![\w/])([0-3]?\s*\d)\s*d\s*e\s*(" + spaced_months
        + r")\s*d\s*e\s*((?:1\s*\.?\s*9|2\s*\.?\s*0)\s*\d\s*\d)(?!\d)", re.I)
    text = full_date.sub(lambda match: re.sub(r"\s", "", match.group(1)) + " de "
                        + re.sub(r"\s", "", match.group(2)) + " de "
                        + re.sub(r"[\s.]", "", match.group(3)), text)
    for month in PT_MONTHS:
        letters = r"[ \t]*".join(re.escape(letter) for letter in month)
        text = re.sub(r"(?<!\w)" + letters + r"(?!\w)", month, text, flags=re.I)
    text = re.sub(r"(\b\d{1,2}\s+de\s+(?:" + "|".join(PT_MONTHS) + r")\s+de\s+)([12])\.(\d{3})\b", r"\1\2\3", text, flags=re.I)
    text = re.sub(r"(\b\d{1,2}\s+de\s+(?:" + "|".join(PT_MONTHS) + r")\s+de\s+)([12](?:[ \t]+\d){3})\b",
                  lambda match: match.group(1) + re.sub(r"[ \t]", "", match.group(2)), text, flags=re.I)
    spaced_abbreviations = "|".join(r"[ \t]*".join(name[:3]) for name in (*PT_MONTHS, *EN_MONTHS))
    text = re.sub(r"(?<![\w/])([0-3]?[ \t]*\d)[ \t]+(" + spaced_abbreviations + r")\.?[ \t]+((?:[12][ \t]*[09][ \t]*)?\d[ \t]*\d)(?![\w/])",
                  lambda match: re.sub(r"[ \t]", "", match.group(1)) + " " + re.sub(r"[ \t]", "", match.group(2)) + " " + re.sub(r"[ \t]", "", match.group(3)), text, flags=re.I)
    spaced_date = re.compile(r"(?<![\w/])([0-3]?[ \t]*\d)[ \t]*/[ \t]*([01]?[ \t]*\d)[ \t]*/[ \t]*((?:[12][ \t]*[09][ \t]*)?\d[ \t]*\d)(?![\w/])")
    return spaced_date.sub(lambda match: "/".join(re.sub(r"[ \t]", "", part) for part in match.groups()), text)


def _dates(text: str, *, language: str) -> Counter[str]:
    values: Counter[str] = Counter()
    # Embedded French book synopses retain their original-language dates.
    french_date = re.compile(
        r"\b(\d{1,2}(?:\s*(?:,|et)\s*\d{1,2})*)\s+(" + "|".join(FR_MONTHS)
        + r")\s+((?:1\d|20)\d{2})\b", re.I)
    def add_french(match: re.Match[str]) -> str:
        days, month, year = match.groups()
        for day in re.findall(r"\d{1,2}", days):
            values[f"{int(year):04d}-{FR_MONTHS[month.casefold()]:02d}-{int(day):02d}"] += 1
        return ""
    text = french_date.sub(add_french, text)
    # Bibliographic Portuguese dates may separate the year with a comma.
    text = re.sub(r"(\b\d{1,2}[º°o]?\s+de\s+(?:" + "|".join(PT_MONTHS)
                  + r")),\s*((?:1\d|20)\d{2})\b", r"\1 de \2", text, flags=re.I)
    # Enumerated days and inclusive ranges must preserve every stated day.
    pt_list = re.compile(r"\b(\d{1,2}(?:\s*(?:,|e)\s*\d{1,2})+)\s+de\s+(" + "|".join(PT_MONTHS) + r")\s+de\s+((?:1\d|20)\d{2})\b", re.I)
    en_list = re.compile(r"\b(" + "|".join(EN_MONTHS) + r")\s+(\d{1,2}(?:st|nd|rd|th)?(?:\s*(?:,\s*(?:and\s+)?|and\s+)\d{1,2}(?:st|nd|rd|th)?)+),?\s+((?:1\d|20)\d{2})\b", re.I)
    def add_list(match: re.Match[str], portuguese: bool) -> str:
        days, month, year = match.groups() if portuguese else (match.group(2), match.group(1), match.group(3))
        month_number = (PT_MONTHS if portuguese else EN_MONTHS)[month.casefold()]
        for day in re.findall(r"\d{1,2}", days):
            values[f"{int(year):04d}-{month_number:02d}-{int(day):02d}"] += 1
        return ""
    text = pt_list.sub(lambda match: add_list(match, True), text)
    text = en_list.sub(lambda match: add_list(match, False), text)
    # English dates may retain the source's two-digit year and day-first order.
    text = re.sub(
        r"\b(" + "|".join(EN_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{2})\b(?!:|\s*(?:a\.?m\.?|p\.?m\.?)\b)",
        lambda match: match.group(1) + " " + match.group(2) + ", "
        + ("20" if int(match.group(3)) < 50 else "19") + match.group(3),
        text, flags=re.I,
    )
    pt_range = re.compile(r"\b(\d{1,2})(?:\s*\((?:(?:segunda|terça|quarta|quinta|sexta)(?:-feira)?|s[áa]bado|domingo)\))?\s+(?:a|e)\s+(\d{1,2})\s+de\s+(" + "|".join(PT_MONTHS) + r")\s+de\s+((?:1\d|20)\d{2})\b", re.I)
    en_range = re.compile(r"\b(" + "|".join(EN_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s+(?:and|to|through)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+((?:1\d|20)\d{2})\b", re.I)
    def add_range(match: re.Match[str], portuguese: bool) -> str:
        first, last, month, year = match.groups() if portuguese else (match.group(2), match.group(3), match.group(1), match.group(4))
        month_number = (PT_MONTHS if portuguese else EN_MONTHS)[month.casefold()]
        inclusive = re.search(r"\b(?:a|to|through)\b", match.group(0), re.I)
        days = range(int(first), int(last) + 1) if inclusive and int(first) <= int(last) else (int(first), int(last))
        for day in days:
            values[f"{int(year):04d}-{month_number:02d}-{int(day):02d}"] += 1
        return ""
    text = pt_range.sub(lambda match: add_range(match, True), text)
    text = en_range.sub(lambda match: add_range(match, False), text)
    abbreviations = {name[:3]: number for name, number in PT_MONTHS.items()}
    abbreviations.update({name[:3]: number for name, number in EN_MONTHS.items()})
    abbreviations.update(PT_MONTHS)
    abbreviations["marco"] = 3
    abbreviations.update(EN_MONTHS)
    # Brazilian correspondence files can contain original Italian letters.
    abbreviations.update(IT_MONTHS)
    abbreviation = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[ \t]+(?:day[ \t]+of[ \t]+|de[ \t]+)?(" + "|".join(abbreviations) + r")\.?\s+(?:de\s+)?((?:1\d|20)?\d{2})\b", re.I)
    def add_abbreviation(match: re.Match[str]) -> str:
        day, month, year = match.groups()
        # A volume number beside a month-only publication date is not its day.
        if re.search(r"\bvol(?:ume)?\.?\s*$", match.string[:match.start()], re.I):
            return match.group(0)
        if len(year) == 2:
            year = ("20" if int(year) < 50 else "19") + year
        values[f"{int(year):04d}-{abbreviations[month.casefold()]:02d}-{int(day):02d}"] += 1
        return ""
    text = abbreviation.sub(add_abbreviation, text)
    for match in DATE_NUMERIC.finditer(text):
        raw = match.group(0)
        if "-" in raw and raw[:4].isdigit():
            year, month, day = raw.split("-")
        else:
            first, second, year = re.split(r"[/.\-]", raw)
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
    # OCR letter spacing in a duration must not become the metre abbreviation.
    text = re.sub(r"\bm[ \t]+i[ \t]+n[ \t]+u[ \t]+t[ \t]+o(?:[ \t]+s)?\b",
                  "minutos", text, flags=re.I)
    # Keep OCR spaces after decimal/grouping commas inside the same value.
    text = re.sub(r"(?<=\d),[ \t]+(?=\d)", ",", text)
    # Attributive English measures retain the same value: a 45-minute interview.
    text = re.sub(r"(?<=\d)[-–](?=(?:minute|meter|kilometer|foot|mile)s?\b)", " ", text, flags=re.I)
    for match in MEASUREMENT.finditer(text):
        raw = match.group(0)
        number_match = re.match(r"\d+(?:[.,]\d+)?", raw)
        unit_match = re.search(r"([A-Za-zÀ-ÿ/]+)\s*$", raw)
        if number_match and unit_match:
            unit = UNIT_ALIASES.get(unit_match.group(1).casefold(), unit_match.group(1).casefold())
            numbers = re.findall(r"\d+(?:[.,]\d+)?", raw[:unit_match.start()])
            value = " to ".join(_number_value(number) for number in numbers)
            values[f"{value} {unit}"] += 1
    return values


def _numbers(text: str) -> Counter[str]:
    return Counter(_number_value(match.group(0)) for match in NUMBER.finditer(text))


def _remove_exact_numeric_dates(source: str, target: str) -> tuple[str, str]:
    for match in DATE_NUMERIC.finditer(source):
        raw = match.group(0)
        count = min(source.count(raw), target.count(raw))
        source = source.replace(raw, "", count)
        target = target.replace(raw, "", count)
    return source, target


def compare_translation(source: str, target: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    marker = re.compile(r"(?<!\w)_*UFO[ _-]*PROTECTED[ _-]*(\d{1,3})_*(?!\w)", re.I)
    if Counter(marker.findall(target)) - Counter(marker.findall(source)):
        findings.append({"check": "unresolved-placeholder", "severity": "error", "status": "unexpected-derived-marker"})
    date_source, date_target = _remove_exact_numeric_dates(_date_spacing(source), _date_spacing(target))
    for name, source_values, target_values, severity in (
        ("urls", _urls(source), _urls(target), "error"),
        ("dates", _dates(date_source, language="pt"), _dates(date_target, language="en"), "error"),
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

    def commentary_markers(text: str) -> Counter[str]:
        return Counter(re.sub(r"\s+", " ", match.group(0)).strip().casefold()
                       for match in TRANSLATOR_COMMENTARY.finditer(text))
    if commentary_markers(target) - commentary_markers(source):
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
    exception_phrase = re.compile(r"\ba\s+não\s+ser\b")
    exception_count = len(exception_phrase.findall(source_folded))
    if exception_count:
        # This phrase introduces an exception rather than another denial.
        # Still require an explicit equivalent so omitted exceptions fail QA.
        equivalents = len(re.findall(r"\b(?:except|unless|other than|apart from|save for|if not)\b", target, re.I))
        if equivalents >= exception_count:
            source_folded = exception_phrase.sub("", source_folded)
        else:
            findings.append({"check": "idiomatic-exception", "severity": "error",
                             "status": "mismatch", "source_marker": "a não ser"})
    polite_reply = re.compile(r"\bpois\s+não(?=\s*[,!?]|\s*$)")
    polite_count = len(polite_reply.findall(source_folded))
    if polite_count:
        # As a standalone reply, "pois não" is an affirmative courtesy.
        # Do not mistake its não for a factual negation in the sentence.
        source_folded = polite_reply.sub("", source_folded)
        equivalent_count = len(re.findall(r"(?:^|[.!?]\s*)\s*(?:well,\s*)?(?:certainly|of course|yes|sure|go ahead|at your service)\b", target, re.I))
        if equivalent_count < polite_count:
            findings.append({"check": "idiomatic-affirmation", "severity": "error",
                             "status": "mismatch", "source_marker": "pois não"})
    for marker, target_pattern in PT_NEGATIONS.items():
        count = len(re.findall(rf"\b{re.escape(marker)}\b", source_folded))
        translated_count = len(target_pattern.findall(target))
        if marker in {"nenhum", "nenhuma"}:
            # Portuguese negative concord corresponds to English "not ... any".
            # Require the negation and "any" in the same bounded clause; a
            # positive "any" or an unrelated negative sentence is insufficient.
            translated_count += len(re.findall(
                r"\b(?:not|never|cannot|without|\w+n['’]t)\b[^.!?;\n]{0,160}\bany\b",
                target, re.I,
            ))
        if marker == "não":
            translated_count += len(re.findall(r"\b\w+n['’]t\b", target, re.I))
        if marker in {"não", "sem"}:
            # Negative concord may collapse to one English negative pronoun:
            # "não vi nada" -> "I saw nothing", "sem nada" -> "nothing".
            # Limit this equivalent to clauses that actually contain nada.
            concord_count = len(re.findall(
                rf"\b{marker}\b[^.!?;\n]{{0,160}}\bnada\b", source_folded,
            ))
            translated_count += min(concord_count, len(re.findall(r"\bnothing\b", target, re.I)))
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
