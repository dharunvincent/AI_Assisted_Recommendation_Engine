"""
src/catalog.py

Loads the real MovieLens catalog (movies.csv and ratings.csv) into plain
Python dictionaries that the rest of the system can use. This is the only
file in the project that touches the raw CSV files directly.
"""

import csv
import os
import re

DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ml-latest-small")


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


def load_catalog():
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

    return catalog


def genre_set(catalog):
    """Returns the full set of genres present in the catalog."""
    all_genres = set()
    for movie in catalog.values():
        all_genres.update(movie["genres"])
    return all_genres
