"""
src/stage1_candidate_generation/session_based.py

GENERATOR 6 of 9: Session based filtering

This looks only at what the user has clicked on or watched in the
current sitting, not their whole history. If someone just finished two
true crime documentaries back to back right now, this generator reacts
to that immediately, it does not wait for the long term taste profile to
update.

This is different from content based filtering. Content based filtering
looks at everything a user has ever liked. Session based filtering only
looks at what they just did, right now, in this one sitting.
"""

from src.catalog_pools import trusted_titles


def generate(user, catalog, max_candidates=10):
    session_movie_ids = user.get("current_session", [])
    if not session_movie_ids:
        return []

    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}

    session_genres = set()
    for movie_id in session_movie_ids:
        movie = catalog.get(movie_id)
        if movie:
            session_genres.update(movie["genres"])

    if not session_genres:
        return []

    candidates = []
    # Best known titles first, and none without enough ratings. It used to
    # take the first matches in catalog file order.
    for movie in trusted_titles(catalog, watched_ids | set(session_movie_ids)):
        if session_genres.intersection(movie["genres"]):
            candidates.append({
                "movie_id": movie["movie_id"],
                "source": "session_based",
                "reason": "similar to what you just watched in this session",
            })

    return candidates[:max_candidates]
