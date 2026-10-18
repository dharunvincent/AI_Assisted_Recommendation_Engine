"""
tests/test_evaluate.py

Checks the hold out split used by the offline evaluation never leaks an
answer into the history.

Run with:  python3 -m unittest tests.test_evaluate
"""

import unittest

from src.evaluate import (
    split_ratings, completion_for_rating, HELD_OUT_COUNT, TOP_K,
    describe_ranked_item, summarize_diagnostics,
)


def ratings_with_pattern(ratings):
    """Fake time sorted ratings: movie ids 1, 2, 3 ... one rating per day."""
    return [(1000 + day, day + 1, rating) for day, rating in enumerate(ratings)]


class TestHoldOutSplit(unittest.TestCase):
    def test_no_held_out_title_is_in_the_history(self):
        ratings = ratings_with_pattern([4.0, 2.0, 5.0, 3.0, 4.5, 4.0, 1.0, 5.0, 4.0, 4.0, 2.5, 5.0])
        history, held_out = split_ratings(ratings)
        history_ids = {movie_id for _, movie_id, _ in history}
        held_out_ids = {movie_id for _, movie_id, _ in held_out}
        self.assertEqual(history_ids & held_out_ids, set())

    def test_held_out_are_the_last_high_ratings_and_history_comes_before_them(self):
        ratings = ratings_with_pattern([4.0, 5.0, 4.0, 2.0, 4.5, 5.0, 4.0, 1.0])
        history, held_out = split_ratings(ratings)
        self.assertEqual(len(held_out), HELD_OUT_COUNT)
        self.assertTrue(all(rating >= 4.0 for _, _, rating in held_out))
        self.assertLess(max(t for t, _, _ in history), min(t for t, _, _ in held_out))
        # The low rating after the first answer is neither history nor an answer.
        used = {m for _, m, _ in history} | {m for _, m, _ in held_out}
        self.assertNotIn(8, used)

    def test_user_with_too_few_high_ratings_is_skipped(self):
        self.assertIsNone(split_ratings(ratings_with_pattern([4.0, 3.0, 2.0, 5.0, 1.0, 4.5])))

    def test_user_with_no_history_before_the_answers_is_skipped(self):
        self.assertIsNone(split_ratings(ratings_with_pattern([4.0] * HELD_OUT_COUNT)))


class TestCompletionProxy(unittest.TestCase):
    def test_high_middle_and_low_ratings_map_to_like_neutral_and_dislike(self):
        self.assertEqual(completion_for_rating(4.0), 0.95)
        self.assertEqual(completion_for_rating(3.5), 0.6)
        self.assertEqual(completion_for_rating(3.0), 0.6)
        self.assertEqual(completion_for_rating(2.5), 0.1)


def ranked_item(movie_id, sources, before, after, override=False, bias=0.8):
    return {
        "movie_id": movie_id,
        "sources": sources,
        "dislike_override_used": override,
        "jev_answers": {"completion_likelihood": {"answer": 0.7}, "context_fit": {"answer": 0.4}},
        "diagnostics": {
            "genre_overlap_count": 2,
            "dislike_penalty": 0.5,
            "taste_fit_before_penalty": before,
            "taste_fit_after_penalty": after,
            "taste_bias_before_cap": bias,
        },
    }


class TestDiagnostics(unittest.TestCase):
    def test_row_flags_a_penalty_that_pushed_taste_fit_to_zero(self):
        row = describe_ranked_item(ranked_item(1, ["trending"], 0.2, 0.0), rank=4)
        self.assertTrue(row["pushed_to_zero"])
        self.assertEqual(row["rank"], 4)

    def test_title_whose_taste_fit_was_already_zero_is_not_blamed_on_the_penalty(self):
        row = describe_ranked_item(ranked_item(1, ["trending"], 0.0, 0.0), rank=4)
        self.assertFalse(row["pushed_to_zero"])

    def test_row_flags_a_bias_above_one_as_capped(self):
        self.assertTrue(describe_ranked_item(ranked_item(1, [], 0.9, 0.9, bias=1.2), 1)["bias_capped"])
        self.assertFalse(describe_ranked_item(ranked_item(1, [], 0.9, 0.9, bias=1.0), 1)["bias_capped"])

    def test_summary_averages_ranks_and_counts_collaborative_hits(self):
        rows = [
            describe_ranked_item(ranked_item(1, ["collaborative"], 0.9, 0.9), rank=2),
            describe_ranked_item(ranked_item(2, ["collaborative"], 0.9, 0.9), rank=TOP_K + 20),
            describe_ranked_item(ranked_item(3, ["trending"], 0.9, 0.9), rank=8),
        ]
        summary = summarize_diagnostics(rows, shortlisted_count=50, pushed_to_zero_count=3, bias_capped_count=7)
        self.assertEqual(summary["answers_in_top"], 2)
        self.assertAlmostEqual(summary["average_rank_of_shortlisted_answers"], (2 + TOP_K + 20 + 8) / 3)
        self.assertEqual(summary["average_rank_of_answers_in_top"], 5)
        self.assertEqual(summary["collaborative_answers"], 2)
        self.assertEqual(summary["collaborative_hit_rate"], 0.5)
        self.assertEqual((summary["pushed_to_zero"], summary["bias_capped"]), (3, 7))

    def test_summary_with_no_answers_does_not_divide_by_zero(self):
        summary = summarize_diagnostics([], 0, 0, 0)
        self.assertIsNone(summary["average_rank_of_shortlisted_answers"])
        self.assertEqual(summary["collaborative_hit_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
