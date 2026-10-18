"""
src/stage1_candidate_generation/diversity.py

GENERATOR 8 of 9: Diversity injection

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

from config.weights import DIVERSITY_MIN_AVG_RATING, DIVERSITY_MIN_RATINGS


def generate(user, catalog, max_candidates=5, random_seed=None):
    # A private random generator, so a seed here never changes the random
    # numbers used by any other code in the program. random.seed() would
    # reset the shared global generator for everyone.
    rng = random.Random(random_seed)

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
        and movie["avg_rating"] >= DIVERSITY_MIN_AVG_RATING
        and movie["rating_count"] >= DIVERSITY_MIN_RATINGS
        and not set(movie["genres"]).intersection(watched_genres)
    ]

    if not unexplored_candidates:
        return []

    sample_size = min(max_candidates, len(unexplored_candidates))
    chosen = rng.sample(unexplored_candidates, sample_size)

    return [
        {
            "movie_id": movie["movie_id"],
            "source": "diversity",
            "reason": "something a little different, well rated, outside your usual genres",
        }
        for movie in chosen
    ]
