"""
tests/test_imdb_data.py

Phase 1 tests. All data is tiny and made by hand, nothing is downloaded.
"""

import csv
import gzip
import os
import tempfile
import unittest

from data import download_imdb
from src.catalog import load_catalog


def _write_gz(path, lines):
    with gzip.open(path, "wt", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


class ImdbIdTests(unittest.TestCase):
    def test_links_id_gets_tt_prefix_and_keeps_leading_zeros(self):
        self.assertEqual(download_imdb.imdb_id_from_link("0114709"), "tt0114709")

    def test_short_id_is_padded_to_seven_digits(self):
        self.assertEqual(download_imdb.imdb_id_from_link("42"), "tt0000042")


class StreamingReadTests(unittest.TestCase):
    def test_cast_keeps_top_five_billed_actors_only(self):
        header = "tconst\tordering\tnconst\tcategory\tjob\tcharacters"
        lines = [header, "tt1\t1\tnm9\twriter\t\\N\t\\N"]
        lines += [f"tt1\t{n}\tnm{n}\tactor\t\\N\t\\N" for n in (7, 3, 1, 2, 4, 5, 6)]
        lines += ["tt2\t1\tnm1\tactor\t\\N\t\\N"]  # not wanted
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "p.tsv.gz")
            _write_gz(path, lines)
            cast = download_imdb.read_cast_ids(path, {"tt1"})
        self.assertEqual(cast, {"tt1": ["nm1", "nm2", "nm3", "nm4", "nm5"]})

    def test_actor_playing_two_roles_takes_one_cast_slot(self):
        people = [(1, "nm1"), (2, "nm1"), (3, "nm2")]
        self.assertEqual(download_imdb._top_billed_people(people), ["nm1", "nm2"])

    def test_movie_with_no_directors_listed_is_left_out(self):
        lines = ["tconst\tdirectors\twriters", "tt1\t\\N\t\\N", "tt2\tnm1,nm2\t\\N"]
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "c.tsv.gz")
            _write_gz(path, lines)
            directors = download_imdb.read_director_ids(path, {"tt1", "tt2"})
        self.assertEqual(directors, {"tt2": ["nm1", "nm2"]})


class BuildRowsTests(unittest.TestCase):
    def test_movie_without_rating_is_kept_and_counted(self):
        links = {"tt1": [10], "tt2": [20], "tt3": [30]}
        rows, summary = download_imdb.build_enriched_rows(
            links, {"tt1": (8.1, 5000)}, {"tt2": ["nm1"]}, {}, {"nm1": "Ann"}
        )
        self.assertEqual([row["movieId"] for row in rows], [10, 20])  # tt3 unknown to IMDb
        self.assertEqual(rows[1]["imdb_rating"], "")
        self.assertEqual(rows[1]["directors"], "Ann")
        self.assertEqual((summary.matched, summary.no_rating), (2, 1))


class CatalogImdbFieldsTests(unittest.TestCase):
    def test_catalog_has_empty_imdb_fields_when_file_is_missing(self):
        catalog = load_catalog(imdb_path="/no/such/file.csv")
        movie = next(iter(catalog.values()))
        self.assertIsNone(movie["imdb_rating"])
        self.assertEqual((movie["directors"], movie["cast"]), ([], []))

    def test_catalog_reads_imdb_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "imdb.csv")
            with open(path, "w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(download_imdb.OUTPUT_COLUMNS)
                writer.writerow([1, 8.3, 900000, "A|B", "C|D"])
                writer.writerow([2, "", "", "", ""])
            catalog = load_catalog(imdb_path=path)
        self.assertEqual(catalog[1]["imdb_rating"], 8.3)
        self.assertEqual(catalog[1]["directors"], ["A", "B"])
        self.assertIsNone(catalog[2]["imdb_rating"])
        self.assertEqual(catalog[2]["cast"], [])


if __name__ == "__main__":
    unittest.main()
