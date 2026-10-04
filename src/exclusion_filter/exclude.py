"""
src/exclusion_filter/exclude.py

This sits between stage 1 and stage 2. It is a cleanup step, not a
generator, it never adds new candidates, it only removes ones that
should never be shown to this user at all.

Two kinds of removal happen here:
1. Titles the user has already watched (a safety net in case a generator
   missed this, since every generator is already supposed to filter
   this out on its own).
2. Titles the user has explicitly and strongly told the system they do
   not want to see again, for example a "never recommend this again"
   action on a specific title. This is different from the soft dislike
   penalty used in stage 2 scoring, this is a hard, permanent removal
   the user asked for directly.
"""


def exclude(shortlist, user):
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}
    hard_blocked_ids = set(user.get("hard_blocked_movie_ids", []))

    filtered = [
        candidate for candidate in shortlist
        if candidate["movie_id"] not in watched_ids
        and candidate["movie_id"] not in hard_blocked_ids
    ]

    return filtered
