"""Local translation backends with placeholder protection and explicit failures."""

from __future__ import annotations

import json
import hashlib
import importlib.metadata
import shlex
import subprocess
import re
from dataclasses import dataclass
from typing import Protocol

from .qa import compare_translation, mask_protected, restore_protected


WORKFLOW_VERSION = "pt-en-translation-prompt/v4"
DEFAULT_MLX_MODEL = "mlx-community/aya-expanse-8b-4bit"

SYSTEM_PROMPT = """Translate the supplied Brazilian Portuguese text into English. Output only the translation.
Translate only the supplied words. A heading, label, or unfinished sentence must remain a heading, label, or unfinished sentence. Never continue the text, invent an event, or add explanations.
Keep names, numbers, dates, measurements, coordinates, document identifiers, abbreviations, negation and uncertainty faithful to the source. Preserve placeholders such as __UFO_PROTECTED_000__ exactly.
When OCR has damaged a word and its reading is uncertain, copy that damaged word exactly. Do not guess its meaning or fill in missing text. Preserve punctuation and redaction markers.
"""

PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TranslationResult:
    text: str
    status: str
    error: str | None = None
    missing_protected_tokens: tuple[str, ...] = ()


class Backend(Protocol):
    method: str
    model: str
    model_revision: str
    runtime_version: str

    def translate_raw(self, prompt: str) -> str: ...


class DisabledBackend:
    method = "disabled"
    model = ""
    model_revision = ""
    runtime_version = ""

    def translate_raw(self, prompt: str) -> str:
        raise RuntimeError("translation backend is disabled")


class CommandBackend:
    method = "local-command"

    def __init__(self, command: str, *, model: str = "external-command", model_revision: str = "") -> None:
        self.command = shlex.split(command)
        if not self.command:
            raise ValueError("translation command cannot be empty")
        self.model = model
        self.model_revision = model_revision
        self.runtime_version = "external"

    def translate_raw(self, prompt: str) -> str:
        completed = subprocess.run(
            self.command,
            input=json.dumps({"prompt": prompt}, ensure_ascii=False) + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=900,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"exit {completed.returncode}"
            raise RuntimeError(f"translation command failed: {detail[-1000:]}")
        output = completed.stdout.strip()
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return output
        if not isinstance(payload, dict) or not isinstance(payload.get("translation"), str):
            raise RuntimeError("translation command JSON must contain a string 'translation'")
        return payload["translation"].strip()


class MLXBackend:
    method = "local-mlx-lm"

    def __init__(self, model: str = DEFAULT_MLX_MODEL, *, model_revision: str = "main", max_tokens: int = 2048) -> None:
        try:
            from mlx_lm import generate, load
            from mlx_lm.sample_utils import make_sampler
        except ImportError as error:
            raise RuntimeError("mlx-lm is required for the MLX translation backend") from error
        self.model = model
        self.model_revision = model_revision
        self.runtime_version = importlib.metadata.version("mlx-lm")
        self.max_tokens = max_tokens
        self._generate = generate
        self._sampler = make_sampler(temp=0.0)
        self._model, self._tokenizer = load(
            model,
            tokenizer_config={"trust_remote_code": False},
            revision=model_revision,
        )

    def translate_raw(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        formatted = self._tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=False,
        )
        source_text = prompt.partition("\n\n")[2] or prompt
        # A short damaged OCR fragment must not produce thousands of tokens.
        # Leave room for English expansion while retaining the configured cap.
        output_budget = min(self.max_tokens, max(128, 2 * len(self._tokenizer.encode(source_text)) + 64))
        return self._generate(
            self._model,
            self._tokenizer,
            prompt=formatted,
            max_tokens=output_budget,
            sampler=self._sampler,
            verbose=False,
        ).strip()


def translate_text(
    backend: Backend,
    text: str,
    *,
    official_identifiers: list[str] | None = None,
    _allow_chunk_retry: bool = True,
) -> TranslationResult:
    if not text.strip():
        return TranslationResult(text="", status="not-required")
    if not any(character.isalpha() for character in text):
        return TranslationResult(text=text, status="not-required")
    masked, replacements = mask_protected(text, official_identifiers)
    prompt = "Translate this text from Brazilian Portuguese to English:\n\n" + masked
    try:
        raw = backend.translate_raw(prompt)
        restored, missing = restore_protected(raw, replacements)
        original_errors = sum(f.get("severity") == "error" for f in compare_translation(text, restored))
        if missing or original_errors:
            # Some backends interpret the marker's UFO prefix as content. Give
            # one literal-source retry, then enforce the same restoration/QA gates.
            literal_prompt = (
                "Translate the following Brazilian Portuguese text into English. Copy every URL, "
                "filename, identifier, and official abbreviation exactly as written. "
                "Do not summarize. Return only the translation.\n\n" + text
            )
            literal, literal_missing = restore_protected(backend.translate_raw(literal_prompt), replacements)
            literal_errors = sum(f.get("severity") == "error" for f in compare_translation(text, literal))
            if (len(literal_missing) <= len(missing) and literal_errors <= original_errors
                    and (len(literal_missing) < len(missing) or literal_errors < original_errors)):
                restored, missing = literal, literal_missing
        # Long paragraphs can cause the model to drop placeholders or summarize
        # clauses. Retry in sentence-sized context, retaining all QA checks.
        if _allow_chunk_retry and len(text) > 400 and (
            missing or any(f.get("severity") == "error" for f in compare_translation(text, restored))
        ):
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ÿ(\"])", text)
            if len(sentences) == 1:
                sentences = [line for line in text.splitlines() if line.strip()]
            if len(sentences) > 1:
                parts = [translate_text(backend, sentence,
                         official_identifiers=official_identifiers,
                         _allow_chunk_retry=False) for sentence in sentences]
                if all(part.status in {"machine-unreviewed", "not-required"} for part in parts):
                    combined = " ".join(part.text for part in parts)
                    if not any(finding.get("severity") == "error"
                               for finding in compare_translation(text, combined)):
                        return TranslationResult(text=combined, status="machine-unreviewed")
        if missing:
            return TranslationResult(
                text=restored,
                status="failed-protected-token-check",
                error="translator omitted protected tokens",
                missing_protected_tokens=tuple(missing),
            )
        return TranslationResult(text=restored, status="machine-unreviewed")
    except Exception as error:
        return TranslationResult(
            text="",
            status="failed",
            error=f"{type(error).__name__}: {error}",
        )
