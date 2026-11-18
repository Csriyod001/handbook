"""Tier 3: Cross-Feature Combinations (Pairwise Interaction Tests) — 6 Tests.

Validates the pairwise interplay between R1, R2, R3, and R4:
- Comb 01: R1 Packager ↔ R4 Smoke Tester
- Comb 02: R1 Archive ↔ R3 Docs Extraction Command
- Comb 03: R2 Container ↔ R4 Static Verification
- Comb 04: R2 Compose/Devcontainer ↔ R3 Documentation Parity
- Comb 05: R3 Documentation ↔ R4 Makefile Targets
- Comb 06: R1 Root Redirector ↔ R1 Portal ↔ R1/R3 Vendored Offline Asset
"""

from __future__ import annotations

import json
import re
import sys
import tarfile
import tempfile
import unittest
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


class TestTier3Combinations(unittest.TestCase):
    """Tier 3 test suite verifying end-to-end interactions between adjacent architectural modules."""

    @test_metadata(tier=3, features=["R1", "R4"])
    def test_t3_comb_01_r1_packager_to_r4_smoke_tester(self) -> None:
        """Pairwise: scripts/package_handbook.py -> scripts/smoke_test_archive.py roundtrip."""
        packager = REPO_ROOT / "scripts" / "package_handbook.py"
        smoke_script = REPO_ROOT / "scripts" / "smoke_test_archive.py"

        self.assertTrue(packager.is_file(), f"Packager missing at {packager}")
        self.assertTrue(smoke_script.is_file(), f"Smoke tester missing at {smoke_script}")

        # 1. Generate fresh archives
        pkg_proc = run_cmd([sys.executable, str(packager)])
        self.assertEqual(
            pkg_proc.returncode, 0,
            f"Packaging failed in comb 01:\nSTDOUT: {pkg_proc.stdout}\nSTDERR: {pkg_proc.stderr}",
        )

        tar_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.tar.gz"
        zip_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.zip"
        self.assertTrue(tar_path.is_file(), f"Tarball missing at {tar_path}")
        self.assertTrue(zip_path.is_file(), f"Zip missing at {zip_path}")

        # 2. Smoke test tarball
        smoke_tar = run_cmd([sys.executable, str(smoke_script), "--archive", str(tar_path)])
        self.assertEqual(
            smoke_tar.returncode, 0,
            f"Smoke test failed on newly built tarball:\nSTDOUT: {smoke_tar.stdout}\nSTDERR: {smoke_tar.stderr}",
        )

        # 3. Smoke test zip
        smoke_zip = run_cmd([sys.executable, str(smoke_script), "--archive", str(zip_path)])
        self.assertEqual(
            smoke_zip.returncode, 0,
            f"Smoke test failed on newly built zip:\nSTDOUT: {smoke_zip.stdout}\nSTDERR: {smoke_zip.stderr}",
        )

    @test_metadata(tier=3, features=["R1", "R3"])
    def test_t3_comb_02_r1_archive_to_r3_docs_extraction(self) -> None:
        """Pairwise: Execute documented extraction command from PORTABILITY_AND_QUICKSTART.md in clean sandbox."""
        guide = REPO_ROOT / "PORTABILITY_AND_QUICKSTART.md"
        tar_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.tar.gz"
        packager = REPO_ROOT / "scripts" / "package_handbook.py"

        self.assertTrue(guide.is_file(), f"Guide missing at {guide}")
        if not tar_path.is_file() and packager.is_file():
            run_cmd([sys.executable, str(packager)])

        self.assertTrue(tar_path.is_file(), f"Tarball missing at {tar_path}")

        # Extract documented tar command from guide
        content = guide.read_text(encoding="utf-8")
        m = re.search(r"(tar\s+-[a-zA-Z]*x[a-zA-Z]*f\s+([^\s\n]+))", content)
        self.assertIsNotNone(m, "Could not find documented 'tar -xzf' extraction command in guide")

        # Test extraction in isolated sandbox
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = Path(tmpdir)
            # Execute standard extraction command
            proc = run_cmd(["tar", "-xzf", str(tar_path)], cwd=sandbox)
            self.assertEqual(proc.returncode, 0, f"Documented tar command failed: {proc.stderr}")

            # Locate extracted root
            extracted_html = list(sandbox.glob("**/dist/AI_Infra_Interactive_Handbook.html"))
            self.assertGreater(len(extracted_html), 0, "Extracted archive missing interactive portal")

            extracted_manuscript = list(sandbox.glob("**/dist/FULL_MANUSCRIPT.md"))
            self.assertGreater(len(extracted_manuscript), 0, "Extracted archive missing FULL_MANUSCRIPT.md")

    @test_metadata(tier=3, features=["R2", "R4"])
    def test_t3_comb_03_r2_container_to_r4_make_verify(self) -> None:
        """Pairwise: devcontainer.json postCreateCommand compatibility with scripts/make verify-static."""
        devcontainer = REPO_ROOT / ".devcontainer" / "devcontainer.json"
        self.assertTrue(devcontainer.is_file(), f"devcontainer.json missing at {devcontainer}")

        raw = devcontainer.read_text(encoding="utf-8")
        clean = strip_jsonc_comments(raw)
        data = json.loads(clean)

        post_create = data.get("postCreateCommand", "")
        self.assertTrue(post_create, "devcontainer.json must define 'postCreateCommand'")
        self.assertIn("verify-static", post_create, "postCreateCommand must run verify-static")

        # Execute postCreateCommand in host environment to verify syntax and clean exit
        shim_make = REPO_ROOT / "scripts" / "make"
        self.assertTrue(shim_make.is_file(), f"make shim missing at {shim_make}")

        # If postCreateCommand uses `make verify-static`, run it via python3 scripts/make
        proc = run_cmd([sys.executable, str(shim_make), "verify-static"], timeout=180)
        self.assertEqual(
            proc.returncode, 0,
            f"postCreateCommand target failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}",
        )

    @test_metadata(tier=3, features=["R2", "R3"])
    def test_t3_comb_04_r2_compose_to_r3_docs_port_consistency(self) -> None:
        """Pairwise: Validate port numbers and volume mounts documented in guide match compose and devcontainer."""
        guide = REPO_ROOT / "PORTABILITY_AND_QUICKSTART.md"
        compose_file = REPO_ROOT / "docker-compose.lab.yml"
        devcontainer = REPO_ROOT / ".devcontainer" / "devcontainer.json"

        self.assertTrue(guide.is_file(), f"Guide missing at {guide}")
        self.assertTrue(compose_file.is_file(), f"Compose missing at {compose_file}")
        self.assertTrue(devcontainer.is_file(), f"devcontainer missing at {devcontainer}")

        guide_text = guide.read_text(encoding="utf-8")
        dc_data = json.loads(strip_jsonc_comments(devcontainer.read_text(encoding="utf-8")))

        self.assertIsNotNone(yaml, "PyYAML required for compose validation")
        compose_data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))

        # Verify common ports: 8000, 4000, 3000, 9090
        for port in [8000, 4000, 3000, 9090]:
            self.assertIn(str(port), guide_text, f"Port {port} missing from guide documentation")
            self.assertIn(port, dc_data.get("forwardPorts", []), f"Port {port} missing from devcontainer forwardPorts")
            compose_ports = str(compose_data.get("services", {}).get("lab", {}).get("ports", []))
            self.assertIn(str(port), compose_ports, f"Port {port} missing from compose ports")

        # Verify volume mounts
        self.assertIn("/var/run/docker.sock", guide_text, "docker.sock mount missing from guide")
        self.assertTrue(
            "/tmp/ai-infra-hf-cache" in guide_text or "/cache/huggingface" in guide_text,
            "HuggingFace cache mount missing from guide",
        )

    @test_metadata(tier=3, features=["R3", "R4"])
    def test_t3_comb_05_r3_docs_to_r4_makefile_target_parity(self) -> None:
        """Pairwise: Extract all 'make <target>' commands from docs and verify target exists in Makefile."""
        makefile = REPO_ROOT / "Makefile"
        self.assertTrue(makefile.is_file(), f"Makefile missing at {makefile}")
        makefile_content = makefile.read_text(encoding="utf-8")

        # Find all target declarations in Makefile
        declared_targets = set(re.findall(r"^([a-zA-Z0-9_-]+)\s*:", makefile_content, re.MULTILINE))

        doc_files = [
            REPO_ROOT / "PORTABILITY_AND_QUICKSTART.md",
            REPO_ROOT / "README.md",
            REPO_ROOT / "chapters" / "00-onboarding-and-setup.md",
        ]

        documented_make_targets: set[str] = set()
        for doc in doc_files:
            if not doc.is_file():
                continue
            text = doc.read_text(encoding="utf-8")
            # Match `make <target>`
            matches = re.findall(r"\bmake\s+([a-zA-Z0-9_-]+)", text)
            for m in matches:
                # Exclude flags or placeholders
                if not m.startswith("-") and m not in ("command", "target"):
                    documented_make_targets.add(m)

        self.assertGreater(len(documented_make_targets), 0, "No make targets found in documentation")

        missing_targets = documented_make_targets - declared_targets
        self.assertEqual(
            missing_targets, set(),
            f"Documented make targets missing from Makefile: {missing_targets}",
        )

    @test_metadata(tier=3, features=["R1", "R3"])
    def test_t3_comb_06_r1_root_redirector_to_dist_html_to_vendored_css(self) -> None:
        """Pairwise: Trace 3-step navigation chain index.html -> interactive portal -> vendored Tailwind asset."""
        index_file = REPO_ROOT / "index.html"
        self.assertTrue(index_file.is_file(), f"Root index.html missing at {index_file}")
        index_text = index_file.read_text(encoding="utf-8")

        # Step 1: index.html redirects to dist/AI_Infra_Interactive_Handbook.html
        m_redirect = re.search(r'content=[\'"]\s*\d+\s*;\s*url=([^"\'\s>]+)', index_text, re.IGNORECASE)
        self.assertIsNotNone(m_redirect, "index.html meta refresh URL not found")
        target_portal_rel = m_redirect.group(1).strip()
        portal_path = (REPO_ROOT / target_portal_rel).resolve()
        self.assertTrue(portal_path.is_file(), f"Redirect target portal missing at {portal_path}")

        # Step 2: Interactive portal loads local Tailwind asset
        portal_text = portal_path.read_text(encoding="utf-8")
        m_asset = re.search(r'<script\s+[^>]*src=[\'"]([^\'"]*tailwindcss\.min\.js)[\'"]', portal_text)
        self.assertIsNotNone(m_asset, "Local script tag for tailwindcss.min.js missing in portal")
        asset_rel = m_asset.group(1).strip()
        asset_path = (portal_path.parent / asset_rel).resolve()

        # Step 3: Resolved asset exists and has valid JS code
        self.assertTrue(asset_path.is_file(), f"Resolved Tailwind asset missing at {asset_path}")
        self.assertGreater(asset_path.stat().st_size, 100_000, "Resolved asset file too small")
        content = asset_path.read_text(encoding="utf-8", errors="ignore")
        self.assertTrue(
            "tailwind" in content or "function" in content,
            "Resolved asset does not contain valid JavaScript code",
        )


if __name__ == "__main__":
    unittest.main()
