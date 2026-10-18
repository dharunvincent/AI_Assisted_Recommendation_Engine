"""
src/interactive.py

Interactive mode: asks the user one plain English question at a time and
builds the same persona dict that a personas/*.json file holds.

Every rule (valid genres, rating 0 to 10, year order, known people and
titles) comes from src/user_profile/persona_loader.py. This file only turns
typed text into those values and decides when to ask again.

Rules this file keeps:
- Nothing here calls input() or print() directly. The caller passes in
  `ask` and `say`, so tests can feed fake answers and read the output.
- A bad answer never ends the interview: the reason is shown and the same
  question is asked again. Only "n" at the end, or the end of input, stops it.
- Nothing is saved until the user has said "y" to the summary.
"""

import json
import os
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from src.catalog import catalog_has_imdb_data
from src.results_report import safe_file_stem
from src.user_profile.persona_loader import (
    Catalog,
    clean_genres,
    closest_people,
    find_blocked_titles,
    find_favourites,
    people_in_catalog,
    read_limits,
    suggest_titles,
    valid_genres_in,
    titles_by_name,
)

Ask = Callable[[str], str]
Say = Callable[[str], None]

PERSONAS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "personas")


class Parsed(NamedTuple):
    """Exactly one is set: the value, or the reason the answer was refused."""
    value: Any
    problem: Optional[str]


def split_answer(text: str) -> List[str]:
    """Comma separated answer to a clean list. Empty text is an empty list."""
    return [part.strip() for part in text.split(",") if part.strip()]


DEFAULT_NAME = "me"  # used when the name question is skipped, only liked genres is required


def parse_name(text: str) -> Parsed:
    """Never refuses: Enter means the default name, so the file is saved as personas/me.json."""
    return Parsed(text.strip() or DEFAULT_NAME, None)


def parse_genres(text: str, valid_genres: List[str], field: str, required: bool) -> Parsed:
    """Any unknown genre refuses the whole answer, so a typo is never silently dropped."""
    kept, problems = clean_genres(split_answer(text), valid_genres, field)
    if problems:
        return Parsed(None, " ".join(problems))
    if required and not kept:
        return Parsed(None, f"At least one genre is needed. Valid genres: {', '.join(valid_genres)}.")
    return Parsed(kept, None)


def parse_limit(text: str, key: str, other: Dict[str, Optional[float]]) -> Parsed:
    """
    One of min_imdb_rating, year_from, year_to. Empty means "not set".
    `other` holds the limits already answered, so year_to can be checked
    against year_from by the loader's own rule.
    """
    if not text.strip():
        return Parsed(None, None)
    try:
        number = float(text) if key == "min_imdb_rating" else int(text)
    except ValueError:
        kind = "a number like 7.5" if key == "min_imdb_rating" else "a whole year like 1995"
        return Parsed(None, f"'{text.strip()}' is not {kind}.")
    _, errors = read_limits({**other, key: number})
    return Parsed(None, " ".join(errors)) if errors else Parsed(number, None)


def format_summary(data: Dict[str, Any]) -> List[str]:
    """Pure: the short summary shown before the final y/n."""
    def show(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(value) or "-"
        return "-" if value is None else str(value)

    return ["", "Your answers:"] + [f"- {key}: {show(value)}" for key, value in data.items()]


def safe_persona_path(name: str, folder: str = PERSONAS_FOLDER) -> str:
    """personas/<name>.json, with anything odd in the name made safe."""
    return os.path.join(folder, safe_file_stem(name, "persona") + ".json")


def save_persona_file(data: Dict[str, Any], folder: str = PERSONAS_FOLDER) -> Tuple[Optional[str], Optional[str]]:
    """
    Writes the answers to personas/<name>.json (an existing file of the same
    name is replaced). Returns (path, None), or (None, reason) if the disk
    refuses. Written to a temp file and renamed so a crash never leaves half a file.
    """
    path = safe_persona_path(data["name"], folder)
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")
        os.replace(path + ".tmp", path)
    except OSError as error:
        return None, f"Could not save '{path}': {error}"
    return os.path.abspath(path), None


def _ask_until_valid(ask: Ask, say: Say, prompt: str, parse: Callable[[str], Parsed]) -> Any:
    """Asks the same question again, with the reason, until the answer is accepted."""
    while True:
        result = parse(ask(prompt))
        if result.problem is None:
            return result.value
        say(f"  {result.problem}")


def _confirm(ask: Ask, say: Say, question: str) -> bool:
    """Only a clear y or n is accepted, anything else asks again."""
    while True:
        answer = ask(question).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        say("  Please type y or n.")


def _ask_people(ask: Ask, say: Say, prompt: str, known: Dict[str, str]) -> List[str]:
    """Names not found get a single "did you mean" the user can accept with y."""
    kept: List[str] = []
    for name in split_answer(ask(prompt)):
        if name.lower() in known:
            kept.append(known[name.lower()])
            continue
        suggestions = closest_people(name.lower(), known)
        if suggestions and _confirm(ask, say, f"  '{name}' was not found. Did you mean {suggestions[0]}? (y/n) "):
            kept.append(suggestions[0])
        else:
            say(f"  Skipped '{name}'.")
    return [name for index, name in enumerate(kept) if name not in kept[:index]]


def _ask_titles(ask: Ask, say: Say, prompt: str, catalog: Catalog) -> List[str]:
    """Same as _ask_people, for favourite movies."""
    by_title = titles_by_name(catalog)
    kept: List[str] = []
    for title in split_answer(ask(prompt)):
        found, _ = find_favourites([title], catalog)
        if found:
            kept.append(title)
            continue
        suggestions = suggest_titles(title, by_title)
        if suggestions and _confirm(ask, say, f"  '{title}' was not found. Did you mean {suggestions[0]}? (y/n) "):
            kept.append(suggestions[0])
        else:
            say(f"  Skipped '{title}'.")
    return kept


def _ask_blocked_titles(ask: Ask, say: Say, prompt: str, catalog: Catalog) -> List[str]:
    """
    Titles to never recommend. A name that blocks something is kept as typed,
    one that matches nothing gets a single "did you mean" the user can accept.
    """
    by_title = titles_by_name(catalog)
    kept: List[str] = []
    for title in split_answer(ask(prompt)):
        blocked_ids, _ = find_blocked_titles([title], catalog)
        if blocked_ids:
            kept.append(title)
            continue
        suggestions = suggest_titles(title, by_title)
        if suggestions and _confirm(ask, say, f"  '{title}' was not found. Did you mean {suggestions[0]}? (y/n) "):
            kept.append(suggestions[0])
        else:
            say(f"  Skipped '{title}'.")
    return kept


def _ask_limits(ask: Ask, say: Say, imdb_ready: bool) -> Dict[str, Optional[float]]:
    """Rating, year from, year to. The rating needs IMDb data, so it is skipped without it."""
    limits: Dict[str, Optional[float]] = {"min_imdb_rating": None, "year_from": None, "year_to": None}
    questions = [
        ("min_imdb_rating", "Minimum IMDb rating, 0 to 10 (Enter to skip): "),
        ("year_from", "Only movies from this year on (Enter to skip): "),
        ("year_to", "Only movies up to this year (Enter to skip): "),
    ]
    for key, prompt in questions:
        if key == "min_imdb_rating" and not imdb_ready:
            say("IMDb data is not downloaded, skipping the rating question.")
            continue
        limits[key] = _ask_until_valid(
            ask, say, prompt, lambda text, key=key: parse_limit(text, key, limits)
        )
    return limits


def interview(ask: Ask, say: Say, catalog: Catalog, confirm: bool = True) -> Optional[Dict[str, Any]]:
    """
    Asks every question. With confirm=True (the --interactive command) it also
    shows the summary and asks "Run with these? (y/n)". With confirm=False
    (the recommend launcher) it returns right after the last question, because
    the launcher shows its own summary and go / redo / quit choice.
    Returns the persona dict, or None when the user said n or the input ended.
    """
    genres = valid_genres_in(catalog)
    imdb_ready = catalog_has_imdb_data(catalog)
    try:
        name = _ask_until_valid(ask, say, "What is your name? (Enter to skip) ", parse_name)
        say(f"Valid genres: {', '.join(genres)}")
        liked = _ask_until_valid(
            ask, say, "Genres you like (comma separated): ",
            lambda text: parse_genres(text, genres, "liked_genres", required=True),
        )
        disliked = _ask_until_valid(
            ask, say, "Genres you dislike (Enter to skip): ",
            lambda text: parse_genres(text, genres, "disliked_genres", required=False),
        )
        limits = _ask_limits(ask, say, imdb_ready)
        people: Dict[str, List[str]] = {}
        if imdb_ready:
            directors = people_in_catalog(catalog, "directors")
            cast = people_in_catalog(catalog, "cast")
            people["preferred_directors"] = _ask_people(ask, say, "Directors you like (Enter to skip): ", directors)
            people["preferred_cast"] = _ask_people(ask, say, "Actors you like (Enter to skip): ", cast)
            people["avoided_directors"] = _ask_people(ask, say, "Directors you want to avoid (Enter to skip): ", directors)
            people["avoided_cast"] = _ask_people(ask, say, "Actors you want to avoid (Enter to skip): ", cast)
        else:
            say("IMDb data is not downloaded, skipping the director and cast questions.")
        favourites = _ask_titles(ask, say, "Your favourite movies (Enter to skip): ", catalog)
        blocked = _ask_blocked_titles(
            ask, say, "Titles to never recommend, a name blocks every title containing it, "
            "like Star Wars (Enter to skip): ", catalog,
        )

        data = {
            "name": name, "liked_genres": liked, "disliked_genres": disliked, **limits, **people,
            "favourite_titles": favourites, "never_recommend_titles": blocked,
        }
        if not confirm:
            return data
        for line in format_summary(data):
            say(line)
        return data if _confirm(ask, say, "Run with these? (y/n) ") else None
    except EOFError:
        # Input closed (Ctrl-D or a pipe ended): stop cleanly, save nothing.
        say("\nInput ended, nothing was saved.")
        return None

