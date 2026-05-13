"""Jinja2 environment factory for the playbook reporter.

A single ``Environment`` is built once at module import and cached.  The
environment is configured with:

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
is pre-compiled when this module is first imported (loaded from
``importlib.resources``).  Pre-compilation catches syntax errors at startup
rather than at render time, and amortises the parse cost across multiple
findings that share the same rule.

Usage::

    from finops_assess.reporters._playbook_env import get_playbook_env
    env = get_playbook_env()
    tmpl = env.get_template("m365/M365.UNUSED_LICENSE_30D.j2")
    rendered = tmpl.render(principal="alice@contoso.com", ...)
"""

from __future__ import annotations

import logging
from importlib.resources import files
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, StrictUndefined, nodes

if TYPE_CHECKING:
    pass

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level cache — built once per process.
# ---------------------------------------------------------------------------

_ENV: Environment | None = None


def _playbook_templates_root() -> str:
    """Return the filesystem path to the bundled playbooks directory.

    Uses ``importlib.resources`` so the path resolves correctly whether the
    package is installed as a wheel or used from a source checkout.
    """
    # ``files()`` returns a Traversable; ``.joinpath()`` navigates into it.
    # ``str()`` gives the concrete filesystem path that FileSystemLoader needs.
    pkg_data = files("finops_assess").joinpath("data").joinpath("playbooks")
    return str(pkg_data)


def _build_env() -> Environment:
    """Construct and pre-compile the ``Environment``.

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
    from pathlib import Path

    playbooks_root = Path(root)
    for j2_path in sorted(playbooks_root.rglob("*.j2")):
        # Template name relative to the loader root (uses forward slashes on
        # all platforms — FileSystemLoader normalises the separator).
        rel = j2_path.relative_to(playbooks_root).as_posix()
        source = j2_path.read_text(encoding="utf-8")
        try:
            env.parse(source)  # syntax-check only; get_template() caches the compiled code
        except Exception as exc:  # noqa: BLE001
            _log.warning("Playbook template syntax error in %s: %s", rel, exc)
            raise
        # Trigger actual compilation + caching inside Jinja2.
        env.get_template(rel)
        _log.debug("Pre-compiled playbook template: %s", rel)

    return env


def get_playbook_env() -> Environment:
    """Return the cached ``Environment``, building it on first call.

    Thread safety: CPython's GIL makes the double-checked initialisation safe
    for the common single-threaded CLI use case.  The function is idempotent
    — repeated calls return the same object.
    """
    global _ENV  # noqa: PLW0603
    if _ENV is None:
        _ENV = _build_env()
    return _ENV


def extract_template_vars(source: str) -> list[str]:
    """Return a sorted list of variable names referenced in a Jinja2 template source.

    Used to populate ``template_render_inputs`` in each playbook row so
    consumers know which context keys the template actually consumed.

    Only top-level ``Name`` nodes are collected; attribute accesses
    (``foo.bar``) are represented as the root name ``foo``.
    """
    env = get_playbook_env()
    parsed = env.parse(source)
    names: set[str] = {node.name for node in parsed.find_all(nodes.Name)}  # type: ignore[attr-defined]
    return sorted(names)
