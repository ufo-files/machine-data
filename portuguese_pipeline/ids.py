"""Deterministic identifiers and hashes shared by paired language artifacts."""

from __future__ import annotations

import hashlib
import re
import unicodedata


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: str, length: int = 24) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest}"


def identity_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(character for character in decomposed if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value).strip()
