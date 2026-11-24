#!/usr/bin/env python3
"""Offline/Daemonless Validator for DevContainer and Docker Compose Lab Configs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

VALID_DOCKERFILE_INSTRUCTIONS = {
    "FROM",
    "RUN",
    "CMD",
    "LABEL",
    "MAINTAINER",
    "EXPOSE",
    "ENV",
    "ADD",
    "COPY",
    "ENTRYPOINT",
    "VOLUME",
    "USER",
    "WORKDIR",
    "ARG",
    "ONBUILD",
    "STOPSIGNAL",
    "HEALTHCHECK",
    "SHELL",
}


def strip_jsonc(raw: str) -> str:
    """Strip // and /* */ comments and trailing commas from JSONC."""
    no_block = re.sub(r"/\*[\s\S]*?\*/", "", raw)
    no_line = re.sub(r"//.*$", "", no_block, flags=re.MULTILINE)
    return re.sub(r",(\s*[}\]])", r"\1", no_line)


def validate_dockerfile(path: Path, strict_repo: bool = True) -> list[str]:
    """Validate Dockerfile instruction syntax and required lab configuration."""
    errors: list[str] = []
    if not path.is_file():
        return [f"Missing Dockerfile: {path}"]

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    has_from = False
    in_continuation = False

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if in_continuation:
            in_continuation = stripped.endswith("\\")
            continue
        if not stripped or stripped.startswith("#"):
            continue
        # Handle parser directives like # syntax=...
        token = stripped.split()[0].upper()
        if token not in VALID_DOCKERFILE_INSTRUCTIONS:
            errors.append(f"{path}:{lineno}: Invalid Dockerfile instruction '{token}'")
        if token == "FROM":
            has_from = True
        in_continuation = stripped.endswith("\\")

    if not has_from:
        errors.append(f"{path}: Missing FROM instruction")

    if strict_repo:
        for req in ["ARG TARGETARCH", "WORKDIR /workspace", "uv"]:
            if req not in text:
                errors.append(f"{path}: Missing required declaration '{req}'")
    return errors


def validate_devcontainer(path: Path) -> list[str]:
    """Validate devcontainer.json syntax and DooD / HF cache mounts."""
    errors: list[str] = []
    if not path.is_file():
        return [f"Missing devcontainer.json: {path}"]

    try:
        data = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    except Exception as exc:
        return [f"{path}: Invalid JSON/JSONC syntax: {exc}"]

    if not isinstance(data, dict) or not data.get("name"):
        errors.append(f"{path}: Missing non-empty 'name'")

    mounts_str = str(data.get("mounts", []))
    if "/var/run/docker.sock" not in mounts_str:
        errors.append(f"{path}: Missing required DooD mount '/var/run/docker.sock'")
    if "/tmp/ai-infra-hf-cache" not in mounts_str and "/cache/huggingface" not in mounts_str:
        errors.append(f"{path}: Missing Hugging Face cache mount")

    ports = data.get("forwardPorts", [])
    for p in (8000, 4000, 3000, 9090):
        if p not in ports:
            errors.append(f"{path}: Missing forwardPort {p}")
    return errors


def validate_compose(path: Path) -> list[str]:
    """Validate docker-compose.lab.yml YAML structure and 'lab' service."""
    errors: list[str] = []
    if not path.is_file():
        return [f"Missing compose file: {path}"]

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path}: Invalid YAML: {exc}"]

    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        return [f"{path}: Missing 'services' mapping"]

    services = data["services"]
    if "lab" not in services or not isinstance(services["lab"], dict):
        return [f"{path}: Missing 'lab' service under services"]

    lab = services["lab"]
    volumes_str = str(lab.get("volumes", []))
    if "/var/run/docker.sock" not in volumes_str:
        errors.append(f"{path}: 'lab' service missing '/var/run/docker.sock' volume")

    ports_str = str(lab.get("ports", []))
    for p in ("8000", "4000", "3000", "9090"):
        if p not in ports_str:
            errors.append(f"{path}: 'lab' service missing port {p}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate container lab configs offline.")
    parser.add_argument("--dockerfile", type=Path, help="Path to Dockerfile")
    parser.add_argument("--devcontainer", type=Path, help="Path to devcontainer.json")
    parser.add_argument("--compose", type=Path, help="Path to docker-compose.lab.yml")
    args = parser.parse_args()

    errors: list[str] = []
    checked: list[str] = []

    if args.dockerfile or args.devcontainer or args.compose:
        if args.dockerfile:
            checked.append("dockerfile")
            errors.extend(validate_dockerfile(args.dockerfile, strict_repo=False))
        if args.devcontainer:
            checked.append("devcontainer")
            errors.extend(validate_devcontainer(args.devcontainer))
        if args.compose:
            checked.append("compose")
            errors.extend(validate_compose(args.compose))
    else:
        cwd = Path.cwd()
        repo_root = Path(__file__).resolve().parent.parent
        base = cwd if (cwd / ".devcontainer").is_dir() or (cwd / "docker-compose.lab.yml").is_file() else repo_root
        checked = ["dockerfile", "devcontainer", "compose"]
        errors.extend(validate_dockerfile(base / ".devcontainer" / "Dockerfile", strict_repo=True))
        errors.extend(validate_devcontainer(base / ".devcontainer" / "devcontainer.json"))
        errors.extend(validate_compose(base / "docker-compose.lab.yml"))

    if errors:
        for err in errors:
            print(f"[FAIL] {err}", file=sys.stderr)
        return 1

    print(f"[PASS] Offline container configuration validation passed ({', '.join(checked)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
