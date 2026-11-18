#!/usr/bin/env python3
"""
AI Infrastructure & Platform Engineering Handbook — Portable Archive Generator
Builds dist/ai-infra-handbook-portable.tar.gz and dist/ai-infra-handbook-portable.zip
with strict exclusion filtering, POSIX permission enforcement, and cross-platform path normalization.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import NamedTuple

# Canonical Repository Root
REPO_ROOT = Path(__file__).resolve().parent.parent

# Exclusion Sets
EXCLUDE_DIRS = {
    ".git",
    ".agents",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "env",
    ".terraform",
}

ALLOW_DOT_DIRS = {
    ".github",
    ".devcontainer",
}

EXCLUDE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".env",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".tar.gz",
    ".tgz",
    ".zip",
    ".swp",
    ".swo",
}

# Deliverables to verify before packaging
MANDATORY_DELIVERABLES = [
    "dist/AI_Infra_Interactive_Handbook.html",
    "dist/FULL_MANUSCRIPT.md",
    "SPEC_AND_STYLE_GUIDE.md",
    "README.md",
    "Makefile",
    "chapters/00-onboarding-and-setup.md",
    "chapters/01-foundations-containers-iac.md",
    "chapters/02-kubernetes-gpu-orchestration.md",
    "chapters/03-vllm-serving-optimization.md",
    "chapters/04-ai-gateway-governance.md",
    "chapters/05-observability-autoscaling-sre.md",
    "chapters/06-capstone-siamshield-ai.md",
    "labs/m1-foundations/verify_m1.sh",
    "labs/m2-k8s-gpu/verify_m2.sh",
    "labs/m3-vllm/verify_m3.sh",
    "labs/m4-gateway/verify_m4.sh",
    "labs/m5-observability-sre/verify_m5.sh",
    "labs/m6-capstone-siamshield/verify_capstone.sh",
    "scripts/check-env.sh",
    "scripts/build_manuscript.py",
]

RECOMMENDED_OFFLINE_ASSETS = [
    "dist/assets/tailwindcss.min.js",
    "index.html",
]


class ManifestEntry(NamedTuple):
    source_path: Path
    arcname: str
    is_executable: bool
    is_symlink: bool
    symlink_target: str = ""


def is_executable_file(rel_path: str, full_path: Path) -> bool:
    """Determine if a file should have POSIX 0755 execution permission."""
    if rel_path.endswith(".sh") or rel_path.startswith("scripts/"):
        return True
    try:
        st = full_path.stat()
        return bool(st.st_mode & 0o111)
    except Exception:
        return False


def normalize_arcname(rel_path: str, prefix: str = "") -> str:
    """Normalize file paths to standard POSIX forward slashes with optional root prefix."""
    clean = rel_path.replace("\\", "/").lstrip("/")
    if prefix:
        prefix_clean = prefix.replace("\\", "/").strip("/")
        return f"{prefix_clean}/{clean}"
    return clean


def collect_manifest(repo_root: Path, prefix: str = "") -> list[ManifestEntry]:
    """Scan the repository tree and compile the inclusion manifest."""
    manifest: list[ManifestEntry] = []

    for root, dirs, files in os.walk(repo_root, followlinks=False):
        rel_root = os.path.relpath(root, repo_root)
        if rel_root == ".":
            rel_root = ""

        # Prune excluded directories in-place
        pruned_dirs = []
        for d in dirs:
            if d in EXCLUDE_DIRS:
                continue
            if d.startswith(".") and d not in ALLOW_DOT_DIRS:
                continue
            pruned_dirs.append(d)
        dirs[:] = pruned_dirs

        # Skip scanning root if it falls under an excluded directory
        parts = rel_root.split(os.sep) if rel_root else []
        if any(p in EXCLUDE_DIRS or (p.startswith(".") and p not in ALLOW_DOT_DIRS) for p in parts):
            continue

        # Add regular files
        for f in sorted(files):
            if f in EXCLUDE_FILES or any(f.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
                continue
            full_path = Path(root) / f
            rel_path = full_path.relative_to(repo_root).as_posix()
            arcname = normalize_arcname(rel_path, prefix)
            is_exec = is_executable_file(rel_path, full_path)

            if full_path.is_symlink():
                sym_target = os.readlink(full_path)
                manifest.append(ManifestEntry(
                    source_path=full_path,
                    arcname=arcname,
                    is_executable=is_exec,
                    is_symlink=True,
                    symlink_target=sym_target
                ))
            else:
                manifest.append(ManifestEntry(
                    source_path=full_path,
                    arcname=arcname,
                    is_executable=is_exec,
                    is_symlink=False
                ))

        # Check for directory symlinks inside dirs
        for d in list(dirs):
            full_d = Path(root) / d
            if full_d.is_symlink():
                rel_d = full_d.relative_to(repo_root).as_posix()
                arcname_d = normalize_arcname(rel_d, prefix)
                sym_target = os.readlink(full_d)
                manifest.append(ManifestEntry(
                    source_path=full_d,
                    arcname=arcname_d,
                    is_executable=True,
                    is_symlink=True,
                    symlink_target=sym_target
                ))
                dirs.remove(d)  # Don't descend into symlinked directory

    return manifest


def build_tar_archive(manifest: list[ManifestEntry], output_path: Path, verbose: bool = False) -> int:
    """Build .tar.gz archive with POSIX permissions and symlinks."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output_path.with_suffix(".tmp.tar.gz")

    count = 0
    with tarfile.open(temp_output, "w:gz") as tar:
        for entry in manifest:
            if entry.is_symlink:
                ti = tarfile.TarInfo(name=entry.arcname)
                ti.type = tarfile.SYMTYPE
                ti.linkname = entry.symlink_target
                ti.mode = 0o777
                ti.uid = 0
                ti.gid = 0
                ti.uname = ""
                ti.gname = ""
                tar.addfile(ti)
                count += 1
                if verbose:
                    print(f"  [TAR SYMLINK] {entry.arcname} -> {entry.symlink_target}")
            else:
                ti = tar.gettarinfo(entry.source_path, arcname=entry.arcname)
                ti.uid = 0
                ti.gid = 0
                ti.uname = ""
                ti.gname = ""
                ti.mode = 0o755 if entry.is_executable else 0o644
                with open(entry.source_path, "rb") as fp:
                    tar.addfile(ti, fp)
                count += 1
                if verbose:
                    mode_str = "0755" if entry.is_executable else "0644"
                    print(f"  [TAR {mode_str}] {entry.arcname}")

    if output_path.exists():
        output_path.unlink()
    temp_output.rename(output_path)
    return count


def build_zip_archive(manifest: list[ManifestEntry], output_path: Path, prefix: str = "", verbose: bool = False) -> int:
    """Build .zip archive with Deflate compression and dereferenced symlinks for Windows."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output_path.with_suffix(".tmp.zip")

    count = 0
    with zipfile.ZipFile(temp_output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in manifest:
            if entry.is_symlink:
                # Dereference symlink for Windows cross-platform compatibility
                target_path = (entry.source_path.parent / entry.symlink_target).resolve()
                if target_path.is_dir():
                    for sroot, sdirs, sfiles in os.walk(target_path):
                        sdirs[:] = [sd for sd in sdirs if sd not in EXCLUDE_DIRS]
                        for sf in sorted(sfiles):
                            if sf in EXCLUDE_FILES or any(sf.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
                                continue
                            sfull = Path(sroot) / sf
                            srel = sfull.relative_to(target_path).as_posix()
                            sub_arcname = f"{entry.arcname}/{srel}"
                            is_exec = is_executable_file(sub_arcname, sfull)
                            mode = 0o100755 if is_exec else 0o100644
                            zinfo = zipfile.ZipInfo.from_file(sfull, arcname=sub_arcname)
                            zinfo.external_attr = mode << 16
                            zinfo.compress_type = zipfile.ZIP_DEFLATED
                            with open(sfull, "rb") as fp:
                                zf.writestr(zinfo, fp.read())
                            count += 1
                            if verbose:
                                print(f"  [ZIP DEREF] {sub_arcname}")
                elif target_path.is_file():
                    is_exec = is_executable_file(entry.arcname, target_path)
                    mode = 0o100755 if is_exec else 0o100644
                    zinfo = zipfile.ZipInfo.from_file(target_path, arcname=entry.arcname)
                    zinfo.external_attr = mode << 16
                    zinfo.compress_type = zipfile.ZIP_DEFLATED
                    with open(target_path, "rb") as fp:
                        zf.writestr(zinfo, fp.read())
                    count += 1
                    if verbose:
                        print(f"  [ZIP DEREF FILE] {entry.arcname}")
            else:
                mode = 0o100755 if entry.is_executable else 0o100644
                zinfo = zipfile.ZipInfo.from_file(entry.source_path, arcname=entry.arcname)
                zinfo.external_attr = mode << 16
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                with open(entry.source_path, "rb") as fp:
                    zf.writestr(zinfo, fp.read())
                count += 1
                if verbose:
                    mode_str = "0755" if entry.is_executable else "0644"
                    print(f"  [ZIP {mode_str}] {entry.arcname}")

    if output_path.exists():
        output_path.unlink()
    temp_output.rename(output_path)
    return count


def verify_archive(archive_path: Path) -> tuple[bool, list[str]]:
    """Assert integrity and absence of blacklisted artifacts in generated archive."""
    errors = []
    if not archive_path.is_file() or archive_path.stat().st_size == 0:
        return False, [f"Archive {archive_path.name} is missing or empty"]

    if archive_path.name.endswith(".tar.gz"):
        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
    elif archive_path.name.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = zf.namelist()
    else:
        return False, [f"Unknown archive format: {archive_path.name}"]

    for n in names:
        parts = n.split("/")
        if any(d in parts for d in EXCLUDE_DIRS):
            errors.append(f"Forbidden directory leak in {archive_path.name}: {n}")
        if any(n.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
            errors.append(f"Forbidden extension leak in {archive_path.name}: {n}")
        if any(f in parts for f in EXCLUDE_FILES):
            errors.append(f"Forbidden file leak in {archive_path.name}: {n}")

    # Check key anchors exist
    has_html = any("dist/AI_Infra_Interactive_Handbook.html" in n for n in names)
    has_manuscript = any("dist/FULL_MANUSCRIPT.md" in n for n in names)
    has_index = any(n == "index.html" or n.endswith("/index.html") for n in names)
    has_assets = any("dist/assets/tailwindcss.min.js" in n for n in names)

    if not has_html:
        errors.append(f"Missing core HTML portal in {archive_path.name}")
    if not has_manuscript:
        errors.append(f"Missing FULL_MANUSCRIPT.md in {archive_path.name}")
    if not has_index:
        errors.append(f"Missing root index.html in {archive_path.name}")
    if not has_assets:
        errors.append(f"Missing dist/assets/tailwindcss.min.js in {archive_path.name}")

    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Package AI Infrastructure Handbook into portable standalone archives."
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="dist",
        help="Output directory for generated archives (default: dist)"
    )
    parser.add_argument(
        "--format",
        choices=["both", "tar", "zip"],
        default="both",
        help="Archive format to build (default: both)"
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Optional top-level folder prefix in archive (default: '')"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate manifest without creating archives"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if optional offline assets or portal redirector are missing"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print verbose file listing during packaging"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress messages"
    )

    args = parser.parse_args(argv)

    out_dir = (REPO_ROOT / args.output_dir).resolve()
    tar_out = out_dir / "ai-infra-handbook-portable.tar.gz"
    zip_out = out_dir / "ai-infra-handbook-portable.zip"

    # Pre-flight check
    missing_mandatory = [p for p in MANDATORY_DELIVERABLES if not (REPO_ROOT / p).exists()]
    if missing_mandatory:
        print(f"[ERROR] Missing mandatory deliverables ({len(missing_mandatory)}):", file=sys.stderr)
        for m in missing_mandatory:
            print(f"  • {m}", file=sys.stderr)
        return 1

    missing_recommended = [p for p in RECOMMENDED_OFFLINE_ASSETS if not (REPO_ROOT / p).exists()]
    if missing_recommended:
        if args.strict:
            print(f"[ERROR] Strict mode: missing recommended assets:", file=sys.stderr)
            for r in missing_recommended:
                print(f"  • {r}", file=sys.stderr)
            return 1
        elif not args.quiet:
            print(f"[WARNING] Recommended offline assets not yet present (will be packaged if created later):")
            for r in missing_recommended:
                print(f"  • {r}")

    manifest = collect_manifest(REPO_ROOT, prefix=args.prefix)
    exec_count = sum(1 for m in manifest if m.is_executable)

    if not args.quiet:
        print(f"Manifest compiled: {len(manifest)} items ({exec_count} executables, {len(manifest) - exec_count} files/links)")

    if args.check_only:
        print("[OK] Manifest check completed successfully.")
        return 0

    success = True
    if args.format in ("both", "tar"):
        if not args.quiet:
            print(f"Building tarball: {tar_out} ...")
        count = build_tar_archive(manifest, tar_out, verbose=args.verbose)
        ok, errors = verify_archive(tar_out)
        if ok:
            sz = tar_out.stat().st_size
            if not args.quiet:
                print(f"  [PASS] {tar_out.name} ({count} entries, {sz:,} bytes)")
        else:
            success = False
            print(f"  [FAIL] {tar_out.name} validation errors:", file=sys.stderr)
            for err in errors:
                print(f"    - {err}", file=sys.stderr)

    if args.format in ("both", "zip"):
        if not args.quiet:
            print(f"Building zip archive: {zip_out} ...")
        count = build_zip_archive(manifest, zip_out, prefix=args.prefix, verbose=args.verbose)
        ok, errors = verify_archive(zip_out)
        if ok:
            sz = zip_out.stat().st_size
            if not args.quiet:
                print(f"  [PASS] {zip_out.name} ({count} entries, {sz:,} bytes)")
        else:
            success = False
            print(f"  [FAIL] {zip_out.name} validation errors:", file=sys.stderr)
            for err in errors:
                print(f"    - {err}", file=sys.stderr)

    if success:
        if not args.quiet:
            print("[SUCCESS] Portable archive packaging complete!")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
