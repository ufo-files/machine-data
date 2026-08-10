"""Conservative, dependency-free language routing for Portuguese sources."""

from __future__ import annotations

import re


PORTUGUESE = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos", "e", "em",
    "entre", "foi", "não", "no", "nos", "o", "os", "para", "pela", "pelo", "por",
    "que", "se", "sem", "uma", "um",
}
ENGLISH = {
    "a", "and", "as", "at", "by", "for", "from", "in", "is", "it", "no", "not",
    "of", "on", "or", "that", "the", "this", "to", "was", "were", "with", "without",
}


def detect_language(text: str, default: str = "pt-BR") -> dict[str, object]:
    words = re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
    if not words:
        return {"code": "und", "confidence": 0.0, "method": "stopword-heuristic/v1"}
    pt = sum(word in PORTUGUESE for word in words)
    en = sum(word in ENGLISH for word in words)
    if pt == en == 0:
        code = default
        confidence = 0.2
    elif pt >= en:
        code = "pt-BR"
        confidence = min(0.99, 0.5 + (pt - en) / max(2, pt + en) / 2)
    else:
        code = "en"
        confidence = min(0.99, 0.5 + (en - pt) / max(2, pt + en) / 2)
    return {"code": code, "confidence": round(confidence, 3), "method": "stopword-heuristic/v1"}
