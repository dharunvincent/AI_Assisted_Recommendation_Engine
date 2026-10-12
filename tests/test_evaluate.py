"""
tests/test_evaluate.py

Checks the hold out split used by the offline evaluation never leaks an
answer into the history.

Run with:  python3 -m unittest tests.test_evaluate
"""

import unittest

from src.evaluate import split_ratings, completion_for_rating, HELD_OUT_COUNT


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


if __name__ == "__main__":
    unittest.main()
