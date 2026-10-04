"""
src/stage1_candidate_generation/collaborative.py

GENERATOR 2 of 8: Collaborative filtering (item based)

This generator uses the real MovieLens ratings data from hundreds of
real anonymous users to find patterns like "people who rated movie A
highly also tended to rate movie B highly". This is the classic example
from the design brainstorm, if two real users both rated Harry Potter 1
highly and one of them also rated Harry Potter 2 highly, this generator
will surface Harry Potter 2 for our user after they watch and like Harry
Potter 1.

This generator does not use our synthetic user's own history the way
content based filtering does, it uses the pattern of hundreds of other
real people to find connections our one user's history alone cannot see.

Honesty note on scale: for a dataset this small (about 100000 ratings)
building the full co occurrence table on the fly like this is fine. A
real platform with millions of users and titles would need a smarter
approach, such as matrix factorization or an approximate nearest
neighbour search, instead of this simple full comparison.
"""

import csv
import os
from collections import defaultdict, Counter

DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "ml-latest-small")

_co_occurrence_cache = None


def _build_co_occurrence():
    """
    Builds a lookup table, for every movie, which other movies did the
    same real users also rate 4 stars or higher. Built once and cached
    in memory because ratings.csv does not change between runs.
    """
    global _co_occurrence_cache
    if _co_occurrence_cache is not None:
        return _co_occurrence_cache

    ratings_path = os.path.join(DATA_FOLDER, "ratings.csv")
    user_high_ratings = defaultdict(set)

    if not os.path.exists(ratings_path):
        _co_occurrence_cache = {}
        return _co_occurrence_cache

    with open(ratings_path, encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if float(row["rating"]) >= 4.0:
                user_high_ratings[row["userId"]].add(int(row["movieId"]))

    co_occurrence = defaultdict(Counter)
    for movie_set in user_high_ratings.values():
        movie_list = list(movie_set)
        for i, movie_a in enumerate(movie_list):
            for movie_b in movie_list[i + 1:]:
                co_occurrence[movie_a][movie_b] += 1
                co_occurrence[movie_b][movie_a] += 1

    _co_occurrence_cache = co_occurrence
    return co_occurrence


def generate(user, catalog, max_candidates=15):
    co_occurrence = _build_co_occurrence()
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}
    liked_ids = [entry["movie_id"] for entry in user["watch_history"] if entry["completion_pct"] >= 0.7]

    score_board = Counter()
    for liked_id in liked_ids:
        for related_id, strength in co_occurrence.get(liked_id, {}).items():
            if related_id not in watched_ids:
                score_board[related_id] += strength

    candidates = []
    for movie_id, strength in score_board.most_common(max_candidates):
        if movie_id not in catalog:
            continue
        candidates.append({
            "movie_id": movie_id,
            "source": "collaborative",
            "reason": "other viewers with similar taste also watched this",
        })
    return candidates
