"""
tests/test_rank.py

Tests for the stage 2 ranking logic in src/stage2_jev_ranking/rank.py, which
holds the most important rules: the dislike penalty, the override, the
business weight and the badge. The mock JEV client is replaced with fixed
answers, so every number below is exact and does not depend on the mock's
pseudo random behaviour.

Run with:  python3 -m unittest tests.test_rank
"""

import unittest
from unittest.mock import patch

from src.stage2_jev_ranking.rank import rank_candidates
from config.weights import (
    TASTE_FIT_WEIGHT,
    COMPLETION_LIKELIHOOD_WEIGHT,
    CONTEXT_FIT_WEIGHT,
    BUSINESS_WEIGHT_WEIGHT,
    BUSINESS_WEIGHT_NEUTRAL,
    BADGE_DISPLAY_THRESHOLD_PERCENT,
    DISLIKE_PENALTY_SCALE,
    OVERRIDE_PENALTY_RETAINED,
    OVERRIDE_CONFIDENCE_THRESHOLD,
)

TASTE, COMPLETION, CONTEXT = 0.8, 0.6, 0.5  # the fixed answers used in most tests
CONFIDENT = OVERRIDE_CONFIDENCE_THRESHOLD + 0.2
NOT_CONFIDENT = OVERRIDE_CONFIDENCE_THRESHOLD - 0.15


def fixed_answers(taste=TASTE, completion=COMPLETION, context=CONTEXT,
                  override="keep_penalty", override_confidence=CONFIDENT):
    """The answer dict the mock JEV client would return, with chosen numbers."""
    return {
        "taste_fit": {"answer": taste, "confidence": 0.9},
        "completion_likelihood": {"answer": completion, "confidence": 0.9},
        "context_fit": {"answer": context, "confidence": 0.9},
        "dislike_override": {"answer": override, "confidence": override_confidence},
    }


def expected_final_score(taste, completion=COMPLETION, context=CONTEXT, business=BUSINESS_WEIGHT_NEUTRAL):
    """The final score formula written out by hand, so a change to rank.py shows up here."""
    return round((
        taste * TASTE_FIT_WEIGHT
        + completion * COMPLETION_LIKELIHOOD_WEIGHT
        + context * CONTEXT_FIT_WEIGHT
        + business * BUSINESS_WEIGHT_WEIGHT
    ) * 100, 1)


def tiny_catalog():
    return {
        1: {"movie_id": 1, "title": "Horror One", "year": 2000, "genres": ["Horror"], "avg_rating": 4.0},
        2: {"movie_id": 2, "title": "Comedy Two", "year": 2001, "genres": ["Comedy"], "avg_rating": 4.0},
    }


def candidate(movie_id, **extra):
    return {"movie_id": movie_id, "sources": ["test"], "reasons": ["test"], **extra}


USER = {"age_group": "25 to 34", "watch_history": []}
CONTEXT_INFO = {"time_of_day": "evening", "day_of_week": "Friday"}
ASK = "src.stage2_jev_ranking.rank.jev_client.ask"


def rank_one(answers, dislike_scores, **candidate_extra):
    with patch(ASK, return_value=answers):
        return rank_candidates(USER, tiny_catalog(), [candidate(1, **candidate_extra)], CONTEXT_INFO, dislike_scores)[0]


class TestDislikePenalty(unittest.TestCase):
    def test_no_penalty_leaves_taste_fit_alone_and_never_uses_override(self):
        # Even if the mock says "override", there is no penalty to override.
        result = rank_one(fixed_answers(override="override_show_anyway"), dislike_scores={})
        self.assertEqual(result["final_score"], expected_final_score(TASTE))
        self.assertFalse(result["dislike_override_used"])

    def test_penalty_without_override_lowers_taste_fit_by_penalty_times_scale(self):
        penalty = 1.0
        result = rank_one(fixed_answers(override="keep_penalty"), dislike_scores={"Horror": penalty})
        self.assertEqual(result["final_score"], expected_final_score(TASTE - penalty * DISLIKE_PENALTY_SCALE))
        self.assertFalse(result["dislike_override_used"])

    def test_confident_override_applies_only_the_retained_share_of_the_penalty(self):
        penalty = 1.0
        answers = fixed_answers(override="override_show_anyway", override_confidence=CONFIDENT)
        result = rank_one(answers, dislike_scores={"Horror": penalty})
        retained = penalty * OVERRIDE_PENALTY_RETAINED
        self.assertEqual(result["final_score"], expected_final_score(TASTE - retained * DISLIKE_PENALTY_SCALE))
        self.assertTrue(result["dislike_override_used"])

    def test_override_below_the_confidence_threshold_applies_the_full_penalty(self):
        penalty = 1.0
        answers = fixed_answers(override="override_show_anyway", override_confidence=NOT_CONFIDENT)
        result = rank_one(answers, dislike_scores={"Horror": penalty})
        self.assertEqual(result["final_score"], expected_final_score(TASTE - penalty * DISLIKE_PENALTY_SCALE))
        self.assertFalse(result["dislike_override_used"])


class TestBusinessWeight(unittest.TestCase):
    def test_title_with_no_business_weight_uses_the_neutral_weight(self):
        result = rank_one(fixed_answers(), dislike_scores={})
        self.assertEqual(result["final_score"], expected_final_score(TASTE, business=BUSINESS_WEIGHT_NEUTRAL))

    def test_promoted_title_gets_its_weight_times_the_business_share(self):
        result = rank_one(fixed_answers(), dislike_scores={}, business_weight=0.4)
        self.assertEqual(result["final_score"], expected_final_score(TASTE, business=0.4))


class TestBadgeAndOrder(unittest.TestCase):
    def rank_with_uniform_scores(self, score_by_title):
        """Every answer, and the business weight, equal to the given score per title."""
        def fake_ask(state, questions):
            value = score_by_title[state["movie_title"]]
            return fixed_answers(taste=value, completion=value, context=value)

        shortlist = [candidate(1, business_weight=score_by_title["Horror One"]),
                     candidate(2, business_weight=score_by_title["Comedy Two"])]
        with patch(ASK, side_effect=fake_ask):
            return rank_candidates(USER, tiny_catalog(), shortlist, CONTEXT_INFO, {})

    def test_badge_follows_the_threshold_exactly(self):
        threshold = BADGE_DISPLAY_THRESHOLD_PERCENT / 100
        ranked = self.rank_with_uniform_scores({"Horror One": threshold, "Comedy Two": threshold - 0.01})
        badge_by_title = {item["title"]: item["show_badge"] for item in ranked}
        self.assertTrue(badge_by_title["Horror One"])    # exactly on the line gets the badge
        self.assertFalse(badge_by_title["Comedy Two"])   # just below does not

    def test_list_is_ordered_by_final_score_only(self):
        # The lower scoring title comes first in the shortlist on purpose.
        ranked = self.rank_with_uniform_scores({"Horror One": 0.5, "Comedy Two": 0.9})
        self.assertEqual([item["title"] for item in ranked], ["Comedy Two", "Horror One"])
        self.assertGreater(ranked[0]["final_score"], ranked[1]["final_score"])


if __name__ == "__main__":
    unittest.main()
