"""Portuguese OCR, embedded-text extraction, and media transcription adapters."""

from __future__ import annotations

import csv
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


DOCUMENT_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pgm", ".pbm"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pgm", ".pbm"}
MEDIA_SUFFIXES = {
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpg", ".mpeg",
    ".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus", ".aiff", ".aif",
}


@dataclass(frozen=True)
class ExtractedUnit:
    index: int
    text: str
    confidence: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True)
class Extraction:
    medium: str
    mode: str
    engine: str
    units: tuple[ExtractedUnit, ...]
    tools: dict[str, str] | None = None


def command(name: str) -> str:
    search_paths = [
        *os.environ.get("PATH", "").split(os.pathsep),
        "/opt/homebrew/bin",
        str(Path.home() / ".local" / "bin"),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    path = shutil.which(name, path=os.pathsep.join(dict.fromkeys(filter(None, search_paths))))
    if not path:
        raise RuntimeError(f"required command not found: {name}")
    return path


def run_checked(args: list[str], *, timeout: int, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{Path(args[0]).name} exited {completed.returncode}: {detail[-1000:]}")
    return completed


def alpha_words(text: str) -> int:
    return len(re.findall(r"[^\W\d_]{2,}", text, re.UNICODE))


def tool_version(name: str, *version_args: str) -> str:
    completed = run_checked([command(name), *(version_args or ("--version",))], timeout=60)
    output = completed.stdout.strip() or completed.stderr.strip()
    return output.splitlines()[0] if output else "unknown"


def split_pdf_text(text: str) -> tuple[ExtractedUnit, ...]:
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if not pages:
        pages = [""]
    return tuple(ExtractedUnit(index=index, text=page.strip()) for index, page in enumerate(pages, 1))


def extract_pdf(path: Path, *, work_dir: Path, workers: int, dpi: int, embedded_word_floor: int) -> Extraction:
    embedded = run_checked([command("pdftotext"), "-layout", str(path), "-"], timeout=300).stdout
    if alpha_words(embedded) >= embedded_word_floor:
        return Extraction(
            "document", "embedded-text", "poppler-pdftotext", split_pdf_text(embedded),
            {"pdftotext": tool_version("pdftotext", "-v")},
        )

    searchable = work_dir / f"{path.stem}.searchable.pdf"
    run_checked(
        [
            command("ocrmypdf"),
            "--language", "por+eng",
            "--deskew",
            "--rotate-pages",
            "--skip-text",
            "--output-type", "pdf",
            "--jobs", str(workers),
            "--oversample", str(dpi),
            str(path), str(searchable),
        ],
        timeout=7200,
    )
    text = run_checked([command("pdftotext"), "-layout", str(searchable), "-"], timeout=300).stdout
    return Extraction(
        "document", "ocr", "ocrmypdf+tesseract-por+eng", split_pdf_text(text),
        {
            "ocrmypdf": tool_version("ocrmypdf"),
            "pdftotext": tool_version("pdftotext", "-v"),
            "tesseract": tool_version("tesseract"),
        },
    )


def extract_image(path: Path) -> Extraction:
    completed = run_checked(
        [command("tesseract"), str(path), "stdout", "-l", "por+eng", "--psm", "3", "tsv"],
        timeout=1800,
    )
    rows = list(csv.DictReader(completed.stdout.splitlines(), delimiter="\t"))
    words: list[str] = []
    confidences: list[float] = []
    last_line: tuple[str, ...] | None = None
    for row in rows:
        word = (row.get("text") or "").strip()
        if not word:
            continue
        line = tuple(row.get(field, "") for field in ("block_num", "par_num", "line_num"))
        if last_line is not None and line != last_line:
            words.append("\n")
        elif words and words[-1] != "\n":
            words.append(" ")
        words.append(word)
        last_line = line
        try:
            confidence = float(row.get("conf", "-1"))
        except ValueError:
            confidence = -1
        if confidence >= 0:
            confidences.append(confidence / 100)
    confidence = sum(confidences) / len(confidences) if confidences else None
    return Extraction(
        "image",
        "ocr",
        "tesseract-por+eng-psm3",
        (ExtractedUnit(index=1, text="".join(words).strip(), confidence=confidence),),
        {"tesseract": tool_version("tesseract"), "page_segmentation_mode": "3-auto"},
    )


def _has_audio(path: Path) -> bool:
    completed = run_checked(
        [
            command("ffprobe"), "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
        ],
        timeout=120,
    )
    return bool(completed.stdout.strip())


def script_distribution_version(executable: str, distribution: str) -> str:
    try:
        first_line = Path(executable).read_text(encoding="utf-8").splitlines()[0]
        if not first_line.startswith("#!"):
            return "unknown"
        interpreter = shlex.split(first_line[2:])[0]
        completed = run_checked(
            [interpreter, "-c", f"import importlib.metadata; print(importlib.metadata.version({distribution!r}))"],
            timeout=60,
        )
        return completed.stdout.strip() or "unknown"
    except (OSError, RuntimeError, IndexError):
        return "unknown"


def extract_media(path: Path, *, work_dir: Path, model: str, model_revision: str) -> Extraction:
    if not _has_audio(path):
        raise RuntimeError("source has no audio stream")
    output_dir = work_dir / "whisper"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise RuntimeError("huggingface-hub is required to pin the Whisper model revision") from error
    model_path = Path(model)
    resolved_model = str(model_path) if model_path.exists() else snapshot_download(repo_id=model, revision=model_revision)
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        dict.fromkeys(
            filter(
                None,
                [
                    *environment.get("PATH", "").split(os.pathsep),
                    "/opt/homebrew/bin",
                    str(Path.home() / ".local" / "bin"),
                    "/usr/local/bin",
                    "/usr/bin",
                    "/bin",
                ],
            )
        )
    )
    args = [
        command("mlx_whisper"), str(path),
        "--model", resolved_model,
        "--language", "Portuguese",
        "--output-dir", str(output_dir),
        "--output-format", "tsv",
        "--output-name", path.stem,
        "--verbose", "True",
        "--condition-on-previous-text", "False",
        "--word-timestamps", "True",
        "--hallucination-silence-threshold", "2",
    ]
    completed = subprocess.run(args, cwd=path.parent, env=environment, timeout=86400, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"mlx_whisper exited {completed.returncode}")
    tsv_path = output_dir / f"{path.stem}.tsv"
    if not tsv_path.is_file():
        raise RuntimeError("mlx_whisper did not create TSV output")
    with tsv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    units: list[ExtractedUnit] = []
    for index, row in enumerate(rows, 1):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            start_ms = int(float(row.get("start", "0")))
            end_ms = int(float(row.get("end", "0")))
        except ValueError:
            start_ms = end_ms = 0
        units.append(ExtractedUnit(index=index, text=text, start_ms=start_ms, end_ms=end_ms))
    if not units:
        raise RuntimeError("mlx_whisper returned no transcript segments")
    return Extraction(
        "media", "transcription", f"mlx-whisper:{model}@{model_revision}", tuple(units),
        {
            "ffmpeg": tool_version("ffmpeg", "-version"),
            "ffprobe": tool_version("ffprobe", "-version"),
            "mlx_whisper": script_distribution_version(command("mlx_whisper"), "mlx-whisper"),
            "mlx_whisper_executable": command("mlx_whisper"),
            "transcription_model": model,
            "transcription_model_revision": model_revision,
        },
    )


def extract_source(
    path: Path,
    *,
    work_dir: Path,
    workers: int = 2,
    dpi: int = 300,
    embedded_word_floor: int = 80,
    whisper_model: str = "mlx-community/whisper-large-v3-mlx",
    whisper_model_revision: str = "main",
) -> Extraction:
    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        return extract_pdf(path, work_dir=work_dir, workers=workers, dpi=dpi, embedded_word_floor=embedded_word_floor)
    if suffix in IMAGE_SUFFIXES:
        return extract_image(path)
    if suffix in MEDIA_SUFFIXES:
        return extract_media(path, work_dir=work_dir, model=whisper_model, model_revision=whisper_model_revision)
    if suffix in {".txt", ".md"}:
        return Extraction("document", "embedded-text-fixture", "utf-8", (ExtractedUnit(1, path.read_text(encoding="utf-8")),), {"reader": "python-utf-8"})
    raise RuntimeError(f"unsupported Portuguese source type: {suffix}")


def validate_dependencies(*, include_translation: bool = True) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in ("tesseract", "ocrmypdf", "pdftotext", "pdfinfo", "ffmpeg", "ffprobe", "mlx_whisper"):
        executable = command(name)
        versions[name] = executable
    languages = run_checked([command("tesseract"), "--list-langs"], timeout=60).stdout.splitlines()
    available = {line.strip() for line in languages}
    missing = {"por", "eng"} - available
    if missing:
        raise RuntimeError("missing Tesseract language data: " + ", ".join(sorted(missing)))
    if include_translation:
        try:
            import mlx_lm  # noqa: F401
        except ImportError as error:
            raise RuntimeError("missing Python dependency: mlx-lm") from error
    return versions
