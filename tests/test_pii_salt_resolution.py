"""Unit tests for _resolve_pii_salt() edge cases."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from click import BadParameter

from finops_assess.cli import _resolve_pii_salt


def test_resolve_salt_per_run_by_default(tmp_path: Path) -> None:
    """When no salt file and no env var, return (None, 'per_run')."""
    salt, mode = _resolve_pii_salt(pii_salt_file=None, no_pii_redaction=False)
    assert salt is None
    assert mode == "per_run"


def test_resolve_salt_file_not_found(tmp_path: Path) -> None:
    """Missing salt file raises BadParameter."""
    missing = tmp_path / "nosuch.txt"
    with pytest.raises(BadParameter, match="Salt file not found"):
        _resolve_pii_salt(pii_salt_file=missing, no_pii_redaction=False)


def test_resolve_salt_file_empty(tmp_path: Path) -> None:
    """Empty salt file (0 bytes) raises BadParameter."""
    empty = tmp_path / "empty.txt"
    empty.touch()
    with pytest.raises(BadParameter, match="Salt file is empty"):
        _resolve_pii_salt(pii_salt_file=empty, no_pii_redaction=False)


def test_resolve_salt_file_whitespace_only(tmp_path: Path) -> None:
    """Salt file containing only whitespace raises BadParameter."""
    whitespace_only = tmp_path / "whitespace.txt"
    whitespace_only.write_text("   \n  \t  \n", encoding="utf-8")
    with pytest.raises(BadParameter, match="contains only whitespace"):
        _resolve_pii_salt(pii_salt_file=whitespace_only, no_pii_redaction=False)


def test_resolve_salt_file_strips_whitespace(tmp_path: Path) -> None:
    """Trailing newlines / whitespace are stripped."""
    salt_file = tmp_path / "salt.txt"
    salt_file.write_text("  my-secret-salt-value-here  \n\n", encoding="utf-8")
    salt, mode = _resolve_pii_salt(pii_salt_file=salt_file, no_pii_redaction=False)
    assert salt == "my-secret-salt-value-here"
    assert mode == "tenant_stable"


def test_resolve_salt_file_too_large(tmp_path: Path) -> None:
    """Salt file > 1 MiB raises BadParameter."""
    huge = tmp_path / "huge.txt"
    huge.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(BadParameter, match="too large"):
        _resolve_pii_salt(pii_salt_file=huge, no_pii_redaction=False)


def test_resolve_env_var_empty_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty FINOPS_PII_SALT env var falls through to per_run."""
    monkeypatch.setenv("FINOPS_PII_SALT", "")
    salt, mode = _resolve_pii_salt(pii_salt_file=None, no_pii_redaction=False)
    assert salt is None
    assert mode == "per_run"


def test_resolve_env_var_whitespace_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FINOPS_PII_SALT with only whitespace falls through to per_run."""
    monkeypatch.setenv("FINOPS_PII_SALT", "   \n  ")
    salt, mode = _resolve_pii_salt(pii_salt_file=None, no_pii_redaction=False)
    assert salt is None
    assert mode == "per_run"


def test_resolve_env_var_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FINOPS_PII_SALT env var is used when set."""
    monkeypatch.setenv("FINOPS_PII_SALT", "env-salt-value")
    salt, mode = _resolve_pii_salt(pii_salt_file=None, no_pii_redaction=False)
    assert salt == "env-salt-value"
    assert mode == "tenant_stable"


def test_resolve_file_overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """File flag takes precedence over env var."""
    monkeypatch.setenv("FINOPS_PII_SALT", "env-salt")
    salt_file = tmp_path / "salt.txt"
    salt_file.write_text("file-salt", encoding="utf-8")
    salt, mode = _resolve_pii_salt(pii_salt_file=salt_file, no_pii_redaction=False)
    assert salt == "file-salt"
    assert mode == "tenant_stable"


def test_no_redaction_ignores_salt_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """--no-pii-redaction + salt file → salt unused, warning logged."""
    salt_file = tmp_path / "salt.txt"
    salt_file.write_text("ignored-salt", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        salt, mode = _resolve_pii_salt(pii_salt_file=salt_file, no_pii_redaction=True)
    assert salt is None
    assert mode == "disabled"
    assert "ignored because --no-pii-redaction is set" in caplog.text


def test_low_entropy_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Salt < 32 chars triggers entropy warning."""
    short_salt = tmp_path / "short.txt"
    short_salt.write_text("abc123", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        salt, mode = _resolve_pii_salt(pii_salt_file=short_salt, no_pii_redaction=False)
    assert salt == "abc123"
    assert mode == "tenant_stable"
    assert "low entropy" in caplog.text
    assert "consider regenerating" in caplog.text


def test_low_entropy_warning_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Salt from env var < 32 chars triggers entropy warning."""
    monkeypatch.setenv("FINOPS_PII_SALT", "short")
    with caplog.at_level(logging.WARNING):
        salt, mode = _resolve_pii_salt(pii_salt_file=None, no_pii_redaction=False)
    assert salt == "short"
    assert mode == "tenant_stable"
    assert "low entropy" in caplog.text


def test_high_entropy_no_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Salt ≥ 32 chars does not trigger entropy warning."""
    good_salt = tmp_path / "good.txt"
    good_salt.write_text("a" * 32, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        salt, mode = _resolve_pii_salt(pii_salt_file=good_salt, no_pii_redaction=False)
    assert salt == "a" * 32
    assert mode == "tenant_stable"
    # No entropy warning, but INFO log about tenant_stable mode
    assert "low entropy" not in caplog.text


def test_world_readable_warning_unix(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """World-readable salt file triggers advisory warning on Unix."""
    salt_file = tmp_path / "worldreadable.txt"
    salt_file.write_text("a" * 32, encoding="utf-8")
    # Make world-readable (Unix-specific; skip on Windows)
    if hasattr(os, "chmod"):
        os.chmod(salt_file, 0o644)
        with caplog.at_level(logging.WARNING):
            _salt, mode = _resolve_pii_salt(pii_salt_file=salt_file, no_pii_redaction=False)
        assert mode == "tenant_stable"
        # Only check warning if we're actually on a platform where st_mode & 0o004 is meaningful
        if salt_file.stat().st_mode & 0o004:
            assert "world-readable" in caplog.text
