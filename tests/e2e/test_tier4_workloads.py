"""Tier 4: Real-World Application Workloads & User Journeys — 5 Tests.

End-to-end simulations of learner, developer, and maintainer lifecycles:
- Workload 01: Clean Machine Extraction & Offline Reading Journey (R1, R3, R4)
- Workload 02: Full Manuscript Navigation & Link Resolution in Cleanroom (R1, R4)
- Workload 03: Daemonless Container Audit & Devcontainer Lifecycle Simulation (R2, R3)
- Workload 04: Universal Makefile Execution on Minimal Linux (R2, R4)
- Workload 05: End-to-End Fresh Learner Onboarding Journey (R1, R2, R3, R4)
"""

from __future__ import annotations

import json
import re
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from tests.e2e import (
    REPO_ROOT,
    extract_relative_markdown_links,
    parse_portal_deliverable_links,
    run_cmd,
    test_metadata,
)


class TestTier4Workloads(unittest.TestCase):
    """Tier 4 test suite validating realistic real-world workflows from the user's perspective."""

    @test_metadata(tier=4, features=["R1", "R3", "R4"])
    def test_t4_workload_01_clean_machine_offline_reading(self) -> None:
        """Workload 1: Fresh learner downloads portable tarball and reads offline in air-gapped cleanroom."""
        tar_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.tar.gz"
        packager = REPO_ROOT / "scripts" / "package_handbook.py"

        if not tar_path.is_file() and packager.is_file():
            pkg_res = run_cmd([sys.executable, str(packager)])
            self.assertEqual(pkg_res.returncode, 0, f"Packager failed: {pkg_res.stderr}")

        self.assertTrue(tar_path.is_file(), f"Portable archive missing at {tar_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = Path(tmpdir)

            # Step 1: Unpack archive in clean sandbox
            with tarfile.open(tar_path, "r:gz") as tar:
                # Python 3.12 data_filter support
                if hasattr(tarfile, "data_filter"):
                    tar.extractall(sandbox, filter="data")
                else:
                    tar.extractall(sandbox)

            # Locate root of extracted handbook
            index_candidates = list(sandbox.glob("**/index.html"))
            self.assertGreater(len(index_candidates), 0, "Extracted archive missing root index.html")
            extracted_root = index_candidates[0].parent

            # Step 2: Validate essential reading assets
            portal = extracted_root / "dist" / "AI_Infra_Interactive_Handbook.html"
            manuscript = extracted_root / "dist" / "FULL_MANUSCRIPT.md"
            tailwind_asset = extracted_root / "dist" / "assets" / "tailwindcss.min.js"

            self.assertTrue(portal.is_file(), f"Extracted portal missing at {portal}")
            self.assertTrue(manuscript.is_file(), f"Extracted manuscript missing at {manuscript}")
            self.assertTrue(tailwind_asset.is_file(), f"Extracted Tailwind asset missing at {tailwind_asset}")
            self.assertGreater(tailwind_asset.stat().st_size, 100_000, "Tailwind asset too small")

            # Step 3: Check root redirector
            index_content = (extracted_root / "index.html").read_text(encoding="utf-8")
            self.assertIn("dist/AI_Infra_Interactive_Handbook.html", index_content)

            # Step 4: Verify 100% of deliverable links resolve within the extracted sandbox
            portal_text = portal.read_text(encoding="utf-8")
            deliverables = parse_portal_deliverable_links(portal_text)
            self.assertGreaterEqual(len(deliverables), 40, f"Expected >= 40 deliverables, found {len(deliverables)}")

            missing_files: list[str] = []
            for rel in deliverables:
                # Deliverables in HTML are relative to portal.parent.parent (repo root) or portal.parent (dist/)
                target1 = (portal.parent.parent / rel).resolve()
                target2 = (portal.parent / rel).resolve()
                if not (target1.exists() or target2.exists()):
                    missing_files.append(rel)

            self.assertEqual(
                missing_files, [],
                f"Extracted reading sandbox missing deliverable files: {missing_files}",
            )

    @test_metadata(tier=4, features=["R1", "R4"])
    def test_t4_workload_02_full_manuscript_integrity_and_navigation_in_cleanroom(self) -> None:
        """Workload 2: Learner navigates FULL_MANUSCRIPT.md in offline cleanroom; all links resolve."""
        tar_path = REPO_ROOT / "dist" / "ai-infra-handbook-portable.tar.gz"
        packager = REPO_ROOT / "scripts" / "package_handbook.py"

        if not tar_path.is_file() and packager.is_file():
            run_cmd([sys.executable, str(packager)])

        self.assertTrue(tar_path.is_file(), f"Archive missing at {tar_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = Path(tmpdir)
            with tarfile.open(tar_path, "r:gz") as tar:
                if hasattr(tarfile, "data_filter"):
                    tar.extractall(sandbox, filter="data")
                else:
                    tar.extractall(sandbox)

            manuscripts = list(sandbox.glob("**/dist/FULL_MANUSCRIPT.md"))
            self.assertGreater(len(manuscripts), 0, "FULL_MANUSCRIPT.md missing in extracted sandbox")
            manuscript = manuscripts[0]

            content = manuscript.read_text(encoding="utf-8")
            self.assertGreater(len(content), 300_000, "Extracted manuscript content unexpectedly small")

            # Extract relative links
            rel_links = extract_relative_markdown_links(content)
            self.assertGreaterEqual(
                len(rel_links), 50,
                f"Expected >= 50 relative links in manuscript, found {len(rel_links)}",
            )

            broken_links: list[str] = []
            for target in rel_links:
                target_path = (manuscript.parent / target).resolve()
                if not target_path.exists():
                    broken_links.append(target)

            self.assertEqual(
                broken_links, [],
                f"Found broken relative links in extracted manuscript: {broken_links}",
            )

            # Check that build_manuscript.py --check passes inside cleanroom if script is present
            build_scripts = list(sandbox.glob("**/scripts/build_manuscript.py"))
            if build_scripts:
                proc = run_cmd([sys.executable, str(build_scripts[0]), "--check"], cwd=build_scripts[0].parent.parent)
                self.assertEqual(
                    proc.returncode, 0,
                    f"Manuscript check in cleanroom failed:\n{proc.stdout}\n{proc.stderr}",
                )

    @test_metadata(tier=4, features=["R2", "R3"])
    def test_t4_workload_03_devcontainer_and_compose_lifecycle_simulation(self) -> None:
        """Workload 3: SRE / Platform Engineer runs offline deterministic container config validation."""
        validator = REPO_ROOT / "scripts" / "validate_container_config.py"
        self.assertTrue(validator.is_file(), f"Container validator missing at {validator}")

        # Execute container config validation offline
        proc = run_cmd([sys.executable, str(validator)], timeout=30)
        self.assertEqual(
            proc.returncode, 0,
            f"Container config validation failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}",
        )

        out = proc.stdout.lower()
        self.assertTrue(
            "dockerfile" in out or "pass" in out,
            "Validator output should confirm Dockerfile validation",
        )
        self.assertTrue(
            "devcontainer" in out or "pass" in out,
            "Validator output should confirm devcontainer.json validation",
        )
        self.assertTrue(
            "compose" in out or "pass" in out,
            "Validator output should confirm docker-compose.lab.yml validation",
        )

    @test_metadata(tier=4, features=["R2", "R4"])
    def test_t4_workload_04_universal_makefile_execution_on_minimal_linux(self) -> None:
        """Workload 4: Universal Makefile execution on minimal host via scripts/make fallback shim."""
        shim_make = REPO_ROOT / "scripts" / "make"
        self.assertTrue(shim_make.is_file(), f"make shim missing at {shim_make}")

        # 1. Target: help
        p_help = run_cmd([sys.executable, str(shim_make), "help"])
        self.assertEqual(p_help.returncode, 0, f"make help failed: {p_help.stderr}")

        # 2. Target: init-cache
        p_cache = run_cmd([sys.executable, str(shim_make), "init-cache"])
        self.assertEqual(p_cache.returncode, 0, f"make init-cache failed: {p_cache.stderr}")
        self.assertTrue(
            Path("/tmp/ai-infra-hf-cache").is_dir() or Path("/cache/huggingface").is_dir(),
            "init-cache should ensure /tmp/ai-infra-hf-cache exists",
        )

        # 3. Target: check-env
        p_env = run_cmd([sys.executable, str(shim_make), "check-env"])
        self.assertEqual(p_env.returncode, 0, f"make check-env failed: {p_env.stderr}")

        # 4. Target: verify-structure
        p_struct = run_cmd([sys.executable, str(shim_make), "verify-structure"])
        self.assertEqual(p_struct.returncode, 0, f"make verify-structure failed: {p_struct.stderr}")

        # 5. Target: verify-static
        p_static = run_cmd([sys.executable, str(shim_make), "verify-static"], timeout=180)
        self.assertEqual(p_static.returncode, 0, f"make verify-static failed: {p_static.stderr}")

    @test_metadata(tier=4, features=["R1", "R2", "R3", "R4"])
    def test_t4_workload_05_end_to_end_learner_onboarding_journey(self) -> None:
        """Workload 5: Complete end-to-end simulated journey across all 4 requirements."""
        # 1. Verify README Section 7 Track 1 points to index.html and documentation
        readme = REPO_ROOT / "README.md"
        self.assertTrue(readme.is_file(), f"README.md missing at {readme}")
        readme_text = readme.read_text(encoding="utf-8")
        self.assertIn("PORTABILITY_AND_QUICKSTART.md", readme_text)
        self.assertIn("index.html", readme_text)

        # 2. Execute handbook packaging
        packager = REPO_ROOT / "scripts" / "package_handbook.py"
        self.assertTrue(packager.is_file(), f"Packaging script missing at {packager}")
        pkg_res = run_cmd([sys.executable, str(packager)])
        self.assertEqual(pkg_res.returncode, 0, f"Packaging step failed: {pkg_res.stderr}")

        # 3. Execute smoke verification
        smoke_script = REPO_ROOT / "scripts" / "smoke_test_archive.py"
        self.assertTrue(smoke_script.is_file(), f"Smoke tester missing at {smoke_script}")
        smoke_res = run_cmd([sys.executable, str(smoke_script)])
        self.assertEqual(smoke_res.returncode, 0, f"Smoke verification step failed: {smoke_res.stderr}")

        # 4. Execute container validator
        validator = REPO_ROOT / "scripts" / "validate_container_config.py"
        self.assertTrue(validator.is_file(), f"Container validator missing at {validator}")
        val_res = run_cmd([sys.executable, str(validator)])
        self.assertEqual(val_res.returncode, 0, f"Container validation step failed: {val_res.stderr}")

        # 5. Execute full static verification suite
        shim = REPO_ROOT / "scripts" / "make"
        self.assertTrue(shim.is_file(), f"make shim missing at {shim}")
        static_res = run_cmd([sys.executable, str(shim), "verify-static"], timeout=180)
        self.assertEqual(static_res.returncode, 0, f"Static verification step failed: {static_res.stderr}")


if __name__ == "__main__":
    unittest.main()
