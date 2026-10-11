"""
src/exclusion_filter/exclude.py

This sits between stage 1 and stage 2. It is a cleanup step, not a
generator, it never adds new candidates, it only removes ones that
should never be shown to this user at all.

Three kinds of removal happen here:
1. Titles the user has already watched (a safety net in case a generator
   missed this, since every generator is already supposed to filter
   this out on its own).
2. Titles the user has explicitly and strongly told the system they do
   not want to see again, for example a "never recommend this again"
   action on a specific title. This is different from the soft dislike
   penalty used in stage 2 scoring, this is a hard, permanent removal
   the user asked for directly.
3. Titles below the user's own quality floor, when they set one. A user
   who says "I never watch anything rated below 6 out of 10" is asking
   for a rule, not a lean, so this is a hard removal too. Titles with no
   rating at all are removed as well, since there is no way to show they
   clear the floor. So are titles with fewer than
   MIN_RATINGS_FOR_QUALITY_FLOOR ratings, because a high average from only
   a few raters is not trustworthy.
"""

from config.weights import MIN_RATINGS_FOR_QUALITY_FLOOR


def exclude(shortlist, user, catalog):
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}
    hard_blocked_ids = set(user.get("hard_blocked_movie_ids", []))
    min_avg_rating = user.get("min_avg_rating")

    def below_quality_floor(movie_id):
        if min_avg_rating is None:
            return False
        movie = catalog.get(movie_id)
        return (
            movie is None
            or movie["avg_rating"] is None
            or movie["rating_count"] < MIN_RATINGS_FOR_QUALITY_FLOOR
            or movie["avg_rating"] < min_avg_rating
        )

    filtered = [
        candidate for candidate in shortlist
        if candidate["movie_id"] not in watched_ids
        and candidate["movie_id"] not in hard_blocked_ids
        and not below_quality_floor(candidate["movie_id"])
    ]

    return filtered
