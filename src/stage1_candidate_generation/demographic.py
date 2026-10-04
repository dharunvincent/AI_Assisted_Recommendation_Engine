"""
src/stage1_candidate_generation/demographic.py

GENERATOR 3 of 8: Demographic filtering

Recommends movies that tend to do well with people who share the user's
age group, regardless of that specific user's own watch history. This is
mainly useful for new users who have little or no history yet.

Honesty note: the real MovieLens ml-latest-small dataset we use for the
movie catalog does not include age or region data for its real users, so
we cannot actually compute "which real MovieLens users aged 18 to 24
rated this highly" the way a real streaming platform would. Instead this
generator uses a simple, clearly made up mapping of age group to genre
preference, combined with the real average ratings already in the
catalog. This is a simplification made for this portfolio project, not a
claim that this is how a production demographic filter should be built.
"""

AGE_GROUP_GENRE_PREFERENCE = {
    "13 to 17": ["Animation", "Adventure", "Comedy", "Fantasy"],
    "18 to 24": ["Action", "Comedy", "Sci-Fi", "Thriller"],
    "25 to 34": ["Drama", "Action", "Comedy", "Crime"],
    "35 to 44": ["Drama", "Thriller", "Crime", "Romance"],
    "45 plus": ["Drama", "Documentary", "Romance", "Mystery"],
}


def generate(user, catalog, max_candidates=15):
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}
    preferred_genres = AGE_GROUP_GENRE_PREFERENCE.get(user["age_group"], [])

    if not preferred_genres:
        return []

    matches = []
    for movie in catalog.values():
        if movie["movie_id"] in watched_ids:
            continue
        if movie["avg_rating"] is None:
            continue
        if set(preferred_genres).intersection(movie["genres"]):
            matches.append(movie)

    matches.sort(key=lambda movie: movie["avg_rating"], reverse=True)

    candidates = []
    for movie in matches[:max_candidates]:
        candidates.append({
            "movie_id": movie["movie_id"],
            "source": "demographic",
            "reason": f"popular among the {user['age_group']} age group",
        })
    return candidates
