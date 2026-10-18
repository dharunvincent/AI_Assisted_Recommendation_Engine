"""
src/results_report.py

Everything about showing and keeping the results of a persona file run:
the readable printed list, the CSV with the full ranked list, and the
"filter report" that says how many titles each hard filter removed.

The row building and text formatting are pure (data in, data out). Only
write_results_csv touches the disk.
"""

import csv
import os
import re
from datetime import date
from typing import Any, Dict, List, NamedTuple, Optional

from config.weights import SHORT_LIST_WARNING_BELOW

RESULTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
CSV_COLUMNS = [
    "rank", "title", "year", "imdb_rating", "directors", "top_cast",
    "match_percent", "final_score", "badge", "main_reason", "all_reasons",
]
BADGE_MARK = "✓"  # shown when the engine's badge flag is set (match 85 percent or above)
TOP_CAST_SHOWN = 2  # the printed line stays short, the full cast is in the data

# Filters that are not a user preference (a title already watched cannot be
# "relaxed"), so they are never named as the one to relax.
NOT_RELAXABLE_FILTERS = {"already watched", "never recommend again"}


def build_result_rows(
    ranked: List[Dict[str, Any]], catalog: Dict[int, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    One row per ranked title, in rank order, with every column the printout and
    the CSV need. A missing IMDb rating, director or cast becomes an empty
    value, never an error.
    """
    rows = []
    for position, item in enumerate(ranked, start=1):
        movie = catalog[item["movie_id"]]
        rows.append({
            "rank": position,
            "title": item["title"],
            "year": item["year"],
            "imdb_rating": "" if movie["imdb_rating"] is None else movie["imdb_rating"],
            "directors": ", ".join(movie["directors"]),
            "top_cast": ", ".join(movie["cast"][:TOP_CAST_SHOWN]),
            "match_percent": item["match_percent"],
            "final_score": item["final_score"],
            "badge": "yes" if item["show_badge"] else "no",
            "main_reason": item["reasons"][0],
            "all_reasons": " | ".join(item["reasons"]),
        })
    return rows


class DisplayOptions(NamedTuple):
    """What to show on screen. The CSV always has the full list."""
    badged_only: bool = False
    top: Optional[int] = None


def select_rows(rows: List[Dict[str, Any]], options: DisplayOptions) -> List[Dict[str, Any]]:
    """
    Pure. The badge filter runs first, then --top, so "--badged-only --top 5"
    means the best five movies that carry the badge. Rank numbers are kept.
    """
    shown = [row for row in rows if row["badge"] == "yes"] if options.badged_only else rows
    return shown if options.top is None else shown[:options.top]


def format_result_table(rows: List[Dict[str, Any]]) -> List[str]:
    """Every given row as an aligned table: rank, title, year, IMDb, match %, badge, reason."""
    header = ["Rank", "Title", "Year", "IMDb", "Match", "Badge", "Main reason"]
    body = [
        [
            str(row["rank"]), row["title"], str(row["year"]),
            str(row["imdb_rating"]) if row["imdb_rating"] != "" else "n/a",
            f"{row['match_percent']:g}%", BADGE_MARK if row["badge"] == "yes" else "",
            row["main_reason"],
        ]
        for row in rows
    ]
    widths = [max(len(line[i]) for line in [header] + body) for i in range(len(header) - 1)]
    return [
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths)) + "  " + line[-1]
        for line in [header] + body
    ]


def format_launcher_table(rows: List[Dict[str, Any]]) -> List[str]:
    """
    The table of the `recommend` launcher: every row, numbers right aligned,
    a divider under the header. Separate from format_result_table on purpose,
    so the output of the older commands never changes.
    """
    header = ["Rank", "Title", "Year", "IMDb", "Match", "Badge", "Main reason"]
    body = [
        [
            str(row["rank"]), row["title"], str(row["year"]),
            str(row["imdb_rating"]) if row["imdb_rating"] != "" else "n/a",
            f"{row['match_percent']:g}%", BADGE_MARK if row["badge"] == "yes" else "",
            row["main_reason"],
        ]
        for row in rows
    ]
    widths = [max(len(line[i]) for line in [header] + body) for i in range(len(header) - 1)]
    right_aligned = {0, 2, 3, 4}  # rank, year, IMDb, match

    def render(line: List[str]) -> str:
        cells = [
            cell.rjust(width) if i in right_aligned else cell.ljust(width)
            for i, (cell, width) in enumerate(zip(line, widths))
        ]
        return "  ".join(cells + [line[-1]]).rstrip()

    divider = "  ".join("-" * width for width in widths) + "  " + "-" * len(header[-1])
    return [render(header), divider] + [render(line) for line in body]


def badge_summary_line(rows: List[Dict[str, Any]]) -> str:
    """Pure: "X of Y movies earned the badge."."""
    earned = sum(1 for row in rows if row["badge"] == "yes")
    return f"{earned} of {len(rows)} movies earned the badge."


def format_filter_report(
    removed_counts: Dict[str, int], candidate_count: int, final_count: int
) -> List[str]:
    """
    Says how many of the stage 1 candidates each hard filter removed. Counts
    are per filter on its own, so they can add up to more than the total, see
    src/exclusion_filter/exclude.py. When the final list is short, names the
    preference filter that removed the most, so the user knows what to relax.
    """
    lines = [f"Filter report ({candidate_count} stage 1 candidates, {final_count} recommended):"]
    lines += [f"- {name}: removed {count}" for name, count in removed_counts.items()]

    if final_count < SHORT_LIST_WARNING_BELOW:
        lines.append(_short_list_advice(removed_counts, final_count))
    return lines


def _short_list_advice(removed_counts: Dict[str, int], final_count: int) -> str:
    """The line that explains a short final list."""
    relaxable = {n: c for n, c in removed_counts.items() if n not in NOT_RELAXABLE_FILTERS}
    prefix = f"Only {final_count} titles are left (fewer than {SHORT_LIST_WARNING_BELOW})."
    if not relaxable or max(relaxable.values()) == 0:
        return prefix + " No preference filter removed anything, so stage 1 found few titles."
    strictest = max(relaxable, key=relaxable.get)
    return (
        f"{prefix} The '{strictest}' filter removed the most "
        f"({relaxable[strictest]}), relax that preference first."
    )


def safe_file_stem(text: str, fallback: str) -> str:
    """Text made safe to use in a file name. Shared by the results and persona files."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or fallback


def results_file_name(persona_name: str, today: date) -> str:
    """results/<persona name>_<date>.csv, with anything odd in the name made safe."""
    return f"{safe_file_stem(persona_name, 'persona')}_{today.isoformat()}.csv"


def write_results_csv(
    rows: List[Dict[str, Any]], persona_name: str, today: date, folder: str = RESULTS_FOLDER
) -> str:
    """
    Saves the full ranked list and returns the file path. Raises OSError if the
    disk refuses, the caller turns that into a warning because the printed
    list is already on screen. Written to a temp file and renamed so a crash
    never leaves half a file.
    """
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, results_file_name(persona_name, today))
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp_path, path)
    return os.path.abspath(path)
