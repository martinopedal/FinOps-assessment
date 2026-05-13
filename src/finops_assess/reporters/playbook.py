"""Playbook / ticket reporter for finops-assess (v0.5.0 — issue #61).

Exports findings as a JSONL file (one JSON object per line) alongside a
sidecar ``<output>.manifest.json``.  Each row is a self-contained "playbook
ticket" that can be loaded into ServiceNow, Jira, GitHub Issues, or any
queue system without the consumer needing to understand the raw finding schema.

Row schema contract
-------------------
Every row conforms to ``schemas/playbook_row.schema.json`` and carries:

* ``ticket_key`` — a stable SHA-256 ID for cross-run deduplication.  See
  ``pii_handling.ticket_key_stability_by_surface`` in the manifest for the
  stability guarantee per surface.
* ``finding_revision`` — always ``1`` in v0.5.0; will increment when the
  playbook for a rule is structurally changed in a future release.
* ``title``, ``description``, ``remediation_steps``, ``verification_checklist``,
  ``references`` — rendered from the per-rule Jinja2 template.
* ``template_render_inputs`` — sorted list of context variable names referenced
  by the template (extracted statically via AST walk at env-build time).
* ``adapter_hints`` — nested optional block with sub-dicts for
  ``servicenow``, ``jira``, and ``github`` derived from ``severity``.

Atomic-write contract (Option C)
---------------------------------
The JSONL is written to a tempfile in the **same directory** as the target
output path, then atomically renamed via ``os.replace()`` (uses
``MoveFileEx(MOVEFILE_REPLACE_EXISTING)`` on Windows — safe for same-volume
renames).  The manifest sidecar follows the same pattern.

Manifest presence is the canonical readiness marker.  A JSONL file without
a matching manifest is considered "orphaned" and MUST NOT be consumed.
The ``--cleanup-orphans`` CLI flag removes orphaned JSONL files.

Reader contract (documented here and in ``docs/user-guide.md``)
----------------------------------------------------------------
If ``playbook.jsonl.manifest.json`` is missing OR
``output_artifacts.jsonl_sha256`` does not match the SHA-256 of
``playbook.jsonl`` on disk, the JSONL is orphaned and MUST NOT be consumed.

Template source
---------------
Templates live under ``src/finops_assess/data/playbooks/{surface}/{rule_id}.j2``
and are shipped as package data (``importlib.resources``).  Runtime template
overlay is not supported in v0.5.0 (tracked at #74).

PII warning
-----------
When ``pii_redaction=True`` (default) and findings from non-Azure surfaces
are present, the CLI emits a stderr warning: ``ticket_key`` is computed from
the (possibly redacted) principal, so identical principals across runs will
produce different keys when the redaction salt changes.  Suppress with
``--skip-warnings``.

Reproducibility
---------------
Row order is deterministic: ``(surface, rule_id, ticket_key, evidence_ref or "")``.
Timestamps honour ``SOURCE_DATE_EPOCH`` via
``finops_assess.reporters._determinism.generated_at_iso``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from finops_assess import __version__
from finops_assess.reporters._determinism import generated_at_iso
from finops_assess.reporters._playbook_env import extract_template_vars, get_playbook_env

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAYBOOK_SCHEMA_VERSION = "0.1"
FINDING_REVISION = 1

# Section-delimiter markers used in .j2 template output.
_SEC_TITLE = "[TITLE]"
_SEC_DESC = "[DESCRIPTION]"
_SEC_REMEDIATION = "[REMEDIATION_STEPS]"
_SEC_CHECKLIST = "[VERIFICATION_CHECKLIST]"
_SEC_REFS = "[REFERENCES]"

_ORDERED_SECTIONS = [_SEC_TITLE, _SEC_DESC, _SEC_REMEDIATION, _SEC_CHECKLIST, _SEC_REFS]

# Surfaces where ticket_key is stable (cleartext resource ID is the principal
# and doesn't change with redaction).
_STABLE_SURFACES: frozenset[str] = frozenset({"azure"})

# Severity → adapter-system priority mapping.
_SEVERITY_TO_ADAPTER: dict[str, dict[str, Any]] = {
    "high": {
        "servicenow": {"category": "Cloud Cost Optimisation", "urgency": 1, "priority": 1},
        "jira": {"issuetype": "Task", "priority": "High", "labels": ["finops", "severity:high"]},
        "github": {"labels": ["finops", "severity:high"]},
    },
    "medium": {
        "servicenow": {"category": "Cloud Cost Optimisation", "urgency": 2, "priority": 2},
        "jira": {
            "issuetype": "Task",
            "priority": "Medium",
            "labels": ["finops", "severity:medium"],
        },
        "github": {"labels": ["finops", "severity:medium"]},
    },
    "low": {
        "servicenow": {"category": "Cloud Cost Optimisation", "urgency": 3, "priority": 3},
        "jira": {"issuetype": "Task", "priority": "Low", "labels": ["finops", "severity:low"]},
        "github": {"labels": ["finops", "severity:low"]},
    },
    "info": {
        "servicenow": {"category": "Cloud Cost Optimisation", "urgency": 4, "priority": 4},
        "jira": {"issuetype": "Task", "priority": "Lowest", "labels": ["finops", "severity:info"]},
        "github": {"labels": ["finops", "severity:info"]},
    },
}


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class PlaybookTemplateNotFoundError(Exception):
    """Raised when no .j2 template exists for a given rule_id.

    Fail-fast per OQ-5: if a shipped rule has no template the whole export
    aborts rather than silently emitting partial output.
    """

    def __init__(self, rule_id: str, expected_path: str) -> None:
        self.rule_id = rule_id
        self.expected_path = expected_path
        super().__init__(
            f"Playbook template not found for rule '{rule_id}': expected {expected_path}"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _canonicalise(value: Any) -> Any:
    """Recursively canonicalise an evidence value for deterministic JSON serialisation.

    Mirrors the canonicalise logic in ``focus_aligned.py`` so ticket_key
    digests are stable against re-ordering of evidence dict keys.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [_canonicalise(item) for item in value]
    if isinstance(value, dict):
        return {k: _canonicalise(v) for k, v in sorted(value.items())}
    raise TypeError(f"unhashable evidence value type: {type(value).__name__}")


def _ticket_key(finding: dict[str, Any]) -> str:
    """Compute a per-finding ticket_key as ``sha256:<hex>``.

    Inputs: ``(rule_id, principal, normalized_evidence_json)``.
    For Azure surfaces the principal is the cleartext ARM resource ID, making
    the key stable across runs.  For M365/GitHub/ADO with PII redaction on,
    the principal changes when the salt changes, so the key is ``per_run``.
    """
    rule_id: str = finding.get("rule_id", "")
    principal: str = finding.get("principal", "")
    evidence = finding.get("evidence") or {}
    norm = json.dumps(
        _canonicalise(evidence),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    envelope = json.dumps(
        [rule_id, principal, norm],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(envelope.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _parse_template_output(rendered: str) -> dict[str, Any]:
    """Parse a section-delimited template output into structured fields.

    Expected format::

        [TITLE]
        Single-line title text.

        [DESCRIPTION]
        Multi-line description …

        [REMEDIATION_STEPS]
        1. Step one.
        2. Step two.

        [VERIFICATION_CHECKLIST]
        - Check item one.
        - Check item two.

        [REFERENCES]
        - https://example.com

    Returns a dict with keys ``title``, ``description``, ``remediation_steps``,
    ``verification_checklist``, ``references``.
    """
    sections: dict[str, list[str]] = {s: [] for s in _ORDERED_SECTIONS}
    current: str | None = None

    for line in rendered.splitlines():
        stripped = line.strip()
        if stripped in _ORDERED_SECTIONS:
            current = stripped
            continue
        if current is not None:
            sections[current].append(line)

    def _join(key: str) -> str:
        return "\n".join(sections[key]).strip()

    def _list_lines(key: str) -> list[str]:
        items = []
        for raw in sections[key]:
            text = raw.strip()
            if text:
                items.append(text)
        return items

    return {
        "title": _join(_SEC_TITLE),
        "description": _join(_SEC_DESC),
        "remediation_steps": _list_lines(_SEC_REMEDIATION),
        "verification_checklist": _list_lines(_SEC_CHECKLIST),
        "references": _list_lines(_SEC_REFS),
    }


def _surface_for_rule_id(rule_id: str) -> str:
    """Derive the surface sub-directory from the rule_id prefix."""
    prefix = rule_id.split(".")[0].upper()
    _MAP = {"M365": "m365", "AZ": "azure", "GH": "github", "ADO": "ado"}
    return _MAP.get(prefix, "generic")


def _template_rel_path(rule_id: str) -> str:
    """Return the loader-relative path for the rule's .j2 template."""
    surface_dir = _surface_for_rule_id(rule_id)
    return f"{surface_dir}/{rule_id}.j2"


def _template_source_for_rule(rule_id: str) -> str:
    """Return the raw template source for a rule_id, read from package data.

    Raises ``PlaybookTemplateNotFoundError`` if the template file is absent.
    """
    surface_dir = _surface_for_rule_id(rule_id)
    resource_path = (
        files("finops_assess")
        .joinpath("data")
        .joinpath("playbooks")
        .joinpath(surface_dir)
        .joinpath(f"{rule_id}.j2")
    )
    expected_str = f"data/playbooks/{surface_dir}/{rule_id}.j2"
    try:
        return resource_path.read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError, AttributeError) as exc:
        raise PlaybookTemplateNotFoundError(rule_id, expected_str) from exc


def _adapter_hints(severity: str) -> dict[str, Any]:
    """Build the ``adapter_hints`` sub-dict for a given severity level."""
    return _SEVERITY_TO_ADAPTER.get(severity, _SEVERITY_TO_ADAPTER["info"])


def _sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    """Deterministic row sort: (surface, rule_id, ticket_key, evidence_ref or "")."""
    return (
        row.get("surface", ""),
        row.get("rule_id", ""),
        row.get("ticket_key", ""),
        row.get("evidence_ref") or "",
    )


def _sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file read from disk."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Public render helper
# ---------------------------------------------------------------------------


def render_row(finding: dict[str, Any], adapter_class: str = "generic") -> dict[str, Any]:
    """Render a single finding dict into a playbook row dict.

    The Jinja2 template is loaded from package data via the cached environment.
    Template variables are the merged finding fields (top-level) plus all keys
    from the finding's ``evidence`` dict.

    Raises ``PlaybookTemplateNotFoundError`` if no template exists for
    ``finding["rule_id"]``.
    Raises ``jinja2.UndefinedError`` if the template references a variable not
    present in the merged context (StrictUndefined).
    """
    rule_id: str = finding.get("rule_id", "")
    severity: str = finding.get("severity", "info")

    env = get_playbook_env()
    rel_path = _template_rel_path(rule_id)

    # Fail-fast if template is missing.
    template_source = _template_source_for_rule(rule_id)

    tmpl = env.get_template(rel_path)

    # Build render context: top-level finding fields + flattened evidence.
    evidence = finding.get("evidence") or {}
    ctx: dict[str, Any] = {
        "rule_id": rule_id,
        "surface": finding.get("surface", ""),
        "severity": severity,
        "principal": finding.get("principal", ""),
        "current_sku": finding.get("current_sku"),
        "recommended_sku": finding.get("recommended_sku"),
        "estimated_monthly_savings_usd": finding.get("estimated_monthly_savings_usd"),
        "recommendation": finding.get("recommendation", ""),
        "evidence_ref": finding.get("evidence_ref"),
        "confidence": finding.get("confidence", "high"),
        **evidence,
    }

    rendered = tmpl.render(**ctx)
    parsed = _parse_template_output(rendered)

    # Extract variable names referenced by the template (static AST walk).
    template_vars = extract_template_vars(template_source)

    ticket_k = _ticket_key(finding)
    hints = _adapter_hints(severity)

    row: dict[str, Any] = {
        "playbook_schema_version": PLAYBOOK_SCHEMA_VERSION,
        "ticket_key": ticket_k,
        "finding_revision": FINDING_REVISION,
        "rule_id": rule_id,
        "surface": finding.get("surface", ""),
        "severity": severity,
        "adapter_class": adapter_class,
        "principal": finding.get("principal", ""),
        "current_sku": finding.get("current_sku"),
        "recommended_sku": finding.get("recommended_sku"),
        "estimated_monthly_savings_usd": finding.get("estimated_monthly_savings_usd"),
        "evidence_ref": finding.get("evidence_ref"),
        "template_render_inputs": template_vars,
        "title": parsed["title"],
        "description": parsed["description"],
        "remediation_steps": parsed["remediation_steps"],
        "verification_checklist": parsed["verification_checklist"],
        "references": parsed["references"],
        "adapter_hints": hints,
    }
    return row


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def build_playbook_manifest(
    report: dict[str, Any],
    *,
    row_count: int,
    jsonl_sha256: str,
    jsonl_byte_count: int,
    surfaces: list[str],
    pii_redaction: bool,
) -> dict[str, Any]:
    """Build the sidecar manifest dict for a playbook JSONL export.

    Manifest schema version ``"0.1"`` is additive-only in v0.5.0.
    """
    run = report.get("run", {})
    stability: dict[str, str] = {
        "azure": "stable",
        "ado": "per_run",
        "github": "per_run",
        "m365": "per_run",
    }
    return {
        "playbook_schema_version": PLAYBOOK_SCHEMA_VERSION,
        "tool": {"name": "finops-assess", "version": __version__},
        "generated_at": generated_at_iso(),
        "source_report": {
            "path": run.get("input", ""),
            "schema_version": run.get("schema_version", "1.0"),
            "pii_redaction": run.get("pii_redaction", pii_redaction),
        },
        "row_count": row_count,
        "output_artifacts": {
            "jsonl_sha256": jsonl_sha256,
            "jsonl_byte_count": jsonl_byte_count,
        },
        "pii_handling": {
            "mode": "salted_hash" if pii_redaction else "cleartext",
            "ticket_key_stability_by_surface": stability,
            "note": (
                "ticket_key is per_run for M365/GitHub/ADO when PII redaction is on "
                "because the principal is hashed with a per-run salt. "
                "Engine-level stable-salt deferred to #73."
            ),
        },
        "surfaces": sorted(surfaces),
        "sort_key": "(surface, rule_id, ticket_key, evidence_ref)",
        "templates_source": "importlib.resources:finops_assess.data.playbooks",
    }


# ---------------------------------------------------------------------------
# Orphan detection
# ---------------------------------------------------------------------------


def find_orphaned_jsonl(directory: Path) -> list[Path]:
    """Return all ``.jsonl`` files in ``directory`` that lack a matching manifest.

    A ``.jsonl`` file is considered orphaned when:
    - ``<name>.manifest.json`` does not exist alongside it, OR
    - ``output_artifacts.jsonl_sha256`` in the manifest does not match the
      SHA-256 of the ``.jsonl`` file on disk.

    This is a best-effort scan: manifest files that are not valid JSON are
    treated as absent (the sibling JSONL is reported as orphaned).
    """
    orphans: list[Path] = []
    for jsonl_path in sorted(directory.glob("*.jsonl")):
        manifest_path = jsonl_path.parent / (jsonl_path.name + ".manifest.json")
        if not manifest_path.exists():
            orphans.append(jsonl_path)
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected_sha = manifest.get("output_artifacts", {}).get("jsonl_sha256", "")
            actual_sha = _sha256_file(jsonl_path)
            if actual_sha != expected_sha:
                orphans.append(jsonl_path)
        except Exception:
            orphans.append(jsonl_path)
    return orphans


# ---------------------------------------------------------------------------
# Primary writer
# ---------------------------------------------------------------------------


def write_playbook_export(
    report: dict[str, Any],
    output_jsonl: Path,
    *,
    skip_warnings: bool = False,
) -> tuple[Path, Path]:
    """Write a playbook JSONL export and sidecar manifest using atomic-write Option C.

    Returns ``(jsonl_path, manifest_path)`` — both as resolved ``Path`` objects.

    Atomic-write contract (Option C)
    ---------------------------------
    1. JSONL rows are written to a tempfile in the **same directory** as
       ``output_jsonl``.
    2. ``os.fsync()`` is called on the tempfile before rename (skipped on
       Windows because Windows does not guarantee parent-dir fsync, but
       the file content is still flushed to the OS buffer).
    3. ``os.replace()`` atomically renames the tempfile to ``output_jsonl``.
    4. SHA-256 and byte count are computed from the **on-disk** JSONL (not
       from in-memory state) to ensure the manifest attestation is accurate.
    5. The manifest is written to a separate tempfile and atomically renamed.

    Manifest presence is the canonical readiness marker.  If this function
    raises after step 3 but before step 5, the JSONL exists but the manifest
    does not — that JSONL is treated as orphaned and MUST NOT be consumed.
    """
    output_jsonl = Path(output_jsonl)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    all_findings: list[dict[str, Any]] = report.get("findings", [])
    pii_redaction: bool = report.get("run", {}).get("pii_redaction", True)

    # PII warning: non-Azure findings with redaction on yield per_run ticket_keys.
    non_azure = [f for f in all_findings if f.get("surface") != "azure"]
    if non_azure and pii_redaction and not skip_warnings:
        click_echo = _get_click_echo()
        click_echo(
            "Warning: ticket_key for M365/GitHub/ADO findings is per_run when PII redaction "
            "is on (principal is hashed with a per-run salt). Cross-run deduplication will not "
            "work for these surfaces unless the same salt is reused. "
            "Use --skip-warnings to suppress. Tracked at #73.",
            file=sys.stderr,
        )

    # Render rows.
    rows: list[dict[str, Any]] = []
    rule_id_to_adapter: dict[str, str] = _build_adapter_class_map()
    for finding in all_findings:
        rule_id = finding.get("rule_id", "")
        adapter_class = rule_id_to_adapter.get(rule_id, "generic")
        try:
            row = render_row(finding, adapter_class=adapter_class)
            rows.append(row)
        except PlaybookTemplateNotFoundError:
            raise
        except Exception as exc:
            _log.warning("Failed to render playbook row for %s: %s", rule_id, exc)
            raise

    sorted_rows = sorted(rows, key=_sort_key)
    surfaces = sorted({r.get("surface", "") for r in sorted_rows if r.get("surface")})

    # --- Atomic write: JSONL ---
    tmp_jsonl: str | None = None
    try:
        fd, tmp_jsonl = tempfile.mkstemp(
            dir=output_jsonl.parent,
            prefix=f".tmp-{output_jsonl.name}-",
            suffix=".jsonl",
        )
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            for row in sorted_rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")
            # fsync inside the write-mode context so the OS buffer is flushed
            # before rename. On Linux/macOS this is required; on Windows it is
            # best-effort (MoveFileEx is not guaranteed to be durable on
            # power-loss without a parent-dir sync, but this is an honest
            # constraint documented in the plan §5.1).
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_jsonl, output_jsonl)
        tmp_jsonl = None  # Rename succeeded; no cleanup needed.
    except Exception:
        if tmp_jsonl and os.path.exists(tmp_jsonl):
            os.unlink(tmp_jsonl)
        raise

    # Compute SHA-256 and byte count from the on-disk JSONL (not from memory).
    jsonl_sha256 = _sha256_file(output_jsonl)
    jsonl_byte_count = output_jsonl.stat().st_size

    # Build manifest.
    manifest = build_playbook_manifest(
        report,
        row_count=len(sorted_rows),
        jsonl_sha256=jsonl_sha256,
        jsonl_byte_count=jsonl_byte_count,
        surfaces=surfaces,
        pii_redaction=pii_redaction,
    )
    manifest_path = output_jsonl.parent / (output_jsonl.name + ".manifest.json")

    # --- Atomic write: manifest ---
    tmp_manifest: str | None = None
    try:
        fd2, tmp_manifest = tempfile.mkstemp(
            dir=manifest_path.parent,
            prefix=f".tmp-{manifest_path.name}-",
            suffix=".json",
        )
        payload = json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False)
        with os.fdopen(fd2, "w", encoding="utf-8", newline="") as fh:
            fh.write(payload + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_manifest, manifest_path)
        tmp_manifest = None
    except Exception:
        if tmp_manifest and os.path.exists(tmp_manifest):
            os.unlink(tmp_manifest)
        raise

    return output_jsonl, manifest_path


# ---------------------------------------------------------------------------
# Internal helpers called lazily to avoid circular imports
# ---------------------------------------------------------------------------


def _get_click_echo() -> Any:
    """Return ``click.echo`` lazily so the library module stays import-clean."""
    import click

    return click.echo


def _build_adapter_class_map() -> dict[str, str]:
    """Load rules and return a mapping of rule_id → adapter_class.

    Falls back to ``"generic"`` for any rule not found.
    """
    try:
        from finops_assess.rules import load_rules

        rules = load_rules()
        return {r.id: r.adapter_class for r in rules}
    except Exception:
        return {}
