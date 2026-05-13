# SKILL: FOCUS-aligned Reporter — Golden Fixture Pattern

**Owner:** Yuki (Tester)
**Extracted from:** PR #70 hardening review, issue #58

---

## Problem this skill solves

Reporter PRs that ship golden fixtures for byte-identical comparisons will silently fail on Windows CI if the fixtures are not pinned to LF line endings in `.gitattributes`. Linux and macOS pass; only Windows fails. This creates a false sense of cross-platform safety.

---

## The LF-pinning pattern

### Production code (already correct in v0.5.0)

```python
# CSV writer — LF on all platforms
with output_csv.open("w", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(
        fh, fieldnames=list(COLUMN_ORDER),
        lineterminator="\n",    # <-- explicit, never os.linesep
    )

# JSON manifest writer — LF on all platforms
payload = json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False)
manifest_path.write_text(payload + "\n", encoding="utf-8", newline="")
# Note: Path.write_text(..., newline="") (Python ≥ 3.10) disables OS newline translation
```

### .gitattributes entries (required for every byte-compared fixture)

```gitattributes
# Generated output examples — LF pinned
examples/my-reporter.csv                       text eol=lf
examples/my-reporter.csv.manifest.json         text eol=lf

# Test golden fixtures — LF pinned (byte-compared in tests 1 & 2)
tests/fixtures/my_reporter/golden-output.csv   text eol=lf
tests/fixtures/my_reporter/golden-output.json  text eol=lf
```

**Rule:** If your test does `(FIXTURES / "golden-X").read_bytes()`, that file needs `text eol=lf`.

### Test pattern for byte-identical comparison

```python
def test_golden_csv_byte_identical(tmp_path: Path) -> None:
    """Rendered CSV bytes must match the committed golden fixture."""
    report = _load_fixture("input-two-findings.json")
    csv_path, _ = _render(report, tmp_path, epoch="0")    # SOURCE_DATE_EPOCH pinned!
    actual = csv_path.read_bytes()
    expected = (FIXTURES / "golden-output.csv").read_bytes()
    assert actual == expected, "CSV output has drifted from golden-output.csv"
```

Key requirements:
1. **Pin `SOURCE_DATE_EPOCH=0`** in the `_render` helper (or equivalent) so the `generated_at` timestamp is stable.
2. **`read_bytes()`** for both actual and expected — never `read_text()` for byte-identical tests.
3. **Both files must be LF-only** — production code via `lineterminator="\n"`, golden via `.gitattributes`.

---

## Advisory finding key — regression test patterns

### NUL bytes in evidence (sha256 json-envelope regression)

```python
def test_advisory_finding_key_nul_bytes_in_evidence_no_collision():
    f_nul = {"rule_id": "AZ.X", "principal": "/res", "evidence": {"k": "v\x00nul"}}
    f_no_nul = {"rule_id": "AZ.X", "principal": "/res", "evidence": {"k": "vnul"}}
    assert advisory_finding_key(f_nul) != advisory_finding_key(f_no_nul)
    # Cross-boundary: NUL in rule_id must not collide with NUL in evidence value
    f_rule_nul = {"rule_id": "AZ\x00X", "principal": "/res", "evidence": {"k": "v"}}
    f_ev_nul   = {"rule_id": "AZ",      "principal": "/res", "evidence": {"k": "X\x00v"}}
    assert advisory_finding_key(f_rule_nul) != advisory_finding_key(f_ev_nul)
```

### Unicode evidence (emoji, RTL, supplementary planes)

```python
def test_advisory_finding_key_unicode_evidence():
    f = {"rule_id": "AZ.X", "principal": "/res", "evidence": {"tag": "🚀", "rtl": "مرحبا"}}
    key = advisory_finding_key(f)
    assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)
    assert key == advisory_finding_key(f)  # deterministic
```

### Long resource_id (no truncation)

```python
def test_advisory_finding_key_long_resource_id():
    long_id = "/subscriptions/" + "0" * 36 + "/resourceGroups/" + "x" * 900
    f_long    = {"rule_id": "AZ.X", "principal": long_id,      "evidence": {}}
    f_shorter = {"rule_id": "AZ.X", "principal": long_id[:-1], "evidence": {}}
    assert advisory_finding_key(f_long) != advisory_finding_key(f_shorter)
    assert len(advisory_finding_key(f_long)) == 64
```

---

## PR checklist for reporter PRs

- [ ] Production CSV writer uses `open(..., newline="")` + `lineterminator="\n"`.
- [ ] Production manifest writer uses `write_text(..., newline="")` (Python ≥ 3.10).
- [ ] `examples/*.csv` and `examples/*.json` pinned in `.gitattributes`.
- [ ] `tests/fixtures/**/golden-*.csv` and `tests/fixtures/**/golden-*.json` pinned in `.gitattributes`.
- [ ] Golden fixtures were generated with `SOURCE_DATE_EPOCH=0`.
- [ ] Golden tests use `read_bytes()` for both sides of the comparison.
- [ ] NUL-byte regression test present if finding key uses string-based hashing.
- [ ] Unicode round-trip test present for any column written to CSV.
- [ ] CI passes on `windows-latest`, `ubuntu-latest`, and `macos-latest`.

---

## Failure signature

If you see this on Windows CI only:

```
FAILED tests/test_X_reporter.py::test_golden_csv_byte_identical
AssertionError: CSV output has drifted from golden-azure.csv
```

And Linux/macOS both pass — the fix is almost always the missing `.gitattributes` `text eol=lf` entry for the golden fixture file.
