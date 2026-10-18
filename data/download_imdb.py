"""
data/download_imdb.py

Run this once to add real IMDb ratings, directors and cast to the catalog.

MovieLens has no IMDb scores, directors or actors. It does ship links.csv,
which maps every MovieLens movieId to an IMDb id, so we can join the two.
IMDb publishes free datasets for personal, non commercial use at
https://datasets.imdbws.com/ , see data/README.md for the licence and credit.

The raw IMDb files are huge (title.principals alone is several hundred MB),
so everything is streamed line by line with gzip and we only keep rows for
movies that exist in MovieLens. The result is one small file,
data/imdb_enriched.csv, and the big downloads are deleted afterwards.

Run with:  python3 data/download_imdb.py
"""

import csv
import gzip
import os
import shutil
import sys
import urllib.request
from typing import Dict, Iterator, List, NamedTuple, Set, Tuple

DATA_FOLDER = os.path.dirname(os.path.abspath(__file__))
LINKS_PATH = os.path.join(DATA_FOLDER, "ml-latest-small", "links.csv")
RAW_FOLDER = os.path.join(DATA_FOLDER, "imdb_raw")
OUTPUT_PATH = os.path.join(DATA_FOLDER, "imdb_enriched.csv")

IMDB_BASE_URL = "https://datasets.imdbws.com/"
IMDB_FILES = [
    "title.ratings.tsv.gz",
    "title.crew.tsv.gz",
    "title.principals.tsv.gz",
    "name.basics.tsv.gz",
]

# These are not tunable preferences, they describe the IMDb file format.
MAX_CAST_PER_MOVIE = 5
CAST_CATEGORIES = {"actor", "actress"}
IMDB_MISSING = "\\N"  # how IMDb writes "no value" in its files
OUTPUT_COLUMNS = ["movieId", "imdb_rating", "imdb_votes", "directors", "cast"]


class Summary(NamedTuple):
    """The numbers printed at the end of a run."""
    movielens_movies: int
    matched: int
    no_rating: int


def imdb_id_from_link(raw_imdb_id: str) -> str:
    """
    links.csv stores "0114709", IMDb's own files use "tt0114709". The number
    is always at least 7 digits, so we pad with zeros before adding "tt"
    (reading the csv as text keeps the leading zeros, a number would lose them).
    """
    return "tt" + raw_imdb_id.strip().zfill(7)


def read_links(links_path: str) -> Dict[str, List[int]]:
    """
    Returns IMDb id mapped to the MovieLens ids that point at it. A list,
    because in rare cases two MovieLens rows share one IMDb id.
    """
    links: Dict[str, List[int]] = {}
    with open(links_path, encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if not row["imdbId"].strip():
                continue  # MovieLens has no IMDb id for this movie
            links.setdefault(imdb_id_from_link(row["imdbId"]), []).append(int(row["movieId"]))
    return links


def stream_rows(gz_path: str) -> Iterator[List[str]]:
    """
    Yields one list of columns per line of a .tsv.gz file, skipping the header.
    Reading line by line keeps memory flat however big the file is. IMDb fields
    never contain tabs, so a plain split is safe (and faster than csv here).
    """
    with gzip.open(gz_path, "rt", encoding="utf-8") as file:
        next(file, None)  # header line
        for line in file:
            yield line.rstrip("\n").split("\t")


def read_ratings(gz_path: str, wanted: Set[str]) -> Dict[str, Tuple[float, int]]:
    """title.ratings: tconst, averageRating, numVotes."""
    return {
        row[0]: (float(row[1]), int(row[2]))
        for row in stream_rows(gz_path)
        if row[0] in wanted
    }


def read_director_ids(gz_path: str, wanted: Set[str]) -> Dict[str, List[str]]:
    """title.crew: tconst, directors (comma separated person ids), writers."""
    return {
        row[0]: row[1].split(",")
        for row in stream_rows(gz_path)
        if row[0] in wanted and row[1] != IMDB_MISSING
    }


def read_cast_ids(gz_path: str, wanted: Set[str]) -> Dict[str, List[str]]:
    """
    title.principals: tconst, ordering, nconst, category, job, characters.
    Keeps the top MAX_CAST_PER_MOVIE billed actors and actresses. "ordering"
    is the billing order, so the lowest numbers are the top billed people.
    Other categories (writer, producer ...) are not cast, so they are skipped.
    """
    billed: Dict[str, List[Tuple[int, str]]] = {}
    for row in stream_rows(gz_path):
        if row[0] in wanted and row[3] in CAST_CATEGORIES:
            billed.setdefault(row[0], []).append((int(row[1]), row[2]))
    return {
        tconst: _top_billed_people(people)
        for tconst, people in billed.items()
    }


def _top_billed_people(people: List[Tuple[int, str]]) -> List[str]:
    """
    Lowest billing number first, each person once. IMDb lists an actor twice
    when they play two roles in one film, and a repeat would waste a cast slot.
    """
    ordered: List[str] = []
    for _, person in sorted(people):
        if person not in ordered:
            ordered.append(person)
    return ordered[:MAX_CAST_PER_MOVIE]


def read_names(gz_path: str, wanted: Set[str]) -> Dict[str, str]:
    """name.basics: nconst, primaryName, ... Only people we need are kept."""
    return {row[0]: row[1] for row in stream_rows(gz_path) if row[0] in wanted}


def names_for(person_ids: List[str], names: Dict[str, str]) -> List[str]:
    """Turns person ids into names. An id with no known name is dropped."""
    return [names[person] for person in person_ids if person in names]


def build_enriched_rows(
    links: Dict[str, List[int]],
    ratings: Dict[str, Tuple[float, int]],
    director_ids: Dict[str, List[str]],
    cast_ids: Dict[str, List[str]],
    names: Dict[str, str],
) -> Tuple[List[Dict[str, object]], Summary]:
    """
    Pure join of everything we read into output rows, one per MovieLens movie
    that IMDb knows about. A movie with no rating still gets a row (empty
    rating), so later code can tell "IMDb knows it" from "IMDb never heard of it".
    """
    rows: List[Dict[str, object]] = []
    movielens_movies = sum(len(ids) for ids in links.values())
    no_rating = 0

    for tconst, movie_ids in links.items():
        known = tconst in ratings or tconst in director_ids or tconst in cast_ids
        if not known:
            continue
        rating, votes = ratings.get(tconst, (None, None))
        no_rating += len(movie_ids) if rating is None else 0
        for movie_id in movie_ids:
            rows.append({
                "movieId": movie_id,
                "imdb_rating": "" if rating is None else rating,
                "imdb_votes": "" if votes is None else votes,
                "directors": "|".join(names_for(director_ids.get(tconst, []), names)),
                "cast": "|".join(names_for(cast_ids.get(tconst, []), names)),
            })

    rows.sort(key=lambda row: row["movieId"])
    return rows, Summary(movielens_movies, len(rows), no_rating)


def write_enriched_csv(rows: List[Dict[str, object]], output_path: str) -> None:
    """
    Writes the small output file. Saved as utf-8 because names have accents.
    It is written to a temp file and then renamed, so a crash half way can
    never leave a broken imdb_enriched.csv (or damage a good older one).
    """
    temp_path = output_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp_path, output_path)


def download_imdb_files(raw_folder: str) -> None:
    """Downloads the four IMDb files into raw_folder, one after another."""
    os.makedirs(raw_folder, exist_ok=True)
    for file_name in IMDB_FILES:
        print(f"Downloading {file_name} ...")
        urllib.request.urlretrieve(IMDB_BASE_URL + file_name, os.path.join(raw_folder, file_name))


def build_from_raw_files(raw_folder: str, links: Dict[str, List[int]]) -> Summary:
    """
    Reads the four downloaded files and writes data/imdb_enriched.csv. Names
    are read last, and only for the people who actually appear in the cast or
    director lists, so the huge name file never sits in memory.
    """
    wanted = set(links)

    def path(file_name: str) -> str:
        """Full path of one downloaded file."""
        return os.path.join(raw_folder, file_name)

    print("Reading ratings, directors and cast ...")
    ratings = read_ratings(path("title.ratings.tsv.gz"), wanted)
    director_ids = read_director_ids(path("title.crew.tsv.gz"), wanted)
    cast_ids = read_cast_ids(path("title.principals.tsv.gz"), wanted)

    needed_people = {p for ids in (*director_ids.values(), *cast_ids.values()) for p in ids}
    print(f"Looking up {len(needed_people)} names ...")
    names = read_names(path("name.basics.tsv.gz"), needed_people)

    rows, summary = build_enriched_rows(links, ratings, director_ids, cast_ids, names)
    write_enriched_csv(rows, OUTPUT_PATH)
    return summary


def print_summary(summary: Summary) -> None:
    """Prints the short result report."""
    print(f"Matched {summary.matched} of {summary.movielens_movies} MovieLens movies to IMDb.")
    print(f"{summary.no_rating} of the matched movies have no IMDb rating.")
    print(f"Saved {OUTPUT_PATH}")
    print("Information courtesy of IMDb (https://www.imdb.com). Used with permission.")


def main() -> int:
    """
    Returns the exit code: 0 for success, 1 for a problem we can explain.
    The raw downloads are deleted on every path, success or failure, because
    they are hundreds of MB and nothing else needs them.
    """
    if not os.path.exists(LINKS_PATH):
        print(f"Cannot find {LINKS_PATH}. Run 'python3 data/download_movielens.py' first.")
        return 1

    try:
        links = read_links(LINKS_PATH)
        download_imdb_files(RAW_FOLDER)
        print_summary(build_from_raw_files(RAW_FOLDER, links))
        return 0
    except (OSError, ValueError, EOFError) as error:
        # OSError covers network and disk problems, ValueError a malformed row,
        # EOFError a download that was cut off half way.
        print(f"IMDb download or processing failed: {error}")
        print("Any older imdb_enriched.csv was left untouched. Run the script again to retry.")
        return 1
    finally:
        shutil.rmtree(RAW_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
