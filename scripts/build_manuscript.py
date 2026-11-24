#!/usr/bin/env python3
"""Compile the unabridged AI Infrastructure & Platform Engineering Handbook.

Merges README.md and chapters/00 through 06 without truncating a single line,
prepends an auto-generated Master Table of Contents with GitHub-compatible
unique anchors, appends Curated Resources (Modules 0-6) and the 5-DoD
Verification Matrix, and validates code fences, LaTeX equations, Mermaid syntax,
and anchor/file links on the final artifact.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_FILE = REPO_ROOT / "dist" / "FULL_MANUSCRIPT.md"

SOURCE_FILES: list[tuple[str, str]] = [
    ("README", "README.md"),
    ("CH00", "chapters/00-onboarding-and-setup.md"),
    ("CH01", "chapters/01-foundations-containers-iac.md"),
    ("CH02", "chapters/02-kubernetes-gpu-orchestration.md"),
    ("CH03", "chapters/03-vllm-serving-optimization.md"),
    ("CH04", "chapters/04-ai-gateway-governance.md"),
    ("CH05", "chapters/05-observability-autoscaling-sre.md"),
    ("CH06", "chapters/06-capstone-siamshield-ai.md"),
]

# Official Module 0 tooling and environment references observed in Chapter 00-02 & SPEC.
MODULE_0_RESOURCES: list[tuple[str, list[str], str]] = [
    (
        "Astral `uv` Installer & Docker Integration Docs",
        [
            "https://astral.sh/uv/install.sh",
            "https://docs.astral.sh/uv/guides/integration/docker/",
        ],
        "Installation & multi-stage Python dependency caching (~1 ชั่วโมง | ฟรี)",
    ),
    (
        "Docker Engine & Official Multi-Stage Docs",
        [
            "https://get.docker.com",
            "https://docs.docker.com/build/building/multi-stage/",
        ],
        "Docker Engine setup, non-root runtime, read-only rootfs (~1.5 ชั่วโมง | ฟรี)",
    ),
    (
        "Kubernetes Toolchain (`kubectl`, `kind`, `helm`)",
        [
            "https://kubernetes.io/docs/home/",
            "https://kind.sigs.k8s.io/docs/",
            "https://helm.sh/docs/",
        ],
        "Local 16GB Kind cluster configuration with shared `HF_HOME` extraMounts (~2 ชั่วโมง | ฟรี)",
    ),
    (
        "OpenTofu & Trivy Security Scanner",
        [
            "https://opentofu.org/docs/",
            "https://trivy.dev/docs/",
        ],
        "Declarative IaC installation and container vulnerability scanning (~1.5 ชั่วโมง | ฟรี)",
    ),
    (
        "Handbook Canonical Naming & Guardrails SSOT",
        ["../SPEC_AND_STYLE_GUIDE.md"],
        "Canonical ports, model IDs, `HF_HOME=/cache/huggingface`, V1 metrics (~30 นาที | Local)",
    ),
    (
        "Portability Guide & Optional AWS Cloud Track (`g6.xlarge` Spot L4)",
        ["../PORTABILITY_AND_QUICKSTART.md", "../labs/optional-cloud-aws/README.md"],
        "DevContainer/Compose setup, Offline Reading, AWS S3/ECR/Budgets & Dead-Man's Switch (~1.5 ชั่วโมง | ฟรี / \\$10–\\$30 AWS)",
    ),
    (
        "2025–2026 Core Books (*AI Systems Performance Engineering*, *AI Engineering*, *Ultra-Scale Playbook*, *How to Scale Your Model*)",
        [
            "https://huggingface.co/spaces/nanotron/ultrascale-playbook",
            "https://jax-ml.github.io/scaling-book/",
        ],
        "Roofline math, Disaggregated PD, Tensor/Pipeline Parallelism & Eval Gates (เสริมเชิงลึก)",
    ),
]

FIVE_DOD_ROWS: list[tuple[str, str, str, str, str]] = [
    (
        "**DoD #1**",
        "Architecture Design Document & VRAM/FinOps Math",
        "[`labs/m6-capstone-siamshield/docs/design-doc.md`](../labs/m6-capstone-siamshield/docs/design-doc.md)<br>[`labs/m1-foundations/docs/adr-001...`](../labs/m1-foundations/docs/adr-001-container-and-model-cache-strategy.md), [`adr-002`](../labs/m2-k8s-gpu/docs/adr-002-gpu-sharing-and-scheduling.md), [`adr-003`](../labs/m4-gateway/docs/adr-003-ai-gateway-and-inference-routing.md), [`adr-004`](../labs/m5-observability-sre/docs/adr-004-observability-and-keda-autoscaling.md)",
        "คำนวณ GQA KV-Cache (`299,593 tokens`), Break-even (`27.1%` Utilization), และมี Trade-off Matrix $\\ge 2$ ทางเลือกครบ 3 การตัดสินใจหลัก",
        "20 คะแนน",
    ),
    (
        "**DoD #2**",
        "Reproducible IaC, K8s Helm, Gateway & Two-Tier Stack",
        "[`labs/m6-capstone-siamshield/Makefile`](../labs/m6-capstone-siamshield/Makefile)<br>[`labs/m6-capstone-siamshield/k8s/siamshield-platform.yaml`](../labs/m6-capstone-siamshield/k8s/siamshield-platform.yaml)<br>[`labs/m6-capstone-siamshield/src/siamshield_simulator.py`](../labs/m6-capstone-siamshield/src/siamshield_simulator.py)",
        "Non-root (`UID 10001`), `readOnlyRootFilesystem: true`, `HF_HOME=/cache/huggingface` PVC, `terminationGracePeriodSeconds: 60`, PDPA `<THAI_ID_REDACTED>`, แยกโควตา Two-Tier (`HTTP 429` บน `tier-batch`)",
        "25 คะแนน",
    ),
    (
        "**DoD #3**",
        "Measurable Latency & Throughput Optimization Report",
        "[`labs/m6-capstone-siamshield/reports/capstone-optimization-report.md`](../labs/m6-capstone-siamshield/reports/capstone-optimization-report.md)<br>[`labs/m3-vllm/optimization-report-template.md`](../labs/m3-vllm/optimization-report-template.md)",
        "แสดง Before vs After (`AWQ 4-bit` + APC + Chunked Prefill + EPP): `tier-realtime` TTFT p95 `< 800 ms`, ITL p95 `< 30 ms`, KV-Cache pool `4.76x` พร้อมอธิบายกลไกฮาร์ดแวร์",
        "20 คะแนน",
    ),
    (
        "**DoD #4**",
        "SRE Observability, KEDA Autoscaling, Runbook & Blameless Postmortem",
        "[`labs/m6-capstone-siamshield/docs/runbooks/capstone-runbook.md`](../labs/m6-capstone-siamshield/docs/runbooks/capstone-runbook.md)<br>[`labs/m6-capstone-siamshield/docs/postmortems/capstone-postmortem.md`](../labs/m6-capstone-siamshield/docs/postmortems/capstone-postmortem.md)<br>[`labs/m5-observability-sre/grafana-dashboard-vllm-v1.json`](../labs/m5-observability-sre/grafana-dashboard-vllm-v1.json)",
        "ใช้ Canonical `vLLM` V1 Metrics (`prefix_cache_hits_total`, `kv_cache_usage_perc`, `num_requests_waiting`), Dual-Trigger KEDA (`AverageValue` + `Value`), 4-Step Runbook และ 5 Whys Postmortem",
        "20 คะแนน",
    ),
    (
        "**DoD #5**",
        "Mid-Level Architecture Defense & Interview Readiness",
        "[`labs/m6-capstone-siamshield/docs/interview-defense-guide.md`](../labs/m6-capstone-siamshield/docs/interview-defense-guide.md)<br>คำถาม-เฉลย 29 ข้อในบทที่ 1–6",
        "ตอบคำถามเชิงสถาปัตยกรรม การคำนวณคอขวด (`Prefill` Compute vs `Decode` Memory Bandwidth), FinOps Break-even และการกู้คืนระบบได้อย่างมีเหตุผลเชิงวิศวกรรม",
        "15 คะแนน",
    ),
]

FENCE_OPEN_RE = re.compile(r"^[ ]*(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
INLINE_MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
HTML_TAG_RE = re.compile(r"<[A-Za-z/!][^>]*>")


@dataclass(frozen=True)
class HeadingEntry:
    """Represents a parsed Markdown heading outside code fences."""

    line_idx: int
    level: int
    raw_title: str
    display_title: str
    slug: str


def strip_inline_markdown(text: str) -> str:
    """Format heading text for ToC labels while preserving backticks and escaped '\\$'."""
    cleaned = INLINE_MD_LINK_RE.sub(lambda m: m.group(1), text)
    return cleaned.strip()


def github_slug(heading_text: str) -> str:
    """Generate a GitHub Flavored Markdown compatible heading anchor slug."""
    plain = INLINE_MD_LINK_RE.sub(lambda m: m.group(1), heading_text)
    plain = plain.replace("\\$", "$").replace("`", "")
    plain = re.sub(r"(\*\*|__)", "", plain).strip().lower()

    kept: list[str] = []
    for ch in plain:
        if ch in (" ", "-", "_"):
            kept.append("-" if ch == " " else ch)
            continue
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "M", "N"):
            kept.append(ch)
    return "".join(kept)


def iter_non_fenced_lines(lines: list[str]):
    """Yield (0-based line index, line, in_fence, fence_lang) tracking CommonMark fences."""
    fence_char: str | None = None
    fence_len = 0
    fence_lang = ""

    for idx, raw_line in enumerate(lines):
        if fence_char is None:
            match = FENCE_OPEN_RE.match(raw_line)
            if match:
                marker, info = match.group(1), match.group(2).strip()
                # Backtick info strings cannot contain another backtick.
                if not (marker[0] == "`" and "`" in info):
                    fence_char = marker[0]
                    fence_len = len(marker)
                    fence_lang = info.lower()
                    yield idx, raw_line, True, fence_lang
                    continue
            yield idx, raw_line, False, ""
        else:
            stripped = raw_line.strip()
            if (
                len(stripped) >= fence_len
                and set(stripped) == {fence_char}
            ):
                yield idx, raw_line, True, fence_lang
                fence_char = None
                fence_len = 0
                fence_lang = ""
            else:
                yield idx, raw_line, True, fence_lang


def parse_headings(lines: list[str]) -> list[HeadingEntry]:
    """Parse all non-fenced ATX headings and assign globally unique GitHub slugs."""
    seen_counts: dict[str, int] = {}
    entries: list[HeadingEntry] = []

    for idx, line, in_fence, _ in iter_non_fenced_lines(lines):
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        raw_title = match.group(2).strip()
        base_slug = github_slug(raw_title)
        count = seen_counts.get(base_slug, 0)
        seen_counts[base_slug] = count + 1
        unique_slug = base_slug if count == 0 else f"{base_slug}-{count}"
        entries.append(
            HeadingEntry(
                line_idx=idx,
                level=level,
                raw_title=raw_title,
                display_title=strip_inline_markdown(raw_title),
                slug=unique_slug,
            )
        )
    return entries


def strip_inline_code_spans(line: str) -> str:
    """Replace inline code spans with harmless spaces for link/math scanning."""
    out: list[str] = []
    pos = 0
    n = len(line)
    while pos < n:
        if line[pos] == "`":
            tick_end = pos
            while tick_end < n and line[tick_end] == "`":
                tick_end += 1
            tick_len = tick_end - pos
            close_idx = line.find("`" * tick_len, tick_end)
            if close_idx != -1:
                # Ensure exact backtick run match on closing delimiter.
                end_after = close_idx + tick_len
                while close_idx != -1 and (
                    (end_after < n and line[end_after] == "`")
                    or (close_idx > 0 and line[close_idx - 1] == "`")
                ):
                    close_idx = line.find("`" * tick_len, close_idx + 1)
                    end_after = close_idx + tick_len
                if close_idx != -1:
                    out.append(" " * (close_idx + tick_len - pos))
                    pos = close_idx + tick_len
                    continue
        out.append(line[pos])
        pos += 1
    return "".join(out)


def rewrite_source_links(
    source_id: str,
    lines: list[str],
    local_to_global_slug: dict[str, str],
) -> list[str]:
    """Normalize relative links for dist/FULL_MANUSCRIPT.md without altering line counts."""
    rewritten: list[str] = []
    for _, line, in_fence, _ in iter_non_fenced_lines(lines):
        if in_fence:
            rewritten.append(line)
            continue

        # Match links on a shadow copy where inline code spans become equal-length spaces.
        shadow = strip_inline_code_spans(line)
        edits: list[tuple[int, int, str]] = []
        for match in MD_LINK_RE.finditer(shadow):
            t_start, t_end = match.span(2)
            target = line[t_start:t_end]
            new_target = target
            if source_id == "README" and target.startswith("./"):
                new_target = f"../{target[2:]}"
            elif target.startswith("#") and len(target) > 1:
                local_slug = target[1:]
                new_target = f"#{local_to_global_slug.get(local_slug, local_slug)}"
            if new_target != target:
                edits.append((t_start, t_end, new_target))

        if not edits:
            rewritten.append(line)
            continue

        parts: list[str] = []
        cursor = 0
        for s_idx, e_idx, replacement in edits:
            parts.append(line[cursor:s_idx])
            parts.append(replacement)
            cursor = e_idx
        parts.append(line[cursor:])
        rewritten.append("".join(parts))
    return rewritten


def extract_curated_resources(lines: list[str]) -> list[str]:
    """Extract the Curated Verified Resources bullet/numbered lines from a chapter."""
    collecting = False
    captured: list[str] = []
    for line in lines:
        if re.match(r"^###\s+.*Curated Verified Resources", line):
            collecting = True
            continue
        if collecting:
            if line.startswith("## ") or line.startswith("### "):
                break
            captured.append(line.rstrip())

    while captured and not captured[-1]:
        captured.pop()
    return captured


def build_appendix_sections(sources: dict[str, list[str]]) -> list[str]:
    """Build Appendices A (Curated Resources M0-M6) and B (5 DoDs Verification Matrix)."""
    out: list[str] = [
        "# ภาคผนวก (Appendices)",
        "",
        "## ภาคผนวก ก: รวมแหล่งเรียนรู้อ้างอิงฉบับสมบูรณ์ครบทุก Module (Consolidated Curated Verified Resources: M0–M6)",
        "",
        "ตารางและรายการด้านล่างรวบรวมเอกสารทางการ (Official Documentation), งานวิจัยต้นฉบับ (Whitepapers), และสเปกมาตรฐานที่ใช้จริงในทุกบทตั้งแต่ Module 0 ถึง Module 6 เพื่อให้ใช้อ้างอิงและทบทวนเชิงลึกหลังเรียนจบ:",
        "",
        "### Module 0: สภาพแวดล้อมวิศวกรรม, 16GB RAM Strategy & มาตรฐานกลาง (`chapters/00`)",
    ]

    for idx, (title, urls, note) in enumerate(MODULE_0_RESOURCES, start=1):
        url_str = " และ ".join(f"[{u}]({u})" if u.startswith("http") else f"[`{u}`]({u})" for u in urls)
        out.append(f"{idx}. **{title}**  ")
        out.append(f"   - URL / Reference: {url_str}  ")
        out.append(f"   - ส่วนที่ควรอ่าน: {note}")

    module_titles = [
        ("CH01", "### Module 1: Production Containers, Bounded Concurrency, CI/CD & IaC (`chapters/01`)"),
        ("CH02", "### Module 2: Kubernetes GPU Orchestration, VRAM Sizing & Time-Slicing (`chapters/02`)"),
        ("CH03", "### Module 3: `vLLM` V1 Internals, Prefix Caching, Quantization & FinOps (`chapters/03`)"),
        ("CH04", "### Module 4: `LiteLLM` AI Gateway, K8s `InferencePool`/`EPP` & PDPA Guardrails (`chapters/04`)"),
        ("CH05", "### Module 5: NVIDIA DCGM Telemetry, Prometheus, KEDA & SRE Drills (`chapters/05`)"),
        ("CH06", "### Module 6: Capstone — `Project SiamShield AI` (`chapters/06`)"),
    ]
    for src_id, heading in module_titles:
        out.append("")
        out.append(heading)
        resources = extract_curated_resources(sources[src_id])
        out.extend(resources)

    out.extend(
        [
            "",
            "---",
            "",
            "## ภาคผนวก ข: ตารางตรวจสอบเกณฑ์ผ่าน 5 Definitions of Done (5 DoDs Traceability & Verification Matrix)",
            "",
            "ผู้เรียนระดับ **Mid-Level Ready** ต้องสร้างผลงานครบทั้ง **5 Portfolio DoDs**, ทำคะแนนประเมิน Capstone ไม่ต่ำกว่า **85 / 100 คะแนน**, และไม่ติดเงื่อนไขตกอัตโนมัติ (Mandatory Auto-Fail):",
            "",
            "| รหัส DoD | สมรรถนะหลัก (Core Competency) | ไฟล์ผลงานส่งมอบ (Canonical Artifact Paths) | เกณฑ์ตรวจสอบเชิงประจักษ์ (Auditable Criteria) | น้ำหนักคะแนน |",
            "| :---: | :--- | :--- | :--- | :---: |",
        ]
    )
    for dod_id, comp, paths, criteria, pts in FIVE_DOD_ROWS:
        out.append(f"| {dod_id} | {comp} | {paths} | {criteria} | {pts} |")

    out.extend(
        [
            "| **รวมทั้งหมด** | **End-to-End AI Platform Readiness** | **ครบทั้ง 6 Labs (`labs/m1`–`labs/m6`)** | **รันชุดสคริปต์ตรวจสอบอัตโนมัติครบทุก Module ผ่าน 100%** | **100 คะแนน** |",
            "",
            "### ชุดคำสั่งตรวจสอบอัตโนมัติครบทั้งเล่ม (Complete Verification Suite Commands)",
            "",
            "```bash",
            "# 0. ตรวจสอบเครื่องมือและหน่วยความจำบนเครื่อง Local 16GB RAM",
            "bash scripts/check-env.sh",
            "",
            "# 1. Milestone Gate 1 (Weeks 1-4): Foundations + Kubernetes GPU Orchestration",
            "bash labs/m1-foundations/verify_m1.sh",
            "bash labs/m2-k8s-gpu/verify_m2.sh",
            "",
            "# 2. Milestone Gate 2 (Weeks 5-8): vLLM V1 Serving + LiteLLM/EPP AI Gateway",
            "bash labs/m3-vllm/verify_m3.sh",
            "bash labs/m4-gateway/verify_m4.sh",
            "",
            "# 3. Milestone Gate 3 (Weeks 9-12): Observability/KEDA SRE + Project SiamShield AI Capstone",
            "bash labs/m5-observability-sre/verify_m5.sh",
            "bash labs/m6-capstone-siamshield/verify_capstone.sh",
            "```",
            "",
            "### เงื่อนไขตกอัตโนมัติที่ต้องเฝ้าระวังเป็นพิเศษ (Mandatory Auto-Fail Checklist)",
            "- [ ] **PDPA Leakage Check:** ห้ามมีเลขบัตรประชาชนไทย 13 หลัก หรือเบอร์โทรศัพท์หลุดรอดโดยไม่ถูกแปลงเป็น `<THAI_ID_REDACTED>` และ `<THAI_PHONE_REDACTED>`",
            "- [ ] **Model Cache Volume Check:** ทุก Deployment ของโมเดลใน M2, M3, M5, M6 ต้องผูก `HF_HOME=/cache/huggingface` เข้ากับ `hf-model-cache-pvc`",
            "- [ ] **Canonical `vLLM` V1 Metrics Check:** ห้ามใช้ชื่อ Metric เก่าของ V0 (`vllm:gpu_cache_usage_perc`) หรือทำ KEDA Autoscale จาก CPU/Memory เพียงอย่างเดียว",
        ]
    )
    return out


def build_toc_block(headings: list[HeadingEntry], toc_marker: str, max_level: int = 3) -> list[str]:
    """Render nested Markdown Table of Contents from parsed document headings."""
    toc_lines: list[str] = []
    started = False
    prev_depth = 0
    for entry in headings:
        if entry.raw_title == toc_marker:
            started = True
            continue
        if not started or entry.level > max_level:
            continue
        target_depth = entry.level - 1
        depth = min(target_depth, prev_depth + 1)
        prev_depth = depth
        indent = "  " * depth
        toc_lines.append(f"{indent}- [{entry.display_title}](#{entry.slug})")
    return toc_lines


def validate_code_fences(lines: list[str]) -> list[str]:
    """Validate that all code fences open and close cleanly without unclosed blocks."""
    errors: list[str] = []
    fence_char: str | None = None
    fence_len = 0
    fence_open_line = 0
    fence_lang = ""

    for line_no, raw_line in enumerate(lines, start=1):
        if fence_char is None:
            match = FENCE_OPEN_RE.match(raw_line)
            if match:
                marker, info = match.group(1), match.group(2).strip()
                if not (marker[0] == "`" and "`" in info):
                    fence_char = marker[0]
                    fence_len = len(marker)
                    fence_open_line = line_no
                    fence_lang = info.lower()
        else:
            stripped = raw_line.strip()
            if fence_lang == "mermaid" and HTML_TAG_RE.search(raw_line):
                errors.append(
                    f"Line {line_no}: Forbidden HTML tag inside Mermaid block: {stripped}"
                )
            if len(stripped) >= fence_len and set(stripped) == {fence_char}:
                fence_char = None
                fence_len = 0
                fence_open_line = 0
                fence_lang = ""

    if fence_char is not None:
        errors.append(
            f"Unclosed code fence ({fence_char * fence_len} {fence_lang}) opened at line {fence_open_line}"
        )
    return errors


def validate_latex_equations(lines: list[str]) -> list[str]:
    """Validate display math ($$...$$) and inline math ($...$) outside code spans/fences."""
    errors: list[str] = []
    display_open_line: int | None = None

    for idx, raw_line, in_fence, _ in iter_non_fenced_lines(lines):
        if in_fence:
            continue
        line_no = idx + 1
        sanitized = strip_inline_code_spans(raw_line)
        # Mask escaped \$ before tokenizing math delimiters.
        sanitized = sanitized.replace("\\$", "  ")

        pos = 0
        n = len(sanitized)
        line_inline_dollars: list[int] = []
        while pos < n:
            if sanitized[pos : pos + 2] == "$$":
                if display_open_line is None:
                    display_open_line = line_no
                else:
                    display_open_line = None
                pos += 2
            elif sanitized[pos] == "$":
                if display_open_line is None:
                    line_inline_dollars.append(pos)
                pos += 1
            else:
                pos += 1

        if len(line_inline_dollars) % 2 != 0:
            errors.append(
                f"Line {line_no}: Unclosed inline LaTeX '$' delimiter in: {raw_line.strip()[:100]}"
            )

    if display_open_line is not None:
        errors.append(f"Unclosed display LaTeX block '$$' opened at line {display_open_line}")
    return errors


def validate_links_and_completeness(
    final_lines: list[str],
    source_line_counts: dict[str, int],
) -> tuple[list[str], dict[str, int]]:
    """Verify ToC/heading anchors, relative file paths from dist/, and zero truncation."""
    errors: list[str] = []
    headings = parse_headings(final_lines)
    valid_slugs = {h.slug for h in headings}

    anchor_count = 0
    rel_link_count = 0
    for idx, raw_line, in_fence, _ in iter_non_fenced_lines(final_lines):
        if in_fence:
            continue
        clean = strip_inline_code_spans(raw_line)
        for match in MD_LINK_RE.finditer(clean):
            target = match.group(2).strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if target.startswith("#"):
                anchor_count += 1
                slug = target[1:]
                if slug and slug not in valid_slugs:
                    errors.append(f"Line {idx + 1}: Broken internal anchor '#{slug}'")
                continue
            rel_link_count += 1
            resolved = (DIST_FILE.parent / target.split("#")[0]).resolve()
            if not resolved.exists():
                errors.append(f"Line {idx + 1}: Broken relative file link '{target}'")

    raw_text = "\n".join(final_lines)
    expected_embedded = sum(source_line_counts.values())
    if len(final_lines) <= expected_embedded:
        errors.append(
            f"Final manuscript has fewer lines ({len(final_lines)}) than sources ({expected_embedded})"
        )

    stats = {
        "total_lines": len(final_lines),
        "embedded_source_lines": expected_embedded,
        "headings_indexed": len(headings),
        "toc_entries": sum(1 for h in headings if h.level <= 3) - 1,
        "anchors_checked": anchor_count,
        "relative_links_checked": rel_link_count,
        "raw_bytes": len(raw_text.encode("utf-8")),
    }
    return errors, stats


def build_manuscript(check_only: bool = False) -> int:
    """Assemble dist/FULL_MANUSCRIPT.md and run all structural integrity validators."""
    raw_sources: dict[str, list[str]] = {}
    source_counts: dict[str, int] = {}

    for src_id, rel_path in SOURCE_FILES:
        file_path = REPO_ROOT / rel_path
        if not file_path.is_file():
            print(f"[ERROR] Missing required source file: {file_path}", file=sys.stderr)
            return 1
        lines = file_path.read_text(encoding="utf-8").splitlines()
        raw_sources[src_id] = lines
        source_counts[src_id] = len(lines)

    toc_heading_title = "สารบัญหลักของหนังสือ (Master Table of Contents)"
    preamble = [
        "# AI Infrastructure & Platform Engineering Handbook (Complete Unabridged Edition)",
        "",
        "> **ฉบับรวมเล่มสมบูรณ์ (Zero-Truncation Master Manuscript):** รวบรวมเนื้อหาทั้งหมดจาก `README.md`, `บทที่ 0–6`, พร้อม **สารบัญหลักอัตโนมัติ (ToC)** และ **ภาคผนวกครบทั้ง Modules 0–6 และ 5 DoDs Verification Matrix**",
        "",
        f"## {toc_heading_title}",
        "",
        "{{TOC_PLACEHOLDER}}",
        "",
        "---",
        "",
    ]

    part_banners = {
        "README": "> **ส่วนนำ — ภาพรวมแผนการเรียนรู้และสถาปัตยกรรมหลัก** ([`README.md`](../README.md))",
        "CH00": "> **ส่วนที่ 0 — Onboarding & 16GB RAM Setup** ([`chapters/00-onboarding-and-setup.md`](../chapters/00-onboarding-and-setup.md))",
        "CH01": "> **ส่วนที่ 1 — Module 1: Containers, Bounded Queue & IaC** ([`chapters/01-foundations-containers-iac.md`](../chapters/01-foundations-containers-iac.md))",
        "CH02": "> **ส่วนที่ 2 — Module 2: Kubernetes & GPU Orchestration** ([`chapters/02-kubernetes-gpu-orchestration.md`](../chapters/02-kubernetes-gpu-orchestration.md))",
        "CH03": "> **ส่วนที่ 3 — Module 3: Model Serving & `vLLM` Optimization** ([`chapters/03-vllm-serving-optimization.md`](../chapters/03-vllm-serving-optimization.md))",
        "CH04": "> **ส่วนที่ 4 — Module 4: AI Gateway, EPP & Multi-Tenant Governance** ([`chapters/04-ai-gateway-governance.md`](../chapters/04-ai-gateway-governance.md))",
        "CH05": "> **ส่วนที่ 5 — Module 5: Observability, KEDA Autoscaling & SRE** ([`chapters/05-observability-autoscaling-sre.md`](../chapters/05-observability-autoscaling-sre.md))",
        "CH06": "> **ส่วนที่ 6 — Module 6: Capstone `Project SiamShield AI`** ([`chapters/06-capstone-siamshield-ai.md`](../chapters/06-capstone-siamshield-ai.md))",
    }

    # Pass 1: Assemble provisional body with untouched chapters to compute global unique slugs.
    provisional_lines: list[str] = list(preamble)
    chapter_slices: dict[str, tuple[int, int]] = {}
    for src_id, _ in SOURCE_FILES:
        provisional_lines.append(part_banners[src_id])
        provisional_lines.append("")
        start_idx = len(provisional_lines)
        provisional_lines.extend(raw_sources[src_id])
        end_idx = len(provisional_lines)
        chapter_slices[src_id] = (start_idx, end_idx)
        provisional_lines.extend(["", "---", ""])

    appendix_lines = build_appendix_sections(raw_sources)
    provisional_lines.extend(appendix_lines)

    global_headings = parse_headings(provisional_lines)
    by_line = {h.line_idx: h for h in global_headings}

    # Map each chapter's standalone local heading slug -> global disambiguated slug.
    final_body: list[str] = list(preamble)
    for src_id, _ in SOURCE_FILES:
        local_headings = parse_headings(raw_sources[src_id])
        start_idx, _ = chapter_slices[src_id]
        local_to_global: dict[str, str] = {}
        for lh in local_headings:
            global_entry = by_line[start_idx + lh.line_idx]
            local_to_global[lh.slug] = global_entry.slug

        rewritten = rewrite_source_links(src_id, raw_sources[src_id], local_to_global)
        # Verify exact 1:1 line count preservation per source file.
        assert len(rewritten) == source_counts[src_id], (
            f"Line count mismatch in {src_id}: {len(rewritten)} != {source_counts[src_id]}"
        )
        final_body.append(part_banners[src_id])
        final_body.append("")
        final_body.extend(rewritten)
        final_body.extend(["", "---", ""])

    final_body.extend(appendix_lines)

    # Pass 2: Inject auto-generated ToC at top without shifting heading slug disambiguation.
    placeholder_idx = final_body.index("{{TOC_PLACEHOLDER}}")
    toc_lines = build_toc_block(parse_headings(final_body), toc_heading_title, max_level=3)
    final_lines = final_body[:placeholder_idx] + toc_lines + final_body[placeholder_idx + 1 :]

    errors: list[str] = []
    errors.extend(validate_code_fences(final_lines))
    errors.extend(validate_latex_equations(final_lines))
    link_errors, stats = validate_links_and_completeness(final_lines, source_counts)
    errors.extend(link_errors)

    # Also verify each source file closes all fences & math internally (no bleed across files).
    for src_id, src_lines in raw_sources.items():
        for err in validate_code_fences(src_lines):
            errors.append(f"[{src_id}] {err}")
        for err in validate_latex_equations(src_lines):
            errors.append(f"[{src_id}] {err}")

    if errors:
        print(f"[FAIL] Manuscript validation failed with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    if not check_only:
        DIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        DIST_FILE.write_text("\n".join(final_lines) + "\n", encoding="utf-8")

    # Re-read the written artifact to verify disk output matches validation state.
    if DIST_FILE.is_file():
        disk_lines = DIST_FILE.read_text(encoding="utf-8").splitlines()
        disk_errors = validate_code_fences(disk_lines) + validate_latex_equations(disk_lines)
        disk_link_errors, disk_stats = validate_links_and_completeness(disk_lines, source_counts)
        if disk_errors or disk_link_errors:
            print("[FAIL] On-disk validation failed!", file=sys.stderr)
            for err in disk_errors + disk_link_errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        stats = disk_stats

    mode = "CHECK" if check_only else "BUILD + VERIFY"
    print(f"[PASS] {mode} succeeded: {DIST_FILE}")
    print(f"  - Embedded source lines : {stats['embedded_source_lines']} (0 truncated)")
    print(f"  - Total output lines    : {stats['total_lines']} ({stats['raw_bytes']:,} bytes)")
    print(f"  - Auto ToC entries      : {stats['toc_entries']} (of {stats['headings_indexed']} total headings)")
    print(f"  - Code fences           : 0 unclosed (CommonMark + Mermaid clean)")
    print(f"  - LaTeX equations       : 0 unclosed ($$ display & $ inline clean)")
    print(
        f"  - Links checked         : {stats['anchors_checked']} anchors, "
        f"{stats['relative_links_checked']} relative paths (0 broken)"
    )
    return 0


def main() -> int:
    """CLI entrypoint for building and validating dist/FULL_MANUSCRIPT.md."""
    parser = argparse.ArgumentParser(
        description="Build and validate the unabridged handbook at dist/FULL_MANUSCRIPT.md."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate assembly and on-disk FULL_MANUSCRIPT.md without rewriting it.",
    )
    args = parser.parse_args()
    return build_manuscript(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
