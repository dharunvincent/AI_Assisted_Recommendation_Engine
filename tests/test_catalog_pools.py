"""
tests/test_catalog_pools.py

Tests for the shared "enough ratings to trust" helper and for the rule it
exists to enforce: no stage 1 generator that picks titles from the catalog can
ever offer a title with too few ratings. Tiny made up catalogs, no download.

Run with:  python3 -m unittest tests.test_catalog_pools
"""

import unittest

from config.weights import MIN_RATINGS_TO_TRUST, RATING_SHRINKAGE_STRENGTH
from src.catalog_pools import NEUTRAL_RATING, catalog_mean_rating, is_trusted, shrunk_rating, trusted_titles
from src.stage1_candidate_generation import (
    collaborative, content_based, context_aware, demographic, diversity, session_based, trending,
)

ALL_GENRES = ["Mystery", "Horror", "Drama", "Action", "Comedy", "Crime", "Sci-Fi", "Thriller", "Adventure", "Family"]


def movie(movie_id, rating_count, avg_rating, genres=None):
    return {
        "movie_id": movie_id, "title": f"M{movie_id}", "year": 2000,
        "genres": genres or ALL_GENRES, "rating_count": rating_count, "avg_rating": avg_rating,
    }


class TestTrustedTitles(unittest.TestCase):
    def ids(self, *movies, excluded=()):
        catalog = {m["movie_id"]: m for m in movies}
        return [m["movie_id"] for m in trusted_titles(catalog, excluded)]

    def test_title_below_the_minimum_is_left_out(self):
        self.assertEqual(self.ids(movie(1, MIN_RATINGS_TO_TRUST - 1, 5.0), movie(2, MIN_RATINGS_TO_TRUST, 3.0)), [2])

    def test_title_with_no_average_is_left_out(self):
        self.assertEqual(self.ids(movie(1, 500, None)), [])

    def test_best_known_first_and_average_breaks_ties(self):
        self.assertEqual(self.ids(movie(1, 30, 4.9), movie(2, 300, 3.0), movie(3, 100, 3.1), movie(4, 100, 4.2)), [2, 4, 3, 1])

    def test_excluded_ids_are_left_out(self):
        self.assertEqual(self.ids(movie(1, 50, 4.0), movie(2, 60, 4.0), excluded={2}), [1])

    def test_every_returned_title_is_trusted(self):
        # Rule: nothing returned can be a one-rater fluke, whatever the mix.
        catalog = {n: movie(n, n * 3, 1.0 + (n % 5)) for n in range(1, 40)}
        self.assertTrue(all(is_trusted(m) for m in trusted_titles(catalog)))

    def test_empty_catalog_gives_an_empty_list(self):
        self.assertEqual(trusted_titles({}), [])


class TestShrunkRating(unittest.TestCase):
    PRIOR = 3.5

    def test_no_raters_gives_the_prior(self):
        self.assertEqual(shrunk_rating(5.0, 0, self.PRIOR), self.PRIOR)

    def test_missing_average_gives_the_prior(self):
        self.assertEqual(shrunk_rating(None, 100, self.PRIOR), self.PRIOR)

    def test_a_huge_crowd_gives_almost_its_own_average(self):
        self.assertAlmostEqual(shrunk_rating(4.4, 10_000_000, self.PRIOR), 4.4, places=4)

    def test_one_perfect_rating_stays_near_the_middle(self):
        self.assertLess(shrunk_rating(5.0, 1, self.PRIOR), 3.8)

    def test_half_way_at_the_shrinkage_strength(self):
        self.assertAlmostEqual(shrunk_rating(4.5, RATING_SHRINKAGE_STRENGTH, 3.5), 4.0)

    def test_always_between_the_prior_and_the_own_average_and_closer_with_more_raters(self):
        # Rules: stays between the two, and each extra rater can only move it toward the own average.
        for own in (1.0, 2.5, 3.5, 4.4, 5.0):
            previous_gap = abs(own - self.PRIOR)
            for count in (1, 2, 5, 20, 100, 1000):
                result = shrunk_rating(own, count, self.PRIOR)
                low, high = sorted((own, self.PRIOR))
                self.assertTrue(low - 1e-9 <= result <= high + 1e-9)
                gap = abs(own - result)
                self.assertLessEqual(gap, previous_gap + 1e-9)
                previous_gap = gap

    def test_prior_is_the_rating_weighted_catalog_average(self):
        catalog = {1: movie(1, 100, 4.0), 2: movie(2, 300, 2.0)}
        self.assertAlmostEqual(catalog_mean_rating(catalog), 2.5)

    def test_prior_without_any_ratings_is_the_neutral_rating(self):
        self.assertEqual(catalog_mean_rating({}), NEUTRAL_RATING)
        self.assertEqual(catalog_mean_rating({1: movie(1, 0, None)}), NEUTRAL_RATING)


class TestNoGeneratorPicksAThinlyRatedTitle(unittest.TestCase):
    FLUKE, SOLID, WATCHED = 10, 11, 1

    def setUp(self):
        watched = movie(self.WATCHED, 500, 4.0, ["Mystery"])
        # One rater, a perfect 5.0, and every genre every generator looks for.
        self.catalog = {
            self.WATCHED: watched,
            self.FLUKE: movie(self.FLUKE, 1, 5.0),
            self.SOLID: movie(self.SOLID, 300, 4.5),
        }
        self.user = {
            "age_group": "25 to 34",
            "preferred_genres": [],
            "watch_history": [{"movie_id": self.WATCHED, "completion_pct": 0.95}],
            "current_session": [self.WATCHED],
        }
        self.context = {"day_of_week": "Saturday", "time_of_day": "daytime"}

    def picked(self, generator_name):
        user, catalog = self.user, self.catalog
        if generator_name == "demographic":
            found = demographic.generate(user, catalog)
        elif generator_name == "trending":
            found = trending.generate(user, catalog)
        elif generator_name == "context_aware":
            found = context_aware.generate(user, catalog, self.context)
        elif generator_name == "content_based_inferred":
            found = content_based.generate(user, catalog)
        elif generator_name == "content_based_declared":
            found = content_based.generate({**user, "preferred_genres": ["Mystery", "Drama"]}, catalog)
        elif generator_name == "session_based":
            found = session_based.generate(user, catalog)
        elif generator_name == "collaborative":
            table = {self.WATCHED: {self.FLUKE: 0.9, self.SOLID: 0.5}}
            found = collaborative.generate(user, catalog, similarity_table=table)
        else:
            raise AssertionError(generator_name)
        return {c["movie_id"] for c in found}

    def test_the_one_rating_title_is_never_picked_but_the_solid_one_is(self):
        for name in ["demographic", "trending", "context_aware", "content_based_inferred",
                     "content_based_declared", "session_based", "collaborative"]:
            with self.subTest(generator=name):
                picked = self.picked(name)
                self.assertNotIn(self.FLUKE, picked)
                self.assertIn(self.SOLID, picked)  # proves the test is not passing because nothing is picked

    def test_diversity_never_picks_it_either(self):
        # Diversity wants genres the user has not touched, so give it its own catalog.
        catalog = {
            self.WATCHED: movie(self.WATCHED, 500, 4.0, ["Action"]),
            self.FLUKE: movie(self.FLUKE, 1, 5.0, ["Horror"]),
            self.SOLID: movie(self.SOLID, 300, 4.5, ["Horror"]),
        }
        found = diversity.generate(self.user, catalog, max_candidates=10, random_seed=3)
        picked = {c["movie_id"] for c in found}
        self.assertEqual(picked, {self.SOLID})

    def test_collaborative_keeps_its_strength_scale_after_dropping_a_thin_title(self):
        table = {self.WATCHED: {self.FLUKE: 0.9, self.SOLID: 0.45}}
        found = collaborative.generate(self.user, self.catalog, similarity_table=table)
        self.assertEqual([c["movie_id"] for c in found], [self.SOLID])
        self.assertEqual(found[0]["collab_strength"], 1.0)  # the best KEPT pick is the scale

    def test_demographic_with_the_old_bug_shape(self):
        # The original bug: only the average decided, so a single 5.0 rating won.
        catalog = {n: movie(n, 300, 3.5, ["Drama"]) for n in range(20, 40)}
        catalog[self.FLUKE] = movie(self.FLUKE, 1, 5.0, ["Drama"])
        found = demographic.generate({**self.user, "watch_history": []}, catalog, max_candidates=5)
        self.assertNotIn(self.FLUKE, {c["movie_id"] for c in found})


if __name__ == "__main__":
    unittest.main()
