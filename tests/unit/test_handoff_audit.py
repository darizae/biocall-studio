"""Static handoff maintenance regression, independent of Qt and scientific services."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("handoff_audit", ROOT / "scripts/verify_handoff.py")
assert _SPEC is not None and _SPEC.loader is not None
handoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(handoff)


def test_current_handoff_is_audited_without_removed_stages():
    assert handoff.REVIEW_CONTRACTS == ("README.md", "SPECTROGRAM_DECISIONS.md")
    assert all(not name.startswith("SPEC_01") for name in handoff.REQUIRED)
    assert all("UX_PARITY_MATRIX.md" not in name for name in handoff.REQUIRED)
    assert all("GIT_DELIVERY.md" not in name for name in handoff.REQUIRED)
    assert handoff.audit_repository(ROOT) == []


def test_broken_live_markdown_link_remains_a_failure(tmp_path):
    document = tmp_path / "docs" / "current.md"
    document.parent.mkdir()
    document.write_text("Refer to [required evidence](missing.md).", encoding="utf-8")
    problems = handoff.audit_markdown_links(tmp_path)
    assert problems == ["Broken Markdown link: docs/current.md → missing.md"]
    (document.parent / "missing.md").write_text("Present.", encoding="utf-8")
    assert handoff.audit_markdown_links(tmp_path) == []


def test_required_current_review_contract_cannot_disappear(tmp_path):
    problems = handoff.audit_repository(tmp_path)
    assert (
        "Missing current Review contract: "
        "docs/specs/review/SPECTROGRAM_DECISIONS.md"
    ) in problems
    assert "Missing current handoff file: docs/agent/ROUTING.md" in problems


def test_private_site_links_are_optional_unless_explicitly_requested(tmp_path):
    document = tmp_path / "docs" / "start.md"
    document.parent.mkdir()
    document.write_text(
        "[private skill](priv/hpc-source-access/SKILL.md)", encoding="utf-8"
    )
    assert handoff.audit_markdown_links(tmp_path) == []
    assert handoff.audit_markdown_links(tmp_path, require_private=True) == [
        "Broken Markdown link: docs/start.md → priv/hpc-source-access/SKILL.md"
    ]


def test_missing_markdown_image_is_a_failure(tmp_path):
    document = tmp_path / "docs" / "readme.md"
    document.parent.mkdir()
    document.write_text("![Native UI proof](images/current.png)", encoding="utf-8")
    assert handoff.audit_markdown_links(tmp_path) == [
        "Broken Markdown link: docs/readme.md → images/current.png"
    ]


def test_native_gate_checks_current_st11_evidence(tmp_path):
    errors = handoff.audit_repository(tmp_path, require_native_ux=True)
    assert (
        "Missing ST-11 native evidence: "
        "docs/design/evidence/st-11-native/review-normal.png"
    ) in errors
    assert all("spec-01-native" not in error for error in errors)


def test_current_native_evidence_is_valid():
    assert not any(
        "ST-11 native" in error or "ST-11 PNG" in error
        for error in handoff.audit_repository(ROOT, require_native_ux=True)
    )
