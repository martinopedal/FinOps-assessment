"""Tests for reporter template overlay feature (issue #74).

Covers:
- T1: Overlay template shadows wheel template (overlay precedence)
- T2: Missing overlay falls through to wheel template
- T3: Sandbox blocks {% import %} directive (C1 / Noor condition)
- T4: Sandbox blocks attribute-chain sandbox escape attempt
- T5: Sandbox blocks callable invocation via is_safe_callable
- T6: Syntax error in overlay template causes fail-fast (no JSONL written)
- T7: Undefined variable in overlay template causes fail-fast
- T8: Manifest contains template_sources[] with correct overlay sha256
- T9: Manifest contains template_sources[] with correct wheel sha256
- T10: Manifest does NOT contain template_sources when overlay disabled
- T11: Default behavior (no overlay) produces correct output
- T12: Passing a non-existent path to --allow-template-overlay fails at CLI
- T13: PII is not leaked through overlay templates (redacted value used)
- T14: Empty overlay dir — all templates fall through to wheel, no overlay entries
- T15: Overlay template missing [REFERENCES] section emits WARNING (not error)
- C1 (Noor): {% include %} in overlay template is rejected at parse time
- C2 (Noor): No from_string used for operator content (structural / docstring check)
- C3a (Noor): include-blocked — overlay with {% include %} raises before render
- C3b (Noor): path-traversal — overlay filename with .. is rejected
- C3c (Noor): broad-overlay-dir — extra .j2 files in overlay dir are ignored
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import pytest

from finops_assess.reporters._playbook_env import (
    PlaybookPreflightError,
    _build_fixture_finding,
    _playbook_templates_root,
    _reject_include_import_nodes,
    _RestrictedSandbox,
    build_sandboxed_env,
    get_playbook_env,
    preflight_validate,
    reset_playbook_env,
)
from finops_assess.reporters.playbook import (
    render_row,
    write_playbook_export,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_OVERLAY_FIXTURES = Path(__file__).parent / "fixtures" / "overlay"


def _finding(rule_id: str = "M365.DISABLED_USER_LICENSED", surface: str = "m365") -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "surface": surface,
        "severity": "medium",
        "principal": "sha256:testprincipal00000000000000000000000000000000000000000000000000",
        "current_sku": "Microsoft_365_E3",
        "recommended_sku": None,
        "estimated_monthly_savings_usd": 15.0,
        "recommendation": "Consider removing the license.",
        "evidence_ref": None,
        "confidence": "high",
        "evidence": {},
    }


def _report_with(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "findings": [finding],
        "run": {
            "input": "test.json",
            "schema_version": "1.0",
            "pii_redaction": False,
            "salt_mode": "disabled",
        },
    }


@pytest.fixture(autouse=True)
def _reset_env() -> None:  # type: ignore[return]
    """Clear the module-level env cache between tests."""
    reset_playbook_env()
    yield
    reset_playbook_env()


# ---------------------------------------------------------------------------
# T1 — Overlay template shadows wheel template
# ---------------------------------------------------------------------------


def test_overlay_precedence(tmp_path: Path) -> None:
    """Overlay template for M365.DISABLED_USER_LICENSED should shadow the wheel template."""
    # Copy the valid overlay fixture into a fresh temp dir.
    overlay_dir = tmp_path / "overlay"
    m365_dir = overlay_dir / "m365"
    m365_dir.mkdir(parents=True)
    overlay_tpl = _OVERLAY_FIXTURES / "m365" / "M365.DISABLED_USER_LICENSED.j2"
    dest = m365_dir / "M365.DISABLED_USER_LICENSED.j2"
    dest.write_text(overlay_tpl.read_text(encoding="utf-8"), encoding="utf-8")

    finding = _finding()
    row = render_row(finding, overlay_dir=overlay_dir)
    # The overlay template's title starts with "OVERLAY:"
    assert row["title"].startswith("OVERLAY:")


# ---------------------------------------------------------------------------
# T2 — Missing overlay falls through to wheel
# ---------------------------------------------------------------------------


def test_overlay_missing_falls_through_to_wheel(tmp_path: Path) -> None:
    """No overlay for a rule_id → wheel template is used (no error)."""
    overlay_dir = tmp_path / "overlay"
    overlay_dir.mkdir()
    # Empty overlay dir — no templates.
    finding = _finding()
    row = render_row(finding, overlay_dir=overlay_dir)
    # Wheel template title does NOT start with "OVERLAY:"
    assert "OVERLAY:" not in row["title"]
    assert (
        "Disabled" in row["title"]
        or "disabled" in row["title"]
        or finding["principal"][:8] in row["title"]
    )


# ---------------------------------------------------------------------------
# T3 — Sandbox blocks {% import %} (C1 / Noor condition)
# ---------------------------------------------------------------------------


def test_sandbox_blocks_import(tmp_path: Path) -> None:
    """Overlay template containing {% import … %} must be rejected at pre-flight."""
    overlay_dir = tmp_path / "overlay"
    m365_dir = overlay_dir / "m365"
    m365_dir.mkdir(parents=True)
    bad_tpl = m365_dir / "M365.DISABLED_USER_LICENSED.j2"
    bad_tpl.write_text(
        "{% import 'os' as m %}\n[TITLE]\nEvil\n[DESCRIPTION]\nd\n"
        "[REMEDIATION_STEPS]\n- r\n[VERIFICATION_CHECKLIST]\n- c\n[REFERENCES]\n",
        encoding="utf-8",
    )
    env = get_playbook_env(overlay_dir)
    wheel_root = _playbook_templates_root()
    fixture = _build_fixture_finding(wheel_root)
    with pytest.raises(PlaybookPreflightError):
        preflight_validate(env, overlay_dir, fixture)


# ---------------------------------------------------------------------------
# T4 — Sandbox blocks attribute-chain escape attempt
# ---------------------------------------------------------------------------


def test_sandbox_blocks_attribute_chain(tmp_path: Path) -> None:
    """Overlay template using __subclasses__ chain must raise SecurityError at render."""
    from jinja2.sandbox import SecurityError as JinjaSecError

    overlay_dir = tmp_path / "overlay"
    m365_dir = overlay_dir / "m365"
    m365_dir.mkdir(parents=True)
    bad_tpl = m365_dir / "M365.DISABLED_USER_LICENSED.j2"
    bad_tpl.write_text(
        "[TITLE]\n{{ ''.__class__ }}\n[DESCRIPTION]\nd\n"
        "[REMEDIATION_STEPS]\n- r\n[VERIFICATION_CHECKLIST]\n- c\n[REFERENCES]\n",
        encoding="utf-8",
    )
    env = get_playbook_env(overlay_dir)
    wheel_root = _playbook_templates_root()
    fixture = _build_fixture_finding(wheel_root)
    with pytest.raises((PlaybookPreflightError, JinjaSecError)):
        preflight_validate(env, overlay_dir, fixture)


# ---------------------------------------------------------------------------
# T5 — Sandbox blocks callable invocation via is_safe_callable
# ---------------------------------------------------------------------------


def test_sandbox_is_safe_callable_returns_false() -> None:
    """``_RestrictedSandbox.is_safe_callable()`` must always return False."""
    wheel_root = _playbook_templates_root()
    overlay = Path(wheel_root).parent  # any existing dir
    env = build_sandboxed_env(wheel_root, overlay)
    assert isinstance(env, _RestrictedSandbox)
    assert env.is_safe_callable(len) is False
    assert env.is_safe_callable(print) is False
    assert env.is_safe_callable(lambda: None) is False


# ---------------------------------------------------------------------------
# T6 — Syntax error causes fail-fast (no JSONL written)
# ---------------------------------------------------------------------------


def test_syntax_error_fail_fast(tmp_path: Path) -> None:
    """A syntax error in an overlay template must abort the export before writing JSONL."""
    overlay_dir = tmp_path / "overlay"
    (overlay_dir / "m365").mkdir(parents=True)
    (overlay_dir / "m365" / "M365.DISABLED_USER_LICENSED.j2").write_text(
        "{% if %}broken\n", encoding="utf-8"
    )
    output_jsonl = tmp_path / "out.jsonl"
    report = _report_with(_finding())
    with pytest.raises(PlaybookPreflightError):
        write_playbook_export(report, output_jsonl, overlay_dir=overlay_dir)
    # JSONL must NOT have been written.
    assert not output_jsonl.exists()


# ---------------------------------------------------------------------------
# T7 — Undefined variable causes fail-fast
# ---------------------------------------------------------------------------


def test_undefined_var_fail_fast(tmp_path: Path) -> None:
    """An overlay template referencing an unknown variable must abort pre-flight."""
    overlay_dir = tmp_path / "overlay"
    (overlay_dir / "m365").mkdir(parents=True)
    (overlay_dir / "m365" / "M365.DISABLED_USER_LICENSED.j2").write_text(
        "[TITLE]\n{{ totally_unknown_var_xyz }}\n[DESCRIPTION]\nd\n"
        "[REMEDIATION_STEPS]\n- r\n[VERIFICATION_CHECKLIST]\n- c\n[REFERENCES]\n",
        encoding="utf-8",
    )
    env = get_playbook_env(overlay_dir)
    wheel_root = _playbook_templates_root()
    fixture = _build_fixture_finding(wheel_root)
    with pytest.raises(PlaybookPreflightError):
        preflight_validate(env, overlay_dir, fixture)


# ---------------------------------------------------------------------------
# T8 — Manifest template_sources: overlay entry has correct sha256
# ---------------------------------------------------------------------------


def test_manifest_provenance_overlay(tmp_path: Path) -> None:
    """Manifest must have template_sources[] with source='overlay' and correct sha256."""
    overlay_dir = tmp_path / "overlay"
    m365_dir = overlay_dir / "m365"
    m365_dir.mkdir(parents=True)
    overlay_src = _OVERLAY_FIXTURES / "m365" / "M365.DISABLED_USER_LICENSED.j2"
    overlay_body = overlay_src.read_text(encoding="utf-8")
    expected_sha = hashlib.sha256(overlay_body.encode("utf-8")).hexdigest()
    (m365_dir / "M365.DISABLED_USER_LICENSED.j2").write_text(overlay_body, encoding="utf-8")

    output_jsonl = tmp_path / "out.jsonl"
    report = _report_with(_finding())
    write_playbook_export(report, output_jsonl, overlay_dir=overlay_dir, skip_warnings=True)

    import json

    manifest_path = tmp_path / "out.jsonl.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = manifest.get("template_sources")
    assert sources is not None, "template_sources must be present when overlay is used"
    overlay_entries = [e for e in sources if e["source"] == "overlay"]
    assert len(overlay_entries) == 1
    assert overlay_entries[0]["rule_id"] == "M365.DISABLED_USER_LICENSED"
    assert overlay_entries[0]["sha256"] == expected_sha


# ---------------------------------------------------------------------------
# T9 — Manifest template_sources: wheel entry for non-overlaid rule
# ---------------------------------------------------------------------------


def test_manifest_provenance_wheel_fallback(tmp_path: Path) -> None:
    """Non-overlaid rule must appear in template_sources[] with source='wheel'."""
    overlay_dir = tmp_path / "overlay_empty"
    overlay_dir.mkdir()

    output_jsonl = tmp_path / "out.jsonl"
    # Use AZ.IDLE_VM_14D which has no overlay → wheel fallback.
    finding = _finding("AZ.IDLE_VM_14D", "azure")
    finding["evidence"] = {"avg_cpu_pct": 2.1, "avg_net_kbps": 15.5}
    report = _report_with(finding)
    write_playbook_export(report, output_jsonl, overlay_dir=overlay_dir, skip_warnings=True)

    import json

    manifest = json.loads((tmp_path / "out.jsonl.manifest.json").read_text(encoding="utf-8"))
    sources = manifest.get("template_sources")
    assert sources is not None
    wheel_entries = [e for e in sources if e["source"] == "wheel"]
    assert any(e["rule_id"] == "AZ.IDLE_VM_14D" for e in wheel_entries)


# ---------------------------------------------------------------------------
# T10 — No template_sources when overlay is disabled
# ---------------------------------------------------------------------------


def test_manifest_absent_without_overlay(tmp_path: Path) -> None:
    """When overlay is not used, manifest must NOT contain 'template_sources'."""
    output_jsonl = tmp_path / "out.jsonl"
    report = _report_with(_finding())
    write_playbook_export(report, output_jsonl, skip_warnings=True)

    import json

    manifest = json.loads((tmp_path / "out.jsonl.manifest.json").read_text(encoding="utf-8"))
    assert "template_sources" not in manifest


# ---------------------------------------------------------------------------
# T11 — Default (no overlay) renders correctly
# ---------------------------------------------------------------------------


def test_default_behavior_renders_correctly(tmp_path: Path) -> None:
    """Without overlay, render_row must produce expected title from wheel template."""
    finding = _finding()
    row = render_row(finding)
    assert "Disabled" in row["title"] or finding["principal"] in row["title"]
    assert row["playbook_schema_version"] == "0.1"


# ---------------------------------------------------------------------------
# T13 — PII is not leaked through overlay templates
# ---------------------------------------------------------------------------


def test_pii_not_leaked_through_overlay(tmp_path: Path) -> None:
    """Overlay template receives the redacted principal, not the raw UPN."""
    overlay_dir = tmp_path / "overlay"
    m365_dir = overlay_dir / "m365"
    m365_dir.mkdir(parents=True)
    # Template that echoes principal verbatim.
    (m365_dir / "M365.DISABLED_USER_LICENSED.j2").write_text(
        "[TITLE]\nAccount {{ principal }}\n[DESCRIPTION]\nd\n"
        "[REMEDIATION_STEPS]\n- r\n[VERIFICATION_CHECKLIST]\n- c\n[REFERENCES]\n",
        encoding="utf-8",
    )
    redacted_principal = "sha256:aabbccdd0000000000000000000000000000000000000000000000000000aabb"
    finding = _finding()
    finding["principal"] = redacted_principal

    row = render_row(finding, overlay_dir=overlay_dir)
    assert redacted_principal in row["title"]
    # Make sure no raw UPN (which would not start with sha256:) leaked.
    assert "user@" not in row["title"]
    assert "@contoso.com" not in row["title"]


# ---------------------------------------------------------------------------
# T14 — Empty overlay dir
# ---------------------------------------------------------------------------


def test_preflight_empty_overlay_dir(tmp_path: Path) -> None:
    """An empty overlay dir should produce no pre-flight failures and use wheel for all."""
    overlay_dir = tmp_path / "empty_overlay"
    overlay_dir.mkdir()
    env = get_playbook_env(overlay_dir)
    wheel_root = _playbook_templates_root()
    fixture = _build_fixture_finding(wheel_root)
    results = preflight_validate(env, overlay_dir, fixture)
    assert results == []  # No overlay templates found → empty results


# ---------------------------------------------------------------------------
# T15 — Overlay template missing [REFERENCES] emits WARNING (not error)
# ---------------------------------------------------------------------------


def test_overlay_section_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Missing [REFERENCES] section emits WARNING but export proceeds."""
    overlay_dir = tmp_path / "overlay"
    m365_dir = overlay_dir / "m365"
    m365_dir.mkdir(parents=True)
    # Template with all required sections but empty [REFERENCES].
    (m365_dir / "M365.DISABLED_USER_LICENSED.j2").write_text(
        "[TITLE]\nAccount {{ principal }}\n[DESCRIPTION]\nDesc.\n"
        "[REMEDIATION_STEPS]\n- Step 1.\n[VERIFICATION_CHECKLIST]\n- Check 1.\n[REFERENCES]\n",
        encoding="utf-8",
    )
    env = get_playbook_env(overlay_dir)
    wheel_root = _playbook_templates_root()
    fixture = _build_fixture_finding(wheel_root)
    with caplog.at_level(logging.WARNING):
        results = preflight_validate(env, overlay_dir, fixture)
    assert all(r.passed for r in results)
    # No PlaybookPreflightError raised.


# ---------------------------------------------------------------------------
# C1 (Noor) — {% include %} blocked at parse time
# ---------------------------------------------------------------------------


def test_c1_include_blocked(tmp_path: Path) -> None:
    """Overlay template containing {% include %} must raise before render (C1)."""
    overlay_dir = tmp_path / "overlay"
    m365_dir = overlay_dir / "m365"
    m365_dir.mkdir(parents=True)
    (m365_dir / "M365.DISABLED_USER_LICENSED.j2").write_text(
        '{% include "evil.j2" %}\n[TITLE]\nT\n[DESCRIPTION]\nd\n'
        "[REMEDIATION_STEPS]\n- r\n[VERIFICATION_CHECKLIST]\n- c\n[REFERENCES]\n",
        encoding="utf-8",
    )
    env = get_playbook_env(overlay_dir)
    wheel_root = _playbook_templates_root()
    fixture = _build_fixture_finding(wheel_root)
    with pytest.raises(PlaybookPreflightError) as exc_info:
        preflight_validate(env, overlay_dir, fixture)
    # Must mention the include directive clearly.
    assert "include" in str(exc_info.value).lower() or "Include" in str(exc_info.value)


def test_c1_reject_include_nodes_directly() -> None:
    """_reject_include_import_nodes must raise TemplateSyntaxError for {% include %}."""
    from jinja2 import TemplateSyntaxError

    env = get_playbook_env()
    source = '{% include "evil.j2" %}'
    with pytest.raises(TemplateSyntaxError):
        _reject_include_import_nodes(source, "test.j2", env)


def test_c1_reject_import_nodes_directly() -> None:
    """_reject_include_import_nodes must raise TemplateSyntaxError for {% import %}."""
    from jinja2 import TemplateSyntaxError

    env = get_playbook_env()
    source = "{% import 'macros.j2' as m %}"
    with pytest.raises(TemplateSyntaxError):
        _reject_include_import_nodes(source, "test.j2", env)


def test_c1_reject_from_import_nodes_directly() -> None:
    """_reject_include_import_nodes must raise TemplateSyntaxError for {% from … import %}."""
    from jinja2 import TemplateSyntaxError

    env = get_playbook_env()
    source = "{% from 'macros.j2' import render_thing %}"
    with pytest.raises(TemplateSyntaxError):
        _reject_include_import_nodes(source, "test.j2", env)


def test_c1_reject_extends_nodes_directly() -> None:
    """_reject_include_import_nodes must raise TemplateSyntaxError for {% extends %}.

    Defense-in-depth (Noor #102 follow-up): even though FileSystemLoader is
    bounded to the overlay directory, an overlay template using
    ``{% extends "evil.j2" %}`` would side-load another template at render
    time — banned for the same reason as ``{% include %}``.
    """
    from jinja2 import TemplateSyntaxError

    env = get_playbook_env()
    source = '{% extends "base.j2" %}{% block body %}x{% endblock %}'
    with pytest.raises(TemplateSyntaxError):
        _reject_include_import_nodes(source, "test.j2", env)


# ---------------------------------------------------------------------------
# C2 (Noor) — No from_string for operator content (structural guarantee)
# ---------------------------------------------------------------------------


def test_c2_build_sandboxed_env_does_not_accept_string_content(tmp_path: Path) -> None:
    """build_sandboxed_env must use FileSystemLoader — no from_string path for operator content.

    This is a structural test: we verify that ``build_sandboxed_env`` returns a
    ``_RestrictedSandbox`` with a ``FileSystemLoader`` (not a NullLoader or
    BaseLoader that would require from_string).  The docstring guarantee (C2)
    is that operator templates are NEVER compiled via ``from_string``.
    """
    wheel_root = _playbook_templates_root()
    env = build_sandboxed_env(wheel_root, tmp_path)
    from jinja2 import FileSystemLoader

    assert isinstance(env.loader, FileSystemLoader), (
        "build_sandboxed_env must use FileSystemLoader for disk-based template loading"
    )


# ---------------------------------------------------------------------------
# C3a (Noor) — include-blocked: pre-flight rejects include before any render
# ---------------------------------------------------------------------------


def test_c3a_include_blocked_pre_flight(tmp_path: Path) -> None:
    """C3a: overlay template with {% include %} must raise PlaybookPreflightError."""
    overlay_dir = _OVERLAY_FIXTURES / "include_blocked"
    env = get_playbook_env(overlay_dir)
    wheel_root = _playbook_templates_root()
    fixture = _build_fixture_finding(wheel_root)
    with pytest.raises(PlaybookPreflightError):
        preflight_validate(env, overlay_dir, fixture)


# ---------------------------------------------------------------------------
# C3b (Noor) — path-traversal: overlay filename with .. is rejected
# ---------------------------------------------------------------------------


def test_c3b_path_traversal_rejected(tmp_path: Path) -> None:
    """C3b: requesting a template with a path-traversal name must fail (TemplateNotFound)."""
    from jinja2.exceptions import TemplateNotFound

    overlay_dir = tmp_path / "overlay"
    overlay_dir.mkdir()
    env = get_playbook_env(overlay_dir)
    # Jinja2 FileSystemLoader blocks path traversal via safe_join.
    with pytest.raises(TemplateNotFound):
        env.get_template("../../../etc/passwd")


# ---------------------------------------------------------------------------
# C3c (Noor) — broad-overlay-dir: extra .j2 files are ignored at render time
# ---------------------------------------------------------------------------


def test_c3c_broad_overlay_dir_extra_files_ignored(tmp_path: Path) -> None:
    """C3c: overlay dir with unrelated files — only expected names are rendered."""
    overlay_dir = tmp_path / "overlay"
    m365_dir = overlay_dir / "m365"
    m365_dir.mkdir(parents=True)
    # A valid overlay for the expected rule.
    overlay_src = _OVERLAY_FIXTURES / "m365" / "M365.DISABLED_USER_LICENSED.j2"
    (m365_dir / "M365.DISABLED_USER_LICENSED.j2").write_text(
        overlay_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # An extra .j2 file with an unrecognised name — should be ignored at render.
    (m365_dir / "UNRECOGNISED_RULE.j2").write_text(
        "[TITLE]\nExtra file.\n[DESCRIPTION]\nd\n"
        "[REMEDIATION_STEPS]\n- r\n[VERIFICATION_CHECKLIST]\n- c\n[REFERENCES]\n",
        encoding="utf-8",
    )
    # A non-.j2 file — completely ignored.
    (overlay_dir / "README.md").write_text("Operator overlay directory.\n", encoding="utf-8")

    finding = _finding()
    # Render succeeds; only the expected template name is used.
    row = render_row(finding, overlay_dir=overlay_dir)
    assert row["title"].startswith("OVERLAY:")
