"""
tests/test_never_recommend.py

Tests for the "never_recommend_titles" field of a persona file and the matching
question in interactive mode. Tiny hand made catalog, nothing is downloaded.

Run with:  python3 -m unittest tests.test_never_recommend
"""

import unittest
from datetime import datetime

from src.exclusion_filter.exclude import exclude
from src.interactive import interview
from src.user_profile.persona_loader import build_persona_result, find_blocked_titles
from tests.test_interactive import FakeConsole
from tests.test_persona_loader import make_movie

NOW = datetime(2024, 1, 1)


def star_wars_catalog():
    return {
        1: make_movie(1, "Star Wars: Episode IV - A New Hope (1977)", ["Sci-Fi"]),
        2: make_movie(2, "Star Wars: Episode V - The Empire Strikes Back (1980)", ["Sci-Fi"]),
        3: make_movie(3, "Mother", ["Drama"]),
        4: make_movie(4, "Her", ["Drama"]),
        5: make_movie(5, "Usual Suspects, The", ["Crime"]),
        6: make_movie(6, "Heat", ["Action"]),
    }


class FindBlockedTitlesTests(unittest.TestCase):
    def test_a_name_blocks_every_title_containing_it(self):
        ids, _ = find_blocked_titles(["Star Wars"], star_wars_catalog())
        self.assertEqual(sorted(ids), [1, 2])

    def test_the_warning_lists_each_blocked_title(self):
        _, warnings = find_blocked_titles(["Star Wars"], star_wars_catalog())
        self.assertEqual(len(warnings), 1)
        self.assertIn("blocks 2 title(s)", warnings[0])
        self.assertIn("A New Hope", warnings[0])
        self.assertIn("Empire Strikes Back", warnings[0])

    def test_matching_ignores_capitals_and_a_leading_the(self):
        ids, _ = find_blocked_titles(["the usual suspects", "STAR WARS"], star_wars_catalog())
        self.assertEqual(sorted(ids), [1, 2, 5])

    def test_whole_words_only_so_her_does_not_block_mother(self):
        ids, _ = find_blocked_titles(["Her"], star_wars_catalog())
        self.assertEqual(ids, [4])

    def test_no_match_blocks_nothing_and_offers_did_you_mean(self):
        ids, warnings = find_blocked_titles(["Hest"], star_wars_catalog())
        self.assertEqual(ids, [])
        self.assertIn("matched no title", warnings[0])
        self.assertIn("Did you mean Heat", warnings[0])

    def test_no_match_and_no_close_name_has_no_suggestion(self):
        _, warnings = find_blocked_titles(["Zzzzzzzz"], star_wars_catalog())
        self.assertNotIn("Did you mean", warnings[0])

    def test_empty_or_symbol_only_name_blocks_nothing(self):
        ids, warnings = find_blocked_titles(["!!!"], star_wars_catalog())
        self.assertEqual(ids, [])
        self.assertEqual(len(warnings), 1)

    def test_two_names_matching_the_same_title_list_it_once(self):
        ids, _ = find_blocked_titles(["Star Wars", "Empire Strikes Back"], star_wars_catalog())
        self.assertEqual(sorted(ids), [1, 2])

    def test_no_names_gives_nothing(self):
        self.assertEqual(find_blocked_titles([], star_wars_catalog()), ([], []))


class PersonaFileTests(unittest.TestCase):
    def build(self, **changes):
        data = {"name": "Test", "liked_genres": ["Sci-Fi"], **changes}
        return build_persona_result(data, star_wars_catalog(), NOW)

    def test_field_fills_hard_blocked_ids_and_warns(self):
        result = self.build(never_recommend_titles=["Star Wars"])
        self.assertEqual(sorted(result.user["hard_blocked_movie_ids"]), [1, 2])
        self.assertTrue(any("blocks 2 title(s)" in warning for warning in result.warnings))

    def test_field_is_optional(self):
        self.assertEqual(self.build().user["hard_blocked_movie_ids"], [])

    def test_wrong_type_is_an_error_not_a_crash(self):
        result = self.build(never_recommend_titles="Star Wars")
        self.assertIsNone(result.user)
        self.assertTrue(any("never_recommend_titles" in error for error in result.errors))

    def test_blocked_titles_are_removed_by_the_exclusion_filter(self):
        catalog = star_wars_catalog()
        user = self.build(never_recommend_titles=["Star Wars"]).user
        shortlist = [{"movie_id": movie_id} for movie_id in catalog]
        kept = [item["movie_id"] for item in exclude(shortlist, user, catalog)]
        self.assertEqual(kept, [3, 4, 5, 6])


class InterviewQuestionTests(unittest.TestCase):
    # name, liked, disliked, 3 limits, 4 people, favourites, never recommend, confirm
    BEFORE = ["Sam", "Sci-Fi"] + [""] * 9

    def run_interview(self, blocked_answers):
        console = FakeConsole(self.BEFORE + blocked_answers + ["y"])
        return interview(console.ask, console.say, star_wars_catalog()), console

    def test_answer_is_saved_in_the_persona_data(self):
        data, _ = self.run_interview(["Star Wars"])
        self.assertEqual(data["never_recommend_titles"], ["Star Wars"])

    def test_enter_skips_the_question(self):
        data, _ = self.run_interview([""])
        self.assertEqual(data["never_recommend_titles"], [])

    def test_did_you_mean_accepted_with_y(self):
        data, _ = self.run_interview(["Hest", "y"])
        self.assertEqual(data["never_recommend_titles"], ["Heat (1995)"])

    def test_did_you_mean_refused_with_n_skips_the_name(self):
        data, console = self.run_interview(["Hest", "n"])
        self.assertEqual(data["never_recommend_titles"], [])
        self.assertTrue(any("Skipped 'Hest'" in line for line in console.said))


if __name__ == "__main__":
    unittest.main()
