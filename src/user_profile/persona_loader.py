"""
src/user_profile/persona_loader.py

Reads a persona file (see personas/README.md) and turns it into the same
user dict the pipeline already uses for the four built in personas.

Problems are handled at three levels, see src/run_warnings.py:
1. ERRORS stop the run, because the results would be meaningless: the file
   cannot be read, "name" is missing, no valid liked genre is left, the year
   range is backwards, or a rating is outside 0 to 10.
2. WARNINGS let the run continue: an unknown genre is dropped, a director,
   actor or favourite title that is not found is skipped (with a "did you
   mean"), and without IMDb data the IMDb based preferences are skipped.
3. Single movies with missing data are handled later, in the filters and
   generators, by counting them quietly.

Rule this file keeps: loading never crashes on bad user input. Every
problem comes back inside a PersonaResult, and exactly one of "user is set"
or "errors is not empty" is true.
"""

import difflib
import json
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from config.weights import (
    FAVOURITE_COMPLETION_PCT,
    FAVOURITE_FIRST_WATCH_DAYS_AGO,
    FAVOURITE_WATCH_SPACING_DAYS,
    MAX_SUGGESTIONS,
    PERSONA_FILE_GENRE_HISTORY_COMPLETION_RANGE,
    PERSONA_FILE_HISTORY_SEED,
    SUGGESTION_MATCH_CUTOFF,
)
from src.catalog import catalog_has_imdb_data
from src.user_profile.synthetic_users import build_persona_user

Catalog = Dict[int, Dict[str, Any]]

PEOPLE_FIELDS = ["preferred_directors", "preferred_cast", "avoided_directors", "avoided_cast"]
# Persona fields that can only work when the IMDb data has been downloaded.
IMDB_FIELDS = ["min_imdb_rating"] + PEOPLE_FIELDS


class PersonaResult(NamedTuple):
    """user is None exactly when errors is not empty."""
    user: Optional[Dict[str, Any]]
    errors: List[str]
    warnings: List[str]


def read_persona_file(path: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """
    The only function here that touches the disk. Returns the parsed JSON
    object, or a list of errors explaining why it could not be used.
    """
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except OSError as error:
        return None, [f"Cannot read persona file '{path}': {error}"]
    except ValueError as error:
        return None, [f"Persona file '{path}' is not valid JSON: {error}"]

    if not isinstance(data, dict):
        return None, [f"Persona file '{path}' must contain one JSON object, in curly braces."]
    return data, []


def normalize_title(title: str) -> str:
    """
    Makes "The Usual Suspects" and MovieLens' "Usual Suspects, The" the same
    text. MovieLens moves the leading article to the end and may add an
    alternative title in brackets, so both are removed along with accents,
    punctuation and capital letters. Used on both sides of the comparison.
    """
    text = unicodedata.normalize("NFKD", title.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\(.*?\)", " ", text).strip()
    text = re.sub(r",\s*(the|a|an)$", "", text)
    text = re.sub(r"^(the|a|an)\s+", "", text)
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return " ".join(text.split())


def _closest(wanted: str, candidates: List[str]) -> List[str]:
    """Up to MAX_SUGGESTIONS candidates that look like the typed text."""
    return difflib.get_close_matches(
        wanted, candidates, n=MAX_SUGGESTIONS, cutoff=SUGGESTION_MATCH_CUTOFF
    )


def _closest_people(wanted: str, known: Dict[str, str]) -> List[str]:
    """
    Like _closest, but names with the same last word come first. Plain text
    similarity ranks "Chris Noonan" above "Christopher Nolan" for "Chris Nolan",
    yet a shared surname is the stronger hint that this is the person meant.
    """
    surname = wanted.split()[-1] if wanted.split() else ""
    matches = difflib.get_close_matches(
        wanted, list(known), n=MAX_SUGGESTIONS * 3, cutoff=SUGGESTION_MATCH_CUTOFF
    )
    matches.sort(key=lambda match: match.split()[-1] != surname)  # stable: keeps ratio order
    return [known[match] for match in matches[:MAX_SUGGESTIONS]]


def _did_you_mean(suggestions: List[str]) -> str:
    """Wording added to a warning, empty when there is nothing to suggest."""
    return f" Did you mean {' or '.join(suggestions)}?" if suggestions else ""


def _read_string_list(data: Dict[str, Any], key: str) -> Tuple[List[str], List[str]]:
    """A missing or null field is an empty list. Anything but a list of text is an error."""
    value = data.get(key)
    if value is None:
        return [], []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return [], [f"'{key}' must be a list of text values, like [\"Action\", \"Crime\"]."]
    return [item.strip() for item in value if item.strip()], []


def _read_number(
    data: Dict[str, Any], key: str, whole_only: bool
) -> Tuple[Optional[float], List[str]]:
    """A missing or null number is None (not set). A wrong type is an error."""
    value = data.get(key)
    if value is None:
        return None, []
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not is_number or (whole_only and not isinstance(value, int)):
        kind = "a whole number" if whole_only else "a number"
        return None, [f"'{key}' must be {kind}, but it is {value!r}."]
    return value, []


def _read_limits(data: Dict[str, Any]) -> Tuple[Dict[str, Optional[float]], List[str]]:
    """Level 1 checks on year_from, year_to and min_imdb_rating."""
    limits: Dict[str, Optional[float]] = {}
    errors: List[str] = []
    for key, whole_only in [("year_from", True), ("year_to", True), ("min_imdb_rating", False)]:
        limits[key], new_errors = _read_number(data, key, whole_only)
        errors += new_errors

    rating = limits["min_imdb_rating"]
    if rating is not None and not 0 <= rating <= 10:
        errors.append(f"'min_imdb_rating' must be between 0 and 10, but it is {rating}.")
    year_from, year_to = limits["year_from"], limits["year_to"]
    if year_from is not None and year_to is not None and year_from > year_to:
        errors.append(f"'year_from' ({year_from}) is bigger than 'year_to' ({year_to}).")
    return limits, errors


def _clean_genres(
    raw: List[str], valid_genres: List[str], field: str
) -> Tuple[List[str], List[str]]:
    """
    Level 2. Unknown genres are dropped one by one, valid ones are kept.
    Matching ignores capital letters and returns MovieLens' own spelling.
    """
    by_lower = {genre.lower(): genre for genre in valid_genres}
    kept, warnings = [], []
    for genre in raw:
        if genre.lower() in by_lower:
            kept.append(by_lower[genre.lower()])
        else:
            warnings.append(
                f"Unknown genre '{genre}' in '{field}', ignored. "
                f"Valid genres: {', '.join(valid_genres)}."
            )
    return kept, warnings


def _people_in_catalog(catalog: Catalog, field: str) -> Dict[str, str]:
    """Lower case name mapped to its proper spelling, for every director or actor."""
    return {name.lower(): name for movie in catalog.values() for name in movie[field]}


def _clean_people(
    raw: List[str], known: Dict[str, str], field: str
) -> Tuple[List[str], List[str]]:
    """
    Level 2. A name not found in the data is skipped with a "did you mean".
    The catalog only has MovieLens movies, and the top 5 billed cast of each,
    so a real person can be missing too, the warning says so.
    """
    kept, warnings = [], []
    for name in raw:
        if name.lower() in known:
            kept.append(known[name.lower()])
        else:
            suggestions = _closest_people(name.lower(), known)
            warnings.append(
                f"'{name}' in '{field}' was not found in the IMDb data, skipped."
                + _did_you_mean(suggestions)
            )
    return kept, warnings


def _title_with_year(movie: Dict[str, Any]) -> str:
    """Display form like "Heat (1995)"."""
    return f"{movie['title']} ({movie['year']})"


def _find_favourites(raw: List[str], catalog: Catalog) -> Tuple[List[int], List[str]]:
    """
    Level 2. Returns the movie ids of the favourites that were found.
    A title not found is skipped with close matches. When two movies share
    a title, the one with the most MovieLens ratings is used and the warning
    says which one, so a wrong pick is easy to spot.
    """
    by_title: Dict[str, List[Dict[str, Any]]] = {}
    for movie in catalog.values():
        by_title.setdefault(normalize_title(movie["title"]), []).append(movie)

    found: List[int] = []
    warnings: List[str] = []
    for title in raw:
        matches = by_title.get(normalize_title(title))
        if not matches:
            close = _closest(normalize_title(title), list(by_title))
            suggestions = [_title_with_year(by_title[key][0]) for key in close]
            warnings.append(
                f"Favourite '{title}' was not found, skipped." + _did_you_mean(suggestions)
            )
            continue
        best = max(matches, key=lambda movie: movie["rating_count"])
        if len(matches) > 1:
            warnings.append(
                f"{len(matches)} movies are called '{title}', used the most rated one: "
                f"{_title_with_year(best)}."
            )
        if best["movie_id"] not in found:
            found.append(best["movie_id"])
    return found, warnings


def _favourites_to_history(movie_ids: List[int], as_of: datetime) -> List[Dict[str, Any]]:
    """
    Cold start fix. A new user has no history, so collaborative filtering has
    nothing to compare against. Favourites become finished watches, which the
    rest of the engine reads as "this user loved it".
    """
    return [
        {
            "movie_id": movie_id,
            "completion_pct": FAVOURITE_COMPLETION_PCT,
            "timestamp": as_of - timedelta(
                days=FAVOURITE_FIRST_WATCH_DAYS_AGO + position * FAVOURITE_WATCH_SPACING_DAYS
            ),
        }
        for position, movie_id in enumerate(movie_ids)
    ]


def _genre_history(
    name: str, liked: List[str], disliked: List[str], catalog: Catalog
) -> List[Dict[str, Any]]:
    """
    No favourites given, so reuse the existing genre based history builder in
    synthetic_users.py (called, not copied) and keep only its watch history.
    """
    persona = {
        "user_id": "persona_file",
        "name": name,
        "age_group": "not set",
        "taste_summary": "",
        "preferred_genres": liked,
        "disliked_genres": disliked,
        "completion_range": PERSONA_FILE_GENRE_HISTORY_COMPLETION_RANGE,
    }
    return build_persona_user(persona, catalog, PERSONA_FILE_HISTORY_SEED)["watch_history"]


def _describe_taste(liked: List[str], disliked: List[str]) -> str:
    """One line for the printed report."""
    text = f"likes {', '.join(liked)}"
    return text + (f", dislikes {', '.join(disliked)}" if disliked else "")


def _read_genre_fields(
    data: Dict[str, Any], catalog: Catalog
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """Reads and cleans liked and disliked genres. Returns (liked, disliked, errors, warnings)."""
    valid_genres = sorted({genre for movie in catalog.values() for genre in movie["genres"]})
    errors, warnings, cleaned = [], [], {}
    for field in ["liked_genres", "disliked_genres"]:
        raw, new_errors = _read_string_list(data, field)
        cleaned[field], new_warnings = _clean_genres(raw, valid_genres, field)
        errors += new_errors
        warnings += new_warnings
    if not cleaned["liked_genres"] and not errors:
        errors.append(
            "'liked_genres' has no valid genre left, at least one is needed. "
            f"Valid genres: {', '.join(valid_genres)}."
        )
    return cleaned["liked_genres"], cleaned["disliked_genres"], errors, warnings


def _read_people_fields(
    data: Dict[str, Any], catalog: Catalog, imdb_ready: bool
) -> Tuple[Dict[str, List[str]], List[str], List[str]]:
    """
    Reads the four people lists. The type check always runs, but names are only
    matched against the data when IMDb data exists, otherwise the lists stay
    empty (the single "IMDb not downloaded" warning is added by the caller).
    Returns (people, errors, warnings).
    """
    people: Dict[str, List[str]] = {}
    errors: List[str] = []
    warnings: List[str] = []
    for field in PEOPLE_FIELDS:
        raw, new_errors = _read_string_list(data, field)
        errors += new_errors
        people[field] = []
        if imdb_ready:
            known = _people_in_catalog(catalog, "directors" if "director" in field else "cast")
            people[field], new_warnings = _clean_people(raw, known, field)
            warnings += new_warnings
    return people, errors, warnings


def _persona_uses_imdb(data: Dict[str, Any]) -> bool:
    """True when the file sets any field that needs IMDb data."""
    return any(data.get(field) not in (None, [], "") for field in IMDB_FIELDS)


def build_persona_result(data: Dict[str, Any], catalog: Catalog, as_of: datetime) -> PersonaResult:
    """
    Pure: turns parsed JSON into a user dict. as_of is "now", passed in so
    tests never depend on the clock. Errors and warnings are only collected
    here, the caller decides how to print them.
    """
    name = data.get("name")
    errors = [] if isinstance(name, str) and name.strip() else ["'name' is missing or empty."]
    liked, disliked, genre_errors, warnings = _read_genre_fields(data, catalog)
    limits, limit_errors = _read_limits(data)
    errors += genre_errors + limit_errors

    imdb_ready = catalog_has_imdb_data(catalog)
    if _persona_uses_imdb(data) and not imdb_ready:
        warnings.append(
            "IMDb data is not downloaded, so the IMDb rating and the director and cast "
            "preferences are skipped. Run 'python3 data/download_imdb.py' to use them."
        )
    people, people_errors, people_warnings = _read_people_fields(data, catalog, imdb_ready)
    errors += people_errors
    warnings += people_warnings
    favourites_raw, favourite_errors = _read_string_list(data, "favourite_titles")
    errors += favourite_errors

    if errors:
        return PersonaResult(None, errors, warnings)

    favourite_ids, favourite_warnings = _find_favourites(favourites_raw, catalog)
    history = (
        _favourites_to_history(favourite_ids, as_of)
        if favourite_ids else _genre_history(name, liked, disliked, catalog)
    )
    user = {
        "user_id": "persona_file",
        "name": name.strip(),
        "preferred_genres": liked,
        "disliked_genres": disliked,
        # The MovieLens 3.0 stand in is replaced by the real IMDb floor below.
        "min_avg_rating": None,
        "min_imdb_rating": limits["min_imdb_rating"] if imdb_ready else None,
        "year_from": limits["year_from"],
        "year_to": limits["year_to"],
        **people,
        "age_group": "not set",
        "taste_summary": _describe_taste(liked, disliked),
        "watch_history": history,
        "hard_blocked_movie_ids": [],
        "current_session": [],
    }
    return PersonaResult(user, [], warnings + favourite_warnings)


def load_persona_file(
    path: str, catalog: Catalog, as_of: Optional[datetime] = None
) -> PersonaResult:
    """Reads the file at path and builds the user. Never raises on bad user input."""
    data, read_errors = read_persona_file(path)
    if data is None:
        return PersonaResult(None, read_errors, [])
    return build_persona_result(data, catalog, as_of or datetime.now())
