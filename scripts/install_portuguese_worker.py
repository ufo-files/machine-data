#!/usr/bin/env python3
"""Install the bounded Portuguese worker and plist without loading the service."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def atomic_text(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.chmod(mode)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-from", type=Path, required=True)
    parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / "Library" / "Application Support" / "ufo-files" / "portuguese-worker",
    )
    parser.add_argument(
        "--launch-agent",
        type=Path,
        default=Path.home() / "Library" / "LaunchAgents" / "com.ufo-files.portuguese-worker.plist",
    )
    parser.add_argument("--skip-dependencies", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    config = json.loads(args.config_from.read_text(encoding="utf-8"))
    required = {"host", "user", "identity_file", "remote_root", "scratch_root"}
    missing = sorted(required - config.keys())
    if missing:
        parser.error("config is missing: " + ", ".join(missing))

    install_root = args.install_root.expanduser().resolve()
    install_root.mkdir(parents=True, exist_ok=True)
    (Path.home() / "Library" / "Logs" / "ufo-files").mkdir(parents=True, exist_ok=True)
    shutil.copytree(repository / "portuguese_pipeline", install_root / "portuguese_pipeline", dirs_exist_ok=True)
    (install_root / "scripts").mkdir(exist_ok=True)
    for script_name in ("portuguese_ssh_worker.py", "process_portuguese.py", "check_portuguese_outputs.py", "review_portuguese_translation.py", "retranslate_portuguese.py"):
        shutil.copy2(repository / "scripts" / script_name, install_root / "scripts" / script_name)
    shutil.copy2(repository / "requirements-macos.txt", install_root / "requirements-macos.txt")
    atomic_text(install_root / "config.json", json.dumps(config, indent=2, sort_keys=True) + "\n")

    python = Path(sys.executable)
    venv_python = install_root / ".venv" / "bin" / "python"
    if not args.skip_dependencies:
        if not venv_python.exists():
            subprocess.run([str(python), "-m", "venv", str(install_root / ".venv")], check=True)
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--requirement", str(install_root / "requirements-macos.txt")],
            check=True,
        )
    if not venv_python.exists():
        parser.error(f"worker virtual environment is missing: {venv_python}")

    template = (repository / "launchd" / "com.ufo-files.portuguese-worker.plist.template").read_text(encoding="utf-8")
    rendered = template.replace("__INSTALL_ROOT__", str(install_root)).replace("__USERNAME__", Path.home().name)
    rendered = rendered.replace("/opt/homebrew/bin/python3", str(venv_python), 1)
    atomic_text(args.launch_agent.expanduser(), rendered, mode=0o644)
    print(f"installed worker: {install_root}")
    print(f"installed unloaded LaunchAgent: {args.launch_agent.expanduser()}")
    print("service was not bootstrapped or enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
