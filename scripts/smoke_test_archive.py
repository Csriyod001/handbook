#!/usr/bin/env python3
"""Cleanroom Smoke Tester for Portable Handbook Archives (.tar.gz / .zip)."""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REQUIRED_ARCHIVE_FILES = [
    "index.html",
    "README.md",
    "SPEC_AND_STYLE_GUIDE.md",
    "PORTABILITY_AND_QUICKSTART.md",
    "Makefile",
    "dist/AI_Infra_Interactive_Handbook.html",
    "dist/FULL_MANUSCRIPT.md",
    "dist/assets/tailwindcss.min.js",
    "chapters/00-onboarding-and-setup.md",
    "chapters/01-foundations-containers-iac.md",
    "chapters/02-kubernetes-gpu-orchestration.md",
    "chapters/03-vllm-serving-optimization.md",
    "chapters/04-ai-gateway-governance.md",
    "chapters/05-observability-autoscaling-sre.md",
    "chapters/06-capstone-siamshield-ai.md",
]


def strip_code(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`\n]+`", "", text)
    return text


def verify_relative_links(md_path: Path) -> list[str]:
    broken: list[str] = []
    cleaned = strip_code(md_path.read_text(encoding="utf-8"))
    for raw in re.findall(r"\[(?:[^\]]*)\]\(([^)]+)\)", cleaned):
        target = raw.strip().split()[0].strip("<>")
        if not target or target.startswith(("http://", "https://", "mailto:", "ftp:", "javascript:")):
            continue
        file_part = target.split("#")[0].split("?")[0].strip()
        if not file_part:
            continue
        resolved = (md_path.parent / file_part).resolve()
        if not resolved.exists():
            broken.append(file_part)
    return broken


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    name_lower = archive_path.name.lower()
    if name_lower.endswith(".zip"):
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                bad = zf.testzip()
                if bad is not None:
                    raise RuntimeError(f"Corrupted member in zip: {bad}")
                zf.extractall(dest_dir)
        except zipfile.BadZipFile as exc:
            raise RuntimeError(f"Corrupted zip archive: {exc}") from exc
    else:
        try:
            with tarfile.open(archive_path, "r:gz") as tf:
                if hasattr(tarfile, "data_filter"):
                    tf.extractall(dest_dir, filter="data")
                else:
                    tf.extractall(dest_dir)
        except (tarfile.TarError, EOFError, OSError) as exc:
            raise RuntimeError(f"Corrupted tar.gz archive: {exc}") from exc


def smoke_test(archive_path: Path) -> int:
    if not archive_path.is_file():
        print(f"[FAIL] Archive not found: {archive_path}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = Path(tmpdir)
        try:
            extract_archive(archive_path, sandbox)
        except Exception as exc:
            print(f"[FAIL] Failed to extract {archive_path}: {exc}", file=sys.stderr)
            return 1

        index_hits = list(sandbox.glob("**/index.html"))
        if not index_hits:
            print("[FAIL] Extracted archive missing index.html", file=sys.stderr)
            return 1
        root = index_hits[0].parent

        missing = [rel for rel in REQUIRED_ARCHIVE_FILES if not (root / rel).exists()]
        if missing:
            print(f"[FAIL] Missing required files in extracted archive: {missing}", file=sys.stderr)
            return 1

        manuscript = root / "dist" / "FULL_MANUSCRIPT.md"
        broken = verify_relative_links(manuscript)
        if broken:
            print(
                f"[FAIL] Broken relative links in extracted FULL_MANUSCRIPT.md: {broken[:10]}",
                file=sys.stderr,
            )
            return 1

        print(f"[PASS] Archive smoke test succeeded: {archive_path} ({len(REQUIRED_ARCHIVE_FILES)} core assets & links verified)")
        return 0


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    default_archive = repo_root / "dist" / "ai-infra-handbook-portable.tar.gz"

    parser = argparse.ArgumentParser(description="Smoke-test portable handbook archive.")
    parser.add_argument("--archive", type=Path, help="Archive path (.tar.gz or .zip)")
    parser.add_argument("positional_archive", nargs="?", type=Path, help="Optional positional archive path")
    args = parser.parse_args()

    target = args.archive or args.positional_archive or default_archive
    return smoke_test(target)


if __name__ == "__main__":
    raise SystemExit(main())
