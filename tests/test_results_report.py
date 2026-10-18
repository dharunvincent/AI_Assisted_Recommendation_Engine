"""
tests/test_results_report.py

Phase 5 tests: the printed list, the saved CSV and the filter report.
Tiny hand made data, files only go to a temporary folder.
"""

import csv
import os
import tempfile
import unittest
from datetime import date

from src.results_report import (
    CSV_COLUMNS,
    build_result_rows,
    format_filter_report,
    DisplayOptions,
    format_result_table,
    select_rows,
    results_file_name,
    write_results_csv,
)

CATALOG = {
    1: {"imdb_rating": 8.5, "directors": ["Michael Mann"], "cast": ["A", "B", "C"]},
    2: {"imdb_rating": None, "directors": [], "cast": []},
}


def ranked_item(movie_id, score, badge, reasons):
    return {
        "movie_id": movie_id, "title": f"Movie {movie_id}", "year": 1995,
        "final_score": score, "match_percent": score + 10, "show_badge": badge, "reasons": reasons,
    }


RANKED = [
    ranked_item(1, 80.0, True, ["directed by Michael Mann", "trending now"]),
    ranked_item(2, 50.0, False, ["trending now"]),
]


class RowsAndPrintTests(unittest.TestCase):
    def test_rows_have_every_column_and_only_top_two_cast(self):
        rows = build_result_rows(RANKED, CATALOG)
        self.assertEqual(set(rows[0]), set(CSV_COLUMNS))
        self.assertEqual(rows[0]["top_cast"], "A, B")
        self.assertEqual(rows[0]["all_reasons"], "directed by Michael Mann | trending now")
        self.assertEqual((rows[0]["rank"], rows[1]["rank"]), (1, 2))

    def test_table_has_every_column_and_handles_missing_imdb(self):
        lines = format_result_table(build_result_rows(RANKED, CATALOG))
        self.assertEqual(len(lines), 3)  # header + 2 rows
        for column in ["Rank", "Title", "Year", "IMDb", "Match", "Badge", "Main reason"]:
            self.assertIn(column, lines[0])
        self.assertIn("8.5", lines[1])
        self.assertIn("90%", lines[1])  # the Match column shows match_percent, not final_score
        self.assertNotIn("80%", lines[1])
        self.assertIn("✓", lines[1])
        self.assertIn("n/a", lines[2])
        self.assertNotIn("✓", lines[2])

    def test_table_lists_every_row_not_just_fifteen(self):
        many = [ranked_item(2, 50.0, False, ["x"]) for _ in range(40)]
        self.assertEqual(len(format_result_table(build_result_rows(many, CATALOG))), 41)


class SelectRowsTests(unittest.TestCase):
    def rows(self):
        items = [ranked_item(1, s, s + 10 >= 85, ["x"]) for s in (90, 80, 75, 60, 50)]
        return build_result_rows(items, CATALOG)

    def test_default_shows_everything(self):
        self.assertEqual(len(select_rows(self.rows(), DisplayOptions())), 5)

    def test_badged_only_keeps_only_badged_rows_with_their_rank(self):
        shown = select_rows(self.rows(), DisplayOptions(badged_only=True))
        self.assertEqual([row["rank"] for row in shown], [1, 2, 3])

    def test_top_limits_the_list(self):
        self.assertEqual(len(select_rows(self.rows(), DisplayOptions(top=2))), 2)

    def test_top_is_applied_after_badged_only(self):
        shown = select_rows(self.rows(), DisplayOptions(badged_only=True, top=2))
        self.assertEqual([row["rank"] for row in shown], [1, 2])

    def test_selecting_never_changes_the_full_list(self):
        rows = self.rows()
        select_rows(rows, DisplayOptions(badged_only=True, top=1))
        self.assertEqual(len(rows), 5)


class FilterReportTests(unittest.TestCase):
    counts = {"already watched": 9, "year range": 4, "IMDb rating floor": 30}

    def test_long_list_gets_counts_and_no_advice(self):
        lines = format_filter_report(self.counts, 100, 60)
        self.assertEqual(len(lines), 4)
        self.assertIn("- IMDb rating floor: removed 30", lines)
        self.assertFalse(any("relax" in line for line in lines))

    def test_short_list_names_the_strictest_preference_filter(self):
        advice = format_filter_report(self.counts, 100, 10)[-1]
        # Not "already watched": that is not a preference anyone can relax.
        self.assertIn("'IMDb rating floor'", advice)

    def test_short_list_with_no_preference_filter_hits_says_so(self):
        advice = format_filter_report({"already watched": 5, "year range": 0}, 8, 3)[-1]
        self.assertIn("stage 1 found few titles", advice)


class CsvTests(unittest.TestCase):
    def test_file_name_is_safe_and_dated(self):
        self.assertEqual(
            results_file_name("Dharun V.", date(2026, 1, 2)), "Dharun_V_2026-01-02.csv"
        )
        self.assertEqual(results_file_name("///", date(2026, 1, 2)), "persona_2026-01-02.csv")

    def test_csv_holds_the_full_ranked_list(self):
        rows = build_result_rows(RANKED, CATALOG)
        with tempfile.TemporaryDirectory() as folder:
            path = write_results_csv(rows, "Dharun", date(2026, 1, 2), os.path.join(folder, "r"))
            with open(path, encoding="utf-8", newline="") as file:
                saved = list(csv.DictReader(file))
            leftovers = os.listdir(os.path.dirname(path))
        self.assertEqual([row["title"] for row in saved], ["Movie 1", "Movie 2"])
        self.assertEqual(saved[0]["all_reasons"], "directed by Michael Mann | trending now")
        self.assertEqual(leftovers, ["Dharun_2026-01-02.csv"])  # no temp file left behind

    def test_unwritable_folder_raises_oserror_for_the_caller_to_handle(self):
        with tempfile.NamedTemporaryFile() as not_a_folder:
            with self.assertRaises(OSError):
                write_results_csv([], "Dharun", date(2026, 1, 2), not_a_folder.name)


if __name__ == "__main__":
    unittest.main()
