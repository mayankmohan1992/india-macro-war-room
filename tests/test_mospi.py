#!/usr/bin/env python3
"""Unit tests for fetch_mospi.py - the pure parts, so CI covers them without touching the network.

The three things tested here are the three that would publish a wrong number silently:
  * the sector map (the first version returned the map KEY, filing the headline series under
    "act_ur_rural + urban" so the all-India tile vanished);
  * the fiscal-quarter date rule (Q4 belongs to the NEXT calendar year);
  * the reference-period labels the page shows ("Sep 2026", "Q1 FY2026-27").
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import fetch_mospi as M  # noqa: E402


class SectorMap(unittest.TestCase):
    def norm(self, raw):
        """The same normalisation fetch_plfs applies before the lookup."""
        return " ".join((raw or "").split()).lower()

    def test_all_india_row_maps_to_both(self):
        self.assertEqual(M.SECTOR_KEY.get(self.norm("rural + urban")), "both")

    def test_spacing_and_case_do_not_matter(self):
        for raw in ("Rural + Urban", "RURAL  +   URBAN", " rural + urban "):
            self.assertEqual(M.SECTOR_KEY.get(self.norm(raw)), "both", raw)

    def test_rural_and_urban_stay_distinct(self):
        self.assertEqual(M.SECTOR_KEY.get(self.norm("rural")), "rural")
        self.assertEqual(M.SECTOR_KEY.get(self.norm("urban")), "urban")

    def test_unknown_sector_is_not_guessed(self):
        self.assertIsNone(M.SECTOR_KEY.get(self.norm("north")), "an unknown sector must be skipped, "
                                                                "never folded into all-India")


class ReferencePeriods(unittest.TestCase):
    def test_month_label_is_the_publishers_form(self):
        self.assertEqual(M.month_label(2026, 9), "Sep 2026")
        self.assertEqual(M.month_label(2025, 4), "Apr 2025")

    def test_month_start_is_first_of_month(self):
        self.assertEqual(M.month_start(2026, 9), "2026-09-01")

    def test_quarter_dates_follow_the_indian_fiscal_year(self):
        self.assertEqual(M.quarter_date("2026-27", "Q1"), ("2026-04-01", "Q1 FY2026-27"))
        self.assertEqual(M.quarter_date("2026-27", "Q2"), ("2026-07-01", "Q2 FY2026-27"))
        self.assertEqual(M.quarter_date("2026-27", "Q3"), ("2026-10-01", "Q3 FY2026-27"))

    def test_q4_crosses_into_the_next_calendar_year(self):
        # FY2026-27 Q4 is Jan-Mar 2027. Dating it 2026-01-01 shifts the whole y-o-y series a year early.
        self.assertEqual(M.quarter_date("2026-27", "Q4"), ("2027-01-01", "Q4 FY2026-27"))

    def test_bad_quarter_inputs_return_none(self):
        for fy, q in (("", "Q1"), ("2026-27", ""), ("2026-27", "Q9"), ("2026-27", "1")):
            self.assertIsNone(M.quarter_date(fy, q), f"{fy}/{q} should be rejected")


class Gate(unittest.TestCase):
    def test_required_series_are_the_headline_ones(self):
        # The gate is the reason a short pull never reaches raw/: if these keys stop being required, a
        # truncated PLFS month could publish with no history behind it.
        for key in ("act_ur", "act_lfpr", "act_wpr", "act_iip", "act_gva"):
            self.assertIn(key, M.REQUIRED, f"{key} must stay behind the completeness gate")
            self.assertGreaterEqual(M.REQUIRED[key], 3, f"{key} needs real history, not one point")


if __name__ == "__main__":
    unittest.main(verbosity=2)
