"""
src/stage1_candidate_generation/collaborative.py

GENERATOR 2 of 9: Collaborative filtering (item based)

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

How two movies are scored, in plain English (cosine similarity):
Count how many users rated movie A highly, how many rated movie B highly,
and how many rated BOTH highly. The link between A and B is

    users who liked both / square root of (users who liked A x users who liked B)

This is a fraction between 0 and 1. It fixes a problem with raw counts.
A blockbuster that half of all users liked shares fans with almost every
movie, so with raw counts it wins for everyone. With this formula, a
blockbuster only scores high next to a movie if its fans overlap with that
movie's fans MORE than chance would suggest. A small, niche movie whose
fans nearly all also liked movie A scores higher than a blockbuster that
only a small part of A's fans liked. Pairs shared by fewer than
COLLAB_MIN_CO_OCCURRENCE users are ignored, because tiny counts are noise.

Honesty note on scale: for a dataset this small (about 100000 ratings)
building the full table on the fly like this is fine. A real platform
with millions of users and titles would need a smarter approach, such as
matrix factorization or an approximate nearest neighbour search, instead
of this simple full comparison.
"""

import csv
import math
import os
from collections import defaultdict, Counter

from src.catalog_pools import is_trusted
from config.weights import (
    LIKED_COMPLETION_THRESHOLD,
    COLLAB_HIGH_RATING_THRESHOLD,
    COLLAB_MIN_CO_OCCURRENCE,
)

DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "ml-latest-small")

_similarity_cache = {}  # one finished table per set of excluded ratings


def build_similarity_table(rating_rows, excluded_pairs=frozenset()):
    """
    rating_rows: an iterable of (user_id, movie_id, rating).
    excluded_pairs: (user_id, movie_id) ratings to leave out completely.
    The evaluation uses this to keep held out ratings out of the table, so
    the model never sees the answers it is tested on.

    Returns a dict: movie_id mapped to {other_movie_id: similarity}, where
    similarity is the cosine similarity described at the top of this file.
    """
    # 1. For every user, the set of movies they rated highly.
    user_high_ratings = defaultdict(set)
    for user_id, movie_id, rating in rating_rows:
        if rating >= COLLAB_HIGH_RATING_THRESHOLD and (user_id, movie_id) not in excluded_pairs:
            user_high_ratings[user_id].add(movie_id)

    # 2. How many users rated each movie highly, and how many rated each
    # pair of movies highly together.
    fans_of = Counter()
    fans_of_both = defaultdict(Counter)
    for movie_set in user_high_ratings.values():
        movie_list = list(movie_set)
        fans_of.update(movie_list)
        for i, movie_a in enumerate(movie_list):
            for movie_b in movie_list[i + 1:]:
                fans_of_both[movie_a][movie_b] += 1
                fans_of_both[movie_b][movie_a] += 1

    # 3. Turn the counts into cosine similarity, dropping noisy pairs.
    similarity = {}
    for movie_a, partners in fans_of_both.items():
        similarity[movie_a] = {
            movie_b: shared / math.sqrt(fans_of[movie_a] * fans_of[movie_b])
            for movie_b, shared in partners.items()
            if shared >= COLLAB_MIN_CO_OCCURRENCE
        }
    return similarity


def _read_rating_rows():
    ratings_path = os.path.join(DATA_FOLDER, "ratings.csv")
    if not os.path.exists(ratings_path):
        return
    with open(ratings_path, encoding="utf-8") as file:
        for row in csv.DictReader(file):
            yield int(row["userId"]), int(row["movieId"]), float(row["rating"])


def get_similarity_table(excluded_pairs=frozenset()):
    """
    The table for the real ratings file, built once per set of excluded
    ratings and kept in memory, because ratings.csv does not change.
    """
    key = frozenset(excluded_pairs)
    if key not in _similarity_cache:
        _similarity_cache[key] = build_similarity_table(_read_rating_rows(), key)
    return _similarity_cache[key]


def generate(user, catalog, max_candidates=15, similarity_table=None):
    if similarity_table is None:
        similarity_table = get_similarity_table()
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}
    liked_ids = [entry["movie_id"] for entry in user["watch_history"] if entry["completion_pct"] >= LIKED_COMPLETION_THRESHOLD]

    score_board = Counter()
    for liked_id in liked_ids:
        for related_id, similarity in similarity_table.get(liked_id, {}).items():
            if related_id not in watched_ids:
                score_board[related_id] += similarity

    # Take the strongest links first, but skip titles without enough ratings:
    # a link needs only a few shared fans, so a thinly rated title could
    # otherwise get through. The cut to max_candidates comes AFTER this.
    picks = [
        (movie_id, score) for movie_id, score in score_board.most_common()
        if movie_id in catalog and is_trusted(catalog[movie_id])
    ][:max_candidates]
    # Strength is each pick's score relative to the best pick, so it is 0 to 1
    # for every user whatever the size of their history. Stage 2 reads it.
    best_score = picks[0][1] if picks else 1.0
    candidates = []
    for movie_id, score in picks:
        candidates.append({
            "movie_id": movie_id,
            "source": "collaborative",
            "reason": "other viewers with similar taste also watched this",
            "collab_strength": score / best_score,
        })
    return candidates
