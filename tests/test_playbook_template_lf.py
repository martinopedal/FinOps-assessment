"""Regression test: every shipped .j2 template has LF-only line endings.

Without the `src/finops_assess/data/playbooks/**/*.j2 text eol=lf` rule in
.gitattributes, a Windows clone with core.autocrlf=true rewrites templates
to CRLF. Jinja2 then includes the \\r in rendered strings, json.dumps escapes
them as \\\\r in the JSONL, and golden-fixture byte comparisons fail on
Windows-hosted runners only.

This test catches that regression at the byte level.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Collect all shipped .j2 template paths
# ---------------------------------------------------------------------------


def _shipped_templates() -> list[Path]:
    """Return Path objects for every .j2 file under data/playbooks/."""
    root = files("finops_assess").joinpath("data").joinpath("playbooks")
    # ``root`` is a Traversable; cast to Path for glob support.
    root_path = Path(str(root))
    return sorted(root_path.rglob("*.j2"))


_ALL_TEMPLATES = _shipped_templates()
assert _ALL_TEMPLATES, "No .j2 templates found — package data may not be installed correctly"


# ---------------------------------------------------------------------------
# Test 1 — parametrize over every shipped template
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tmpl_path", _ALL_TEMPLATES, ids=[p.name for p in _ALL_TEMPLATES])
def test_template_is_lf_only(tmpl_path: Path) -> None:
    """Every shipped .j2 template must contain no CRLF or bare CR bytes."""
    raw = tmpl_path.read_bytes()
    assert b"\r\n" not in raw, (
        f"{tmpl_path.name}: CRLF line endings detected. "
        "Ensure .gitattributes `src/finops_assess/data/playbooks/**/*.j2 text eol=lf` "
        "is honoured on this platform."
    )
    assert b"\r" not in raw, f"{tmpl_path.name}: bare CR detected."


# ---------------------------------------------------------------------------
# Test 2 — templates are UTF-8 decodable without BOM
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tmpl_path", _ALL_TEMPLATES, ids=[p.name for p in _ALL_TEMPLATES])
def test_template_is_utf8_no_bom(tmpl_path: Path) -> None:
    """Every shipped .j2 template must be UTF-8 without a BOM."""
    raw = tmpl_path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{tmpl_path.name}: BOM found"
    raw.decode("utf-8")  # raises UnicodeDecodeError if not valid UTF-8


# ---------------------------------------------------------------------------
# Test 3 — expected template count matches shipped rule count
# ---------------------------------------------------------------------------


def test_template_count_matches_rules() -> None:
    """There must be exactly one .j2 template per shipped rule."""
    from finops_assess.rules import load_rules

    rules = load_rules()
    template_names = {p.stem for p in _ALL_TEMPLATES}  # strip .j2
    rule_ids = {r.id for r in rules}

    missing = rule_ids - template_names
    extra = template_names - rule_ids

    assert not missing, f"Rules with no template: {sorted(missing)}"
    assert not extra, f"Templates with no matching rule: {sorted(extra)}"
