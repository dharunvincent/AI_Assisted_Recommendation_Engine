"""
src/stage1_candidate_generation/trending.py

GENERATOR 4 of 9: Popularity and trending

In a real streaming platform, this generator would call services like
JustWatch or TMDB to see what is trending across the whole internet, not
just on this one platform, so new users and new releases always get a
fair chance even before our own platform has any watch history on them.

This project has no live internet connection for trending data, so as a
stand in, we treat the number of ratings a movie received in the real
MovieLens dataset as a simple proxy for "how many real people watched
and cared enough to rate this". This is a simulation, not a real
trending signal, and it is clearly labeled as such.
"""

from src.catalog_pools import trusted_titles


def generate(user, catalog, max_candidates=15):
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}

    # The shared list is already ordered by number of ratings, which is the
    # stand in for "trending" here.
    popular_movies = trusted_titles(catalog, watched_ids)

    candidates = []
    for movie in popular_movies[:max_candidates]:
        candidates.append({
            "movie_id": movie["movie_id"],
            "source": "trending",
            "reason": "trending now",
        })
    return candidates
