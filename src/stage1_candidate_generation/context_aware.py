"""
src/stage1_candidate_generation/context_aware.py

GENERATOR 5 of 8: Context aware filtering

Looks at the situation the user is in right now, not their long term
taste. For example, a weekday lunch break probably calls for something
short and light, a Friday night probably calls for something bigger.

This generator reads a "context" dictionary that pipeline.py builds for
the current session, such as time of day, day of week and device. The
rules below are simple and hand written for this project. A real
platform would learn these patterns over time instead of hard coding
them, which is also why "personalized context pattern scoring" (learning
each individual user's own personal context habits) was intentionally
left out of this project, it was flagged during planning as extra scope
not needed to prove the architecture works.
"""

CONTEXT_GENRE_RULES = {
    "weekday_daytime": ["Comedy", "Animation", "Documentary"],
    "weekday_evening": ["Drama", "Thriller", "Crime", "Action"],
    "weekend_daytime": ["Animation", "Adventure", "Family", "Comedy"],
    "weekend_evening": ["Action", "Sci-Fi", "Thriller", "Adventure"],
}


def _context_bucket(context):
    is_weekend = context.get("day_of_week") in ("Saturday", "Sunday")
    is_evening = context.get("time_of_day") == "evening"
    weekend_part = "weekend" if is_weekend else "weekday"
    time_part = "evening" if is_evening else "daytime"
    return f"{weekend_part}_{time_part}"


def generate(user, catalog, context, max_candidates=15):
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}
    bucket = _context_bucket(context)
    preferred_genres = CONTEXT_GENRE_RULES.get(bucket, [])

    if not preferred_genres:
        return []

    candidates = []
    for movie in catalog.values():
        if movie["movie_id"] in watched_ids:
            continue
        if set(preferred_genres).intersection(movie["genres"]):
            candidates.append({
                "movie_id": movie["movie_id"],
                "source": "context_aware",
                "reason": f"fits a {bucket.replace('_', ' ')} viewing moment",
            })

    return candidates[:max_candidates]
