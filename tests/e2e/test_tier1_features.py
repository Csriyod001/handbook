"""Tier 1: Feature Coverage (Happy Path Verification) — 20 Tests.

Covers:
- Requirement R1: Standalone Offline Reading Package & Portable Archive (5 tests)
- Requirement R2: Containerized Lab Environment (5 tests)
- Requirement R3: Portability Documentation & Quickstart (5 tests)
- Requirement R4: Static & Smoke Verification (5 tests)
"""

from __future__ import annotations

import json
import re
import sys
import tarfile
import unittest
import zipfile
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from tests.e2e import (
    REPO_ROOT,
    run_cmd,
    strip_jsonc_comments,
    test_metadata,
)


class TestTier1Features(unittest.TestCase):
    """Tier 1 test suite covering primary happy-path features for R1-R4."""

    # -------------------------------------------------------------------------
    # Requirement R1: Standalone Offline Reading Package & Portable Archive
    # -------------------------------------------------------------------------

    @test_metadata(tier=1, features=["R1"])
    def test_t1_r1_01_tar_gz_generation_and_validity(self) -> None:
        """Assert scripts/package_handbook.py generates a valid .tar.gz archive."""
        packager = REPO_ROOT / "scripts" / "package_handbook.py"
        self.assertTrue(packager.is_file(), f"Packaging script missing at {packager}")

        tar_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.tar.gz"
        if not tar_path.is_file():
            proc = run_cmd([sys.executable, str(packager)])
            self.assertEqual(
                proc.returncode, 0,
                f"Packaging script failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
            )

        self.assertTrue(tar_path.is_file(), f"Tarball missing at {tar_path}")
        size = tar_path.stat().st_size
        self.assertGreater(size, 200_000, f"Tarball size too small ({size} bytes)")
        self.assertTrue(tarfile.is_tarfile(tar_path), f"File {tar_path} is not a valid tar archive")

        with tarfile.open(tar_path, "r:gz") as tar:
            names = tar.getnames()
            self.assertGreaterEqual(
                len(names), 40,
                f"Expected >= 40 archive members, found {len(names)}"
            )

    @test_metadata(tier=1, features=["R1"])
    def test_t1_r1_02_zip_generation_and_validity(self) -> None:
        """Assert scripts/package_handbook.py generates a valid .zip archive."""
        packager = REPO_ROOT / "scripts" / "package_handbook.py"
        zip_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.zip"
        if not zip_path.is_file():
            self.assertTrue(packager.is_file(), f"Packaging script missing at {packager}")
            proc = run_cmd([sys.executable, str(packager)])
            self.assertEqual(proc.returncode, 0, f"Packaging failed: {proc.stderr}")

        self.assertTrue(zip_path.is_file(), f"Zip package missing at {zip_path}")
        size = zip_path.stat().st_size
        self.assertGreater(size, 200_000, f"Zip size too small ({size} bytes)")
        self.assertTrue(zipfile.is_zipfile(zip_path), f"File {zip_path} is not a valid zip")

        with zipfile.ZipFile(zip_path, "r") as zf:
            bad_crc = zf.testzip()
            self.assertIsNone(bad_crc, f"Corrupted file CRC in zip archive: {bad_crc}")
            self.assertGreaterEqual(
                len(zf.namelist()), 40,
                f"Expected >= 40 members in zip, found {len(zf.namelist())}"
            )

    @test_metadata(tier=1, features=["R1"])
    def test_t1_r1_03_interactive_portal_offline_asset_loader(self) -> None:
        """Verify dist/AI_Infra_Interactive_Handbook.html includes offline local asset loader."""
        portal_path = REPO_ROOT / "dist" / "AI_Infra_Interactive_Handbook.html"
        self.assertTrue(portal_path.is_file(), f"Interactive portal missing at {portal_path}")
        portal_text = portal_path.read_text(encoding="utf-8")

        # Must reference local assets/tailwindcss.min.js
        local_ref = re.search(
            r'<script\s+[^>]*src=[\'"](?:\./)?assets/tailwindcss\.min\.js[\'"]',
            portal_text,
        )
        self.assertIsNotNone(
            local_ref,
            "Portal HTML must include local script tag for assets/tailwindcss.min.js",
        )

        # Asset file must exist and have reasonable size (> 100KB)
        asset_path = REPO_ROOT / "dist" / "assets" / "tailwindcss.min.js"
        self.assertTrue(asset_path.is_file(), f"Vendored asset missing at {asset_path}")
        self.assertGreater(asset_path.stat().st_size, 100_000, "Vendored Tailwind asset too small")

    @test_metadata(tier=1, features=["R1"])
    def test_t1_r1_04_full_manuscript_presence_and_integrity(self) -> None:
        """Verify monolithic manuscript exists, contains chapters 00-06, and passes check."""
        manuscript_path = REPO_ROOT / "dist" / "FULL_MANUSCRIPT.md"
        self.assertTrue(manuscript_path.is_file(), f"Manuscript missing at {manuscript_path}")
        self.assertGreater(
            manuscript_path.stat().st_size, 400_000,
            f"Manuscript too small: {manuscript_path.stat().st_size} bytes",
        )

        content = manuscript_path.read_text(encoding="utf-8")
        # Verify chapter headings
        for ch_num in range(7):
            pattern = rf"(#\s+บทที่\s+{ch_num}\b|#\s+บทที่\s+0{ch_num}\b)"
            self.assertRegex(
                content,
                re.compile(pattern),
                f"Manuscript missing heading for chapter {ch_num}",
            )

        # Compiler check must pass cleanly
        build_script = REPO_ROOT / "scripts" / "build_manuscript.py"
        if build_script.is_file():
            proc = run_cmd([sys.executable, str(build_script), "--check"])
            self.assertEqual(proc.returncode, 0, f"Manuscript check failed:\n{proc.stdout}\n{proc.stderr}")

    @test_metadata(tier=1, features=["R1"])
    def test_t1_r1_05_root_index_html_redirector(self) -> None:
        """Verify root index.html redirects browser to dist/AI_Infra_Interactive_Handbook.html."""
        index_path = REPO_ROOT / "index.html"
        self.assertTrue(index_path.is_file(), f"Root index.html missing at {index_path}")
        content = index_path.read_text(encoding="utf-8")

        self.assertRegex(
            content,
            re.compile(r'http-equiv=[\'"]refresh[\'"]', re.IGNORECASE),
            "index.html must have http-equiv='refresh' meta tag",
        )
        self.assertIn(
            "dist/AI_Infra_Interactive_Handbook.html",
            content,
            "index.html must point to dist/AI_Infra_Interactive_Handbook.html",
        )
        self.assertRegex(
            content,
            re.compile(r'<a\s+[^>]*href=[\'"]dist/AI_Infra_Interactive_Handbook\.html[\'"]', re.IGNORECASE),
            "index.html must provide fallback hyperlink to dist/AI_Infra_Interactive_Handbook.html",
        )

    # -------------------------------------------------------------------------
    # Requirement R2: Containerized Lab Environment
    # -------------------------------------------------------------------------

    @test_metadata(tier=1, features=["R2"])
    def test_t1_r2_01_dockerfile_syntax_and_instructions(self) -> None:
        """Verify .devcontainer/Dockerfile contains required base and toolchain instructions."""
        dockerfile = REPO_ROOT / ".devcontainer" / "Dockerfile"
        self.assertTrue(dockerfile.is_file(), f"Dockerfile missing at {dockerfile}")
        content = dockerfile.read_text(encoding="utf-8")

        self.assertRegex(content, r"^FROM\s+(ubuntu:24\.04|python:3\.12)", "Dockerfile must use Ubuntu 24.04 or Python 3.12")
        self.assertIn("ARG TARGETARCH", content, "Dockerfile must declare ARG TARGETARCH")
        self.assertIn("uv", content, "Dockerfile must install Astral uv")

        # 7 required Python packages
        for pkg in ["fastapi", "uvicorn", "pydantic", "httpx", "pytest", "pyyaml", "ruff"]:
            self.assertIn(pkg, content, f"Dockerfile must include Python package '{pkg}'")

        # Required cloud-native CLIs
        for cli in ["kubectl", "helm", "kind", "tofu", "trivy", "promtool", "docker"]:
            self.assertIn(cli, content, f"Dockerfile must install CLI tool '{cli}'")

        self.assertRegex(content, r"WORKDIR\s+/workspace", "Dockerfile must set WORKDIR under /workspace")

    @test_metadata(tier=1, features=["R2"])
    def test_t1_r2_02_devcontainer_json_validity_and_mounts(self) -> None:
        """Verify .devcontainer/devcontainer.json is valid JSON with DooD and cache mounts."""
        devcontainer = REPO_ROOT / ".devcontainer" / "devcontainer.json"
        self.assertTrue(devcontainer.is_file(), f"devcontainer.json missing at {devcontainer}")
        raw = devcontainer.read_text(encoding="utf-8")
        clean = strip_jsonc_comments(raw)
        try:
            data = json.loads(clean)
        except Exception as exc:
            self.fail(f"devcontainer.json is not valid JSON: {exc}")

        self.assertTrue(data.get("name"), "devcontainer.json must have non-empty 'name'")
        mounts_str = str(data.get("mounts", []))
        self.assertIn("/var/run/docker.sock", mounts_str, "devcontainer.json must mount docker.sock")
        self.assertTrue(
            "/tmp/ai-infra-hf-cache" in mounts_str or "/cache/huggingface" in mounts_str,
            "devcontainer.json must mount HuggingFace model cache",
        )

        ports = data.get("forwardPorts", [])
        for port in [8000, 4000, 3000, 9090]:
            self.assertIn(port, ports, f"devcontainer.json forwardPorts must include port {port}")

    @test_metadata(tier=1, features=["R2"])
    def test_t1_r2_03_docker_compose_lab_validity_and_services(self) -> None:
        """Verify docker-compose.lab.yml is valid YAML defining the 'lab' service."""
        compose_file = REPO_ROOT / "docker-compose.lab.yml"
        self.assertTrue(compose_file.is_file(), f"docker-compose.lab.yml missing at {compose_file}")

        self.assertIsNotNone(yaml, "PyYAML is required for compose validation")
        try:
            data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
        except Exception as exc:
            self.fail(f"docker-compose.lab.yml is not valid YAML: {exc}")

        services = data.get("services", {})
        self.assertIn("lab", services, "docker-compose.lab.yml must define 'lab' service")

        lab = services["lab"]
        volumes_str = str(lab.get("volumes", []))
        self.assertIn("/var/run/docker.sock", volumes_str, "Compose must mount docker.sock")
        self.assertTrue(
            "/tmp/ai-infra-hf-cache" in volumes_str or "/cache/huggingface" in volumes_str,
            "Compose must mount model cache",
        )

        ports_str = str(lab.get("ports", []))
        for p in ["8000", "4000", "3000", "9090"]:
            self.assertIn(p, ports_str, f"Compose must expose port {p}")

    @test_metadata(tier=1, features=["R2"])
    def test_t1_r2_04_container_validator_offline_pass(self) -> None:
        """Verify scripts/validate_container_config.py runs and passes cleanly offline."""
        validator = REPO_ROOT / "scripts" / "validate_container_config.py"
        self.assertTrue(validator.is_file(), f"Validator missing at {validator}")

        proc = run_cmd([sys.executable, str(validator)])
        self.assertEqual(
            proc.returncode, 0,
            f"Container validator failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}",
        )
        self.assertIn("PASS", proc.stdout.upper(), "Validator output should confirm pass status")

    @test_metadata(tier=1, features=["R2"])
    def test_t1_r2_05_multiarch_cli_download_declarations(self) -> None:
        """Verify Dockerfile declares multi-arch download support (TARGETARCH)."""
        dockerfile = REPO_ROOT / ".devcontainer" / "Dockerfile"
        self.assertTrue(dockerfile.is_file(), f"Dockerfile missing at {dockerfile}")
        content = dockerfile.read_text(encoding="utf-8")

        self.assertIn("ARG TARGETARCH", content, "Dockerfile must declare ARG TARGETARCH")
        self.assertTrue(
            "${TARGETARCH}" in content or "$TARGETARCH" in content,
            "Dockerfile must use TARGETARCH parameter in download instructions",
        )

    # -------------------------------------------------------------------------
    # Requirement R3: Portability Documentation & Quickstart
    # -------------------------------------------------------------------------

    @test_metadata(tier=1, features=["R3"])
    def test_t1_r3_01_portability_guide_sections_and_completeness(self) -> None:
        """Verify PORTABILITY_AND_QUICKSTART.md exists and contains required sections."""
        guide = REPO_ROOT / "PORTABILITY_AND_QUICKSTART.md"
        self.assertTrue(guide.is_file(), f"PORTABILITY_AND_QUICKSTART.md missing at {guide}")
        self.assertGreater(guide.stat().st_size, 2000, "PORTABILITY_AND_QUICKSTART.md too short")

        content = guide.read_text(encoding="utf-8").lower()
        required_topics = [
            "tar.gz", "zip", "offline", "index.html",
            "devcontainer", "compose", "port", "troubleshoot",
        ]
        for topic in required_topics:
            self.assertIn(topic, content, f"Guide must discuss '{topic}'")

    @test_metadata(tier=1, features=["R3"])
    def test_t1_r3_02_readme_quickstart_four_tracks(self) -> None:
        """Verify README.md Section 7 documents 4 distinct onboarding tracks."""
        readme = REPO_ROOT / "README.md"
        self.assertTrue(readme.is_file(), f"README.md missing at {readme}")
        content = readme.read_text(encoding="utf-8")

        # Must mention all 4 tracks
        self.assertIn("Track 1", content, "README must document Track 1")
        self.assertIn("Track 2", content, "README must document Track 2")
        self.assertIn("Track 3", content, "README must document Track 3")
        self.assertIn("Track 4", content, "README must document Track 4")
        self.assertIn("PORTABILITY_AND_QUICKSTART.md", content, "README must link to portability guide")

    @test_metadata(tier=1, features=["R3"])
    def test_t1_r3_03_chapter0_containerized_lab_pathway(self) -> None:
        """Verify chapters/00-onboarding-and-setup.md features Containerized Lab pathway."""
        ch0 = REPO_ROOT / "chapters" / "00-onboarding-and-setup.md"
        self.assertTrue(ch0.is_file(), f"Chapter 0 missing at {ch0}")
        content = ch0.read_text(encoding="utf-8")

        self.assertTrue(
            "container" in content.lower() or "docker" in content.lower(),
            "Chapter 0 must introduce containerized lab pathway",
        )
        self.assertIn("PORTABILITY_AND_QUICKSTART.md", content, "Chapter 0 must link to portability guide")

    @test_metadata(tier=1, features=["R3"])
    def test_t1_r3_04_os_specific_extraction_and_run_instructions(self) -> None:
        """Verify PORTABILITY_AND_QUICKSTART.md provides explicit commands for Linux, macOS, and Windows."""
        guide = REPO_ROOT / "PORTABILITY_AND_QUICKSTART.md"
        self.assertTrue(guide.is_file(), f"Guide missing at {guide}")
        content = guide.read_text(encoding="utf-8")

        self.assertIn("tar -xzf", content, "Guide must include tar -xzf extraction command")
        self.assertIn("Expand-Archive", content, "Guide must include Windows PowerShell Expand-Archive command")
        # Browser open commands
        has_browser_cmd = any(cmd in content for cmd in ["xdg-open", "open index.html", "Start-Process"])
        self.assertTrue(has_browser_cmd, "Guide must provide browser open commands")

    @test_metadata(tier=1, features=["R3"])
    def test_t1_r3_05_port_and_volume_documentation_consistency(self) -> None:
        """Verify port and volume documentation in PORTABILITY_AND_QUICKSTART.md matches configs."""
        guide = REPO_ROOT / "PORTABILITY_AND_QUICKSTART.md"
        self.assertTrue(guide.is_file(), f"Guide missing at {guide}")
        content = guide.read_text(encoding="utf-8")

        for port in ["8000", "4000", "3000", "9090"]:
            self.assertIn(port, content, f"Guide must document port {port}")

        self.assertIn("/var/run/docker.sock", content, "Guide must document DooD socket path")
        self.assertTrue(
            "/tmp/ai-infra-hf-cache" in content or "/cache/huggingface" in content,
            "Guide must document HuggingFace model cache directory",
        )

    # -------------------------------------------------------------------------
    # Requirement R4: Static & Smoke Verification
    # -------------------------------------------------------------------------

    @test_metadata(tier=1, features=["R4"])
    def test_t1_r4_01_make_shim_execution_and_help(self) -> None:
        """Verify scripts/make (or make) executes and displays help target."""
        shim = REPO_ROOT / "scripts" / "make"
        self.assertTrue(shim.is_file(), f"make runner shim missing at {shim}")

        proc = run_cmd([sys.executable, str(shim), "help"])
        self.assertEqual(proc.returncode, 0, f"make help failed: {proc.stderr}")
        self.assertIn("verify-static", proc.stdout, "make help should list verify-static target")

    @test_metadata(tier=1, features=["R4"])
    def test_t1_r4_02_make_verify_static_zero_error_pass(self) -> None:
        """Verify make verify-static passes 100% cleanly without errors."""
        shim = REPO_ROOT / "scripts" / "make"
        self.assertTrue(shim.is_file(), f"make shim missing at {shim}")

        proc = run_cmd([sys.executable, str(shim), "verify-static"], timeout=180)
        self.assertEqual(
            proc.returncode, 0,
            f"make verify-static failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}",
        )

    @test_metadata(tier=1, features=["R4"])
    def test_t1_r4_03_archive_smoke_test_script_execution(self) -> None:
        """Verify scripts/smoke_test_archive.py executes successfully in clean temporary directory."""
        smoke_script = REPO_ROOT / "scripts" / "smoke_test_archive.py"
        self.assertTrue(smoke_script.is_file(), f"Smoke tester missing at {smoke_script}")

        proc = run_cmd([sys.executable, str(smoke_script)], timeout=120)
        self.assertEqual(
            proc.returncode, 0,
            f"Archive smoke test failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}",
        )

    @test_metadata(tier=1, features=["R4"])
    def test_t1_r4_04_makefile_target_completeness(self) -> None:
        """Verify Makefile includes targets package, verify-container, verify-archive, verify-static."""
        makefile = REPO_ROOT / "Makefile"
        self.assertTrue(makefile.is_file(), f"Makefile missing at {makefile}")
        content = makefile.read_text(encoding="utf-8")

        for target in ["package:", "verify-container:", "verify-static:"]:
            self.assertIn(target, content, f"Makefile must declare target '{target}'")

        has_archive_target = ("verify-archive:" in content) or ("verify-smoke:" in content)
        self.assertTrue(has_archive_target, "Makefile must declare verify-archive or verify-smoke target")

    @test_metadata(tier=1, features=["R4"])
    def test_t1_r4_05_check_env_script_resilience(self) -> None:
        """Verify scripts/check-env.sh runs cleanly without crashing on minimal environments."""
        check_env = REPO_ROOT / "scripts" / "check-env.sh"
        self.assertTrue(check_env.is_file(), f"check-env.sh missing at {check_env}")

        proc = run_cmd(["bash", str(check_env)])
        self.assertEqual(proc.returncode, 0, f"check-env.sh failed:\n{proc.stdout}\n{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
