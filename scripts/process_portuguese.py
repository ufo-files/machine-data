#!/usr/bin/env python3
"""Process one manifest-backed Brazil source into paired Portuguese/English data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portuguese_pipeline.extract import validate_dependencies  # noqa: E402
from portuguese_pipeline.pipeline import process_source  # noqa: E402
from portuguese_pipeline.translation import (  # noqa: E402
    CommandBackend,
    DEFAULT_MLX_MODEL,
    DisabledBackend,
    MLXBackend,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--translation-backend", choices=("mlx", "command", "disabled"), default="mlx")
    parser.add_argument("--translation-command", default="")
    parser.add_argument("--translation-model", default=DEFAULT_MLX_MODEL)
    parser.add_argument("--translation-model-revision", default="main")
    parser.add_argument("--whisper-model", default="mlx-community/whisper-large-v3-mlx")
    parser.add_argument("--whisper-model-revision", default="main")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--embedded-word-floor", type=int, default=80)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check-dependencies", action="store_true")
    args = parser.parse_args()

    if args.check_dependencies:
        print(json.dumps(validate_dependencies(include_translation=args.translation_backend == "mlx"), indent=2, sort_keys=True))
        return 0
    if args.workers < 1 or args.workers > 4:
        parser.error("--workers must be between 1 and 4")
    if args.dpi < 150 or args.dpi > 600:
        parser.error("--dpi must be between 150 and 600")

    if args.translation_backend == "mlx":
        backend = MLXBackend(args.translation_model, model_revision=args.translation_model_revision)
    elif args.translation_backend == "command":
        if not args.translation_command:
            parser.error("--translation-command is required for command backend")
        backend = CommandBackend(
            args.translation_command,
            model=args.translation_model,
            model_revision=args.translation_model_revision,
        )
    else:
        backend = DisabledBackend()

    manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    result = process_source(
        args.source,
        relative_path=args.relative_path,
        manifest=manifest,
        output_root=args.output_root,
        work_root=args.work_root,
        backend=backend,
        workers=args.workers,
        dpi=args.dpi,
        embedded_word_floor=args.embedded_word_floor,
        whisper_model=args.whisper_model,
        whisper_model_revision=args.whisper_model_revision,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
