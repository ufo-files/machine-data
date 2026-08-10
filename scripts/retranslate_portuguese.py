#!/usr/bin/env python3
"""Regenerate only English-derived files from canonical Portuguese text."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portuguese_pipeline.pipeline import retranslate_existing  # noqa: E402
from portuguese_pipeline.translation import CommandBackend, DEFAULT_MLX_MODEL, MLXBackend  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_dir", type=Path)
    parser.add_argument("--translation-backend", choices=("mlx", "command"), default="mlx")
    parser.add_argument("--translation-command", default="")
    parser.add_argument("--translation-model", default=DEFAULT_MLX_MODEL)
    parser.add_argument("--translation-model-revision", required=True)
    args = parser.parse_args()
    if args.translation_backend == "mlx":
        backend = MLXBackend(args.translation_model, model_revision=args.translation_model_revision)
    else:
        if not args.translation_command:
            parser.error("--translation-command is required for command backend")
        backend = CommandBackend(
            args.translation_command,
            model=args.translation_model,
            model_revision=args.translation_model_revision,
        )
    print(json.dumps(retranslate_existing(args.document_dir, backend), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
