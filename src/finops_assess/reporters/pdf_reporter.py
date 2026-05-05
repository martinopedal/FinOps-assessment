"""PDF executive report (M7) — WeasyPrint render of a print-tuned HTML.

The PDF reporter is split into two layers:

* :func:`build_pdf_html` is pure Jinja2; it produces the print-tuned HTML
  string and has **no** dependency on WeasyPrint, so it can be exercised
  on every CI matrix cell (including Windows/macOS where WeasyPrint's
  native deps are awkward to install).
* :func:`build_pdf_report` and :func:`write_pdf_report` lazily import
  WeasyPrint and raise a clear actionable error if the optional ``pdf``
  extra (``pip install finops-assess[pdf]``) is not present.

Determinism:
    WeasyPrint embeds ``CreationDate`` / ``ModDate`` / a document
    identifier into every PDF, which would otherwise change on every
    render. Since v53 it honours the ``SOURCE_DATE_EPOCH`` environment
    variable for these fields. We derive the epoch from the report's own
    ``run.generated_at`` ISO timestamp so two renders of the same report
    payload are byte-identical, satisfying the M7 "deterministic build"
    exit criterion.

Branding:
    Operators can supply an organisation name, an accent colour, a logo
    file (embedded as a ``data:`` URI so the PDF stays self-contained),
    and a paper size. All fields are optional and have safe defaults.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FunctionLoader, select_autoescape

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    pass

logger = logging.getLogger(__name__)

# Severity ordering: highest impact first in the rendered tables.
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

# Surface tabs — order is deliberate (M365 → Azure → GitHub → ADO).
_SURFACE_LABELS: list[tuple[str, str]] = [
    ("m365", "Microsoft 365"),
    ("azure", "Azure"),
    ("github", "GitHub"),
    ("ado", "Azure DevOps"),
]

_TEMPLATE_NAME = "report.pdf.html.j2"

# Conservative subset of paper sizes WeasyPrint accepts via CSS @page.
_ALLOWED_PAGE_SIZES = frozenset({"A4", "Letter", "Legal", "A3", "A5"})

_DEFAULT_ACCENT = "#0969da"
_DEFAULT_PAGE_SIZE = "Letter"

# Logo files larger than this (raw bytes, before base64) are rejected to
# keep the PDF small and to avoid pathological inputs.
_MAX_LOGO_BYTES = 1 * 1024 * 1024  # 1 MiB

# Only a small allow-list of image types is embeddable. SVG is excluded
# because WeasyPrint's SVG support varies and can pull in fonts; PNG/JPEG
# render deterministically.
_ALLOWED_LOGO_MIME = frozenset({"image/png", "image/jpeg", "image/gif"})


@dataclass(frozen=True)
class Branding:
    """Branding options for the PDF cover page.

    All fields are optional. Defaults reproduce the unbranded look.

    Validation runs in :meth:`__post_init__`, so direct construction
    (``Branding(accent_color="…")``) is checked just as strictly as
    :meth:`from_options`. The convenience factory only adds the
    file-handling step (reading a logo into a ``data:`` URI) on top of
    the same validators.
    """

    name: str | None = None
    accent_color: str = _DEFAULT_ACCENT
    page_size: str = _DEFAULT_PAGE_SIZE
    logo_data_uri: str | None = None

    def __post_init__(self) -> None:
        # Frozen dataclass: re-set normalised values via object.__setattr__
        # so direct ``Branding(page_size="a4")`` calls also normalise to
        # the canonical "A4" the template expects.
        normalised_color = _validate_accent_color(self.accent_color)
        normalised_size = _validate_page_size(self.page_size)
        if self.logo_data_uri is not None:
            _validate_logo_data_uri(self.logo_data_uri)
        if normalised_color != self.accent_color:
            object.__setattr__(self, "accent_color", normalised_color)
        if normalised_size != self.page_size:
            object.__setattr__(self, "page_size", normalised_size)

    @classmethod
    def from_options(
        cls,
        *,
        name: str | None = None,
        accent_color: str | None = None,
        page_size: str | None = None,
        logo_path: Path | str | None = None,
    ) -> Branding:
        """Validate raw operator-supplied branding options.

        The accent colour is restricted to a strict ``#RRGGBB`` hex form
        so it can't break out of the CSS variable assignment in the
        template. The logo path, if given, is read and base64-encoded
        into a ``data:`` URI; only PNG/JPEG/GIF are accepted.
        """
        logo_uri = _read_logo_data_uri(Path(logo_path)) if logo_path is not None else None
        # __post_init__ runs the field validators; this constructor does
        # the file I/O step (which is not safe to repeat on every render).
        return cls(
            name=name,
            accent_color=accent_color if accent_color else _DEFAULT_ACCENT,
            page_size=page_size if page_size else _DEFAULT_PAGE_SIZE,
            logo_data_uri=logo_uri,
        )


def _validate_accent_color(value: str) -> str:
    """Return ``value`` if it is a strict ``#RRGGBB`` hex literal.

    Anything else raises :class:`ValueError`. The strict form prevents
    a hostile branding value from terminating the CSS declaration and
    injecting arbitrary rules.
    """
    candidate = value.strip()
    if (
        len(candidate) == 7
        and candidate.startswith("#")
        and all(c in "0123456789abcdefABCDEF" for c in candidate[1:])
    ):
        return candidate
    raise ValueError(f"branding accent_color must be a #RRGGBB hex literal, got {value!r}")


def _validate_page_size(value: str) -> str:
    """Return ``value`` if it is one of the allow-listed paper sizes."""
    normalised = value.strip()
    # Normalise common-case spellings.
    for allowed in _ALLOWED_PAGE_SIZES:
        if normalised.lower() == allowed.lower():
            return allowed
    raise ValueError(
        f"branding page_size must be one of {sorted(_ALLOWED_PAGE_SIZES)}, got {value!r}"
    )


def _sniff_image_mime(raw: bytes) -> str | None:
    """Return the MIME type implied by the file's magic bytes, or ``None``.

    Extension-based MIME detection is trivially spoofable; sniffing the
    first few bytes catches files whose extension lies about their
    contents (and corrupt files that would otherwise blow up inside
    WeasyPrint with an unhelpful error).
    """
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "image/gif"
    return None


def _read_logo_data_uri(path: Path) -> str:
    """Read ``path`` and encode it as a self-contained ``data:`` URI.

    Both the filename extension and the file's magic bytes are checked,
    and they must agree. This catches both spoofed extensions and
    corrupt image files before they reach WeasyPrint.
    """
    if not path.is_file():
        raise FileNotFoundError(f"branding logo not found: {path}")
    raw = path.read_bytes()
    if len(raw) > _MAX_LOGO_BYTES:
        raise ValueError(f"branding logo {path} is {len(raw)} bytes; max is {_MAX_LOGO_BYTES}")
    extension_mime, _ = mimetypes.guess_type(path.name)
    if extension_mime not in _ALLOWED_LOGO_MIME:
        raise ValueError(
            f"branding logo {path} has unsupported type {extension_mime!r}; "
            f"allowed: {sorted(_ALLOWED_LOGO_MIME)}"
        )
    sniffed_mime = _sniff_image_mime(raw)
    if sniffed_mime is None:
        raise ValueError(
            f"branding logo {path} does not begin with a recognised "
            f"PNG/JPEG/GIF magic-byte signature; refusing to embed."
        )
    if sniffed_mime != extension_mime:
        raise ValueError(
            f"branding logo {path} extension says {extension_mime!r} but "
            f"its magic bytes say {sniffed_mime!r}; refusing to embed."
        )
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{sniffed_mime};base64,{encoded}"


def _validate_logo_data_uri(value: str) -> None:
    """Sanity-check a logo ``data:`` URI passed via direct construction.

    The full :func:`_read_logo_data_uri` path covers operator-supplied
    files; this guard catches the rarer case of a caller building a
    :class:`Branding` directly with a hand-crafted ``logo_data_uri``.
    """
    if not value.startswith("data:"):
        raise ValueError(f"branding logo_data_uri must start with 'data:', got {value[:32]!r}…")
    head = value.split(",", 1)[0]
    if not any(head.startswith(f"data:{m};") for m in _ALLOWED_LOGO_MIME):
        raise ValueError(
            f"branding logo_data_uri MIME must be one of {sorted(_ALLOWED_LOGO_MIME)}; "
            f"got header {head!r}"
        )


def _load_template_source(name: str) -> str | None:
    """Load a template by name from the packaged ``templates/`` resource dir."""
    if name != _TEMPLATE_NAME:
        return None
    template_root = resources.files("finops_assess.reporters") / "templates"
    return (template_root / name).read_text(encoding="utf-8")


def _make_env() -> Environment:
    return Environment(
        loader=FunctionLoader(_load_template_source),
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default=True),
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )


def _group_by_surface(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        grouped.setdefault(f["surface"], []).append(f)
    for _surface, items in grouped.items():
        items.sort(key=lambda f: (_SEVERITY_ORDER.get(f["severity"], 99), f["rule_id"]))
    return grouped


def _top_surfaces_by_savings(
    findings: list[dict[str, Any]],
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Aggregate per-surface savings + count, descending by savings."""
    label_lookup = dict(_SURFACE_LABELS)
    by_surface: dict[str, dict[str, float]] = {}
    for f in findings:
        surface = f.get("surface", "")
        slot = by_surface.setdefault(surface, {"findings": 0.0, "savings": 0.0})
        slot["findings"] += 1
        slot["savings"] += float(f.get("estimated_monthly_savings_usd") or 0.0)
    ordered = sorted(
        by_surface.items(),
        key=lambda item: (-item[1]["savings"], -item[1]["findings"], item[0]),
    )
    return [
        {
            "surface": s,
            "label": label_lookup.get(s, s),
            "findings": int(v["findings"]),
            "savings": v["savings"],
        }
        for s, v in ordered[:limit]
    ]


def build_pdf_html(report: dict[str, Any], branding: Branding | None = None) -> str:
    """Render the print-tuned HTML used as input to WeasyPrint.

    This function is pure Jinja2 and has no WeasyPrint dependency, so it
    is testable on every CI matrix cell.
    """
    if branding is None:
        branding = Branding()

    findings: list[dict[str, Any]] = list(report.get("findings", []))
    summary: dict[str, Any] = dict(report.get("summary", {}))
    run: dict[str, Any] = dict(report.get("run", {}))

    rule_counts: dict[str, int] = summary.get("rule_counts", {}) or {}
    rules_fired_count = sum(1 for v in rule_counts.values() if v)
    total_estimated_savings = sum(
        float(f.get("estimated_monthly_savings_usd") or 0.0) for f in findings
    )

    env = _make_env()
    template = env.get_template(_TEMPLATE_NAME)
    return template.render(
        run=run,
        summary=summary,
        findings=findings,
        findings_by_surface=_group_by_surface(findings),
        rules_fired_count=rules_fired_count,
        total_estimated_savings=total_estimated_savings,
        top_surfaces=_top_surfaces_by_savings(findings),
        surface_labels=_SURFACE_LABELS,
        branding=branding,
    )


def _epoch_from_generated_at(value: Any) -> int | None:
    """Best-effort parse of ``run.generated_at`` into a Unix epoch seconds int.

    Returns ``None`` if the field is missing or unparseable; callers
    fall back to leaving ``SOURCE_DATE_EPOCH`` unset, which means
    WeasyPrint will use the current time and the build will not be
    deterministic. We log a warning rather than raising so a malformed
    timestamp doesn't block report generation.
    """
    if not value:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    # Python <3.11 datetime.fromisoformat doesn't accept trailing 'Z'.
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        return int(datetime.fromisoformat(candidate).timestamp())
    except ValueError:
        logger.warning("could not parse run.generated_at=%r for SOURCE_DATE_EPOCH", value)
        return None


@contextmanager
def _deterministic_environment(epoch: int | None) -> Iterator[None]:
    """Temporarily set ``SOURCE_DATE_EPOCH`` for the WeasyPrint render.

    This is process-global state, but PDF rendering is a synchronous
    CLI operation and the value is restored on exit. Threaded callers
    should serialise their use of this reporter.
    """
    if epoch is None:
        yield
        return
    key = "SOURCE_DATE_EPOCH"
    previous = os.environ.get(key)
    os.environ[key] = str(epoch)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def _import_weasyprint() -> Any:
    """Lazily import WeasyPrint, raising a clear error if missing.

    The optional ``[pdf]`` extra installs WeasyPrint, but it has heavy
    native dependencies (Pango, cairo, GDK-pixbuf) that are not present
    on every environment by default. We surface a friendly error
    pointing operators at the install instructions instead of letting
    a bare :class:`ImportError` bubble up.
    """
    try:
        import weasyprint
    except ImportError as exc:  # pragma: no cover - exercised only when extra missing
        raise RuntimeError(
            "PDF reporting requires the optional 'pdf' extra. "
            "Install with: pip install 'finops-assess[pdf]'. "
            "Note: WeasyPrint also needs system libraries (Pango, cairo, "
            "GDK-pixbuf); see https://doc.courtbouillon.org/weasyprint/ "
            "for platform-specific instructions."
        ) from exc
    return weasyprint


def build_pdf_report(report: dict[str, Any], branding: Branding | None = None) -> bytes:
    """Render ``report`` to a self-contained PDF document as bytes.

    Raises :class:`RuntimeError` (with install hint) if WeasyPrint is
    not installed.
    """
    weasyprint = _import_weasyprint()
    html_payload = build_pdf_html(report, branding=branding)
    epoch = _epoch_from_generated_at(report.get("run", {}).get("generated_at"))
    with _deterministic_environment(epoch):
        # base_url is only used to resolve relative URLs in the HTML —
        # we have none, but pass an empty string so WeasyPrint does not
        # implicitly use the cwd, which would be non-deterministic.
        document = weasyprint.HTML(string=html_payload, base_url="")
        rendered = document.write_pdf()
    if not isinstance(rendered, (bytes, bytearray)):  # pragma: no cover - defensive
        raise RuntimeError(
            f"WeasyPrint returned unexpected type {type(rendered)!r}; expected bytes."
        )
    return bytes(rendered)


def write_pdf_report(
    report: dict[str, Any],
    output: Path,
    branding: Branding | None = None,
) -> bytes:
    """Render ``report`` to PDF and write it to ``output``.

    Returns the rendered bytes for callers that want to inspect them.
    """
    output = Path(output)
    payload = build_pdf_report(report, branding=branding)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    return payload
