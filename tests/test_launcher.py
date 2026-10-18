"""
tests/test_launcher.py

Tests of the `recommend` launcher. Answers come from a fake `ask`, the engine
is replaced by five fake ranked movies, and files only go to a temp folder.
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch

from src.launcher import (
    check_data_ready,
    list_saved_personas,
    main,
    run_launcher,
)
from tests.test_interactive import FakeConsole, fake_stages
from tests.test_persona_loader import make_catalog

NOW = datetime(2026, 1, 1, 12, 0)
BUILT_IN = [
    {"name": "Arjun", "taste_summary": "loves racing movies", "user_id": "p1"},
    {"name": "Meera", "taste_summary": "loves comedy", "user_id": "p2"},
]
# name, liked, disliked, rating, year from, year to, 4 people questions, favourites, never recommend
ANSWERS = ["Dharun", "action", "", "", "", "", "", "", "", "", "", ""]


class LauncherCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.personas = os.path.join(self.folder.name, "personas")
        self.results = os.path.join(self.folder.name, "results")
        os.makedirs(self.personas)
        patches = [
            patch("src.launcher.run_pipeline_stages", fake_stages),
            patch("src.launcher.build_all_personas", return_value=BUILT_IN),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def launch(self, answers):
        console = FakeConsole(answers)
        code = run_launcher(console.ask, console.say, make_catalog(), self.personas, self.results, NOW)
        return code, "\n".join(console.said), console

    def write_saved(self, name="Sam"):
        path = os.path.join(self.personas, f"{name}.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"name": name, "liked_genres": ["Action"]}, file)


class ReadyMadeTests(LauncherCase):
    def test_built_in_persona_goes_straight_to_the_table(self):
        code, text, console = self.launch(["1", "2"])
        self.assertEqual(code, 0)
        self.assertIn("1. Arjun - loves racing movies", text)
        self.assertIn("=== Recommendations for Meera ===", text)
        self.assertIn("3 of 5 movies earned the badge.", text)
        self.assertEqual(os.listdir(self.personas), [])  # nothing saved for a built in one
        self.assertFalse(any("Genres you like" in p for p in console.prompts))  # no questions

    def test_saved_persona_is_listed_and_run_but_not_the_example(self):
        self.write_saved("Sam")
        self.write_saved("example")
        _, text, _ = self.launch(["1", "3"])
        self.assertIn("3. Sam (saved)", text)
        self.assertNotIn("example", text)
        self.assertIn("=== Recommendations for Sam ===", text)

    def test_invalid_menu_choices_are_asked_again(self):
        code, text, console = self.launch(["7", "one", "1", "9", "x", "1"])
        self.assertEqual(code, 0)
        self.assertEqual(console.prompts.count(console.prompts[0]), 3)  # two bad answers, then "1"
        self.assertIn("Please type 1 or 2.", text)
        self.assertIn("Please type a number from 1 to 2.", text)
        self.assertIn("=== Recommendations for Arjun ===", text)


class QuestionTests(LauncherCase):
    def test_happy_path_go_shows_table_and_saves_quietly(self):
        code, text, _ = self.launch(["2"] + ANSWERS + ["go"])
        self.assertEqual(code, 0)
        self.assertIn("Rank", text)
        self.assertIn("✓", text)
        self.assertIn("3 of 5 movies earned the badge.", text)
        self.assertIn("Saved your answers:", text)
        self.assertTrue(os.path.exists(os.path.join(self.personas, "Dharun.json")))
        self.assertEqual(len(os.listdir(self.results)), 1)

    def test_saving_over_an_existing_file_says_updated(self):
        self.write_saved("Dharun")
        _, text, _ = self.launch(["2"] + ANSWERS + ["go"])
        self.assertIn("Updated your saved answers", text)

    def test_skipped_question_is_fine_but_liked_genres_is_required(self):
        _, text, _ = self.launch(["2", "", "", "action", ""] + [""] * 9 + ["go"])
        self.assertIn("At least one genre is needed", text)
        self.assertTrue(os.path.exists(os.path.join(self.personas, "me.json")))

    def test_bad_answer_is_explained_and_asked_again(self):
        answers = ["2", "Sam", "action", "", "", "nineteen", "1995", ""] + [""] * 7 + ["go"]
        _, text, _ = self.launch(answers)
        self.assertIn("'nineteen' is not a whole year", text)
        self.assertIn("=== Recommendations for Sam ===", text)

    def test_confirm_answer_other_than_go_redo_quit_is_asked_again(self):
        _, text, _ = self.launch(["2"] + ANSWERS + ["yes", "go"])
        self.assertIn("Please type go, redo or quit.", text)

    def test_redo_starts_the_questions_over(self):
        second = ["Ann", "crime"] + [""] * 10
        _, text, console = self.launch(["2"] + ANSWERS + ["redo"] + second + ["go"])
        self.assertEqual(console.prompts.count("What is your name? (Enter to skip) "), 2)
        self.assertIn("=== Recommendations for Ann ===", text)
        self.assertEqual(os.listdir(self.personas), ["Ann.json"])

    def test_quit_saves_nothing_and_runs_nothing(self):
        with patch("src.launcher.run_pipeline_stages") as stages:
            code, text, _ = self.launch(["2"] + ANSWERS + ["quit"])
        self.assertEqual(code, 0)
        stages.assert_not_called()
        self.assertIn("Stopped, nothing was saved.", text)
        self.assertEqual(os.listdir(self.personas), [])
        self.assertFalse(os.path.exists(self.results))


class CtrlCAndDataTests(unittest.TestCase):
    def run_main_with(self, error):
        out = io.StringIO()
        with patch("src.launcher.check_data_ready", return_value=[]), \
                patch("src.launcher.load_catalog", return_value={}), \
                patch("src.launcher.run_launcher", side_effect=error), redirect_stdout(out):
            return main(), out.getvalue()

    def test_ctrl_c_prints_one_line_and_exits_cleanly(self):
        code, text = self.run_main_with(KeyboardInterrupt())
        self.assertEqual(code, 0)
        self.assertIn("Stopped, nothing was saved.", text)
        self.assertNotIn("Traceback", text)

    def test_missing_data_names_the_download_and_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            problems = check_data_ready(folder, os.path.join(folder, "none.csv"))
        self.assertEqual(len(problems), 2)
        self.assertIn("python3 data/download_movielens.py", problems[0])
        self.assertIn("python3 data/download_imdb.py", problems[1])

    def test_main_stops_before_loading_when_data_is_missing(self):
        out = io.StringIO()
        with patch("src.launcher.check_data_ready", return_value=["IMDb data is missing."]), \
                patch("src.launcher.load_catalog") as load, redirect_stdout(out):
            self.assertEqual(main(), 1)
        load.assert_not_called()

    def test_empty_personas_folder_lists_nothing(self):
        self.assertEqual(list_saved_personas("/no/such/folder"), [])


if __name__ == "__main__":
    unittest.main()
