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
from config.weights import SIGNAL_HALF_LIFE_DAYS


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


if __name__ == "__main__":
    unittest.main()
