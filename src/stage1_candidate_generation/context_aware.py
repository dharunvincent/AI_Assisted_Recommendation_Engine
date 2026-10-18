"""
src/stage1_candidate_generation/context_aware.py

GENERATOR 5 of 9: Context aware filtering

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

from src.catalog_pools import trusted_titles

CONTEXT_GENRE_RULES = {
    "weekday_daytime": ["Comedy", "Animation", "Documentary"],
    "weekday_evening": ["Drama", "Thriller", "Crime", "Action"],
    "weekend_daytime": ["Animation", "Adventure", "Family", "Comedy"],
    "weekend_evening": ["Action", "Sci-Fi", "Thriller", "Adventure"],
}


def context_bucket(context):
    day = context.get("day_of_week")
    is_evening = context.get("time_of_day") == "evening"
    # Friday evening already feels like the weekend, so it uses the weekend
    # evening genres. Friday daytime is still a working day.
    is_weekend = day in ("Saturday", "Sunday") or (day == "Friday" and is_evening)
    weekend_part = "weekend" if is_weekend else "weekday"
    time_part = "evening" if is_evening else "daytime"
    return f"{weekend_part}_{time_part}"


def genres_for_context(context):
    """
    Pure. The genres that fit the current context bucket. The one place that
    answers this, shared by this generator and by stage 2 context fit.
    """
    return CONTEXT_GENRE_RULES.get(context_bucket(context), [])


def generate(user, catalog, context, max_candidates=15):
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}
    bucket = context_bucket(context)
    preferred_genres = genres_for_context(context)

    if not preferred_genres:
        return []

    # Best known titles come first (the shared helper's order), and titles
    # without enough ratings are left out, so the list is not filled with
    # random obscure films in catalog file order.
    matching = [
        movie for movie in trusted_titles(catalog, watched_ids)
        if set(preferred_genres).intersection(movie["genres"])
    ]

    return [
        {
            "movie_id": movie["movie_id"],
            "source": "context_aware",
            "reason": f"fits a {bucket.replace('_', ' ')} viewing moment",
        }
        for movie in matching[:max_candidates]
    ]
