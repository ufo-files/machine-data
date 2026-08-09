#!/usr/bin/env python3
"""Claim, stage, process, and publish one Brazil source over verified SSH/SFTP."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portuguese_pipeline.extract import DOCUMENT_SUFFIXES, MEDIA_SUFFIXES  # noqa: E402
from portuguese_pipeline.pipeline import PIPELINE_VERSION, output_relative_path, process_source  # noqa: E402
from portuguese_pipeline.translation import DEFAULT_MLX_MODEL, MLXBackend  # noqa: E402


COLLECTION = "Brazil-Government-UAP"
REMOTE_DISCOVER = r'''
from pathlib import Path
import base64, hashlib, json, os, sys, time

root = Path(sys.argv[1])
max_bytes = int(sys.argv[2])
make_claim = sys.argv[3] == "1"
allowed = set(json.loads(base64.urlsafe_b64decode(sys.argv[4]).decode()))
pipeline_version = sys.argv[5]
translation_model = sys.argv[6]
translation_model_revision = sys.argv[7]
whisper_model = sys.argv[8]
whisper_model_revision = sys.argv[9]
collection = "Brazil-Government-UAP"
manifest_path = root / "originals" / collection / "manifest.json"
manifest = json.loads(manifest_path.read_text())
state = root / ".state" / "mac-processor-portuguese"
claims = state / "claims"
completed = state / "completed"
failures = state / "failures"
for directory in (claims, completed, failures, state / "uploads"):
    directory.mkdir(parents=True, exist_ok=True)

now = int(time.time())
for claim in claims.glob("*.json"):
    try:
        if now - int(claim.stat().st_mtime) > 21600:
            claim.unlink()
    except OSError:
        pass

supported = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpg", ".mpeg", ".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus", ".aiff", ".aif"}
seen = set()
candidates = []
for record in manifest.get("items", []):
    rel = record.get("relative_path", "")
    if not rel or rel in seen or (allowed and rel not in allowed):
        continue
    seen.add(rel)
    rel_path = Path(rel)
    collection_root = (root / "originals" / collection).resolve()
    if rel_path.is_absolute() or ".." in rel_path.parts or "\n" in rel or "\r" in rel:
        continue
    source = collection_root / rel_path
    try:
        if not source.resolve().is_relative_to(collection_root):
            continue
    except (OSError, RuntimeError):
        continue
    if Path(rel).suffix.lower() not in supported or not source.is_file():
        continue
    info = source.stat()
    if info.st_size <= 0 or info.st_size > max_bytes:
        continue
    expected_hash = record.get("sha256", "")
    if not expected_hash:
        continue
    identity = (
        f"portuguese:{rel}:{expected_hash}:{pipeline_version}:{translation_model}:"
        f"{translation_model_revision}:{whisper_model}:{whisper_model_revision}"
    )
    claim_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    output_rel = Path("Brazil-Government-UAP") / "paired" / Path(rel).parent / Path(rel).stem
    provenance_path = root / "transcripts" / output_rel / "provenance.json"
    complete = False
    try:
        provenance = json.loads(provenance_path.read_text())
        complete = (
            provenance.get("status") == "complete"
            and provenance.get("source_sha256") == expected_hash
            and provenance.get("pipeline_version") == pipeline_version
            and provenance.get("translation", {}).get("model") == translation_model
            and provenance.get("translation", {}).get("model_revision") == translation_model_revision
        )
        if rel_path.suffix.lower() in {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpg", ".mpeg", ".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus", ".aiff", ".aif"}:
            tools = provenance.get("extraction", {}).get("tools", {})
            complete = (
                complete
                and tools.get("transcription_model") == whisper_model
                and tools.get("transcription_model_revision") == whisper_model_revision
            )
    except Exception:
        pass
    candidate = {
        "claim_id": claim_id,
        "source_rel": rel,
        "source_bytes": info.st_size,
        "source_sha256": expected_hash,
        "output_rel": output_rel.as_posix(),
        "record": record,
        "complete": complete,
    }
    candidates.append(candidate)

candidates.sort(key=lambda item: (item["complete"], item["source_bytes"], item["source_rel"].casefold()))
for item in candidates:
    if item["complete"] or (completed / (item["claim_id"] + ".json")).exists():
        continue
    failure = failures / (item["claim_id"] + ".json")
    if failure.exists():
        try:
            previous = json.loads(failure.read_text())
            if int(previous.get("attempts", 0)) >= 3 or int(previous.get("retry_after", 0)) > now:
                continue
        except Exception:
            pass
    claim = claims / (item["claim_id"] + ".json")
    if make_claim:
        try:
            descriptor = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w") as handle:
            json.dump({**item, "claimed_at": now, "worker": "mac-portuguese-worker"}, handle, sort_keys=True)
            handle.write("\n")
    print(json.dumps(item, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0)
print("{}")
'''

REMOTE_MARK = r'''
from pathlib import Path
import base64, json, os, sys, time
root = Path(sys.argv[1])
claim_id = sys.argv[2]
outcome = sys.argv[3]
record = json.loads(base64.urlsafe_b64decode(sys.argv[4]).decode())
state = root / ".state" / "mac-processor-portuguese"
target_dir = state / ("completed" if outcome == "complete" else "failures")
target_dir.mkdir(parents=True, exist_ok=True)
record["outcome"] = outcome
record["updated_at"] = int(time.time())
target = target_dir / (claim_id + ".json")
if outcome == "failed":
    try:
        previous = json.loads(target.read_text())
    except Exception:
        previous = {}
    attempts = int(previous.get("attempts", 0)) + 1
    record["attempts"] = attempts
    record["retry_after"] = 2147483647 if attempts >= 3 else int(time.time()) + 3600 * (4 ** (attempts - 1))
    record["quarantined"] = attempts >= 3
temporary = target.with_suffix(".json.tmp")
temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
os.replace(temporary, target)
try:
    (state / "claims" / (claim_id + ".json")).unlink()
except FileNotFoundError:
    pass
'''

REMOTE_READ_REVIEW = r'''
from pathlib import Path
import base64, json, sys
path = Path(sys.argv[1])
try:
    data = path.read_bytes()
    parsed = json.loads(data)
    if parsed.get("schema") == "ufo-files-portuguese-translation-reviews/v1":
        print(base64.urlsafe_b64encode(data).decode())
except (OSError, json.JSONDecodeError, AttributeError):
    pass
'''

REMOTE_FINALIZE = r'''
from pathlib import Path
import base64, hashlib, json, os, shutil, sys
root = Path(sys.argv[1])
claim_id = sys.argv[2]
output_rel = Path(sys.argv[3])
items = json.loads(base64.urlsafe_b64decode(sys.argv[4]).decode())
upload_root = root / ".state" / "mac-processor-portuguese" / "uploads" / claim_id
transcript_root = (root / "transcripts").resolve()
final_root = transcript_root / output_rel
if output_rel.is_absolute() or ".." in output_rel.parts or not final_root.resolve().is_relative_to(transcript_root):
    raise RuntimeError("unsafe output path")
incoming = final_root.parent / ("." + final_root.name + ".incoming-" + claim_id)
backup = final_root.parent / ("." + final_root.name + ".previous-" + claim_id)
if not final_root.exists() and backup.exists():
    os.replace(backup, final_root)
shutil.rmtree(incoming, ignore_errors=True)
incoming.mkdir(parents=True)
for item in items:
    temporary = Path(item["temporary"])
    digest = hashlib.sha256()
    with temporary.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != item["sha256"]:
        raise RuntimeError("uploaded checksum mismatch: " + item["final"])
for item in items:
    temporary = Path(item["temporary"])
    final = Path(item["final"])
    relative = final.resolve().relative_to(final_root.resolve())
    staged = incoming / relative
    staged.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporary, staged)
if backup.exists():
    shutil.rmtree(backup)
if final_root.exists():
    os.replace(final_root, backup)
try:
    os.replace(incoming, final_root)
except BaseException:
    if not final_root.exists() and backup.exists():
        os.replace(backup, final_root)
    raise
shutil.rmtree(backup, ignore_errors=True)
shutil.rmtree(upload_root, ignore_errors=True)
'''


@dataclass(frozen=True)
class Config:
    host: str
    user: str
    identity_file: Path
    remote_root: str
    scratch_root: Path
    enabled: bool
    max_source_bytes: int
    min_free_bytes: int
    workers: int
    dpi: int
    translation_model: str
    translation_model_revision: str
    whisper_model: str
    whisper_model_revision: str

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}"


def load_config(path: Path) -> Config:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Config(
        host=data["host"],
        user=data["user"],
        identity_file=Path(data["identity_file"]).expanduser(),
        remote_root=data.get("remote_root", "/srv/ufo-files-downloads"),
        scratch_root=Path(data["scratch_root"]).expanduser(),
        enabled=bool(data.get("enabled", False)),
        max_source_bytes=int(data.get("max_source_bytes", 2 * 1024**3)),
        min_free_bytes=int(data.get("min_free_bytes", 20 * 1024**3)),
        workers=max(1, min(4, int(data.get("workers", 2)))),
        dpi=max(150, min(600, int(data.get("dpi", 300)))),
        translation_model=data.get("translation_model", DEFAULT_MLX_MODEL),
        translation_model_revision=data.get("translation_model_revision", "main"),
        whisper_model=data.get("whisper_model", "mlx-community/whisper-large-v3-mlx"),
        whisper_model_revision=data.get("whisper_model_revision", "main"),
    )


def ssh_base(config: Config) -> list[str]:
    return [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=yes", "-i", str(config.identity_file), config.target,
    ]


def sftp_base(config: Config) -> list[str]:
    return [
        "sftp", "-q", "-b", "-", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=yes", "-i", str(config.identity_file), config.target,
    ]


def run(command: list[str], *, input_text: str | None = None, timeout: int = 86400) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{command[0]} exited {completed.returncode}: {detail[-1000:]}")
    return completed


def ssh_script(config: Config, script: str, arguments: list[str]) -> str:
    remote = "python3 - " + " ".join(shlex.quote(argument) for argument in arguments)
    return run(ssh_base(config) + [remote], input_text=script, timeout=300).stdout.strip()


def claim_candidate(config: Config, allowed: list[str], *, claim: bool) -> dict[str, Any] | None:
    payload = base64.urlsafe_b64encode(json.dumps(allowed).encode()).decode()
    output = ssh_script(
        config,
        REMOTE_DISCOVER,
        [
            config.remote_root, str(config.max_source_bytes), "1" if claim else "0", payload,
            PIPELINE_VERSION, config.translation_model, config.translation_model_revision,
            config.whisper_model, config.whisper_model_revision,
        ],
    )
    record = json.loads(output.splitlines()[-1]) if output else {}
    return record or None


def sftp_quote(path: str) -> str:
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_source(config: Config, candidate: dict, job_root: Path) -> Path:
    remote = Path(config.remote_root) / "originals" / COLLECTION / candidate["source_rel"]
    local = job_root / "originals" / COLLECTION / candidate["source_rel"]
    local.parent.mkdir(parents=True, exist_ok=True)
    run(sftp_base(config), input_text=f"get -p {sftp_quote(str(remote))} {sftp_quote(str(local))}\n")
    if local.stat().st_size != candidate["source_bytes"]:
        raise RuntimeError("staged source byte-size mismatch")
    digest = sha256_file(local)
    if digest != candidate["source_sha256"]:
        raise RuntimeError("staged source SHA-256 mismatch")
    print(f"staged and verified {candidate['source_rel']} sha256={digest}", flush=True)
    return local


def mark(config: Config, candidate: dict, outcome: str, **extra: Any) -> None:
    payload = base64.urlsafe_b64encode(json.dumps({**candidate, **extra}, sort_keys=True).encode()).decode()
    ssh_script(config, REMOTE_MARK, [config.remote_root, candidate["claim_id"], outcome, payload])


def stage_prior_review_audit(config: Config, candidate: dict, output_root: Path) -> None:
    remote = Path(config.remote_root) / "transcripts" / candidate["output_rel"] / "translation-reviews.json"
    encoded = ssh_script(config, REMOTE_READ_REVIEW, [str(remote)])
    if not encoded:
        return
    data = base64.urlsafe_b64decode(encoded)
    parsed = json.loads(data)
    if parsed.get("schema") != "ufo-files-portuguese-translation-reviews/v1":
        raise RuntimeError("invalid prior translation review audit")
    local = output_root / candidate["output_rel"] / "translation-reviews.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)


def publish(config: Config, candidate: dict, output_root: Path) -> list[dict[str, str]]:
    local_root = output_root / candidate["output_rel"]
    files = sorted(path for path in local_root.rglob("*") if path.is_file())
    if not files:
        raise RuntimeError("processor produced no output files")
    upload_root = Path(config.remote_root) / ".state" / "mac-processor-portuguese" / "uploads" / candidate["claim_id"]
    run(ssh_base(config) + [f"mkdir -p -- {shlex.quote(str(upload_root))}"], timeout=60)
    batch: list[str] = []
    published: list[dict[str, str]] = []
    for index, path in enumerate(files):
        relative = path.relative_to(output_root)
        temporary = upload_root / f"{index:02d}-{path.name}"
        final = Path(config.remote_root) / "transcripts" / relative
        digest = sha256_file(path)
        batch.append(f"put {sftp_quote(str(path))} {sftp_quote(str(temporary))}")
        published.append({"relative": relative.as_posix(), "sha256": digest, "temporary": str(temporary), "final": str(final)})
    run(sftp_base(config), input_text="\n".join(batch) + "\n")
    payload = base64.urlsafe_b64encode(json.dumps(published, sort_keys=True).encode()).decode()
    ssh_script(
        config,
        REMOTE_FINALIZE,
        [config.remote_root, candidate["claim_id"], candidate["output_rel"], payload],
    )
    return [{"path": item["relative"], "sha256": item["sha256"]} for item in published]


def ensure_scratch_capacity(config: Config) -> None:
    config.scratch_root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(config.scratch_root).free
    if free < config.min_free_bytes:
        raise RuntimeError(f"scratch volume has {free} bytes free; requires {config.min_free_bytes}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pilot", action="store_true", help="Permit a disabled config only with exact allowlisted paths.")
    parser.add_argument("--allow-relative-path", action="append", default=[])
    args = parser.parse_args()
    config = load_config(args.config)
    if not config.enabled and not args.pilot:
        raise RuntimeError("Portuguese worker is disabled in config")
    if args.pilot and not args.allow_relative_path:
        raise RuntimeError("--pilot requires at least one exact --allow-relative-path")
    ensure_scratch_capacity(config)
    lock_path = config.scratch_root / "portuguese-worker.lock"
    lock = lock_path.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Portuguese worker already running", flush=True)
        return 0
    candidate = claim_candidate(config, args.allow_relative_path, claim=not args.dry_run)
    if not candidate:
        print("no pending Portuguese candidate", flush=True)
        return 0
    print(json.dumps({key: candidate[key] for key in ("claim_id", "source_rel", "source_bytes", "source_sha256", "output_rel")}, ensure_ascii=False), flush=True)
    if args.dry_run:
        return 0
    job_root = config.scratch_root / "jobs" / candidate["claim_id"]
    output_root = job_root / "transcripts"
    try:
        source = stage_source(config, candidate, job_root)
        stage_prior_review_audit(config, candidate, output_root)
        manifest = {"schema": "brazil-government-uap-archive/v1", "items": [candidate["record"]]}
        backend = MLXBackend(config.translation_model, model_revision=config.translation_model_revision)
        result = process_source(
            source,
            relative_path=candidate["source_rel"],
            manifest=manifest,
            output_root=output_root,
            work_root=job_root / "work",
            backend=backend,
            workers=config.workers,
            dpi=config.dpi,
            whisper_model=config.whisper_model,
            whisper_model_revision=config.whisper_model_revision,
        )
        outputs = publish(config, candidate, output_root)
        if result["status"] == "complete":
            mark(config, candidate, "complete", result=result, outputs=outputs)
            print(f"published and verified {len(outputs)} Portuguese/English artifact(s)", flush=True)
            return 0
        mark(
            config,
            candidate,
            "failed",
            result=result,
            outputs=outputs,
            error=f"processing status {result['status']}; retry scheduled",
        )
        print(
            f"published explicit {result['status']} artifacts; remote retry scheduled",
            file=sys.stderr,
            flush=True,
        )
        return 1
    except BaseException as error:
        try:
            mark(config, candidate, "failed", error=f"{type(error).__name__}: {error}")
        except Exception as mark_error:
            print(f"could not release remote claim: {mark_error}", file=sys.stderr, flush=True)
        raise
    finally:
        shutil.rmtree(job_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
