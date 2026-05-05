"""Collectors normalise raw inputs (CSV today, live APIs in M4+) to ``NormalizedDataset``."""

from finops_assess.collectors.csv_collector import collect_from_directory

__all__ = ["collect_from_directory"]
