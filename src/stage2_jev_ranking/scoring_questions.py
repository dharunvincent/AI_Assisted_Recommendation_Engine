"""
src/stage2_jev_ranking/scoring_questions.py

Builds the exact state and questions that get sent to the mock JEV
client (jev_client.py) for one candidate movie, for one user. Each call
to JEV should bundle a small number of narrow, specific questions about
one piece of content at a time, this is the pattern recommended in the
real TypeSafe cookbooks, do not ask one giant vague question, ask
several small calibrated ones and combine them yourself in code.

Three questions are asked per candidate:
1. taste_fit, how well does this match the user's personal taste
2. completion_likelihood, how likely is the user to finish watching it
3. context_fit, how well does it fit the user's current situation

A fourth question, dislike_override, is only meaningful when a dislike
penalty is already active for this movie's genres.

business_weight is not a JEV question at all, it comes straight from
the business_rules generator in stage 1 and is combined separately in
rank.py.
"""

from src.stage2_jev_ranking.jev_client import Score, Choice
from config.weights import (
    TASTE_BIAS_BASE,
    TASTE_BIAS_PER_GENRE_OVERLAP,
    TASTE_BIAS_PER_PREFERRED_PERSON,
    TASTE_BIAS_PEOPLE_CAP,
    CONTEXT_BIAS_FROM_CONTEXT_GENERATOR,
    CONTEXT_BIAS_DEFAULT,
    OVERRIDE_BIAS_STRONG_FIT,
    OVERRIDE_BIAS_WEAK_FIT,
    OVERRIDE_MIN_GENRE_OVERLAP,
)


def build_state(user, movie, candidate, context, dislike_penalty, preferred_people=()):
    """
    Builds the "state", the facts JEV is allowed to see for this one
    user and this one candidate movie. Keeping this small and specific
    mirrors the real JEV context limit, which rewards short, focused
    state over dumping a user's entire history into every call.

    preferred_people are the user's favourite directors and actors found in
    this movie. The key is only added when there are some: the mock JEV
    hashes the whole state, so an always present empty key would change the
    answers for every user who has no preferred people.
    """
    state = {
        "movie_title": movie["title"],
        "movie_genres": tuple(sorted(movie["genres"])),
        "movie_avg_rating": movie["avg_rating"],
        "user_age_group": user["age_group"],
        "candidate_sources": tuple(sorted(candidate["sources"])),
        "dislike_penalty": round(dislike_penalty, 3),
        "context_time_of_day": context.get("time_of_day"),
        "context_day_of_week": context.get("day_of_week"),
    }
    if preferred_people:
        state["preferred_people_matched"] = tuple(sorted(preferred_people))
    return state


def people_taste_boost(preferred_people_count):
    """
    The extra expected taste fit for preferred directors and actors in this
    title: a fixed step per person, capped so cast alone cannot decide the rank.
    """
    return min(preferred_people_count * TASTE_BIAS_PER_PREFERRED_PERSON, TASTE_BIAS_PEOPLE_CAP)


def build_questions(
    movie, candidate, dislike_penalty, genre_overlap_count, preferred_people_count=0
):
    """
    Returns the dict of questions to send to jev_client.ask(), each
    carrying a bias_hint worked out from simple real facts. See
    jev_client.py for why the mock needs this hint.
    """
    # Rough expectation for taste fit, more genre overlap with things
    # the user already liked pushes this up. The dislike penalty is
    # deliberately NOT part of this number. It is applied exactly once,
    # in rank.py, so that the override logic can soften it cleanly. If it
    # was also subtracted here, the override could never fully work.
    taste_bias = (
        TASTE_BIAS_BASE
        + (genre_overlap_count * TASTE_BIAS_PER_GENRE_OVERLAP)
        + people_taste_boost(preferred_people_count)
    )

    # Rough expectation for completion likelihood, a well regarded movie
    # in the real MovieLens data is a reasonable proxy for "most people
    # who start this finish it".
    rating = movie["avg_rating"] if movie["avg_rating"] is not None else 3.0
    completion_bias = rating / 5.0

    # Rough expectation for context fit, if this candidate already came
    # from the context_aware generator in stage 1, it already fits the
    # current moment reasonably well.
    context_bias = (
        CONTEXT_BIAS_FROM_CONTEXT_GENERATOR if "context_aware" in candidate["sources"] else CONTEXT_BIAS_DEFAULT
    )

    return {
        "taste_fit": Score(
            "Ignoring any general dislike of this genre, how well does this "
            "match this user's personal taste?",
            bias_hint=taste_bias,
        ),
        "completion_likelihood": Score(
            "How likely is this user to finish watching this?",
            bias_hint=completion_bias,
        ),
        "context_fit": Score(
            "How well does this fit the user's current viewing context?",
            bias_hint=context_bias,
        ),
        "dislike_override": Choice(
            "Despite a general dislike signal for this genre, does this "
            "specific title stand out enough for this user to override it?",
            options=["override_show_anyway", "keep_penalty"],
            bias_hint=(
                OVERRIDE_BIAS_STRONG_FIT
                if genre_overlap_count >= OVERRIDE_MIN_GENRE_OVERLAP and dislike_penalty > 0
                else OVERRIDE_BIAS_WEAK_FIT
            ),
        ),
    }
