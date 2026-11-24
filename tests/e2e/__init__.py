"""E2E Test Suite Package for AI Infrastructure Handbook.

Contains shared test utilities, metadata decorators, and path constants.
"""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

# Project root directory
REPO_ROOT = Path(
    os.environ.get("AI_INFRA_REPO_ROOT")
    or Path(__file__).resolve().parent.parent.parent
).resolve()


def test_metadata(tier: int, features: list[str]) -> Callable:
    """Decorator attaching tier and requirement feature tags to test methods."""
    def decorator(fn: Callable) -> Callable:
        fn.tier = tier  # type: ignore[attr-defined]
        fn.features = [f.upper() for f in features]  # type: ignore[attr-defined]
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)
        wrapper.tier = tier  # type: ignore[attr-defined]
        wrapper.features = [f.upper() for f in features]  # type: ignore[attr-defined]
        return wrapper
    return decorator


def strip_jsonc_comments(content: str) -> str:
    """Strip single-line (//) and multi-line (/* */) comments and trailing commas."""
    # Remove multi-line comments
    content = re.sub(r"/\*[\s\S]*?\*/", "", content)
    # Remove single-line comments
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    # Remove trailing commas before closing braces/brackets
    content = re.sub(r",(\s*[}\]])", r"\1", content)
    return content


def strip_inline_code_spans(text: str) -> str:
    """Strip backtick inline code spans so regexes inside code blocks are not matched as links."""
    # Strip multi-backtick spans first, then single backtick spans
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`\n]+`", "", text)
    return text


def extract_relative_markdown_links(content: str) -> list[str]:
    """Extract all relative file path links from markdown content.

    Ignores external URLs (http/https), mailto links, and pure anchor fragments (#...).
    """
    cleaned = strip_inline_code_spans(content)
    raw_targets = re.findall(r"\[(?:[^\]]*)\]\(([^)]+)\)", cleaned)
    relative_links: list[str] = []
    for raw in raw_targets:
        # Strip title attribute if present (e.g. `(path "title")`)
        target = raw.strip().split()[0].strip("<>")
        # Ignore external links or empty
        if not target or target.startswith(("http://", "https://", "mailto:", "ftp:", "javascript:")):
            continue
        # Strip anchor fragment
        file_part = target.split("#")[0].strip()
        if not file_part:
            # Pure internal anchor in same file
            continue
        # Strip query params
        file_part = file_part.split("?")[0].strip()
        if file_part:
            relative_links.append(file_part)
    return relative_links


def parse_portal_deliverable_links(html_content: str) -> list[str]:
    """Extract all deliverable and chapter file paths referenced in the HTML portal."""
    paths: set[str] = set()
    # Chapters and labs files referenced in JS objects (ignore template expressions/annotations)
    for prefix in ("chapters", "labs"):
        for raw in re.findall(rf"[\'\"]({prefix}/[^\'\"]+)[\'\"]", html_content):
            cleaned = raw.rstrip("\\").strip()
            if " " not in cleaned and "${" not in cleaned:
                paths.add(cleaned)
    # Footer and manuscript links (ignore JS template literals containing ${...})
    for m in re.finditer(r'<a\s+[^>]*href=[\'\"]([^\'\"]+)[\'\"]', html_content):
        href = m.group(1).split("#")[0].strip()
        if href and "${" not in href and not href.startswith(("http://", "https://", "mailto:", "javascript:")):
            paths.add(href)
    return sorted(paths)


def run_cmd(
    cmd: list[str] | str,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 60,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Execute a command in subprocess with consistent defaults."""
    run_cwd = cwd if cwd is not None else REPO_ROOT
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env["AI_INFRA_REPO_ROOT"] = str(REPO_ROOT)

    is_shell = isinstance(cmd, str)
    return subprocess.run(
        cmd,
        shell=is_shell,
        cwd=run_cwd,
        env=run_env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )
