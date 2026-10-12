"""
tests/test_pipeline.py

Small smoke tests for the pieces of this project that do not need the
MovieLens dataset to be downloaded first, so these can run anywhere,
anytime, as a quick sanity check that the core logic has not broken.

Run with:  python -m pytest tests/test_pipeline.py
or simply: python -m unittest tests.test_pipeline
(run from the project root folder)
"""

import unittest
from datetime import datetime, timedelta

from src.user_profile.taste_score import decay_factor, update_dislike_score
from src.stage1_candidate_generation.merge_shortlist import merge
from src.exclusion_filter.exclude import exclude
from src.stage1_candidate_generation.content_based import generate as generate_content_based
from src.pipeline import build_dislike_scores
from config.weights import MIN_RATINGS_FOR_QUALITY_FLOOR, SIGNAL_HALF_LIFE_DAYS


class TestDecayFormula(unittest.TestCase):
    def test_half_life_cuts_score_in_half(self):
        factor = decay_factor(SIGNAL_HALF_LIFE_DAYS)
        self.assertAlmostEqual(factor, 0.5, places=3)

    def test_no_time_elapsed_means_no_decay(self):
        self.assertAlmostEqual(decay_factor(0), 1.0, places=6)

    def test_update_dislike_score_increases_with_new_signal(self):
        now = datetime.now()
        new_score, new_timestamp = update_dislike_score(
            old_score=0.0,
            old_score_timestamp=now - timedelta(days=10),
            event_type="explicit_thumbs_down",
            event_timestamp=now,
        )
        self.assertGreater(new_score, 0.0)
        self.assertEqual(new_timestamp, now)


class TestMergeShortlist(unittest.TestCase):
    def test_merge_deduplicates_same_movie_from_different_generators(self):
        generator_one_output = [{"movie_id": 1, "source": "content_based", "reason": "test"}]
        generator_two_output = [{"movie_id": 1, "source": "trending", "reason": "test"}]

        merged = merge([generator_one_output, generator_two_output])

        self.assertEqual(len(merged), 1)
        self.assertIn("content_based", merged[0]["sources"])
        self.assertIn("trending", merged[0]["sources"])


class TestQualityFloor(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            1: {"avg_rating": 4.2, "rating_count": 100},
            2: {"avg_rating": 2.4, "rating_count": 100},
            3: {"avg_rating": None, "rating_count": 0},
            4: {"avg_rating": 3.0, "rating_count": 100},
        }
        self.shortlist = [{"movie_id": movie_id} for movie_id in self.catalog]

    def test_floor_removes_low_rated_and_unrated_titles(self):
        user = {"watch_history": [], "min_avg_rating": 3.0}
        kept = [c["movie_id"] for c in exclude(self.shortlist, user, self.catalog)]
        self.assertEqual(kept, [1, 4])  # exactly at the floor is allowed

    def test_floor_removes_titles_with_too_few_ratings(self):
        # A perfect average from only two raters is not trustworthy.
        catalog = {
            1: {"avg_rating": 5.0, "rating_count": 2},
            2: {"avg_rating": 4.0, "rating_count": MIN_RATINGS_FOR_QUALITY_FLOOR},
        }
        shortlist = [{"movie_id": movie_id} for movie_id in catalog]
        user = {"watch_history": [], "min_avg_rating": 3.0}
        kept = [c["movie_id"] for c in exclude(shortlist, user, catalog)]
        self.assertEqual(kept, [2])  # exactly at the minimum count is allowed

    def test_no_floor_keeps_everything(self):
        user = {"watch_history": []}
        self.assertEqual(len(exclude(self.shortlist, user, self.catalog)), 4)


class TestContentBasedSpread(unittest.TestCase):
    def test_rare_genre_with_one_qualifying_title_still_gets_a_slot(self):
        # Twenty well rated titles carry all three of Action, Comedy and
        # Thriller, so in one shared list they would fill every slot.
        catalog = {
            movie_id: {
                "movie_id": movie_id,
                "genres": ["Action", "Comedy", "Thriller"],
                "rating_count": 500 - movie_id,
                "avg_rating": 4.0,
            }
            for movie_id in range(1, 21)
        }
        # The only Documentary with enough ratings, plus one with too few.
        catalog[100] = {"movie_id": 100, "genres": ["Documentary"], "rating_count": 25, "avg_rating": 3.5}
        catalog[101] = {"movie_id": 101, "genres": ["Documentary"], "rating_count": 3, "avg_rating": 5.0}
        user = {"watch_history": [], "preferred_genres": ["Action", "Comedy", "Thriller", "Documentary"]}

        picked_ids = [c["movie_id"] for c in generate_content_based(user, catalog, max_candidates=5)]

        self.assertIn(100, picked_ids)
        self.assertNotIn(101, picked_ids)  # too few ratings to qualify
        self.assertEqual(len(picked_ids), len(set(picked_ids)))  # no duplicates


class TestLikedNeutralDisliked(unittest.TestCase):
    """Leaving early is a dislike, stopping midway is neutral and creates no dislike."""

    def dislike_scores_for_completion(self, completion_pct):
        catalog = {1: {"genres": ["Drama"]}}
        entry = {"movie_id": 1, "completion_pct": completion_pct, "timestamp": datetime.now()}
        return build_dislike_scores({"watch_history": [entry]}, catalog)

    def test_midway_stop_creates_no_dislike_score(self):
        self.assertEqual(self.dislike_scores_for_completion(0.4), {})

    def test_early_exit_creates_a_dislike_score(self):
        self.assertGreater(self.dislike_scores_for_completion(0.1)["Drama"], 0.0)


class TestDislikeDecaysUpToToday(unittest.TestCase):
    AS_OF = datetime(2026, 1, 1)  # fixed, so these tests never depend on the clock

    def test_old_early_drop_off_has_faded_away(self):
        catalog = {1: {"genres": ["Drama"]}}
        year_ago = self.AS_OF - timedelta(days=365)
        entry = {"movie_id": 1, "completion_pct": 0.05, "timestamp": year_ago}
        scores = build_dislike_scores({"watch_history": [entry]}, catalog, as_of=self.AS_OF)
        self.assertLess(scores["Drama"], 0.1)

    def test_thumbs_down_today_keeps_full_strength(self):
        user = {"watch_history": [], "disliked_genres": ["Animation"]}
        scores = build_dislike_scores(user, catalog={}, as_of=self.AS_OF)
        self.assertAlmostEqual(scores["Animation"], 1.0, places=3)


class TestExplicitGenreDislike(unittest.TestCase):
    def test_disliked_genre_gets_a_full_strength_score(self):
        user = {"watch_history": [], "disliked_genres": ["Animation"]}
        scores = build_dislike_scores(user, catalog={})
        self.assertAlmostEqual(scores["Animation"], 1.0, places=3)

    def test_no_disliked_genres_means_no_scores(self):
        self.assertEqual(build_dislike_scores({"watch_history": []}, catalog={}), {})


if __name__ == "__main__":
    unittest.main()
