"""
tests/test_hard_filters.py

Phase 3 tests: each hard filter removes exactly the right titles, and does
nothing when the persona has not set it. Tiny hand made data, no downloads.
"""

import unittest

from src.exclusion_filter.exclude import apply_hard_filters, build_removal_check, exclude


def movie(movie_id, year=2000, rating=8.0, votes=5000, directors=(), cast=(),
          avg_rating=4.0, rating_count=100):
    return {
        "movie_id": movie_id, "year": year, "imdb_rating": rating, "imdb_votes": votes,
        "directors": list(directors), "cast": list(cast),
        "avg_rating": avg_rating, "rating_count": rating_count,
    }


def user(**changes):
    base = {"watch_history": []}
    base.update(changes)
    return base


def kept_ids(catalog_movies, persona):
    catalog = {m["movie_id"]: m for m in catalog_movies}
    shortlist = [{"movie_id": movie_id} for movie_id in catalog]
    return [c["movie_id"] for c in exclude(shortlist, persona, catalog)]


class YearRangeTests(unittest.TestCase):
    movies = [movie(1, year=1985), movie(2, year=1990), movie(3, year=2018),
              movie(4, year=2019), movie(5, year=None)]

    def test_removes_titles_outside_both_ends_and_unknown_years(self):
        self.assertEqual(kept_ids(self.movies, user(year_from=1990, year_to=2018)), [2, 3])

    def test_one_open_end_only_checks_the_other(self):
        self.assertEqual(kept_ids(self.movies, user(year_to=1990)), [1, 2])
        self.assertEqual(kept_ids(self.movies, user(year_from=2018)), [3, 4])


class ImdbFloorTests(unittest.TestCase):
    movies = [
        movie(1, rating=8.0, votes=5000),   # passes
        movie(2, rating=6.9, votes=5000),   # too low
        movie(3, rating=9.5, votes=999),    # too few voters to trust
        movie(4, rating=7.0, votes=1000),   # exactly on both limits, passes
        movie(5, rating=None, votes=None),  # no rating: removed, it is the user's rule
    ]

    def test_floor_removes_low_few_vote_and_unrated_titles(self):
        self.assertEqual(kept_ids(self.movies, user(min_imdb_rating=7.0)), [1, 4])

    def test_without_the_floor_nothing_is_removed(self):
        self.assertEqual(kept_ids(self.movies, user()), [1, 2, 3, 4, 5])

    def test_imdb_floor_replaces_movielens_floor_when_only_imdb_is_set(self):
        low_movielens = [
            movie(1, rating=8.0, avg_rating=2.0), movie(2, rating=8.0, avg_rating=4.5)
        ]
        persona = user(min_imdb_rating=7.0, min_avg_rating=None)
        self.assertEqual(kept_ids(low_movielens, persona), [1, 2])
        self.assertEqual(kept_ids(low_movielens, user(min_avg_rating=3.0)), [2])


class AvoidedPeopleTests(unittest.TestCase):
    movies = [
        movie(1, directors=["Uwe Boll"]),
        movie(2, cast=["Nic Cage", "Someone"]),
        movie(3, directors=["Michael Mann"], cast=["Al Pacino"]),
        movie(4),  # no people data at all: unknown, so it is not removed
    ]

    def test_avoided_director_removes_only_their_titles(self):
        self.assertEqual(kept_ids(self.movies, user(avoided_directors=["Uwe Boll"])), [2, 3, 4])

    def test_avoided_cast_removes_only_their_titles(self):
        self.assertEqual(kept_ids(self.movies, user(avoided_cast=["Nic Cage"])), [1, 3, 4])

    def test_empty_avoid_lists_remove_nothing(self):
        persona = user(avoided_directors=[], avoided_cast=[])
        self.assertEqual(kept_ids(self.movies, persona), [1, 2, 3, 4])


class DislikedGenresStaySoftTests(unittest.TestCase):
    def test_disliked_genre_is_not_a_hard_filter(self):
        animated = movie(1)
        animated["genres"] = ["Animation"]
        self.assertEqual(kept_ids([animated], user(disliked_genres=["Animation"])), [1])


class RemovalCheckTests(unittest.TestCase):
    def test_check_agrees_with_the_filters_title_by_title(self):
        movies = [movie(1, year=1980), movie(2, rating=5.0), movie(3), movie(4, cast=["X"])]
        persona = user(year_from=1990, min_imdb_rating=7.0, avoided_cast=["X"])
        would_remove = build_removal_check(persona)
        removed = [m["movie_id"] for m in movies if would_remove(m["movie_id"], m)]
        self.assertEqual(removed, [1, 2, 4])
        self.assertEqual(kept_ids(movies, persona), [3])

    def test_check_removes_nothing_for_a_user_with_no_rules(self):
        self.assertFalse(build_removal_check(user())(1, movie(1)))


class FilterRulesTests(unittest.TestCase):
    def test_filters_only_remove_and_keep_the_input_order(self):
        movies = [movie(n, year=1990 + n) for n in range(5, 0, -1)]
        persona = user(year_from=1993)
        kept = kept_ids(movies, persona)
        self.assertEqual(kept, [5, 4, 3])  # same relative order as the input
        self.assertTrue(set(kept) <= {m["movie_id"] for m in movies})

    def test_counts_cover_only_active_rules_and_count_each_rule_alone(self):
        movies = [movie(1, year=1980, rating=5.0), movie(2, year=1980), movie(3, rating=5.0),
                  movie(4)]
        catalog = {m["movie_id"]: m for m in movies}
        shortlist = [{"movie_id": movie_id} for movie_id in catalog]
        outcome = apply_hard_filters(shortlist, user(year_from=1990, min_imdb_rating=7.0), catalog)
        self.assertEqual([c["movie_id"] for c in outcome.kept], [4])
        self.assertEqual(outcome.removed_counts["year range"], 2)
        self.assertEqual(outcome.removed_counts["IMDb rating floor"], 2)  # title 1 counted by both
        self.assertNotIn("avoided cast", outcome.removed_counts)

    def test_watched_and_blocked_titles_are_still_removed(self):
        movies = [movie(1), movie(2), movie(3)]
        persona = user(watch_history=[{"movie_id": 1}], hard_blocked_movie_ids=[2])
        self.assertEqual(kept_ids(movies, persona), [3])


if __name__ == "__main__":
    unittest.main()
