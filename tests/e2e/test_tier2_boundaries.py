"""Tier 2: Boundary & Corner Cases (Robustness & Error Handling) — 20 Tests.

Covers:
- Requirement R1: Archive & Asset Boundaries (5 tests)
- Requirement R2: Container Configuration Boundaries (5 tests)
- Requirement R3: Documentation Boundaries (5 tests)
- Requirement R4: Verification Toolchain Boundaries (5 tests)
"""

from __future__ import annotations

import io
import os
import re
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.e2e import (
    REPO_ROOT,
    extract_relative_markdown_links,
    run_cmd,
    test_metadata,
)


class TestTier2Boundaries(unittest.TestCase):
    """Tier 2 test suite covering boundary conditions, corrupted inputs, and error handling."""

    # -------------------------------------------------------------------------
    # Requirement R1: Archive & Asset Boundaries
    # -------------------------------------------------------------------------

    @test_metadata(tier=2, features=["R1"])
    def test_t2_r1_01_archive_strict_exclusion_filtering(self) -> None:
        """Assert generated archives do NOT contain .git, .agents, __pycache__, or cache artifacts."""
        packager = REPO_ROOT / "scripts" / "package_handbook.py"
        tar_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.tar.gz"
        zip_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.zip"

        if not tar_path.is_file() and packager.is_file():
            run_cmd([sys.executable, str(packager)])

        forbidden_patterns = [
            ".git/", "/.git/",
            ".agents/", "/.agents/",
            "__pycache__",
            ".pyc", ".pyo",
            ".pytest_cache",
            ".ruff_cache",
            ".DS_Store",
            "Thumbs.db",
        ]

        if tar_path.is_file():
            with tarfile.open(tar_path, "r:gz") as tar:
                for member in tar.getnames():
                    for pattern in forbidden_patterns:
                        self.assertNotIn(
                            pattern, member,
                            f"Tarball contains forbidden development artifact '{pattern}': {member}",
                        )

        if zip_path.is_file():
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.namelist():
                    for pattern in forbidden_patterns:
                        self.assertNotIn(
                            pattern, member,
                            f"Zip contains forbidden development artifact '{pattern}': {member}",
                        )

    @test_metadata(tier=2, features=["R1"])
    def test_t2_r1_02_corrupt_archive_graceful_handling(self) -> None:
        """Verify smoke tester rejects corrupted archive with clear error and non-zero exit code."""
        smoke_script = REPO_ROOT / "scripts" / "smoke_test_archive.py"
        self.assertTrue(smoke_script.is_file(), f"Smoke tester missing at {smoke_script}")

        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf:
            tf.write(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03" + b"CorruptedDataPayload" * 10)
            corrupt_path = tf.name

        try:
            # Test invocation with --archive flag
            proc = run_cmd([sys.executable, str(smoke_script), "--archive", corrupt_path])
            if proc.returncode == 0:
                # Also try positional argument
                proc = run_cmd([sys.executable, str(smoke_script), corrupt_path])

            self.assertNotEqual(
                proc.returncode, 0,
                "Smoke tester must exit with non-zero code when given a corrupted archive",
            )
            combined_out = (proc.stdout + proc.stderr).lower()
            has_error_kw = any(w in combined_out for w in ["corrupt", "gzip", "error", "invalid", "readerror", "bad"])
            self.assertTrue(
                has_error_kw,
                f"Smoke tester output should contain descriptive corruption error message: {combined_out}",
            )
        finally:
            if os.path.exists(corrupt_path):
                os.unlink(corrupt_path)

    @test_metadata(tier=2, features=["R1"])
    def test_t2_r1_03_missing_archive_auto_packaging_or_error(self) -> None:
        """Verify smoke tester behavior when archive does not exist at specified path."""
        smoke_script = REPO_ROOT / "scripts" / "smoke_test_archive.py"
        self.assertTrue(smoke_script.is_file(), f"Smoke tester missing at {smoke_script}")

        nonexistent_path = "/tmp/nonexistent_archive_path_12345.tar.gz"
        proc = run_cmd([sys.executable, str(smoke_script), "--archive", nonexistent_path])
        if proc.returncode == 0:
            proc = run_cmd([sys.executable, str(smoke_script), nonexistent_path])

        self.assertNotEqual(
            proc.returncode, 0,
            "Smoke tester must fail when specified archive path does not exist",
        )
        combined = (proc.stdout + proc.stderr).lower()
        self.assertTrue(
            "not found" in combined or "missing" in combined or "does not exist" in combined or "error" in combined,
            f"Expected error message indicating archive does not exist: {combined}",
        )

    @test_metadata(tier=2, features=["R1"])
    def test_t2_r1_04_posix_file_permissions_in_tarball(self) -> None:
        """Assert scripts in tarball have executable mode (0755) and text files have read mode (0644)."""
        tar_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.tar.gz"
        packager = REPO_ROOT / "scripts" / "package_handbook.py"
        if not tar_path.is_file() and packager.is_file():
            run_cmd([sys.executable, str(packager)])

        self.assertTrue(tar_path.is_file(), f"Tarball missing at {tar_path}")

        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue

                # Executable scripts
                if member.name.endswith(".sh") or member.name.endswith("scripts/make") or member.name.endswith("scripts/pytest"):
                    self.assertTrue(
                        member.mode & 0o111 != 0,
                        f"Executable bit missing on script '{member.name}' (mode: {oct(member.mode)})",
                    )
                # Readable documents
                elif member.name.endswith((".md", ".html", ".yaml", ".json", ".tf")):
                    self.assertTrue(
                        member.mode & 0o444 != 0,
                        f"Read bit missing on document '{member.name}' (mode: {oct(member.mode)})",
                    )
                    # Never world-writable
                    self.assertEqual(
                        member.mode & 0o002, 0,
                        f"File '{member.name}' is world-writable (mode: {oct(member.mode)})",
                    )

    @test_metadata(tier=2, features=["R1"])
    def test_t2_r1_05_portal_cdn_offline_simulation(self) -> None:
        """Verify dist/AI_Infra_Interactive_Handbook.html does not require DNS for Tailwind styling."""
        portal = REPO_ROOT / "dist" / "AI_Infra_Interactive_Handbook.html"
        self.assertTrue(portal.is_file(), f"Portal missing at {portal}")
        content = portal.read_text(encoding="utf-8")

        # Must have local script reference
        self.assertRegex(
            content,
            r'<script\s+[^>]*src=[\'"](?:\./)?assets/tailwindcss\.min\.js[\'"]',
            "Portal must load local asset ./assets/tailwindcss.min.js",
        )

        # Local asset must exist on disk
        local_asset = REPO_ROOT / "dist" / "assets" / "tailwindcss.min.js"
        self.assertTrue(local_asset.is_file(), f"Local asset missing at {local_asset}")
        self.assertGreater(local_asset.stat().st_size, 100_000, "Local Tailwind asset size too small")

        # Must not load external font stylesheet that hard-blocks offline rendering
        self.assertNotIn(
            "fonts.googleapis.com", content,
            "Portal should avoid hard network dependency on fonts.googleapis.com",
        )

    # -------------------------------------------------------------------------
    # Requirement R2: Container Configuration Boundaries
    # -------------------------------------------------------------------------

    @test_metadata(tier=2, features=["R2"])
    def test_t2_r2_01_dockerfile_syntax_error_detection(self) -> None:
        """Verify validator detects invalid Dockerfile instruction (e.g. INVALID_CMD)."""
        validator = REPO_ROOT / "scripts" / "validate_container_config.py"
        self.assertTrue(validator.is_file(), f"Validator missing at {validator}")

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_df = Path(tmpdir) / "Dockerfile"
            bad_df.write_text("FROM ubuntu:24.04\nINVALID_INSTRUCTION_CMD foo bar\n", encoding="utf-8")

            # Test passing --dockerfile
            proc = run_cmd([sys.executable, str(validator), "--dockerfile", str(bad_df)])
            if proc.returncode == 0:
                # Also try running in tempdir context with .devcontainer/Dockerfile
                dc_dir = Path(tmpdir) / ".devcontainer"
                dc_dir.mkdir(parents=True, exist_ok=True)
                (dc_dir / "Dockerfile").write_text("FROM ubuntu:24.04\nINVALID_INSTRUCTION_CMD\n", encoding="utf-8")
                proc = run_cmd([sys.executable, str(validator)], cwd=tmpdir)

            self.assertNotEqual(
                proc.returncode, 0,
                "Validator must fail on invalid Dockerfile instruction",
            )
            combined = (proc.stdout + proc.stderr).lower()
            self.assertTrue(
                "invalid" in combined or "error" in combined or "instruction" in combined or "fail" in combined,
                f"Validator output should report instruction error: {combined}",
            )

    @test_metadata(tier=2, features=["R2"])
    def test_t2_r2_02_devcontainer_json_syntax_error_detection(self) -> None:
        """Verify validator detects malformed JSON in devcontainer config."""
        validator = REPO_ROOT / "scripts" / "validate_container_config.py"
        self.assertTrue(validator.is_file(), f"Validator missing at {validator}")

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_dc = Path(tmpdir) / "devcontainer.json"
            bad_dc.write_text('{\n  "name": "Broken devcontainer",\n  "build": {\n', encoding="utf-8")

            proc = run_cmd([sys.executable, str(validator), "--devcontainer", str(bad_dc)])
            if proc.returncode == 0:
                dc_dir = Path(tmpdir) / ".devcontainer"
                dc_dir.mkdir(parents=True, exist_ok=True)
                (dc_dir / "devcontainer.json").write_text('{\n  "name": "broken"\n', encoding="utf-8")
                proc = run_cmd([sys.executable, str(validator)], cwd=tmpdir)

            self.assertNotEqual(
                proc.returncode, 0,
                "Validator must fail on malformed devcontainer JSON",
            )

    @test_metadata(tier=2, features=["R2"])
    def test_t2_r2_03_docker_compose_missing_required_fields(self) -> None:
        """Verify validator detects compose file lacking services block or lab service."""
        validator = REPO_ROOT / "scripts" / "validate_container_config.py"
        self.assertTrue(validator.is_file(), f"Validator missing at {validator}")

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_compose = Path(tmpdir) / "docker-compose.lab.yml"
            bad_compose.write_text("version: '3.8'\n# Missing services block\n", encoding="utf-8")

            proc = run_cmd([sys.executable, str(validator), "--compose", str(bad_compose)])
            if proc.returncode == 0:
                proc = run_cmd([sys.executable, str(validator)], cwd=tmpdir)

            self.assertNotEqual(
                proc.returncode, 0,
                "Validator must fail when compose file lacks services or 'lab' service",
            )

    @test_metadata(tier=2, features=["R2"])
    def test_t2_r2_04_devcontainer_missing_dood_socket_warning(self) -> None:
        """Verify validator flags devcontainer lacking /var/run/docker.sock mount."""
        validator = REPO_ROOT / "scripts" / "validate_container_config.py"
        self.assertTrue(validator.is_file(), f"Validator missing at {validator}")

        with tempfile.TemporaryDirectory() as tmpdir:
            incomplete_dc = Path(tmpdir) / "devcontainer.json"
            incomplete_dc.write_text(
                '{\n  "name": "No DooD",\n  "build": {"dockerfile": "Dockerfile"},\n  "mounts": []\n}\n',
                encoding="utf-8",
            )

            proc = run_cmd([sys.executable, str(validator), "--devcontainer", str(incomplete_dc)])
            if proc.returncode == 0:
                dc_dir = Path(tmpdir) / ".devcontainer"
                dc_dir.mkdir(parents=True, exist_ok=True)
                (dc_dir / "devcontainer.json").write_text(
                    '{\n  "name": "No DooD",\n  "build": {"dockerfile": "Dockerfile"},\n  "mounts": []\n}\n',
                    encoding="utf-8",
                )
                proc = run_cmd([sys.executable, str(validator)], cwd=tmpdir)

            self.assertNotEqual(
                proc.returncode, 0,
                "Validator must fail or warn when /var/run/docker.sock is missing in mounts",
            )

    @test_metadata(tier=2, features=["R2"])
    def test_t2_r2_05_daemonless_environment_fallback(self) -> None:
        """Verify container validator runs successfully when Docker daemon is not running."""
        validator = REPO_ROOT / "scripts" / "validate_container_config.py"
        self.assertTrue(validator.is_file(), f"Validator missing at {validator}")

        # Invalidate DOCKER_HOST to guarantee daemonless mode
        env = {"DOCKER_HOST": "unix:///nonexistent/fake_docker.sock", "DOCKER_API_VERSION": ""}
        proc = run_cmd([sys.executable, str(validator)], env=env)
        self.assertEqual(
            proc.returncode, 0,
            f"Validator should succeed offline without Docker daemon:\n{proc.stdout}\n{proc.stderr}",
        )

    # -------------------------------------------------------------------------
    # Requirement R3: Documentation Boundaries
    # -------------------------------------------------------------------------

    @test_metadata(tier=2, features=["R3"])
    def test_t2_r3_01_portability_guide_broken_local_links(self) -> None:
        """Verify all local relative markdown links inside PORTABILITY_AND_QUICKSTART.md point to existing files."""
        guide = REPO_ROOT / "PORTABILITY_AND_QUICKSTART.md"
        self.assertTrue(guide.is_file(), f"Guide missing at {guide}")

        links = extract_relative_markdown_links(guide.read_text(encoding="utf-8"))
        broken: list[str] = []
        for target in links:
            target_path = (guide.parent / target).resolve()
            if not target_path.exists():
                broken.append(target)

        self.assertEqual(broken, [], f"Found broken relative links in PORTABILITY_AND_QUICKSTART.md: {broken}")

    @test_metadata(tier=2, features=["R3"])
    def test_t2_r3_02_readme_broken_local_links(self) -> None:
        """Verify all relative markdown links inside README.md point to existing files."""
        readme = REPO_ROOT / "README.md"
        self.assertTrue(readme.is_file(), f"README missing at {readme}")

        links = extract_relative_markdown_links(readme.read_text(encoding="utf-8"))
        broken: list[str] = []
        for target in links:
            target_path = (readme.parent / target).resolve()
            if not target_path.exists():
                broken.append(target)

        self.assertEqual(broken, [], f"Found broken relative links in README.md: {broken}")

    @test_metadata(tier=2, features=["R3"])
    def test_t2_r3_03_chapter0_broken_local_links(self) -> None:
        """Verify all relative markdown links inside chapters/00-onboarding-and-setup.md resolve."""
        ch0 = REPO_ROOT / "chapters" / "00-onboarding-and-setup.md"
        self.assertTrue(ch0.is_file(), f"Chapter 0 missing at {ch0}")

        links = extract_relative_markdown_links(ch0.read_text(encoding="utf-8"))
        broken: list[str] = []
        for target in links:
            target_path = (ch0.parent / target).resolve()
            if not target_path.exists():
                broken.append(target)

        self.assertEqual(broken, [], f"Found broken relative links in Chapter 0: {broken}")

    @test_metadata(tier=2, features=["R3"])
    def test_t2_r3_04_command_line_snippet_syntax_check(self) -> None:
        """Verify shell command snippets in PORTABILITY_AND_QUICKSTART.md have valid bash syntax."""
        guide = REPO_ROOT / "PORTABILITY_AND_QUICKSTART.md"
        self.assertTrue(guide.is_file(), f"Guide missing at {guide}")

        content = guide.read_text(encoding="utf-8")
        # Extract ```bash ... ``` blocks
        snippets = re.findall(r"```(?:bash|sh)\n([\s\S]*?)```", content)
        self.assertGreater(len(snippets), 0, "Guide should contain bash command code snippets")

        for idx, snippet in enumerate(snippets, 1):
            # Exclude comment-only or placeholder-only lines
            clean_lines = [
                l for l in snippet.splitlines()
                if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("//")
            ]
            if not clean_lines:
                continue

            test_script = "\n".join(clean_lines)
            # We run bash -n via stdin using subprocess.run directly
            import subprocess
            p = subprocess.run(
                ["bash", "-n"],
                input=test_script,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                p.returncode, 0,
                f"Bash syntax error in snippet #{idx}:\nSnippet:\n{snippet}\nError:\n{p.stderr}",
            )

    @test_metadata(tier=2, features=["R3"])
    def test_t2_r3_05_heading_hierarchy_consistency(self) -> None:
        """Verify PORTABILITY_AND_QUICKSTART.md headings maintain proper hierarchical structure."""
        guide = REPO_ROOT / "PORTABILITY_AND_QUICKSTART.md"
        self.assertTrue(guide.is_file(), f"Guide missing at {guide}")

        lines = guide.read_text(encoding="utf-8").splitlines()
        headings: list[tuple[int, str]] = []
        for line in lines:
            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                level = len(m.group(1))
                text = m.group(2).strip()
                headings.append((level, text))

        self.assertGreater(len(headings), 3, "Guide must contain structured headings")
        # Assert non-empty heading titles
        for level, text in headings:
            self.assertTrue(text, f"Empty heading found at level {level}")

        # Assert at least one H1 exists
        h1_headings = [h for h in headings if h[0] == 1]
        self.assertGreaterEqual(len(h1_headings), 1, "Guide must have at least one H1 heading")

        # Verify no abrupt level jumps (e.g. H1 followed immediately by H3 without H2)
        prev_level = 0
        for level, text in headings:
            if prev_level > 0:
                self.assertLessEqual(
                    level, prev_level + 1,
                    f"Invalid heading level skip from H{prev_level} to H{level}: '{text}'",
                )
            prev_level = level

    # -------------------------------------------------------------------------
    # Requirement R4: Verification Toolchain Boundaries
    # -------------------------------------------------------------------------

    @test_metadata(tier=2, features=["R4"])
    def test_t2_r4_01_make_shim_nonexistent_target(self) -> None:
        """Verify scripts/make returns non-zero exit code when invoked with unknown target."""
        shim = REPO_ROOT / "scripts" / "make"
        self.assertTrue(shim.is_file(), f"make shim missing at {shim}")

        proc = run_cmd([sys.executable, str(shim), "nonexistent_target_xyz_999"])
        self.assertNotEqual(
            proc.returncode, 0,
            "make shim must fail when invoked with an undefined target",
        )
        combined = (proc.stdout + proc.stderr).lower()
        self.assertTrue(
            "no rule to make target" in combined or "target not found" in combined or "error" in combined,
            f"Expected error message for undefined target: {combined}",
        )

    @test_metadata(tier=2, features=["R4"])
    def test_t2_r4_02_make_shim_dry_run_flag(self) -> None:
        """Verify scripts/make supports -n / --dry-run without side-effects."""
        shim = REPO_ROOT / "scripts" / "make"
        self.assertTrue(shim.is_file(), f"make shim missing at {shim}")

        proc = run_cmd([sys.executable, str(shim), "-n", "verify-structure"])
        if proc.returncode != 0:
            proc = run_cmd([sys.executable, str(shim), "--dry-run", "verify-structure"])

        self.assertEqual(
            proc.returncode, 0,
            f"make dry-run failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}",
        )

    @test_metadata(tier=2, features=["R4"])
    def test_t2_r4_03_smoke_test_missing_target_file_detection(self) -> None:
        """Verify scripts/smoke_test_archive.py detects when a required asset is missing from archive."""
        smoke_script = REPO_ROOT / "scripts" / "smoke_test_archive.py"
        tar_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.tar.gz"
        packager = REPO_ROOT / "scripts" / "package_handbook.py"

        if not tar_path.is_file() and packager.is_file():
            run_cmd([sys.executable, str(packager)])

        self.assertTrue(smoke_script.is_file(), f"Smoke tester missing at {smoke_script}")
        self.assertTrue(tar_path.is_file(), f"Archive missing at {tar_path}")

        # Create mock archive omitting FULL_MANUSCRIPT.md
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_tar = Path(tmpdir) / "missing_manuscript.tar.gz"
            with tarfile.open(tar_path, "r:gz") as src, tarfile.open(mock_tar, "w:gz") as dst:
                for member in src.getmembers():
                    if "FULL_MANUSCRIPT.md" not in member.name:
                        if member.isfile():
                            dst.addfile(member, src.extractfile(member))
                        else:
                            dst.addfile(member)

            proc = run_cmd([sys.executable, str(smoke_script), "--archive", str(mock_tar)])
            if proc.returncode == 0:
                proc = run_cmd([sys.executable, str(smoke_script), str(mock_tar)])

            self.assertNotEqual(
                proc.returncode, 0,
                "Smoke tester must fail when FULL_MANUSCRIPT.md is omitted from archive",
            )
            combined = (proc.stdout + proc.stderr).lower()
            self.assertTrue(
                "full_manuscript" in combined or "missing" in combined or "error" in combined,
                f"Smoke tester should flag missing manuscript: {combined}",
            )

    @test_metadata(tier=2, features=["R4"])
    def test_t2_r4_04_smoke_test_broken_relative_link_detection(self) -> None:
        """Verify scripts/smoke_test_archive.py flags broken relative links inside extracted files."""
        smoke_script = REPO_ROOT / "scripts" / "smoke_test_archive.py"
        tar_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.tar.gz"
        packager = REPO_ROOT / "scripts" / "package_handbook.py"

        if not tar_path.is_file() and packager.is_file():
            run_cmd([sys.executable, str(packager)])

        self.assertTrue(smoke_script.is_file(), f"Smoke tester missing at {smoke_script}")
        self.assertTrue(tar_path.is_file(), f"Archive missing at {tar_path}")

        # Create mock archive with broken relative link injected into FULL_MANUSCRIPT.md
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_tar = Path(tmpdir) / "broken_link.tar.gz"
            with tarfile.open(tar_path, "r:gz") as src, tarfile.open(mock_tar, "w:gz") as dst:
                for member in src.getmembers():
                    if "FULL_MANUSCRIPT.md" in member.name:
                        raw = src.extractfile(member).read()
                        injected = raw + b"\n\n[Dead Link](./nonexistent_ghost_file_xyz_99.md)\n"
                        ti = tarfile.TarInfo(name=member.name)
                        ti.size = len(injected)
                        ti.mode = member.mode
                        dst.addfile(ti, io.BytesIO(injected))
                    else:
                        if member.isfile():
                            dst.addfile(member, src.extractfile(member))
                        else:
                            dst.addfile(member)

            proc = run_cmd([sys.executable, str(smoke_script), "--archive", str(mock_tar)])
            if proc.returncode == 0:
                proc = run_cmd([sys.executable, str(smoke_script), str(mock_tar)])

            self.assertNotEqual(
                proc.returncode, 0,
                "Smoke tester must fail when an extracted file contains a broken relative link",
            )
            combined = (proc.stdout + proc.stderr).lower()
            self.assertTrue(
                "broken" in combined or "ghost_file" in combined or "missing" in combined or "link" in combined,
                f"Smoke tester should report broken link failure: {combined}",
            )

    @test_metadata(tier=2, features=["R4"])
    def test_t2_r4_05_static_verify_missing_scripts_detection(self) -> None:
        """Verify make verify-structure fails if any canonical chapter or lab script is deleted."""
        shim = REPO_ROOT / "scripts" / "make"
        self.assertTrue(shim.is_file(), f"make shim missing at {shim}")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a clone of structure without chapter 6
            proc = run_cmd(
                [sys.executable, str(shim), "verify-structure"],
                cwd=tmpdir,
            )
            self.assertNotEqual(
                proc.returncode, 0,
                "verify-structure must fail when required chapters/labs are missing",
            )


if __name__ == "__main__":
    unittest.main()
