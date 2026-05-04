"""finops-assess CLI entry point."""

from __future__ import annotations

import click

from finops_assess import __version__
from finops_assess.catalog import load_catalog
from finops_assess.rules import load_personas, load_rules


@click.group()
@click.version_option(__version__, prog_name="finops-assess")
def main() -> None:
    """Read-only FinOps assessment for the Microsoft ecosystem."""


@main.command()
def validate() -> None:
    """Validate the on-disk catalog, personas, and rules."""
    catalog = load_catalog()
    personas = load_personas()
    rules = load_rules()
    click.echo(f"OK — catalog: {len(catalog)} SKUs, personas: {len(personas)}, rules: {len(rules)}")


@main.command()
def info() -> None:
    """Print version + scope summary."""
    click.echo(f"finops-assess {__version__}")
    click.echo("Surfaces: M365 · Azure · GitHub · Azure DevOps")
    click.echo("Mode: read-only (M0 scaffold; collectors arrive in M2+)")


if __name__ == "__main__":  # pragma: no cover
    main()
