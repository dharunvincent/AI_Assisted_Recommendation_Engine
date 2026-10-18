"""
tests/test_interactive.py

Interactive mode tests. The questions are answered by a fake `ask` that
reads from a list, so nothing waits for a keyboard. Tiny hand made catalog,
files only go to a temporary folder.
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src.pipeline import run_interactive
from src.results_report import DisplayOptions
from src.interactive import interview, save_persona_file
from tests.test_persona_loader import make_catalog


class FakeConsole:
    """Feeds scripted answers and records everything asked and said."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []
        self.said = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def say(self, text):
        self.said.append(text)


def run(answers):
    console = FakeConsole(answers)
    return interview(console.ask, console.say, make_catalog()), console


# name, liked, disliked, rating, year from, year to, 4 people questions, favourites, confirm
HAPPY = ["Dharun", "action, crime", "Animation", "7", "1990", "2018",
         "Michael Mann", "Al Pacino", "", "", "Heat", "y"]


class InterviewTests(unittest.TestCase):
    def test_happy_path_builds_the_persona(self):
        data, console = run(HAPPY)
        self.assertEqual(data["name"], "Dharun")
        self.assertEqual(data["liked_genres"], ["Action", "Crime"])
        self.assertEqual(data["disliked_genres"], ["Animation"])
        self.assertEqual((data["min_imdb_rating"], data["year_from"], data["year_to"]), (7.0, 1990, 2018))
        self.assertEqual(data["preferred_directors"], ["Michael Mann"])
        self.assertEqual(data["favourite_titles"], ["Heat"])
        self.assertTrue(any("Valid genres" in line for line in console.said))
        self.assertIn("Run with these? (y/n) ", console.prompts)

    def test_enter_skips_every_optional_question(self):
        data, _ = run(["Sam", "Action", "", "", "", "", "", "", "", "", "", "y"])
        self.assertEqual(data["disliked_genres"], [])
        self.assertIsNone(data["min_imdb_rating"])
        self.assertIsNone(data["year_from"])
        self.assertEqual(data["favourite_titles"], [])

    def test_bad_year_is_explained_and_asked_again(self):
        answers = ["Sam", "Action", "", "", "nineteen", "1995", "", "", "", "", "", "", "y"]
        data, console = run(answers)
        self.assertEqual(data["year_from"], 1995)
        self.assertEqual(console.prompts.count("Only movies from this year on (Enter to skip): "), 2)
        self.assertTrue(any("'nineteen' is not a whole year" in line for line in console.said))

    def test_year_to_before_year_from_is_asked_again(self):
        answers = ["Sam", "Action", "", "", "2000", "1990", "2005", "", "", "", "", "", "y"]
        data, _ = run(answers)
        self.assertEqual(data["year_to"], 2005)

    def test_rating_outside_zero_to_ten_is_asked_again(self):
        data, console = run(["Sam", "Action", "", "11", "8", "", "", "", "", "", "", "", "y"])
        self.assertEqual(data["min_imdb_rating"], 8.0)
        self.assertTrue(any("between 0 and 10" in line for line in console.said))

    def test_unknown_genre_is_explained_and_asked_again(self):
        data, console = run(["Sam", "Actoin", "Action", "", "", "", "", "", "", "", "", "", "y"])
        self.assertEqual(data["liked_genres"], ["Action"])
        self.assertTrue(any("Unknown genre 'Actoin'" in line for line in console.said))

    def test_did_you_mean_accepted_with_y(self):
        answers = ["Sam", "Action", "", "", "", "", "Micheal Mann", "y", "", "", "", "", "y"]
        data, console = run(answers)
        self.assertEqual(data["preferred_directors"], ["Michael Mann"])
        self.assertTrue(any("Did you mean Michael Mann?" in p for p in console.prompts))

    def test_did_you_mean_skipped_with_n(self):
        answers = ["Sam", "Action", "", "", "", "", "Micheal Mann", "n", "", "", "", "", "y"]
        data, _ = run(answers)
        self.assertEqual(data["preferred_directors"], [])

    def test_favourite_title_did_you_mean_accepted(self):
        answers = ["Sam", "Action", "", "", "", "", "", "", "", "", "Inceptoin", "y", "y"]
        data, _ = run(answers)
        self.assertEqual(data["favourite_titles"], ["Inception (1995)"])

    def test_n_at_the_end_returns_nothing(self):
        data, _ = run(HAPPY[:-1] + ["n"])
        self.assertIsNone(data)

    def test_input_ending_midway_returns_nothing(self):
        data, console = run(["Sam", "Action"])
        self.assertIsNone(data)
        self.assertTrue(any("nothing was saved" in line for line in console.said))


class SaveTests(unittest.TestCase):
    def test_saves_to_a_safe_file_name_and_can_be_read_back(self):
        with tempfile.TemporaryDirectory() as folder:
            path, problem = save_persona_file({"name": "Ann/Lee", "liked_genres": ["Action"]}, folder)
            self.assertIsNone(problem)
            self.assertEqual(os.path.basename(path), "Ann_Lee.json")
            with open(path, encoding="utf-8") as file:
                self.assertEqual(json.load(file)["name"], "Ann/Lee")

    def test_save_failure_is_returned_not_raised(self):
        with tempfile.NamedTemporaryFile() as blocker:
            path, problem = save_persona_file({"name": "Ann"}, os.path.join(blocker.name, "x"))
        self.assertIsNone(path)
        self.assertIn("Could not save", problem)


def fake_stages(*_args, **_kwargs):
    """Five ranked movies, three with the badge, so the display flags have something to cut."""
    ranked = [
        {"movie_id": 1, "title": f"Movie {i}", "year": 1995, "final_score": score, "match_percent": score + 5,
         "show_badge": score >= 72, "reasons": ["trending now"]}
        for i, score in enumerate([90, 80, 75, 60, 50], start=1)
    ]
    return {"ranked": ranked, "shortlist": ranked, "filter_counts": {}, "candidate_count": 5}


class DisplayFlagTests(unittest.TestCase):
    """--badged-only and --top, through the real run_interactive / run_persona_file path."""

    def run_and_capture(self, options):
        out = io.StringIO()
        console = FakeConsole(HAPPY)
        with patch("src.pipeline.run_pipeline_stages", fake_stages), \
                patch("src.pipeline.write_results_csv", return_value="results/x.csv") as csv_writer, \
                patch("src.pipeline.save_persona_file", return_value=("personas/Dharun.json", None)), \
                redirect_stdout(out):
            code = run_interactive(make_catalog(), {}, options, console.ask, console.say)
        return code, out.getvalue(), csv_writer

    def test_default_lists_every_movie(self):
        code, text, _ = self.run_and_capture(DisplayOptions())
        self.assertEqual(code, 0)
        self.assertIn("Showing 5 of 5", text)
        self.assertIn("Movie 5", text)

    def test_badged_only_hides_movies_without_the_badge(self):
        _, text, csv_writer = self.run_and_capture(DisplayOptions(badged_only=True))
        self.assertIn("Showing 3 of 5", text)
        self.assertIn("Movie 3", text)
        self.assertNotIn("Movie 4", text)
        self.assertEqual(len(csv_writer.call_args.args[0]), 5)  # the CSV keeps the full list

    def test_top_limits_the_list(self):
        _, text, _ = self.run_and_capture(DisplayOptions(top=2))
        self.assertIn("Showing 2 of 5", text)
        self.assertNotIn("Movie 3", text)

    def test_saying_n_runs_nothing(self):
        console = FakeConsole(HAPPY[:-1] + ["n"])
        with patch("src.pipeline.run_pipeline_stages") as stages:
            self.assertEqual(run_interactive(make_catalog(), {}, DisplayOptions(), console.ask, console.say), 0)
        stages.assert_not_called()


if __name__ == "__main__":
    unittest.main()
