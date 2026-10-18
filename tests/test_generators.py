"""
tests/test_generators.py

Tests for the stage 1 generator fixes: content based (users with no declared
genres), diversity and context aware. Each uses a tiny made up catalog, so
the real MovieLens download is not needed.

Run with:  python3 -m unittest tests.test_generators
"""

import unittest

from config.weights import (
    MIN_RATINGS_FOR_CONTENT_BASED, LIKED_COMPLETION_THRESHOLD,
    DIVERSITY_MIN_AVG_RATING, DIVERSITY_MIN_RATINGS,
)
from src.stage1_candidate_generation import content_based, context_aware, diversity

ENOUGH = MIN_RATINGS_FOR_CONTENT_BASED


def movie(movie_id, genres, rating_count=ENOUGH, avg_rating=4.0):
    return {
        "movie_id": movie_id, "title": f"Movie {movie_id}", "year": 2000,
        "genres": genres, "rating_count": rating_count, "avg_rating": avg_rating,
    }


def catalog_of(*movies):
    # Insertion order is the "catalog file order" the old code relied on.
    return {m["movie_id"]: m for m in movies}


def user_with_history(*movie_ids):
    return {
        "watch_history": [
            {"movie_id": m, "completion_pct": LIKED_COMPLETION_THRESHOLD} for m in movie_ids
        ],
    }


class TestContentBasedInferredGenres(unittest.TestCase):
    def setUp(self):
        # Movie 1 is the watched title that makes Action, Crime, Drama the favourites.
        self.watched = movie(1, ["Action", "Crime", "Drama"])

    def ids(self, *others, max_candidates=15):
        catalog = catalog_of(self.watched, *others)
        found = content_based.generate(user_with_history(1), catalog, max_candidates)
        return [c["movie_id"] for c in found]

    def test_titles_with_too_few_ratings_are_dropped(self):
        self.assertEqual(self.ids(movie(2, ["Action"], rating_count=ENOUGH - 1)), [])

    def test_more_genre_overlap_comes_first_whatever_the_file_order(self):
        one = movie(2, ["Action"], rating_count=5000)
        three = movie(3, ["Action", "Crime", "Drama"], rating_count=ENOUGH)
        two = movie(4, ["Action", "Crime"], rating_count=900)
        self.assertEqual(self.ids(one, three, two), [3, 4, 2])

    def test_same_overlap_is_sorted_by_rating_count_then_average(self):
        few = movie(2, ["Action"], rating_count=30, avg_rating=4.9)
        many = movie(3, ["Action"], rating_count=300, avg_rating=3.0)
        tie_low = movie(4, ["Action"], rating_count=100, avg_rating=3.1)
        tie_high = movie(5, ["Action"], rating_count=100, avg_rating=4.2)
        self.assertEqual(self.ids(few, many, tie_low, tie_high), [3, 5, 4, 2])

    def test_overlap_is_counted_from_the_genres_not_the_reason_text(self):
        # A genre name containing a comma would fool a comma count in the reason.
        odd = movie(2, ["Action", "Crime"])
        plain = movie(3, ["Action"], rating_count=10_000)
        self.assertEqual(self.ids(plain, odd), [2, 3])

    def test_the_list_is_cut_to_max_candidates_after_sorting(self):
        titles = [movie(10 + n, ["Action"], rating_count=ENOUGH + n) for n in range(5)]
        self.assertEqual(self.ids(*titles, max_candidates=2), [14, 13])


class TestDiversity(unittest.TestCase):
    def offered_ids(self, *others):
        catalog = catalog_of(movie(1, ["Action"]), *others)
        found = diversity.generate(user_with_history(1), catalog, max_candidates=50, random_seed=1)
        return {c["movie_id"] for c in found}

    def test_a_well_rated_title_with_too_few_ratings_is_never_offered(self):
        lucky = movie(2, ["Horror"], rating_count=DIVERSITY_MIN_RATINGS - 1, avg_rating=5.0)
        solid = movie(3, ["Horror"], rating_count=DIVERSITY_MIN_RATINGS, avg_rating=DIVERSITY_MIN_AVG_RATING)
        self.assertEqual(self.offered_ids(lucky, solid), {3})

    def test_the_other_rules_still_hold(self):
        seen_genre = movie(2, ["Action"], avg_rating=4.5)
        low_average = movie(3, ["Horror"], avg_rating=DIVERSITY_MIN_AVG_RATING - 0.1)
        self.assertEqual(self.offered_ids(seen_genre, low_average), set())


class TestContextAware(unittest.TestCase):
    def ids(self, context, *titles, max_candidates=15):
        found = context_aware.generate(user_with_history(1), catalog_of(movie(1, ["Mystery"]), *titles),
                                       context, max_candidates)
        return [c["movie_id"] for c in found]

    def test_obscure_titles_are_dropped_and_known_ones_come_first(self):
        saturday = {"day_of_week": "Saturday", "time_of_day": "daytime"}
        obscure_first = movie(2, ["Comedy"], rating_count=ENOUGH - 1)
        small = movie(3, ["Comedy"], rating_count=ENOUGH)
        big_low = movie(4, ["Family"], rating_count=500, avg_rating=3.0)
        big_high = movie(5, ["Family"], rating_count=500, avg_rating=4.5)
        self.assertEqual(self.ids(saturday, obscure_first, small, big_low, big_high), [5, 4, 3])

    def test_friday_evening_uses_the_weekend_evening_genres(self):
        action = movie(2, ["Sci-Fi"])
        drama = movie(3, ["Drama"])  # a weekday evening genre only
        self.assertEqual(self.ids({"day_of_week": "Friday", "time_of_day": "evening"}, action, drama), [2])

    def test_friday_daytime_and_thursday_evening_stay_weekdays(self):
        action = movie(2, ["Sci-Fi"])
        drama = movie(3, ["Drama"])
        self.assertEqual(self.ids({"day_of_week": "Thursday", "time_of_day": "evening"}, action, drama), [3])
        comedy = movie(4, ["Comedy"])
        self.assertEqual(self.ids({"day_of_week": "Friday", "time_of_day": "daytime"}, action, comedy), [4])


if __name__ == "__main__":
    unittest.main()
