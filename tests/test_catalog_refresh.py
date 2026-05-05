"""Tests for the auto-fetch / coverage logic."""

from __future__ import annotations

from pathlib import Path

from finops_assess.catalog import load_catalog
from finops_assess.catalog_refresh import (
    compute_coverage,
    fetch_and_parse,
    parse_csv,
    render_autogen_yaml,
    write_autogen,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_csv_dedups_by_string_id() -> None:
    skus = parse_csv((FIXTURES / "ms_skus_minimal.csv").read_bytes())
    ids = [s.string_id for s in skus]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    e3 = next(s for s in skus if s.string_id == "SPE_E3")
    # Three service-plan rows for E3 collapse to a single SKU with 3+ plan refs.
    assert len(e3.service_plan_ids) >= 3
    assert "Microsoft 365" in e3.display_name


def test_fetch_and_parse_supports_local_path() -> None:
    skus = fetch_and_parse(str(FIXTURES / "ms_skus_minimal.csv"))
    assert {s.string_id for s in skus} >= {"SPE_E3", "SPE_E5", "M365_COPILOT"}


def test_fetch_and_parse_supports_file_url() -> None:
    url = (FIXTURES / "ms_skus_minimal.csv").as_uri()
    skus = fetch_and_parse(url)
    assert any(s.string_id == "SPE_F3" for s in skus)


def test_open_source_treats_windows_drive_letter_as_local(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A bare `D:\\path\\file.csv` must be read as a local file on Windows.

    Regression: ``urlparse`` treats the drive letter as a URL scheme, which
    previously raised ``ValueError("unsupported source scheme: 'd'")`` on
    Windows CI runners.
    """
    from finops_assess import catalog_refresh as cr

    monkeypatch.setattr(cr.os, "name", "nt")
    # A real local file on the test runner; the path itself is POSIX, but
    # the look-like-local-path check is what we're exercising. We
    # synthesise a fake scheme by checking the function directly.
    assert cr._looks_like_local_path("D:\\tmp\\skus.csv", "d") is True
    assert cr._looks_like_local_path("/tmp/skus.csv", "") is True
    monkeypatch.setattr(cr.os, "name", "posix")
    assert cr._looks_like_local_path("D:\\tmp\\skus.csv", "d") is False
    assert cr._looks_like_local_path("/tmp/skus.csv", "") is True


def test_compute_coverage_reports_local_extras_and_upstream_gaps() -> None:
    upstream = fetch_and_parse(str(FIXTURES / "ms_skus_with_gap.csv"))
    coverage = compute_coverage(upstream)
    missing_ids = {s.string_id for s in coverage.missing}
    assert "TOTALLY_NEW_SKU_2099" in missing_ids
    # Our curated catalogue has lots of M365 SKUs not in this tiny fixture.
    assert len(coverage.extra_local_ids) > 5


def test_render_autogen_yaml_produces_loadable_entries() -> None:
    upstream = fetch_and_parse(str(FIXTURES / "ms_skus_with_gap.csv"))
    coverage = compute_coverage(upstream)
    body = render_autogen_yaml(coverage.missing)
    assert "AUTO-GENERATED" in body
    assert "id: TOTALLY_NEW_SKU_2099" in body
    assert "list_price_usd_month: null" in body


def test_write_autogen_round_trips_through_catalog_loader(tmp_path: Path) -> None:
    upstream = fetch_and_parse(str(FIXTURES / "ms_skus_with_gap.csv"))
    coverage = compute_coverage(upstream)
    target = tmp_path / "_autogen_unmapped.yaml"
    written = write_autogen(coverage, target=target)
    assert written == target
    # The autogen file must be a valid CatalogEntry list (the loader's contract).
    # Build an isolated catalog root containing only the autogen file.
    fake_root = tmp_path / "catalog"
    (fake_root / "m365").mkdir(parents=True)
    (fake_root / "m365" / "_autogen_unmapped.yaml").write_text(
        target.read_text(encoding="utf-8"), encoding="utf-8"
    )
    entries = load_catalog(fake_root)
    assert any(e.id == "TOTALLY_NEW_SKU_2099" for e in entries)


def test_autogen_stubs_do_not_pollute_includes(tmp_path: Path) -> None:
    """Regression: stubs must NOT write upstream service-plan GUIDs/names
    into ``includes`` — the engine treats ``includes`` as a list of child
    catalog SKU ids and walks it transitively. Putting raw service-plan
    ids there would silently corrupt :func:`engine.transitive_includes`
    and :func:`engine.effective_features` as soon as the file is loaded.
    """
    upstream = fetch_and_parse(str(FIXTURES / "ms_skus_with_gap.csv"))
    coverage = compute_coverage(upstream)
    body = render_autogen_yaml(coverage.missing)
    # No `includes:` line should carry payload (only `includes: []`).
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("includes:") and stripped != "includes: []":
            raise AssertionError(f"autogen stub leaked service-plan ids into `includes`: {line!r}")
    # The plan ids should still be visible to a human reviewer via `notes`.
    assert "Upstream service plans:" in body or "Auto-generated stub" in body


def test_compute_coverage_excludes_autogen_stubs_from_local_count(tmp_path: Path) -> None:
    """Regression: ``catalog coverage --fail-on-gap`` must stay red after
    ``catalog refresh --write`` — the autogen stub file is loaded by
    ``load_catalog`` and previously made the missing SKU look "covered"
    even though it has no curated features or pricing.
    """
    upstream = fetch_and_parse(str(FIXTURES / "ms_skus_with_gap.csv"))
    # Build an isolated catalog root containing the curated catalog AND
    # an autogen file that "covers" the missing SKU as a stub.
    fake_root = tmp_path / "catalog"
    (fake_root / "m365").mkdir(parents=True)
    (fake_root / "m365" / "stub.yaml").write_text(
        "- id: TOTALLY_NEW_SKU_2099\n"
        "  display_name: Stub\n"
        "  family: m365_uncategorized\n"
        "  cloud: m365\n"
        "  list_price_usd_month: null\n",
        encoding="utf-8",
    )
    coverage = compute_coverage(upstream, catalog_root=fake_root)
    missing_ids = {s.string_id for s in coverage.missing}
    assert "TOTALLY_NEW_SKU_2099" in missing_ids, (
        "autogen-family stubs must NOT count as locally covered"
    )
