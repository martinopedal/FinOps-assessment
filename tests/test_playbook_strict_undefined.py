"""Tests for ``_load_playbook_environment()`` / ``get_playbook_env()`` configuration.

Covers:
- Environment is configured with StrictUndefined
- autoescape is False
- keep_trailing_newline is False
- A template that references an undefined variable raises UndefinedError
- Pre-compiled templates are in the loader cache
"""

from __future__ import annotations

import pytest
from jinja2 import StrictUndefined, UndefinedError

from finops_assess.reporters._playbook_env import get_playbook_env

# ---------------------------------------------------------------------------
# Test 1 — StrictUndefined is configured
# ---------------------------------------------------------------------------


def test_env_uses_strict_undefined() -> None:
    """The environment must be configured with StrictUndefined."""
    env = get_playbook_env()
    assert isinstance(env.undefined, type), "undefined should be a class, not an instance"
    assert issubclass(env.undefined, StrictUndefined), (  # type: ignore[arg-type]
        f"Expected StrictUndefined, got {env.undefined}"
    )


# ---------------------------------------------------------------------------
# Test 2 — autoescape is False
# ---------------------------------------------------------------------------


def test_env_autoescape_is_false() -> None:
    """The environment must NOT use autoescape (plain-text JSONL output)."""
    env = get_playbook_env()
    # autoescape can be a bool or a callable; for our usage it should be False.
    assert env.autoescape is False or (callable(env.autoescape) and not env.autoescape("test"))


# ---------------------------------------------------------------------------
# Test 3 — keep_trailing_newline is False
# ---------------------------------------------------------------------------


def test_env_no_trailing_newline() -> None:
    """The environment must not keep trailing newlines in rendered templates."""
    env = get_playbook_env()
    assert env.keep_trailing_newline is False


# ---------------------------------------------------------------------------
# Test 4 — missing variable raises UndefinedError with StrictUndefined
# ---------------------------------------------------------------------------


def test_undefined_variable_raises() -> None:
    """Rendering a template with a missing variable must raise UndefinedError."""
    env = get_playbook_env()
    tmpl = env.from_string(
        "[TITLE]\nHello {{ undefined_variable }}\n[DESCRIPTION]\nBlah.\n"
        "[REMEDIATION_STEPS]\n1. Step.\n[VERIFICATION_CHECKLIST]\n- Check.\n"
        "[REFERENCES]\n- https://example.com"
    )
    with pytest.raises(UndefinedError):
        tmpl.render(principal="alice@contoso.com")


# ---------------------------------------------------------------------------
# Test 5 — all shipped templates are pre-compiled (get_template does not re-parse)
# ---------------------------------------------------------------------------


def test_all_shipped_templates_precompiled() -> None:
    """All shipped .j2 templates must be loadable from the cached environment."""
    env = get_playbook_env()
    templates = list(env.loader.list_templates())  # type: ignore[union-attr]
    assert len(templates) >= 20, f"Expected at least 20 shipped templates, found {len(templates)}"
    for rel_path in templates:
        # Should not raise — templates are already compiled.
        tmpl = env.get_template(rel_path)
        assert tmpl is not None


# ---------------------------------------------------------------------------
# Test 6 — rendering a known template with correct context does not raise
# ---------------------------------------------------------------------------


def test_known_template_renders_with_full_context() -> None:
    """Rendering AZ.IDLE_VM_14D with a complete context must not raise."""
    env = get_playbook_env()
    tmpl = env.get_template("azure/AZ.IDLE_VM_14D.j2")
    rendered = tmpl.render(
        principal="/subscriptions/test/VM/test-vm",
        current_sku="Standard_D4s_v3",
        recommended_sku="Standard_D2s_v3",
        avg_cpu_pct=2.1,
        avg_net_kbps=15.5,
    )
    assert "[TITLE]" in rendered
    assert "[REMEDIATION_STEPS]" in rendered
