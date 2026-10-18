"""
src/catalog.py

Loads the real MovieLens catalog (movies.csv and ratings.csv) into plain
Python dictionaries that the rest of the system can use. This is the only
file in the project that touches the raw CSV files directly. If
data/imdb_enriched.csv exists (see data/download_imdb.py) its IMDb rating,
directors and cast are added to each movie too.
"""

import csv
import os
import re
from typing import Any, Dict, List

DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ml-latest-small")
# Optional, built by data/download_imdb.py. The engine runs fine without it.
IMDB_ENRICHED_PATH = os.path.join(DATA_FOLDER, "..", "imdb_enriched.csv")


def _extract_year(raw_title):
    """
    MovieLens stores the year inside the title itself, like
    "Toy Story (1995)". This pulls the year out and returns the clean
    title separately.
    """
    match = re.search(r"\((\d{4})\)\s*$", raw_title)
    if match:
        year = int(match.group(1))
        clean_title = raw_title[: match.start()].strip()
        return clean_title, year
    return raw_title.strip(), None


def _split_names(raw_names: str) -> List[str]:
    """directors and cast are stored as "Name One|Name Two", empty means none."""
    return [name for name in raw_names.split("|") if name]


def _add_imdb_fields(catalog: Dict[int, Dict[str, Any]], imdb_path: str) -> None:
    """
    Adds imdb_rating, imdb_votes, directors and cast to every movie. Movies
    IMDb knows nothing about, and every movie when the file has not been
    downloaded, get None and empty lists, never a crash (the engine must run
    without IMDb data). Changes the catalog in place, which is fine because
    this runs once, inside load_catalog, before anyone else can see it.
    """
    for movie in catalog.values():
        movie.update({"imdb_rating": None, "imdb_votes": None, "directors": [], "cast": []})

    if not os.path.exists(imdb_path):
        return

    with open(imdb_path, encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            movie = catalog.get(int(row["movieId"]))
            if movie is None:
                continue  # an older IMDb file can mention movies we no longer load
            movie["imdb_rating"] = float(row["imdb_rating"]) if row["imdb_rating"] else None
            movie["imdb_votes"] = int(row["imdb_votes"]) if row["imdb_votes"] else None
            movie["directors"] = _split_names(row["directors"])
            movie["cast"] = _split_names(row["cast"])


def load_catalog(imdb_path: str = IMDB_ENRICHED_PATH):
    """
    Returns a dict keyed by movie_id, each value a movie record with
    average rating and rating count already worked out from ratings.csv.
    """
    movies_path = os.path.join(DATA_FOLDER, "movies.csv")
    ratings_path = os.path.join(DATA_FOLDER, "ratings.csv")

    if not os.path.exists(movies_path):
        raise FileNotFoundError(
            "MovieLens data not found. Run 'python data/download_movielens.py' first."
        )

    catalog = {}
    with open(movies_path, encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            movie_id = int(row["movieId"])
            title, year = _extract_year(row["title"])
            genres = row["genres"].split("|") if row["genres"] != "(no genres listed)" else []
            catalog[movie_id] = {
                "movie_id": movie_id,
                "title": title,
                "year": year,
                "genres": genres,
                "rating_sum": 0.0,
                "rating_count": 0,
            }

    if os.path.exists(ratings_path):
        with open(ratings_path, encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                movie_id = int(row["movieId"])
                if movie_id in catalog:
                    catalog[movie_id]["rating_sum"] += float(row["rating"])
                    catalog[movie_id]["rating_count"] += 1

    for movie in catalog.values():
        if movie["rating_count"] > 0:
            movie["avg_rating"] = round(movie["rating_sum"] / movie["rating_count"], 2)
        else:
            movie["avg_rating"] = None
        # rating_sum was only ever a working total used to compute
        # avg_rating above, nothing downstream needs it, so drop it
        # instead of leaving a half used field sitting in every record.
        del movie["rating_sum"]

    _add_imdb_fields(catalog, imdb_path)
    return catalog


def catalog_has_imdb_data(catalog: Dict[int, Dict[str, Any]]) -> bool:
    """
    True when data/imdb_enriched.csv was loaded. Checked by looking for at
    least one rating, so a half empty file counts as "no IMDb data" and the
    IMDb based preferences are skipped instead of silently matching nothing.
    """
    return any(movie["imdb_rating"] is not None for movie in catalog.values())
