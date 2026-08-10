"""Local translation backends with placeholder protection and explicit failures."""

from __future__ import annotations

import json
import hashlib
import importlib.metadata
import shlex
import subprocess
from dataclasses import dataclass
from typing import Protocol

from .qa import mask_protected, restore_protected


WORKFLOW_VERSION = "pt-en-translation-prompt/v1"
DEFAULT_MLX_MODEL = "mlx-community/aya-expanse-8b-4bit"

SYSTEM_PROMPT = """You translate archival Brazilian Portuguese into faithful English.
Return only the translation, without notes, markdown, or quotation marks.
Preserve every placeholder shaped like __UFO_PROTECTED_000__ exactly.
Preserve proper names, dates, numbers, measurements, coordinates, negation,
uncertainty, military abbreviations, headings, stamps, classification markings,
and redaction or illegibility markers. Never infer missing or illegible text.
Translate OVNI contextually as UFO or unidentified flying object; it is not
evidence of extraterrestrial origin. Do not strengthen or weaken claims.
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
        return self._generate(
            self._model,
            self._tokenizer,
            prompt=formatted,
            max_tokens=self.max_tokens,
            sampler=self._sampler,
            verbose=False,
        ).strip()


def translate_text(
    backend: Backend,
    text: str,
    *,
    official_identifiers: list[str] | None = None,
) -> TranslationResult:
    if not text.strip():
        return TranslationResult(text="", status="not-required")
    masked, replacements = mask_protected(text, official_identifiers)
    prompt = "Translate this text from Brazilian Portuguese to English:\n\n" + masked
    try:
        raw = backend.translate_raw(prompt)
        restored, missing = restore_protected(raw, replacements)
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
