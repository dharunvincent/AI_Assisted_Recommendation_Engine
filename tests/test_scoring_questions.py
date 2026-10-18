"""
tests/test_scoring_questions.py

Tests for the hints stage 2 builds in src/stage2_jev_ranking/scoring_questions.py.
Tiny made up movies, no download needed.

Run with:  python3 -m unittest tests.test_scoring_questions
"""

import unittest

from config.weights import (
    OVERRIDE_BIAS_STRONG_FIT,
    OVERRIDE_BIAS_WEAK_FIT,
    OVERRIDE_MIN_GENRE_OVERLAP,
    OVERRIDE_STANDOUT_RATING,
    MIN_RATINGS_FOR_QUALITY_FLOOR,
    CONTEXT_BIAS_MATCHES_BUCKET,
    CONTEXT_BIAS_DEFAULT,
)
from src.stage1_candidate_generation.context_aware import genres_for_context
from src.stage2_jev_ranking.scoring_questions import build_questions, context_taste_bias, is_strong_override_fit

ENOUGH = MIN_RATINGS_FOR_QUALITY_FLOOR
CONTEXT = {"time_of_day": "evening", "day_of_week": "Friday"}  # weekend evening bucket


def movie(avg_rating, rating_count=ENOUGH):
    return {"title": "T", "avg_rating": avg_rating, "rating_count": rating_count, "genres": ["Animation"]}


def override_hint(a_movie, overlap, dislike_penalty=1.0):
    questions = build_questions(a_movie, {"sources": ["test"]}, CONTEXT, dislike_penalty, overlap)
    return questions["dislike_override"].bias_hint


class TestStrongOverrideFit(unittest.TestCase):
    def test_toy_story_like_title_is_not_a_strong_fit(self):
        # Toy Story: 3.92 average, 215 ratings, shares 2 liked genres. Used to count as strong.
        self.assertFalse(is_strong_override_fit(movie(3.92, 215), OVERRIDE_MIN_GENRE_OVERLAP))
        self.assertEqual(override_hint(movie(3.92, 215), 2), OVERRIDE_BIAS_WEAK_FIT)

    def test_standout_title_with_enough_shared_genres_is_strong(self):
        self.assertTrue(is_strong_override_fit(movie(OVERRIDE_STANDOUT_RATING), OVERRIDE_MIN_GENRE_OVERLAP))
        self.assertEqual(override_hint(movie(4.5), 2), OVERRIDE_BIAS_STRONG_FIT)

    def test_standout_rating_alone_is_not_enough(self):
        self.assertFalse(is_strong_override_fit(movie(4.6), OVERRIDE_MIN_GENRE_OVERLAP - 1))

    def test_just_below_the_standout_rating_is_not_strong(self):
        self.assertFalse(is_strong_override_fit(movie(OVERRIDE_STANDOUT_RATING - 0.01), 3))

    def test_standout_average_from_too_few_raters_is_not_strong(self):
        self.assertFalse(is_strong_override_fit(movie(5.0, ENOUGH - 1), 3))

    def test_missing_rating_is_not_strong(self):
        self.assertFalse(is_strong_override_fit(movie(None), 3))

    def test_no_dislike_penalty_gives_the_weak_hint_even_for_a_standout(self):
        self.assertEqual(override_hint(movie(4.6), 3, dislike_penalty=0.0), OVERRIDE_BIAS_WEAK_FIT)


class TestContextBias(unittest.TestCase):
    def test_title_with_a_bucket_genre_gets_the_high_bias(self):
        self.assertEqual(context_taste_bias({"genres": ["Sci-Fi", "Drama"]}, CONTEXT), CONTEXT_BIAS_MATCHES_BUCKET)

    def test_title_without_a_bucket_genre_gets_the_default_bias(self):
        self.assertEqual(context_taste_bias({"genres": ["Documentary"]}, CONTEXT), CONTEXT_BIAS_DEFAULT)

    def test_which_generator_found_the_title_makes_no_difference(self):
        a_movie = {"title": "T", "avg_rating": 3.0, "genres": ["Documentary"]}
        for sources in (["context_aware"], ["trending"], ["context_aware", "collaborative"]):
            questions = build_questions(a_movie, {"sources": sources}, CONTEXT, 0.0, 0)
            self.assertEqual(questions["context_fit"].bias_hint, CONTEXT_BIAS_DEFAULT)

    def test_bias_follows_the_bucket_the_generator_uses(self):
        # Same bucket logic as the generator: Friday evening is weekend evening, daytime is not.
        daytime = {"time_of_day": "daytime", "day_of_week": "Friday"}
        self.assertIn("Action", genres_for_context(CONTEXT))
        self.assertNotIn("Action", genres_for_context(daytime))
        self.assertEqual(context_taste_bias({"genres": ["Action"]}, daytime), CONTEXT_BIAS_DEFAULT)
        self.assertEqual(context_taste_bias({"genres": ["Action"]}, CONTEXT), CONTEXT_BIAS_MATCHES_BUCKET)

    def test_empty_context_reads_as_weekday_daytime(self):
        # Same fallback the generator has: no day and no time means a weekday daytime bucket.
        self.assertEqual(context_taste_bias({"genres": ["Comedy"]}, {}), CONTEXT_BIAS_MATCHES_BUCKET)
        self.assertEqual(context_taste_bias({"genres": ["Thriller"]}, {}), CONTEXT_BIAS_DEFAULT)


if __name__ == "__main__":
    unittest.main()
