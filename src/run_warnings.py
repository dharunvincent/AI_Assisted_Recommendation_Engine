"""
src/run_warnings.py

Builds the short "Warnings" section printed once at the end of a run.

The engine handles problems at three levels:
1. Stop with a clear error, when the results would be meaningless.
2. Warn and continue, when one preference cannot be used (an unknown
   genre, a director not found, IMDb data not downloaded).
3. Skip quietly and count, when one movie has missing data (no IMDb
   rating, no cast). The movie is treated as unknown, never a crash.

Levels 2 and 3 end up here. Nothing is ever printed one line per movie,
the same message is grouped with a count instead.
"""

from collections import Counter
from typing import Any, Dict, List

# Level 3: the three kinds of missing movie data we count, and the wording used.
MISSING_DATA_LABELS = {
    "rating": "titles had no IMDb rating",
    "directors": "titles had no director data",
    "cast": "titles had no cast data",
}
# Which catalog field each kind of missing data is read from.
MISSING_DATA_FIELDS = {"rating": "imdb_rating", "directors": "directors", "cast": "cast"}


def count_missing_movie_data(
    catalog: Dict[int, Dict[str, Any]], kinds: List[str]
) -> Dict[str, int]:
    """
    Level 3. For each requested kind ("rating", "directors", "cast"), how many
    catalog titles have nothing for it. Only the kinds the persona actually
    uses are requested, so a persona with no cast preferences never sees a
    cast warning. Counts only, one number per kind, never one line per movie.
    """
    counts = {}
    for kind in kinds:
        field = MISSING_DATA_FIELDS[kind]
        counts[kind] = sum(1 for movie in catalog.values() if not movie[field])
    return counts


def format_warning_section(warnings: List[str], missing_counts: Dict[str, int]) -> List[str]:
    """
    Level 2 messages are grouped (the same text twice becomes "(x2)"), then
    the level 3 counts follow. Returns no lines at all when there is nothing
    to say, so a clean run prints no empty "Warnings" header.
    """
    lines = []
    for message, times in Counter(warnings).items():
        lines.append(f"- {message}" + (f" (x{times})" if times > 1 else ""))
    for kind, count in missing_counts.items():
        if count > 0:
            lines.append(f"- {count} {MISSING_DATA_LABELS[kind]}")

    return ["Warnings:"] + lines if lines else []
