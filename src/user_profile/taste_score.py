"""
src/user_profile/taste_score.py

Implements the signal decay formula agreed on during the planning of
this project. The idea is simple, every time the user does something
that signals like or dislike toward a genre, we do not throw away the
old signal and recompute everything from scratch. Instead we update one
running number using a half life decay, so older signals naturally fade
and recent behaviour matters more, without the system needing to replay
the user's entire history on every single request.

Formula:
new_score = old_score * decay_factor_for_elapsed_time + new_signal_weight

decay_factor_for_elapsed_time is based on a half life, meaning the old
score loses half its strength every SIGNAL_HALF_LIFE_DAYS days.
"""

import math

from config.weights import (
    SIGNAL_HALF_LIFE_DAYS,
    SIGNAL_WEIGHT_EXPLICIT_THUMBS_DOWN,
    SIGNAL_WEIGHT_DROP_OFF_EARLY,
    SIGNAL_WEIGHT_DROP_OFF_LATE,
    SIGNAL_WEIGHT_WATCHLIST_NEGLECT,
    SIGNAL_WEIGHT_HOVER_AND_SKIP,
    EARLY_DROP_OFF_CUTOFF,
    LATE_DROP_OFF_CUTOFF,
    SIGNAL_WEIGHT_DROP_OFF_MIDDLE_FACTOR,
    DISLIKE_SCORE_CAP,
)


def decay_factor(days_elapsed):
    """
    Standard half life decay. After SIGNAL_HALF_LIFE_DAYS days, the old
    score is worth exactly half of what it used to be. After two half
    lives, a quarter, and so on.
    """
    return math.pow(0.5, days_elapsed / SIGNAL_HALF_LIFE_DAYS)


def decay_to(score, last_updated, as_of):
    """
    Returns what a stored score is worth at the moment as_of, given that it
    was last updated at last_updated. update_dislike_score only decays a
    score when a NEW event arrives, so a dislike from a year ago with no
    newer event would otherwise keep its full strength forever. Calling this
    once at read time makes old signals fade even when nothing new happened.
    """
    days_elapsed = max((as_of - last_updated).days, 0)
    return score * decay_factor(days_elapsed)


def signal_weight_for_event(event_type, completion_pct=None):
    """
    Maps a raw user event into the base weight it should carry, before
    decay is applied. Returns 0 for events that are not meaningful
    dislike signals, for example finishing almost the whole thing before
    stopping is basically a completed watch, not a dislike.
    """
    if event_type == "explicit_thumbs_down":
        return SIGNAL_WEIGHT_EXPLICIT_THUMBS_DOWN

    if event_type == "drop_off":
        if completion_pct is None:
            return 0.0
        if completion_pct <= EARLY_DROP_OFF_CUTOFF:
            return SIGNAL_WEIGHT_DROP_OFF_EARLY
        if completion_pct >= LATE_DROP_OFF_CUTOFF:
            return SIGNAL_WEIGHT_DROP_OFF_LATE
        # Dropped off after the early cutoff, counted as a weaker, partial
        # signal. The pipeline only sends drop offs below
        # DISLIKE_SIGNAL_MAX_COMPLETION, so in practice this covers the
        # narrow band between the early cutoff and that line.
        return SIGNAL_WEIGHT_DROP_OFF_EARLY * SIGNAL_WEIGHT_DROP_OFF_MIDDLE_FACTOR

    if event_type == "watchlist_neglect":
        return SIGNAL_WEIGHT_WATCHLIST_NEGLECT

    if event_type == "hover_and_skip":
        return SIGNAL_WEIGHT_HOVER_AND_SKIP

    return 0.0


def update_dislike_score(old_score, old_score_timestamp, event_type, event_timestamp, completion_pct=None):
    """
    Call this once whenever a new dislike style signal happens for a
    given genre. Returns the new running score and the timestamp to
    store alongside it for next time.

    old_score: the previously stored dislike strength for this genre
    (0.0 if this is the first signal ever).
    old_score_timestamp: datetime of when old_score was last updated.
    event_type: one of "explicit_thumbs_down", "drop_off",
    "watchlist_neglect", "hover_and_skip".
    event_timestamp: datetime of the new event.
    completion_pct: required only for "drop_off" events.
    """
    days_elapsed = max((event_timestamp - old_score_timestamp).days, 0)
    decayed_old_score = old_score * decay_factor(days_elapsed)

    new_weight = signal_weight_for_event(event_type, completion_pct)
    new_score = decayed_old_score + new_weight

    # Cap at a sane maximum so repeated signals cannot make the dislike
    # score grow without any limit.
    new_score = min(new_score, DISLIKE_SCORE_CAP)

    return new_score, event_timestamp
