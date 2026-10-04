"""
src/stage1_candidate_generation/diversity.py

GENERATOR 8 of 8: Diversity injection

All seven other generators chase similarity, similar genre, similar
taste, similar session. If we only ever show a user more of the same,
they get stuck in a narrow bubble and might miss something they would
actually have enjoyed. This generator deliberately does the opposite, it
picks a small number of well regarded titles from genres the user has
barely touched, to keep the catalog feeling open rather than repetitive.

This generator is intentionally kept small in the final shortlist
compared to the others. Its job is to add a little variety, not to take
over the recommendations.
"""

import random


def generate(user, catalog, max_candidates=5, random_seed=None):
    if random_seed is not None:
        random.seed(random_seed)

    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}

    watched_genres = set()
    for entry in user["watch_history"]:
        movie = catalog.get(entry["movie_id"])
        if movie:
            watched_genres.update(movie["genres"])

    unexplored_candidates = [
        movie for movie in catalog.values()
        if movie["movie_id"] not in watched_ids
        and movie["avg_rating"] is not None
        and movie["avg_rating"] >= 3.8
        and not set(movie["genres"]).intersection(watched_genres)
    ]

    if not unexplored_candidates:
        return []

    sample_size = min(max_candidates, len(unexplored_candidates))
    chosen = random.sample(unexplored_candidates, sample_size)

    return [
        {
            "movie_id": movie["movie_id"],
            "source": "diversity",
            "reason": "something a little different, well rated, outside your usual genres",
        }
        for movie in chosen
    ]
