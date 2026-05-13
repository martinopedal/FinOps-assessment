"""Jinja2 environment factory for the playbook reporter.

A single ``Environment`` is built lazily on the first call to
``get_playbook_env()`` and cached at module level for the rest of the
process lifetime.  The environment is configured with:

* ``undefined=StrictUndefined`` — a template that references a variable not
  present in the render context raises ``jinja2.UndefinedError`` immediately
  instead of silently emitting an empty string.
* ``autoescape=False`` — playbook templates render plain text / Markdown
  lines that are later stored as JSON strings.  HTML auto-escaping would
  corrupt the output.
* ``keep_trailing_newline=False`` — normalises the rendered string so the
  caller does not have to strip a spurious trailing newline before embedding
  the value in a JSONL row.

Every ``.j2`` template shipped under ``src/finops_assess/data/playbooks/``
is pre-compiled the first time the environment is built (loaded from
``importlib.resources``).  Pre-compilation catches syntax errors at the
point of first use rather than at render time, and amortises the parse
cost across multiple findings that share the same rule.

Lazy initialisation note (Noor PR #78 AMENDMENT #3): pre-compilation does
NOT run at module-import time, only on the first ``get_playbook_env()``
call.  This keeps ``import finops_assess.reporters.playbook`` cheap (no
filesystem I/O at import) and avoids surprising side-effects when the
module is imported for symbol introspection (e.g. by mypy or pdoc).

Overlay mode (v0.6.0 / issue #74)
----------------------------------
When ``overlay_dir`` is passed to ``get_playbook_env()``, a
``_RestrictedSandbox`` is built instead of a plain ``Environment``.
The sandbox uses ``FileSystemLoader([overlay_dir, wheel_root])`` so
overlay templates shadow wheel templates with first-match precedence.
Operator-supplied templates are never rendered via ``from_string()`` —
they are loaded exclusively from disk (C2 guarantee documented in
``build_sandboxed_env``).

Usage::

    from finops_assess.reporters._playbook_env import get_playbook_env
    env = get_playbook_env()
    tmpl = env.get_template("m365/M365.UNUSED_LICENSE_30D.j2")
    rendered = tmpl.render(principal="alice@contoso.com", ...)

    # Overlay mode:
    from pathlib import Path
    env = get_playbook_env(overlay_dir=Path("/path/to/operator/overlays"))
"""

from __future__ import annotations

import logging
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateSyntaxError, nodes
from jinja2.exceptions import SecurityError as JinjaSandboxSecurityError
from jinja2.sandbox import SandboxedEnvironment

if TYPE_CHECKING:
    pass

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception types
# ---------------------------------------------------------------------------


class PlaybookPreflightError(Exception):
    """Raised when one or more overlay templates fail pre-flight validation.

    Pre-flight validation runs before any JSONL rows are written.  A failure
    here means the entire export is aborted — no partial output is produced.
    """


# ---------------------------------------------------------------------------
# Pre-flight result record
# ---------------------------------------------------------------------------


class PreflightResult(NamedTuple):
    """Outcome of pre-flight validation for a single overlay template."""

    template_rel: str
    passed: bool
    error: str | None


# ---------------------------------------------------------------------------
# Restricted sandbox (C1/C2/C3 security controls)
# ---------------------------------------------------------------------------


class _RestrictedSandbox(SandboxedEnvironment):
    """``SandboxedEnvironment`` with tightened restrictions for operator overlay templates.

    Restrictions beyond the default ``SandboxedEnvironment``:

    1. ``is_safe_callable()`` always returns ``False`` — blocks ALL callable
       invocation from template expressions (e.g. ``{{ lipsum() }}``).
    2. ``call()`` raises ``SecurityError`` for any callable (enforces rule 1).
    3. ``{% include %}`` and ``{% import %}`` are rejected at parse time by
       ``_reject_include_import_nodes()`` before the template is cached.

    **C2 from_string guarantee:** This environment is NEVER constructed by
    calling ``Environment.from_string(operator_input)``.  Operator templates
    are loaded exclusively from disk via ``FileSystemLoader(overlay_dir)``,
    referenced by filename.  The public entry point ``build_sandboxed_env()``
    enforces this — it only accepts a ``Path`` (overlay directory) and builds
    a ``FileSystemLoader``; it never exposes a ``from_string`` code path for
    operator-supplied content.
    """

    def is_safe_callable(self, obj: object) -> bool:
        """Return ``False`` for all objects — block arbitrary callable invocation."""
        return False

    def call(
        __self,
        __context: Any,
        __obj: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Raise ``SecurityError`` for any callable invocation from overlay templates."""
        if not __self.is_safe_callable(__obj):
            raise JinjaSandboxSecurityError(
                f"Calling {__obj!r} is not permitted in sandboxed templates."
            )
        return super().call(__context, __obj, *args, **kwargs)


# ---------------------------------------------------------------------------
# Helper: reject {% include %} / {% import %} at AST level (C1)
# ---------------------------------------------------------------------------

_INCLUDE_IMPORT_NODE_TYPES = (nodes.Include, nodes.FromImport, nodes.Import)


def _reject_include_import_nodes(source: str, name: str, env: Environment) -> None:
    """Parse ``source`` and raise ``TemplateSyntaxError`` if it contains include/import.

    C1 control: overlay templates must not load other templates via
    ``{% include %}``, ``{% import %}``, or ``{% from … import %}``.
    These directives could be used to load arbitrary files from the
    overlay directory (or, if the loader were mis-configured, from the
    filesystem at large).

    This function is called during pre-flight validation for every overlay
    template, before the template is entered into the Jinja2 cache.

    Args:
        source: Raw ``.j2`` template source text.
        name: Template name (used in error messages only).
        env: The environment to use for ``env.parse()``.

    Raises:
        TemplateSyntaxError: If the template contains any ``Include``,
            ``Import``, or ``FromImport`` AST nodes.
    """
    parsed = env.parse(source)
    for node in parsed.find_all(_INCLUDE_IMPORT_NODE_TYPES):
        node_type = type(node).__name__
        raise TemplateSyntaxError(
            f"Overlay template '{name}' contains a forbidden '{node_type}' directive. "
            "{% include %} and {% import %} are not permitted in overlay templates.",
            lineno=getattr(node, "lineno", 0),
            name=name,
        )


# ---------------------------------------------------------------------------
# Module-level caches — built once per process.
# ---------------------------------------------------------------------------

_ENV: Environment | None = None
_OVERLAY_ENVS: dict[Path, _RestrictedSandbox] = {}

# ---------------------------------------------------------------------------
# Wheel root resolver
# ---------------------------------------------------------------------------


def _playbook_templates_root() -> str:
    """Return the filesystem path to the bundled playbooks directory.

    Uses ``importlib.resources`` so the path resolves correctly whether the
    package is installed as a wheel or used from a source checkout.
    """
    # ``files()`` returns a Traversable; ``.joinpath()`` navigates into it.
    # ``str()`` gives the concrete filesystem path that FileSystemLoader needs.
    pkg_data = files("finops_assess").joinpath("data").joinpath("playbooks")
    return str(pkg_data)


# ---------------------------------------------------------------------------
# Fixture finding for pre-flight renders
# ---------------------------------------------------------------------------

# Standard context keys always present in every render_row() call.
_STANDARD_FIXTURE_KEYS: dict[str, Any] = {
    "rule_id": "SURFACE.FIXTURE_RULE",
    "surface": "fixture",
    "severity": "medium",
    "principal": "sha256:fixture_principal_placeholder_000000000000000000000000000000",
    "current_sku": "FIXTURE_SKU",
    "recommended_sku": "FIXTURE_SKU_LOWER",
    "estimated_monthly_savings_usd": 0.0,
    "recommendation": "Fixture recommendation text.",
    "evidence_ref": None,
    "confidence": "high",
}


def _build_fixture_finding(wheel_root: str) -> dict[str, Any]:
    """Build a synthetic finding dict for pre-flight template renders.

    Scans every shipped wheel template to collect all ``Name`` nodes
    (variable references).  Returns a flat dict containing every referenced
    variable name mapped to a placeholder value.  Overlay templates that
    reference variables outside this superset will fail pre-flight with
    ``StrictUndefined`` — this is intentional (they must use only context
    keys that the engine actually provides).

    The fixture dict is rebuilt each time a new sandboxed environment is
    constructed (i.e. once per unique overlay_dir per process).  This is
    cheap — typically < 30 templates, sub-millisecond scan.
    """
    wheel_path = Path(wheel_root)
    # Use a fresh minimal env to parse wheel templates without side-effects.
    scan_env = Environment(undefined=StrictUndefined, autoescape=False)
    all_names: set[str] = set()
    for j2_path in wheel_path.rglob("*.j2"):
        source = j2_path.read_text(encoding="utf-8")
        try:
            parsed = scan_env.parse(source)
            for node in parsed.find_all(nodes.Name):
                all_names.add(node.name)
        except Exception:  # pragma: no cover — wheel templates must be valid
            pass

    # Merge: start with standard keys (proper values), add evidence keys as placeholders.
    fixture: dict[str, Any] = dict(_STANDARD_FIXTURE_KEYS)
    for name in all_names:
        if name not in fixture:
            fixture[name] = "fixture_value"
    return fixture


# ---------------------------------------------------------------------------
# Plain environment builder (v0.5.0 path)
# ---------------------------------------------------------------------------


def _build_env() -> Environment:
    """Construct and pre-compile the plain ``Environment`` (wheel-only path).

    Pre-compilation: iterate every ``.j2`` resource under
    ``data/playbooks/`` and call ``Environment.parse()`` on each source.
    Any syntax error is raised immediately (fail-fast), preventing a
    per-finding ``TemplateSyntaxError`` at runtime that would be harder to
    debug.
    """
    root = _playbook_templates_root()
    env = Environment(
        loader=FileSystemLoader(root, encoding="utf-8"),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=False,
    )

    # Pre-compile every shipped template.
    playbooks_root = Path(root)
    for j2_path in sorted(playbooks_root.rglob("*.j2")):
        # Template name relative to the loader root (uses forward slashes on
        # all platforms — FileSystemLoader normalises the separator).
        rel = j2_path.relative_to(playbooks_root).as_posix()
        source = j2_path.read_text(encoding="utf-8")
        try:
            env.parse(source)  # syntax-check only; get_template() caches the compiled code
        except Exception as exc:
            _log.warning("Playbook template syntax error in %s: %s", rel, exc)
            raise
        # Trigger actual compilation + caching inside Jinja2.
        env.get_template(rel)
        _log.debug("Pre-compiled playbook template: %s", rel)

    return env


# ---------------------------------------------------------------------------
# Sandboxed environment builder (overlay path — v0.6.0)
# ---------------------------------------------------------------------------


def build_sandboxed_env(wheel_root: str, overlay_root: Path) -> _RestrictedSandbox:
    """Build a ``_RestrictedSandbox`` for overlay template rendering.

    The search path is ``[overlay_root, wheel_root]``: overlay templates take
    precedence; missing overlays fall through to the wheel.

    **C2 guarantee:** This function is the ONLY entry point for constructing
    a sandboxed environment for operator-supplied content.  It accepts a
    ``Path`` (overlay directory) and builds a ``FileSystemLoader``; it never
    calls ``Environment.from_string(operator_input)`` or any other method that
    would compile operator content without filesystem provenance.

    Configuration:

    * ``loader`` — ``FileSystemLoader([overlay_root, wheel_root])``, UTF-8.
    * ``undefined`` — ``StrictUndefined`` (raise on any missing variable).
    * ``autoescape`` — ``False`` (plain text output, same as wheel env).
    * ``keep_trailing_newline`` — ``False``.
    * ``auto_reload`` — ``False`` (freeze templates after pre-flight; prevents
      TOCTOU between pre-flight and render).

    Args:
        wheel_root: Filesystem path to ``data/playbooks/`` inside the wheel.
        overlay_root: Operator-supplied directory containing overlay ``.j2``
            files.  Must exist; validated by the CLI before this is called.

    Returns:
        A configured and pre-compiled ``_RestrictedSandbox``.
    """
    env = _RestrictedSandbox(
        loader=FileSystemLoader([str(overlay_root), wheel_root], encoding="utf-8"),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=False,
        auto_reload=False,
    )

    # Syntax-check all WHEEL templates (trusted) using env.parse on the raw source.
    # We do NOT call env.get_template() here because the FileSystemLoader search path
    # has overlay_root first — get_template would load the overlay template (if present)
    # instead of the wheel template. Wheel syntax is verified here; overlay syntax is
    # verified separately in preflight_validate().
    wheel_path = Path(wheel_root)
    for j2_path in sorted(wheel_path.rglob("*.j2")):
        rel = j2_path.relative_to(wheel_path).as_posix()
        source = j2_path.read_text(encoding="utf-8")
        try:
            env.parse(source)
        except Exception as exc:
            _log.warning("Wheel template syntax error in %s: %s", rel, exc)
            raise
        _log.debug("Syntax-checked wheel template (sandbox): %s", rel)

    return env


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------


def preflight_validate(
    env: Environment,
    overlay_dir: Path,
    fixture_finding: dict[str, Any],
) -> list[PreflightResult]:
    """Validate every ``.j2`` in ``overlay_dir`` before any rows are rendered.

    For each ``.j2`` file found under ``overlay_dir``:

    1. Read the raw source and check for forbidden ``{% include %}`` /
       ``{% import %}`` nodes (C1 — raises ``TemplateSyntaxError`` on
       violation).
    2. Call ``env.parse(source)`` to syntax-check.
    3. Call ``env.get_template(rel)`` to fill Jinja2's compile cache.
    4. Render against ``fixture_finding`` (``StrictUndefined`` + sandbox
       checks apply).
    5. Parse the rendered output for the 5 required sections; log a WARNING
       for any empty section (not a hard failure — operator may intentionally
       omit ``[REFERENCES]``).

    Returns a list of ``PreflightResult`` records (one per overlay template).

    Raises:
        PlaybookPreflightError: If ANY overlay template fails steps 1-4.
            The error message summarises all failures.  The export MUST NOT
            proceed when this is raised.

    **from_string note:** This function never calls ``env.from_string()``.
    Templates are loaded by filename via the ``FileSystemLoader`` in ``env``.
    """
    from finops_assess.reporters.playbook import _parse_template_output  # local import

    results: list[PreflightResult] = []
    failures: list[str] = []

    for j2_path in sorted(overlay_dir.rglob("*.j2")):
        rel = j2_path.relative_to(overlay_dir).as_posix()
        source = j2_path.read_text(encoding="utf-8")

        try:
            # C1: reject include/import directives.
            _reject_include_import_nodes(source, rel, env)
            # Syntax check + cache fill.
            env.parse(source)
            tmpl = env.get_template(rel)
            # Runtime check: StrictUndefined + sandbox.
            rendered = tmpl.render(**fixture_finding)
        except Exception as exc:
            err_msg = f"{rel}: {type(exc).__name__}: {exc}"
            _log.error("Overlay template pre-flight FAILED — %s", err_msg)
            results.append(PreflightResult(template_rel=rel, passed=False, error=err_msg))
            failures.append(err_msg)
            continue

        # Section-presence check (warnings only).
        parsed = _parse_template_output(rendered)
        required_sections = ("title", "description", "remediation_steps", "verification_checklist")
        for section in required_sections:
            value = parsed.get(section)
            if not value:
                _log.warning(
                    "Overlay template '%s' produced an empty '%s' section during pre-flight. "
                    "This is a WARNING — the export will proceed, but consumers may reject "
                    "rows with missing required sections.",
                    rel,
                    section,
                )

        results.append(PreflightResult(template_rel=rel, passed=True, error=None))
        _log.debug("Overlay template pre-flight PASSED: %s", rel)

    if failures:
        summary = "; ".join(failures)
        raise PlaybookPreflightError(
            f"Overlay template pre-flight failed for {len(failures)} template(s): {summary}"
        )

    return results


# ---------------------------------------------------------------------------
# Public environment accessor
# ---------------------------------------------------------------------------


def get_playbook_env(overlay_dir: Path | None = None) -> Environment:
    """Return the cached ``Environment``, building it on first call.

    When ``overlay_dir`` is ``None`` (default), behaviour is identical to
    v0.5.0: plain ``Environment``, single-path ``FileSystemLoader``, no
    sandbox restrictions.

    When ``overlay_dir`` is a ``Path``, a ``_RestrictedSandbox`` is built
    with ``FileSystemLoader([overlay_dir, wheel_root])`` and cached keyed on
    ``overlay_dir``.  Re-invocations with the same directory reuse the cached
    sandbox.

    Thread safety: CPython's GIL makes the double-checked initialisation safe
    for the common single-threaded CLI use case.  The function is idempotent
    — repeated calls with the same ``overlay_dir`` return the same object.

    **Lazy initialisation note:** The first call to this function triggers
    environment construction and template pre-compilation (filesystem I/O and
    Jinja2 AST parsing).  Subsequent calls return the cached instance without
    side effects.
    """
    global _ENV
    if overlay_dir is None:
        if _ENV is None:
            _ENV = _build_env()
        return _ENV

    # Overlay path: cache keyed on resolved overlay_dir.
    resolved = overlay_dir.resolve()
    if resolved not in _OVERLAY_ENVS:
        wheel_root = _playbook_templates_root()
        _OVERLAY_ENVS[resolved] = build_sandboxed_env(wheel_root, resolved)
    return _OVERLAY_ENVS[resolved]


def reset_playbook_env() -> None:
    """Clear all cached ``Environment`` instances for testing purposes.

    Sets the module-level ``_ENV`` cache to ``None`` and clears
    ``_OVERLAY_ENVS`` so the next call to ``get_playbook_env()`` will
    rebuild and re-compile the environment(s).

    **Cache invalidation semantics:** This function does NOT trigger any
    filesystem sync or Jinja2 template cache flush.  It simply clears the
    module-level references.  The Jinja2 ``Environment`` objects themselves
    (if still referenced elsewhere) retain their compiled template caches
    until garbage-collected.

    **Intended use:** Test fixtures that need to observe lazy-init behavior
    or verify environment configuration in isolation.  NOT for production
    use.
    """
    global _ENV
    _ENV = None
    _OVERLAY_ENVS.clear()


def extract_template_vars(source: str) -> list[str]:
    """Return a sorted list of variable names referenced in a Jinja2 template source.

    Used to populate ``template_render_inputs`` in each playbook row so
    consumers know which context keys the template actually consumed.

    Only top-level ``Name`` nodes are collected; attribute accesses
    (``foo.bar``) are represented as the root name ``foo``.
    """
    env = get_playbook_env()
    parsed = env.parse(source)
    names: set[str] = {node.name for node in parsed.find_all(nodes.Name)}
    return sorted(names)
