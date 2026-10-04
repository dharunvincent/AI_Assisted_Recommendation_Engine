"""
src/stage1_candidate_generation/content_based.py

GENERATOR 1 of 8: Content based filtering

Looks at the genres of movies the user has watched and liked, and finds
other movies in the catalog that share those genres. This is the most
basic form of "if you liked this, you might like that".

This generator only looks at this one user's own history, it does not
look at what other users did. That makes it useful once a user has some
watch history, but it struggles for a brand new user with no history yet
(the classic cold start problem), which is exactly why collaborative
filtering and the other generators exist alongside it.
"""

from collections import Counter


def generate(user, catalog, max_candidates=15):
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}

    # Count how often each genre shows up across the movies this user
    # finished with a decent completion percentage. More appearances
    # means that genre matters more to this user.
    genre_counter = Counter()
    for entry in user["watch_history"]:
        if entry["completion_pct"] >= 0.5:
            movie = catalog.get(entry["movie_id"])
            if movie:
                genre_counter.update(movie["genres"])

    if not genre_counter:
        return []  # nothing to go on yet, cold start, another generator has to cover this user

    # A user's declared preferred genres win over genres inferred from
    # history, since crime and action titles often carry a Drama tag
    # too and would otherwise drown out what the user actually asked for.
    favourite_genres = set(user.get("preferred_genres") or [])
    if not favourite_genres:
        favourite_genres = {genre for genre, _ in genre_counter.most_common(3)}

    candidates = []
    for movie in catalog.values():
        if movie["movie_id"] in watched_ids:
            continue
        overlap = favourite_genres.intersection(movie["genres"])
        if overlap:
            candidates.append({
                "movie_id": movie["movie_id"],
                "source": "content_based",
                "reason": "similar genre to titles you watched, " + ", ".join(sorted(overlap)),
            })

    # Prefer candidates with more genre overlap, and cap the list size.
    candidates.sort(key=lambda c: c["reason"].count(","), reverse=True)
    return candidates[:max_candidates]
