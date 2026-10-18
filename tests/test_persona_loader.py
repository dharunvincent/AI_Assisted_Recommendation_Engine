"""
tests/test_persona_loader.py

Phase 2 tests, one group per failure level (see src/run_warnings.py):
level 1 stops the run, level 2 warns and continues, level 3 counts quietly.
All data is tiny and made by hand, nothing is downloaded.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime

from src.pipeline import run_persona_file
from src.run_warnings import count_missing_movie_data, format_warning_section
from src.user_profile.persona_loader import (
    build_persona_result,
    load_persona_file,
    normalize_title,
)

NOW = datetime(2024, 1, 1)


def make_movie(movie_id, title, genres, directors=(), cast=(), rating=7.5, count=100):
    return {
        "movie_id": movie_id, "title": title, "year": 1995, "genres": list(genres),
        "rating_count": count, "avg_rating": 4.0,
        "imdb_rating": rating, "imdb_votes": 5000 if rating else None,
        "directors": list(directors), "cast": list(cast),
    }


def make_catalog():
    return {
        1: make_movie(1, "Heat", ["Action", "Crime"], ["Michael Mann"], ["Al Pacino"], count=500),
        2: make_movie(2, "Heat", ["Horror"], ["Jerry Jameson"], [], count=5),
        3: make_movie(
            3, "Usual Suspects, The", ["Crime", "Thriller"], ["Bryan Singer"], ["Kevin Spacey"]
        ),
        4: make_movie(
            4, "Inception", ["Action", "Thriller"], ["Christopher Nolan"], [], rating=None
        ),
        5: make_movie(5, "Cars", ["Animation"], ["John Lasseter"], ["Owen Wilson"]),
    }


def valid_data(**changes):
    data = {"name": "Test", "liked_genres": ["Action"]}
    data.update(changes)
    return data


def build(data, catalog=None):
    return build_persona_result(data, catalog or make_catalog(), NOW)


class Level1StopTests(unittest.TestCase):
    """Results would be meaningless, so there is an error and no user."""

    def assert_stops_with(self, result, text):
        self.assertIsNone(result.user)
        self.assertTrue(any(text in error for error in result.errors), result.errors)

    def test_missing_name(self):
        self.assert_stops_with(build({"liked_genres": ["Action"]}), "'name' is missing")

    def test_no_valid_liked_genre_lists_valid_ones(self):
        result = build(valid_data(liked_genres=["Sci Fi"]))
        self.assert_stops_with(result, "no valid genre left")
        self.assert_stops_with(result, "Valid genres: Action, Animation")

    def test_backwards_year_range(self):
        self.assert_stops_with(build(valid_data(year_from=2000, year_to=1990)), "bigger than")

    def test_rating_outside_zero_to_ten(self):
        self.assert_stops_with(build(valid_data(min_imdb_rating=10.5)), "between 0 and 10")

    def test_wrong_type_is_a_clear_error_not_a_crash(self):
        self.assert_stops_with(build(valid_data(year_from="1990")), "must be a whole number")
        self.assert_stops_with(build(valid_data(liked_genres="Action")), "must be a list")

    def test_unreadable_and_invalid_json_files(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = os.path.join(folder, "bad.json")
            with open(bad, "w") as file:
                file.write("{not json")
            self.assert_stops_with(load_persona_file(bad, make_catalog()), "not valid JSON")
            missing = os.path.join(folder, "nope.json")
            self.assert_stops_with(load_persona_file(missing, make_catalog()), "Cannot read")

    def test_pipeline_returns_exit_code_1_and_prints_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "p.json")
            with open(path, "w") as file:
                json.dump({"liked_genres": []}, file)
            self.assertEqual(run_persona_file(path, make_catalog(), {}), 1)


class Level2WarnAndContinueTests(unittest.TestCase):
    """One preference cannot be used: skip it, warn, keep going."""

    def test_unknown_genre_is_dropped_and_valid_ones_kept(self):
        result = build(valid_data(liked_genres=["action", "Foo"], disliked_genres=["Bar"]))
        self.assertEqual(result.user["preferred_genres"], ["Action"])
        self.assertEqual(result.user["disliked_genres"], [])
        self.assertEqual(len([w for w in result.warnings if "Unknown genre" in w]), 2)

    def test_misspelled_director_gets_did_you_mean(self):
        result = build(valid_data(preferred_directors=["Chris Nolan", "michael mann"]))
        self.assertEqual(result.user["preferred_directors"], ["Michael Mann"])
        self.assertTrue(any("Did you mean Christopher Nolan" in w for w in result.warnings))

    def test_unknown_favourite_is_skipped_with_close_matches(self):
        result = build(valid_data(favourite_titles=["Heet", "Usual Suspects"]))
        self.assertTrue(any("'Heet'" in w and "Heat" in w for w in result.warnings))
        history_ids = [entry["movie_id"] for entry in result.user["watch_history"]]
        self.assertEqual(history_ids, [3])

    def test_duplicate_title_uses_most_rated_and_says_so(self):
        result = build(valid_data(favourite_titles=["Heat"]))
        self.assertEqual(result.user["watch_history"][0]["movie_id"], 1)
        self.assertTrue(any("2 movies are called 'Heat'" in w for w in result.warnings))

    def test_favourites_become_finished_recent_watches(self):
        result = build(valid_data(favourite_titles=["The Usual Suspects", "Inception"]))
        history = result.user["watch_history"]
        self.assertEqual([entry["movie_id"] for entry in history], [3, 4])
        self.assertTrue(all(entry["completion_pct"] == 0.95 for entry in history))
        self.assertTrue(all(entry["timestamp"] < NOW for entry in history))

    def test_no_favourites_reuses_genre_history_builder(self):
        # The builder only picks well rated Action titles with 50 or more ratings:
        # Heat (500) and Inception (100) qualify, the Horror "Heat" (5) does not.
        result = build(valid_data())
        self.assertEqual({e["movie_id"] for e in result.user["watch_history"]}, {1, 4})

    def test_missing_imdb_data_skips_imdb_fields_with_one_warning(self):
        catalog = make_catalog()
        for movie in catalog.values():
            movie.update({"imdb_rating": None, "imdb_votes": None, "directors": [], "cast": []})
        result = build(valid_data(min_imdb_rating=7.0, preferred_directors=["Michael Mann"],
                                  avoided_cast=["Al Pacino"], year_from=1990), catalog)
        imdb_warnings = [w for w in result.warnings if "IMDb data is not downloaded" in w]
        self.assertEqual(len(imdb_warnings), 1)
        self.assertIsNone(result.user["min_imdb_rating"])
        self.assertEqual(result.user["preferred_directors"], [])
        self.assertEqual(result.user["year_from"], 1990)  # MovieLens only, still works

    def test_valid_file_gives_pipeline_ready_user_dict(self):
        user = build(valid_data(min_imdb_rating=7, year_to=2000)).user
        for key in ["user_id", "name", "preferred_genres", "disliked_genres", "age_group",
                    "taste_summary", "watch_history", "hard_blocked_movie_ids", "current_session"]:
            self.assertIn(key, user)
        self.assertIsNone(user["min_avg_rating"])  # replaced by the IMDb floor
        self.assertEqual(user["min_imdb_rating"], 7)


class Level3CountQuietlyTests(unittest.TestCase):
    """Single movies with missing data are counted, never one line each."""

    def test_missing_data_counted_only_for_requested_kinds(self):
        counts = count_missing_movie_data(make_catalog(), ["rating", "cast"])
        self.assertEqual(counts, {"rating": 1, "cast": 2})

    def test_warning_section_groups_and_counts(self):
        lines = format_warning_section(["same", "same", "other"], {"cast": 312, "rating": 0})
        self.assertEqual(lines, [
            "Warnings:", "- same (x2)", "- other", "- 312 titles had no cast data",
        ])

    def test_clean_run_prints_no_warning_section(self):
        self.assertEqual(format_warning_section([], {"cast": 0}), [])

    def test_movies_with_no_cast_never_crash_the_loader(self):
        result = build(valid_data(preferred_cast=["Al Pacino"]))
        self.assertIsNotNone(result.user)


class TitleMatchingTests(unittest.TestCase):
    def test_moved_article_and_alternative_title_match(self):
        self.assertEqual(
            normalize_title("Usual Suspects, The"), normalize_title("The Usual Suspects")
        )
        self.assertEqual(normalize_title("Léon: The Professional (a.k.a. Léon)"),
                         normalize_title("leon the professional"))


if __name__ == "__main__":
    unittest.main()
