"""Auto-fetch the Microsoft published service-plan / SKU catalogue.

Microsoft publishes the canonical mapping of product display names →
``String_Id`` (the SKU id Graph returns for ``subscribedSkus``) → child
service-plan IDs as a CSV refreshed monthly. The download URL is referenced
from `Microsoft Learn
<https://learn.microsoft.com/en-us/entra/identity/users/licensing-service-plan-reference>`_.

This module:

* Downloads or reads (from a local path / ``file://`` URL) that CSV.
* Parses it into one record per ``String_Id`` (deduplicated, with its full
  set of included service-plan ids).
* Compares it against the curated YAML catalogue and reports gaps.
* Optionally writes the gap entries to ``data/catalog/m365/_autogen_unmapped.yaml``
  as stub entries (``list_price_usd_month: null``,
  ``family: m365_uncategorized``, ``source_url`` pointing back to the
  Microsoft Learn page) so a human can promote them with feature tags.

The fetch is **read-only** and **never** runs at install time. It is gated
behind explicit ``finops-assess catalog refresh`` / ``catalog coverage``
CLI subcommands. CI does not invoke it.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import yaml

from finops_assess.catalog import load_catalog
from finops_assess.data_paths import checkout_data_root

logger = logging.getLogger(__name__)

# Stable CSV download URL referenced from
# https://learn.microsoft.com/en-us/entra/identity/users/licensing-service-plan-reference.
DEFAULT_SOURCE_URL = (
    "https://download.microsoft.com/download/e/3/e/e3e9faf2-f28b-490a-9ada-c6089a1fc5b0/"
    "Product%20names%20and%20service%20plan%20identifiers%20for%20licensing.csv"
)
DEFAULT_DOC_URL = (
    "https://learn.microsoft.com/en-us/entra/identity/users/licensing-service-plan-reference"
)


def _default_autogen_file() -> Path:
    """Return the source-checkout path for generated M365 catalogue stubs."""
    data_root = checkout_data_root()
    if data_root is None:
        raise RuntimeError(
            "catalog refresh --write requires a source checkout; run from the repository "
            "or add generated stubs to data/catalog/m365/_autogen_unmapped.yaml manually."
        )
    return data_root / "catalog" / "m365" / "_autogen_unmapped.yaml"


_USER_AGENT = "finops-assess/catalog-refresh (read-only)"
_FETCH_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class UpstreamSku:
    """One row in the Microsoft CSV, collapsed to the SKU level."""

    string_id: str
    display_name: str
    guid: str
    service_plan_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass
class CoverageReport:
    """Result of comparing the upstream CSV to the on-disk catalogue."""

    upstream_count: int
    catalog_count: int
    missing: list[UpstreamSku]
    extra_local_ids: list[str]
    source_url: str

    @property
    def coverage_pct(self) -> float:
        if self.upstream_count == 0:
            return 100.0
        covered = self.upstream_count - len(self.missing)
        return round(100.0 * covered / self.upstream_count, 2)


# A "scheme" returned by urlparse that's actually a Windows drive letter
# (e.g. urlparse(r'D:\path\to\file') -> scheme='d', path='\\path\\to\\file').
# RFC 3986 schemes can contain only ASCII letters, digits, +, -, .; so a
# single-letter scheme on a path that exists locally is almost certainly a
# Windows drive letter. We special-case it here so that operators on Windows
# can pass plain native paths to --source.
_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]$")


def _looks_like_local_path(source: str, parsed_scheme: str) -> bool:
    if parsed_scheme == "":
        return True
    # Windows drive-letter path mistaken for a URL scheme.
    return os.name == "nt" and bool(_DRIVE_LETTER_RE.match(parsed_scheme))


def _open_source(source: str) -> bytes:
    """Read the CSV from an HTTP(S) URL, ``file://`` URL, or local path.

    Local paths work cross-platform: a Windows drive-letter path like
    ``D:\\tmp\\skus.csv`` is recognised even though ``urlparse`` would
    otherwise treat ``D`` as a URL scheme. ``file://`` URLs are decoded
    via :func:`urllib.request.url2pathname` so that percent-escapes and
    Windows drive letters round-trip correctly.
    """
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        # urllib.request handles redirects by default.
        # We only ever issue a GET; no auth, no cookies, no payload. The
        # URL scheme is validated above so this is not an open-redirect /
        # arbitrary-scheme call.
        request = urllib.request.Request(
            source,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/csv,application/octet-stream"},
            method="GET",
        )
        with urllib.request.urlopen(
            request,
            timeout=_FETCH_TIMEOUT_SECONDS,
        ) as response:
            return bytes(response.read())
    if parsed.scheme == "file":
        # url2pathname handles `/C:/...` -> `C:\...` on Windows and unescapes
        # percent-encoded characters; on POSIX it strips a leading slash only
        # when followed by a drive letter, otherwise leaves the path alone.
        local = url2pathname(unquote(parsed.path))
        return Path(local).read_bytes()
    if _looks_like_local_path(source, parsed.scheme):
        return Path(source).read_bytes()
    raise ValueError(f"unsupported source scheme: {parsed.scheme!r}")


def parse_csv(data: bytes) -> list[UpstreamSku]:
    """Parse the Microsoft CSV bytes into a deduplicated list of SKUs."""
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("upstream CSV has no header row")

    # Microsoft's columns: Product_Display_Name, String_Id, GUID,
    # Service_Plan_Name, Service_Plan_Id, Service_Plans_Included_Friendly_Names.
    required = {"Product_Display_Name", "String_Id", "GUID"}
    missing = required - set(reader.fieldnames)
    if missing:
        raise ValueError(f"upstream CSV missing required columns: {sorted(missing)}")

    by_string_id: dict[str, dict[str, object]] = {}
    for row in reader:
        string_id = (row.get("String_Id") or "").strip()
        if not string_id:
            continue
        bucket = by_string_id.setdefault(
            string_id,
            {
                "display_name": (row.get("Product_Display_Name") or "").strip(),
                "guid": (row.get("GUID") or "").strip(),
                "plans": set(),
            },
        )
        plan_id = (row.get("Service_Plan_Id") or "").strip()
        if plan_id:
            plans = bucket["plans"]
            assert isinstance(plans, set)
            plans.add(plan_id)
        plan_name = (row.get("Service_Plan_Name") or "").strip()
        if plan_name:
            # Some downstream tooling matches by name; keep both for completeness.
            plans = bucket["plans"]
            assert isinstance(plans, set)
            plans.add(plan_name)

    skus: list[UpstreamSku] = []
    for sid, bucket in by_string_id.items():
        plans = bucket["plans"]
        assert isinstance(plans, set)
        skus.append(
            UpstreamSku(
                string_id=sid,
                display_name=str(bucket["display_name"]) or sid,
                guid=str(bucket["guid"]),
                service_plan_ids=frozenset(plans),
            )
        )
    skus.sort(key=lambda s: s.string_id)
    return skus


_AUTOGEN_FAMILY = "m365_uncategorized"


def compute_coverage(
    upstream: list[UpstreamSku],
    catalog_root: Path | None = None,
    *,
    source_url: str = DEFAULT_SOURCE_URL,
) -> CoverageReport:
    """Compare upstream SKUs against the on-disk catalog.

    Auto-generated stub entries (``family == "m365_uncategorized"``,
    written by :func:`write_autogen` into ``_autogen_unmapped.yaml``)
    are *not* counted as covered: they have no curated features or
    pricing, so treating them as covered would defeat the
    ``catalog coverage --fail-on-gap`` drift gate.
    """
    entries = load_catalog(catalog_root)
    local_ids = {e.id for e in entries if e.cloud == "m365" and e.family != _AUTOGEN_FAMILY}
    upstream_ids = {s.string_id for s in upstream}
    missing = sorted(
        (s for s in upstream if s.string_id not in local_ids),
        key=lambda s: s.string_id,
    )
    extras = sorted(local_ids - upstream_ids)
    return CoverageReport(
        upstream_count=len(upstream),
        catalog_count=len(local_ids),
        missing=missing,
        extra_local_ids=extras,
        source_url=source_url,
    )


def fetch_and_parse(source: str = DEFAULT_SOURCE_URL) -> list[UpstreamSku]:
    """Download (or read locally) and parse the upstream catalogue."""
    return parse_csv(_open_source(source))


def render_autogen_yaml(missing: list[UpstreamSku], *, doc_url: str = DEFAULT_DOC_URL) -> str:
    """Render the YAML body for the auto-generated unmapped-SKUs file.

    These are *stub* entries: ``family: m365_uncategorized``, no
    ``features``, no price. A human (or the surface specialist via the
    §11 loop) promotes them by adding feature tags and moving the entry
    into the curated YAML.

    Service-plan ids from the upstream CSV are recorded in ``notes`` for
    the human reviewer, **never** in ``includes``. The engine treats
    ``includes`` as a list of *child catalog SKU ids* and walks it
    transitively in :func:`engine.transitive_includes` /
    :func:`engine.effective_features`; injecting raw service-plan GUIDs
    there would silently corrupt those traversals as soon as the
    ``_autogen_unmapped.yaml`` file is loaded.
    """
    docs = [
        "# AUTO-GENERATED by `finops-assess catalog refresh`. Do not hand-edit.",
        "# Promotion workflow: copy entries you want to model into the curated",
        "# YAML files (e.g. data/catalog/m365/enterprise.yaml), add feature",
        "# tags + price, then delete them from this file. Re-running refresh",
        "# will not duplicate already-promoted entries.",
        f"# Source: {doc_url}",
        "",
    ]
    payload: list[dict[str, object]] = []
    for sku in missing:
        plan_ids = sorted(sku.service_plan_ids)
        note_lines = [
            "Auto-generated stub. Promote by adding feature tags and moving into curated YAML.",
        ]
        if plan_ids:
            note_lines.append(f"Upstream service plans: {', '.join(plan_ids)}")
        payload.append(
            {
                "id": sku.string_id,
                "display_name": sku.display_name or sku.string_id,
                "family": "m365_uncategorized",
                "cloud": "m365",
                "list_price_usd_month": None,
                "source_url": doc_url,
                # Intentionally empty — see docstring. Service-plan ids are
                # surfaced via `notes` for human review, not via `includes`.
                "includes": [],
                "notes": "\n".join(note_lines),
            }
        )
    return "\n".join(docs) + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def write_autogen(
    coverage: CoverageReport,
    *,
    target: Path | None = None,
    doc_url: str = DEFAULT_DOC_URL,
) -> Path | None:
    """Write the unmapped-SKU stubs to disk; returns the path or ``None`` if no gap."""
    if not coverage.missing:
        return None
    target = target or _default_autogen_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_autogen_yaml(coverage.missing, doc_url=doc_url), encoding="utf-8")
    return target
