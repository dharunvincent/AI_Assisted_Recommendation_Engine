"""
tests/test_collaborative_strength.py

Tests for passing the collaborative match strength from stage 1 into the
stage 2 taste hint. Made up tables and movies, no download needed.

Run with:  python3 -m unittest tests.test_collaborative_strength
"""

import unittest

from config.weights import COLLAB_TASTE_BIAS_MAX, TASTE_BIAS_PER_GENRE_OVERLAP, TASTE_BIAS_BASE
from src.stage1_candidate_generation import collaborative
from src.stage1_candidate_generation.merge_shortlist import merge
from src.stage2_jev_ranking.scoring_questions import build_questions, collab_taste_boost, taste_bias

CATALOG = {i: {"movie_id": i, "title": f"M{i}", "avg_rating": 3.0, "genres": ["Drama"]} for i in (1, 2, 3, 4)}
USER = {"watch_history": [{"movie_id": 1, "completion_pct": 0.95}]}


class TestGeneratorStrength(unittest.TestCase):
    def test_strongest_pick_is_one_and_others_are_relative(self):
        table = {1: {2: 0.6, 3: 0.3}}
        found = {c["movie_id"]: c["collab_strength"] for c in collaborative.generate(USER, CATALOG, similarity_table=table)}
        self.assertEqual(found, {2: 1.0, 3: 0.5})

    def test_strengths_stay_between_zero_and_one(self):
        table = {1: {2: 0.9, 3: 0.2, 4: 0.05}}
        for c in collaborative.generate(USER, CATALOG, similarity_table=table):
            self.assertTrue(0.0 <= c["collab_strength"] <= 1.0)

    def test_no_picks_gives_an_empty_list(self):
        self.assertEqual(collaborative.generate(USER, CATALOG, similarity_table={}), [])


class TestMergeKeepsStrength(unittest.TestCase):
    def test_strongest_strength_wins_across_generators(self):
        first = [{"movie_id": 2, "source": "collaborative", "reason": "r", "collab_strength": 0.4}]
        second = [{"movie_id": 2, "source": "trending", "reason": "r"}]
        third = [{"movie_id": 2, "source": "collaborative", "reason": "r", "collab_strength": 0.9}]
        self.assertEqual(merge([first, second, third])[0]["collab_strength"], 0.9)

    def test_title_without_collaborative_source_has_zero_strength(self):
        merged = merge([[{"movie_id": 5, "source": "trending", "reason": "r"}]])
        self.assertEqual(merged[0]["collab_strength"], 0.0)


class TestStage2Boost(unittest.TestCase):
    def test_boost_is_proportional_to_strength(self):
        self.assertAlmostEqual(collab_taste_boost(0.5), COLLAB_TASTE_BIAS_MAX / 2)

    def test_boost_never_beats_one_shared_genre(self):
        # Rule: whatever strength arrives, the boost stays at or under one shared genre.
        for strength in (-1.0, 0.0, 0.3, 1.0, 2.0, 50.0):
            self.assertLessEqual(collab_taste_boost(strength), TASTE_BIAS_PER_GENRE_OVERLAP)
            self.assertGreaterEqual(collab_taste_boost(strength), 0.0)

    def test_no_strength_leaves_taste_bias_unchanged(self):
        self.assertEqual(taste_bias(1, 0), TASTE_BIAS_BASE + TASTE_BIAS_PER_GENRE_OVERLAP)

    def test_questions_carry_the_boost_in_the_taste_hint(self):
        movie = CATALOG[2]
        plain = build_questions(movie, {"sources": ["collaborative"]}, {}, 0.0, 0)["taste_fit"].bias_hint
        strong = build_questions(
            movie, {"sources": ["collaborative"], "collab_strength": 1.0}, {}, 0.0, 0
        )["taste_fit"].bias_hint
        self.assertAlmostEqual(strong - plain, COLLAB_TASTE_BIAS_MAX)


if __name__ == "__main__":
    unittest.main()
