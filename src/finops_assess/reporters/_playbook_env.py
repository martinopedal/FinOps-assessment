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
        except Exception as exc:
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

    **Lazy initialisation note:** The first call to this function triggers
    environment construction and template pre-compilation (filesystem I/O and
    Jinja2 AST parsing).  Subsequent calls return the cached instance without
    side effects.
    """
    global _ENV
    if _ENV is None:
        _ENV = _build_env()
    return _ENV


def reset_playbook_env() -> None:
    """Clear the cached ``Environment`` for testing purposes.

    Sets the module-level ``_ENV`` cache to ``None`` so the next call to
    ``get_playbook_env()`` will rebuild and re-compile the environment.

    **Cache invalidation semantics:** This function does NOT trigger any
    filesystem sync or Jinja2 template cache flush.  It simply clears the
    module-level reference.  The Jinja2 ``Environment`` object itself (if
    still referenced elsewhere) retains its compiled template cache until
    garbage-collected.

    **Intended use:** Test fixtures that need to observe lazy-init behavior
    or verify environment configuration in isolation.  NOT for production
    use.
    """
    global _ENV
    _ENV = None


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
