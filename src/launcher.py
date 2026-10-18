"""
src/launcher.py

The one word launcher behind the `recommend` script. It checks the data is
downloaded, offers a ready made persona or the questions, asks for a final
"go", then shows every ranked movie as a clean table.

Rules this file keeps:
- Nothing here calls input() or print() inside the logic. The caller passes in
  `ask` and `say`, so tests can feed fake answers and read the output.
- Ctrl+C (or the end of input) at any point stops cleanly. Files are only
  written after the results are on screen, so a stop before that saves nothing.
- "quit" saves nothing. Only "go" runs the engine.
- The engine itself is the one in src/pipeline.py, nothing is re-implemented.
"""

import os
import sys
from datetime import date, datetime
from typing import Any, Dict, List, NamedTuple, Optional

from config.weights import STAGE1_SHORTLIST_MIN_SIZE
from src.catalog import DATA_FOLDER, IMDB_ENRICHED_PATH, load_catalog
from src.interactive import (
    PERSONAS_FOLDER,
    Ask,
    Parsed,
    Say,
    _ask_until_valid,
    interview,
    safe_persona_path,
    save_persona_file,
)
from src.pipeline import missing_data_kinds, run_pipeline_stages
from src.results_report import (
    RESULTS_FOLDER,
    badge_summary_line,
    build_result_rows,
    format_launcher_table,
    write_results_csv,
)
from src.run_warnings import count_missing_movie_data, format_warning_section
from src.user_profile.persona_loader import (
    PersonaResult,
    build_persona_result,
    load_persona_file,
)
from src.user_profile.synthetic_users import build_all_personas

# A simple example context, the same Friday evening session src/pipeline.py uses.
CONTEXT = {"time_of_day": "evening", "day_of_week": "Friday"}
EXAMPLE_FILE = "example.json"  # the shared template, never offered as a persona
STOPPED_MESSAGE = "Stopped, nothing was saved."

CHECKPOINT_PROMPT = (
    "1. Use a ready made persona\n"
    "2. Enter your own preferences\n"
    "Type 1 or 2: "
)
CONFIRM_PROMPT = "Type go to see recommendations, redo to start over, or quit: "


class MenuEntry(NamedTuple):
    """One line of the ready made persona list. `source` is a user dict or a file path."""
    label: str
    source: Any


# ---------------------------------------------------------------- pure parts

def check_data_ready(data_folder: str = DATA_FOLDER, imdb_path: str = IMDB_ENRICHED_PATH) -> List[str]:
    """
    Pure apart from looking for files. Returns one message per missing
    download, each with the exact command that fixes it. Empty means ready.
    """
    problems = []
    needed = [os.path.join(data_folder, "movies.csv"), os.path.join(data_folder, "ratings.csv")]
    if not all(os.path.exists(path) for path in needed):
        problems.append("MovieLens data is missing. Run:  python3 data/download_movielens.py")
    if not os.path.exists(imdb_path):
        problems.append("IMDb data is missing. Run:  python3 data/download_imdb.py")
    return problems


def list_saved_personas(folder: str = PERSONAS_FOLDER) -> List[str]:
    """Paths of personas/*.json except the example template, sorted by name."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []  # no personas folder yet simply means nothing saved
    return [
        os.path.join(folder, name) for name in names
        if name.endswith(".json") and name != EXAMPLE_FILE
    ]


def build_menu(built_in: List[Dict[str, Any]], saved_paths: List[str]) -> List[MenuEntry]:
    """Built in personas first (name and one line taste), then the saved files."""
    entries = [MenuEntry(f"{user['name']} - {user['taste_summary']}", user) for user in built_in]
    entries += [
        MenuEntry(f"{os.path.splitext(os.path.basename(path))[0]} (saved)", path)
        for path in saved_paths
    ]
    return entries


def parse_checkpoint(text: str) -> Parsed:
    answer = text.strip()
    return Parsed(answer, None) if answer in ("1", "2") else Parsed(None, "Please type 1 or 2.")


def parse_menu_number(text: str, size: int) -> Parsed:
    answer = text.strip()
    if answer.isdigit() and 1 <= int(answer) <= size:
        return Parsed(int(answer) - 1, None)
    return Parsed(None, f"Please type a number from 1 to {size}.")


def parse_go(text: str) -> Parsed:
    answer = text.strip().lower()
    if answer in ("go", "redo", "quit"):
        return Parsed(answer, None)
    return Parsed(None, "Please type go, redo or quit.")


def short_summary(data: Dict[str, Any]) -> List[str]:
    """Only the answers that were given, one line each. Empty answers are left out."""
    def show(value: Any) -> str:
        return ", ".join(value) if isinstance(value, list) else str(value)

    lines = [f"- {key}: {show(value)}" for key, value in data.items() if value not in (None, [], "")]
    return ["", "Your answers:"] + lines


def format_results_screen(user: Dict[str, Any], rows: List[Dict[str, Any]], warnings: List[str]) -> List[str]:
    """Pure: title, table, badge count, then the warnings (if any) at the very end."""
    lines = [
        "", f"=== Recommendations for {user['name']} ===", f"Taste: {user['taste_summary']}", "",
        *format_launcher_table(rows), "", badge_summary_line(rows),
    ]
    return lines + ([""] + warnings if warnings else [])


# --------------------------------------------------------------- thin shell

def _persona_warnings(result: PersonaResult, stages: Dict[str, Any], user: Dict[str, Any],
                      catalog: Dict[int, Dict[str, Any]], extra: List[str]) -> List[str]:
    """Every warning line for the end of the screen, the short way."""
    notes = list(result.warnings) + extra
    if len(stages["shortlist"]) < STAGE1_SHORTLIST_MIN_SIZE:
        notes.append(
            f"Only {len(stages['shortlist'])} candidates were found "
            f"(target {STAGE1_SHORTLIST_MIN_SIZE}), try fewer limits."
        )
    missing = count_missing_movie_data(catalog, missing_data_kinds(user))
    return format_warning_section(notes, missing)


def show_recommendations(say: Say, result: PersonaResult, catalog: Dict[int, Dict[str, Any]],
                         extra_warnings: Optional[List[str]] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Runs the engine and prints the table. Returns the result rows (so the
    caller can save the CSV), or None when the persona has errors, which are
    printed instead.
    """
    if result.user is None:
        say("\nCannot run with these answers:")
        for error in result.errors:
            say(f"- {error}")
        return None
    stages = run_pipeline_stages(result.user, catalog, CONTEXT)
    rows = build_result_rows(stages["ranked"], catalog)
    warnings = _persona_warnings(result, stages, result.user, catalog, extra_warnings or [])
    for line in format_results_screen(result.user, rows, warnings):
        say(line)
    return rows


def save_results_quietly(say: Say, rows: List[Dict[str, Any]], name: str, today: date,
                         results_folder: str, saved_path: Optional[str] = None,
                         updated: bool = False) -> None:
    """
    Writes the results CSV and says where in one line. A failed CSV save is
    reported in that same line, the list is already on screen.
    """
    parts = []
    if saved_path:
        parts.append(f"{'Updated your saved answers' if updated else 'Saved your answers'}: {saved_path}")
    try:
        parts.append(f"Results: {write_results_csv(rows, name, today, results_folder)}")
    except OSError as error:
        parts.append(f"Could not save the results file: {error}")
    say("\n" + ". ".join(parts))


def run_answers(ask: Ask, say: Say, catalog: Dict[int, Dict[str, Any]], personas_folder: str,
                results_folder: str, now: datetime) -> int:
    """
    Steps 1 and 2: the questions, then go / redo / quit. Saving happens only
    after "go" and after the table is on screen.
    """
    while True:
        data = interview(ask, say, catalog, confirm=False)
        if data is None:
            return 0  # input ended, interview already said so
        for line in short_summary(data):
            say(line)
        choice = _ask_until_valid(ask, say, CONFIRM_PROMPT, parse_go)
        if choice == "quit":
            say(STOPPED_MESSAGE)
            return 0
        if choice == "go":
            break

    result = build_persona_result(data, catalog, now)
    existed = os.path.exists(safe_persona_path(data["name"], personas_folder))
    rows = show_recommendations(say, result, catalog)
    if rows is None:
        return 1
    path, problem = save_persona_file(data, personas_folder)
    save_results_quietly(say, rows, data["name"], now.date(), results_folder, path, existed)
    if problem:
        say(f"Warning: {problem}")
    return 0


def run_ready_made(ask: Ask, say: Say, catalog: Dict[int, Dict[str, Any]], personas_folder: str,
                   results_folder: str, now: datetime) -> int:
    """Step 0, option 1: pick a built in or saved persona and go straight to the results."""
    menu = build_menu(build_all_personas(catalog), list_saved_personas(personas_folder))
    for number, entry in enumerate(menu, start=1):
        say(f"{number}. {entry.label}")
    pick = _ask_until_valid(ask, say, "Type a number: ", lambda text: parse_menu_number(text, len(menu)))
    source = menu[pick].source

    if isinstance(source, dict):  # built in: nothing of yours to save
        rows = show_recommendations(say, PersonaResult(source, [], []), catalog)
        return 0 if rows is not None else 1
    result = load_persona_file(source, catalog, now)
    rows = show_recommendations(say, result, catalog)
    if rows is None:
        return 1
    save_results_quietly(say, rows, result.user["name"], now.date(), results_folder)
    return 0


def run_launcher(ask: Ask, say: Say, catalog: Dict[int, Dict[str, Any]],
                 personas_folder: str = PERSONAS_FOLDER, results_folder: str = RESULTS_FOLDER,
                 now: Optional[datetime] = None) -> int:
    """The first screen, then whichever way the user picked. Returns the exit code."""
    now = now or datetime.now()
    choice = _ask_until_valid(ask, say, CHECKPOINT_PROMPT, parse_checkpoint)
    run = run_ready_made if choice == "1" else run_answers
    return run(ask, say, catalog, personas_folder, results_folder, now)


def main() -> int:
    """Entry point of `recommend`. Ctrl+C or Ctrl+D anywhere ends with a calm message."""
    try:
        problems = check_data_ready()
        if problems:
            for problem in problems:
                print(problem)
            return 1
        print("Loading movies ...")
        return run_launcher(input, print, load_catalog())
    except (KeyboardInterrupt, EOFError):
        print(f"\n{STOPPED_MESSAGE}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
