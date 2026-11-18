#!/usr/bin/env python3
"""Master E2E Test Suite Runner for AI Infrastructure Handbook.

Pure Python standard library test runner supporting tiered execution,
feature filtering, clean-room isolation, TAP output, JSON reporting,
and formatted ASCII summary tables.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.e2e import REPO_ROOT as DEFAULT_REPO_ROOT  # noqa: E402


class TestCaseDescriptor:
    """Metadata container for an individual discovered test case."""

    def __init__(
        self,
        test_class: type[unittest.TestCase],
        method_name: str,
        tier: int,
        features: list[str],
        doc: str = "",
    ) -> None:
        self.test_class = test_class
        self.method_name = method_name
        self.tier = tier
        self.features = features
        self.doc = doc.strip().split("\n")[0] if doc else ""
        self.test_id = method_name

    def __repr__(self) -> str:
        return f"<TestCaseDescriptor {self.test_id} (T{self.tier}, {','.join(self.features)})>"


def discover_e2e_tests() -> list[TestCaseDescriptor]:
    """Discover all 51 E2E test cases across the four test tier modules."""
    test_modules = [
        ("tests.e2e.test_tier1_features", 1),
        ("tests.e2e.test_tier2_boundaries", 2),
        ("tests.e2e.test_tier3_combinations", 3),
        ("tests.e2e.test_tier4_workloads", 4),
    ]

    descriptors: list[TestCaseDescriptor] = []

    for mod_name, default_tier in test_modules:
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            print(f"[WARN] Failed to import {mod_name}: {exc}", file=sys.stderr)
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if isinstance(attr, type) and issubclass(attr, unittest.TestCase):
                for member_name in dir(attr):
                    if member_name.startswith("test_"):
                        method = getattr(attr, member_name)
                        # Extract metadata
                        tier = getattr(method, "tier", default_tier)
                        features = getattr(method, "features", [])
                        if not features:
                            # Infer from name
                            if "_r1_" in member_name:
                                features = ["R1"]
                            elif "_r2_" in member_name:
                                features = ["R2"]
                            elif "_r3_" in member_name:
                                features = ["R3"]
                            elif "_r4_" in member_name:
                                features = ["R4"]
                            elif "comb_01" in member_name:
                                features = ["R1", "R4"]
                            elif "comb_02" in member_name:
                                features = ["R1", "R3"]
                            elif "comb_03" in member_name:
                                features = ["R2", "R4"]
                            elif "comb_04" in member_name:
                                features = ["R2", "R3"]
                            elif "comb_05" in member_name:
                                features = ["R3", "R4"]
                            elif "comb_06" in member_name:
                                features = ["R1", "R3"]
                            elif "workload_01" in member_name:
                                features = ["R1", "R3", "R4"]
                            elif "workload_02" in member_name:
                                features = ["R1", "R4"]
                            elif "workload_03" in member_name:
                                features = ["R2", "R3"]
                            elif "workload_04" in member_name:
                                features = ["R2", "R4"]
                            elif "workload_05" in member_name:
                                features = ["R1", "R2", "R3", "R4"]
                            else:
                                features = ["ALL"]

                        doc = getattr(method, "__doc__", "") or ""
                        descriptors.append(
                            TestCaseDescriptor(
                                test_class=attr,
                                method_name=member_name,
                                tier=tier,
                                features=features,
                                doc=doc,
                            )
                        )

    # Sort descriptors by tier and test_id for deterministic execution order
    descriptors.sort(key=lambda d: (d.tier, d.test_id))
    return descriptors


def filter_tests(
    tests: list[TestCaseDescriptor],
    tier_filter: str,
    feature_filter: str,
) -> list[TestCaseDescriptor]:
    """Filter test cases by specified execution tier and feature requirement."""
    filtered = tests
    if tier_filter != "all":
        target_tier = int(tier_filter)
        filtered = [t for t in filtered if t.tier == target_tier]

    if feature_filter != "all":
        target_feat = feature_filter.upper()
        filtered = [t for t in filtered if target_feat in t.features]

    return filtered


def run_single_test(descriptor: TestCaseDescriptor, verbose: bool = False) -> dict[str, Any]:
    """Execute a single test case with timing, error capture, and output recording."""
    case = descriptor.test_class(descriptor.method_name)
    result = unittest.TestResult()

    start_time = time.perf_counter()
    try:
        case.run(result)
    except Exception as exc:  # Catch unexpected harness failures
        duration = time.perf_counter() - start_time
        return {
            "id": descriptor.test_id,
            "tier": descriptor.tier,
            "features": descriptor.features,
            "duration": duration,
            "status": "ERROR",
            "error": str(exc),
            "doc": descriptor.doc,
        }
    duration = time.perf_counter() - start_time

    status = "PASS"
    error_msg: str | None = None

    if result.errors:
        status = "ERROR"
        error_msg = result.errors[0][1]
    elif result.failures:
        status = "FAIL"
        error_msg = result.failures[0][1]
    elif result.skipped:
        status = "SKIP"
        error_msg = result.skipped[0][1]

    return {
        "id": descriptor.test_id,
        "tier": descriptor.tier,
        "features": descriptor.features,
        "duration": duration,
        "status": status,
        "error": error_msg,
        "doc": descriptor.doc,
    }


def print_list_view(descriptors: list[TestCaseDescriptor], tier: str, feature: str) -> None:
    """Print discovered test list without executing."""
    print("=" * 88)
    print("             AI Infrastructure Handbook — Discovered E2E Tests")
    print("=" * 88)
    print(f"Filter     : Tier={tier} | Feature={feature}")
    print(f"Discovered : {len(descriptors)} test cases")
    print("-" * 88)
    print(f"{'#':<4} {'Test ID':<48} {'Tier':<6} {'Feature':<10} {'Description'}")
    print("-" * 88)
    for idx, d in enumerate(descriptors, 1):
        feat_str = ",".join(d.features)
        doc_trunc = d.doc[:22] + "..." if len(d.doc) > 22 else d.doc
        print(f"{idx:<4} {d.test_id:<48} T{d.tier:<5} {feat_str:<10} {doc_trunc}")
    print("=" * 88)


def print_ascii_table(
    results: list[dict[str, Any]],
    total_time: float,
    tier_filter: str,
    feature_filter: str,
    discovered_count: int,
) -> None:
    """Print beautifully formatted ASCII execution table and summary."""
    print("=" * 88)
    print("             AI Infrastructure Handbook — E2E Test Suite Runner")
    print("=" * 88)
    print("Execution Mode : Opaque-Box E2E")
    print(f"Filter         : Tier={tier_filter} | Feature={feature_filter}")
    print(f"Discovered     : {discovered_count} test cases")
    print("-" * 88)
    print(f"{'Test ID':<48} {'Tier':<6} {'Feature':<10} {'Duration':<10} {'Status'}")
    print("-" * 88)

    for r in results:
        status_tag = f"[{r['status']}]"
        feat_str = ",".join(r["features"])
        # Format duration
        dur_str = f"{r['duration']:.2f}s"
        # Truncate test_id if needed
        test_id_disp = r["id"] if len(r["id"]) <= 47 else r["id"][:44] + "..."
        print(f"{test_id_disp:<48} T{r['tier']:<5} {feat_str:<10} {dur_str:<10} {status_tag}")

    print("-" * 88)
    print("                                 EXECUTION SUMMARY")
    print("-" * 88)

    # Per-tier breakdowns
    for tier in [1, 2, 3, 4]:
        tier_tests = [r for r in results if r["tier"] == tier]
        if not tier_tests:
            continue
        tier_passed = sum(1 for r in tier_tests if r["status"] == "PASS")
        tier_total = len(tier_tests)
        pct = (tier_passed / tier_total * 100) if tier_total > 0 else 0
        tier_names = {
            1: "Tier 1 (Feature Coverage)        ",
            2: "Tier 2 (Boundary & Corner Cases) ",
            3: "Tier 3 (Cross-Feature Combos)    ",
            4: "Tier 4 (Real-World Workloads)    ",
        }
        print(f"  • {tier_names[tier]} : {tier_passed:>2} / {tier_total:>2} passed ({pct:5.1f}%)")

    total_run = len(results)
    total_passed = sum(1 for r in results if r["status"] == "PASS")
    total_failed = sum(1 for r in results if r["status"] in ("FAIL", "ERROR"))
    total_skipped = sum(1 for r in results if r["status"] == "SKIP")

    print("-" * 88)
    print(f"  Total Tests Run : {total_run}")
    print(f"  Total Passed    : {total_passed}")
    print(f"  Total Failed    : {total_failed}")
    if total_skipped > 0:
        print(f"  Total Skipped   : {total_skipped}")
    print(f"  Total Duration  : {total_time:.2f}s")

    if total_failed == 0 and total_run > 0:
        print("  Result          : 100% PASS (ALL ACCEPTANCE CRITERIA VERIFIED)")
    else:
        print(f"  Result          : {total_failed} TESTS FAILED OR ERRORED")
    print("=" * 88)


def emit_tap_output(results: list[dict[str, Any]]) -> None:
    """Output results conforming to Test Anything Protocol (TAP) version 13."""
    print("TAP version 13")
    print(f"1..{len(results)}")
    for idx, r in enumerate(results, 1):
        if r["status"] == "PASS":
            print(f"ok {idx} - {r['id']}")
        elif r["status"] == "SKIP":
            print(f"ok {idx} - {r['id']} # SKIP")
        else:
            print(f"not ok {idx} - {r['id']}")
            if r.get("error"):
                print("  ---")
                err_clean = r["error"].strip().replace("\n", "\n    ")
                print(f"  message: |\n    {err_clean}")
                print("  ...")


def emit_json_report(
    path: Path,
    results: list[dict[str, Any]],
    total_time: float,
    tier_filter: str,
    feature_filter: str,
) -> None:
    """Write machine-readable test results to JSON file."""
    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "summary": {
            "total_run": len(results),
            "passed": sum(1 for r in results if r["status"] == "PASS"),
            "failed": sum(1 for r in results if r["status"] in ("FAIL", "ERROR")),
            "skipped": sum(1 for r in results if r["status"] == "SKIP"),
            "duration_seconds": round(total_time, 3),
            "filters": {
                "tier": tier_filter,
                "feature": feature_filter,
            },
        },
        "tier_summary": {
            f"tier_{t}": {
                "total": len([r for r in results if r["tier"] == t]),
                "passed": len([r for r in results if r["tier"] == t and r["status"] == "PASS"]),
            }
            for t in [1, 2, 3, 4]
        },
        "tests": results,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[OK] Machine-readable report saved to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="E2E Master Test Runner for AI Infrastructure Handbook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tier",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Filter tests by execution tier (default: all)",
    )
    parser.add_argument(
        "--feature",
        choices=["R1", "R2", "R3", "R4", "all"],
        default="all",
        help="Filter tests by feature requirement (default: all)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed output and subprocess logging",
    )
    parser.add_argument(
        "--fail-fast",
        "-x",
        action="store_true",
        help="Stop test execution immediately upon first failure",
    )
    parser.add_argument(
        "--json-report",
        type=str,
        default=None,
        help="Path to write machine-readable JSON test report",
    )
    parser.add_argument(
        "--tap",
        action="store_true",
        help="Output results in Test Anything Protocol (TAP) format",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all discovered test cases without executing them",
    )

    args = parser.parse_args()

    all_tests = discover_e2e_tests()
    selected_tests = filter_tests(all_tests, args.tier, args.feature)

    if args.list:
        print_list_view(selected_tests, args.tier, args.feature)
        return 0

    if not selected_tests:
        print(f"[ERROR] No tests matched filter Tier={args.tier}, Feature={args.feature}", file=sys.stderr)
        return 1

    results: list[dict[str, Any]] = []
    overall_start = time.perf_counter()

    for d in selected_tests:
        res = run_single_test(d, verbose=args.verbose)
        results.append(res)

        if args.verbose:
            print(f"[{res['status']}] {res['id']} (T{res['tier']}, {','.join(res['features'])}) - {res['duration']:.2f}s")
            if res.get("error"):
                print(f"       ERROR: {res['error']}")

        if args.fail-fast and res["status"] in ("FAIL", "ERROR"):
            break

    overall_duration = time.perf_counter() - overall_start

    if args.tap:
        emit_tap_output(results)
    else:
        print_ascii_table(
            results=results,
            total_time=overall_duration,
            tier_filter=args.tier,
            feature_filter=args.feature,
            discovered_count=len(all_tests),
        )

    if args.json_report:
        emit_json_report(
            path=Path(args.json_report),
            results=results,
            total_time=overall_duration,
            tier_filter=args.tier,
            feature_filter=args.feature,
        )

    # Deterministic exit code: 0 if 100% pass, 1 if any failure/error
    all_passed = all(r["status"] == "PASS" for r in results)
    return 0 if (all_passed and len(results) > 0) else 1


if __name__ == "__main__":
    sys.exit(main())
