"""Smoke tests for the CLI."""

from __future__ import annotations

from click.testing import CliRunner

from finops_assess.cli import main


def test_info() -> None:
    result = CliRunner().invoke(main, ["info"])
    assert result.exit_code == 0
    assert "finops-assess" in result.output


def test_validate() -> None:
    result = CliRunner().invoke(main, ["validate"])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output
