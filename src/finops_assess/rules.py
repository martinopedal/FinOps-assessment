"""Persona + savings-rule loader and validator.

Run as a module to validate on-disk personas and rules:

    python -m finops_assess.rules validate
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from finops_assess.models import Persona, Rule

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
PERSONAS_FILE = DATA_ROOT / "personas.yaml"
RULES_DIR = DATA_ROOT / "rules"


def load_personas(path: Path | None = None) -> list[Persona]:
    path = path or PERSONAS_FILE
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or []
    if not isinstance(doc, list):
        raise ValueError(f"{path}: top-level YAML must be a list")
    seen: set[str] = set()
    personas: list[Persona] = []
    for raw in doc:
        p = Persona.model_validate(raw)
        if p.id in seen:
            raise ValueError(f"{path}: duplicate persona id '{p.id}'")
        seen.add(p.id)
        personas.append(p)
    return personas


def load_rules(root: Path | None = None) -> list[Rule]:
    root = root or RULES_DIR
    rules: list[Rule] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or []
        if not isinstance(doc, list):
            raise ValueError(f"{path}: top-level YAML must be a list")
        for raw in doc:
            r = Rule.model_validate(raw)
            if r.id in seen:
                raise ValueError(f"{path}: duplicate rule id '{r.id}'")
            seen.add(r.id)
            rules.append(r)
    return rules


def _cli(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] != "validate":
        print("usage: python -m finops_assess.rules validate", file=sys.stderr)
        return 2
    try:
        personas = load_personas()
        rules = load_rules()
    except (ValidationError, ValueError, yaml.YAMLError, FileNotFoundError) as exc:
        print(f"rules/personas validation FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"personas OK: {len(personas)} loaded")
    print(f"rules OK: {len(rules)} loaded")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli(sys.argv))
