"""
tests/test_jev_client.py

Checks how the MOCK JEV client behaves. These tests do not say anything
about a real JEV model, they make sure the mock does what its comments
promise, in particular that the dislike override question is rare for weak
fits and common for strong fits.

Run with:  python3 -m unittest tests.test_jev_client
"""

import unittest

from src.stage2_jev_ranking.jev_client import ask, Choice

OVERRIDE_OPTIONS = ["override_show_anyway", "keep_penalty"]
SAMPLE_SIZE = 1000


def override_share(bias_hint):
    """Share of 1000 different fake states where the mock says "override"."""
    overrides = 0
    for number in range(SAMPLE_SIZE):
        state = {"movie_title": f"fake movie {number}", "dislike_penalty": 1.0}
        question = Choice("override?", OVERRIDE_OPTIONS, bias_hint=bias_hint)
        answer = ask(state, {"dislike_override": question})["dislike_override"]["answer"]
        overrides += answer == "override_show_anyway"
    return overrides / SAMPLE_SIZE


class TestMockOverrideRate(unittest.TestCase):
    def test_weak_fit_rarely_overrides(self):
        self.assertTrue(0.05 <= override_share(0.1) <= 0.15)

    def test_strong_fit_often_overrides(self):
        self.assertTrue(0.6 <= override_share(0.7) <= 0.8)

    def test_same_state_and_question_always_give_the_same_answer(self):
        state = {"movie_title": "same movie", "dislike_penalty": 1.0}
        question = Choice("override?", OVERRIDE_OPTIONS, bias_hint=0.5)
        first = ask(state, {"dislike_override": question})
        second = ask(state, {"dislike_override": question})
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
