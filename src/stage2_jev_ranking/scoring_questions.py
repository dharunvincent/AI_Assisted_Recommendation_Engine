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
from config.weights import GENRE_FIT_MAX_BONUS


def build_state(user, movie, candidate, context, dislike_penalty):
    """
    Builds the "state", the facts JEV is allowed to see for this one
    user and this one candidate movie. Keeping this small and specific
    mirrors the real JEV context limit, which rewards short, focused
    state over dumping a user's entire history into every call.
    """
    return {
        "movie_title": movie["title"],
        "movie_genres": tuple(sorted(movie["genres"])),
        "movie_avg_rating": movie["avg_rating"],
        "user_age_group": user["age_group"],
        "candidate_sources": tuple(sorted(candidate["sources"])),
        "dislike_penalty": round(dislike_penalty, 3),
        "context_time_of_day": context.get("time_of_day"),
        "context_day_of_week": context.get("day_of_week"),
    }


def build_questions(movie, candidate, dislike_penalty, genre_overlap_count):
    """
    Returns the dict of questions to send to jev_client.ask(), each
    carrying a bias_hint worked out from simple real facts. See
    jev_client.py for why the mock needs this hint.

    genre_overlap_count is how many of the movie's genres the user likes.
    It feeds the taste bias as a share of the movie's own genres, and it
    also feeds the dislike override question as a raw count.
    """
    # Rough expectation for taste fit. The genre bonus is based on the
    # share of this movie's own genres that the user likes, not on the
    # raw count, so a movie with many genre tags gets no advantage just
    # for having more tags. An active dislike penalty pulls the
    # expectation back down. This is where the dislike override logic
    # from the brainstorm lives, see rank.py for how the override is
    # resolved.
    liked_genre_share = genre_overlap_count / len(movie["genres"]) if movie["genres"] else 0.0
    taste_bias = 0.5 + (liked_genre_share * GENRE_FIT_MAX_BONUS) - (dislike_penalty * 0.25)

    # Rough expectation for completion likelihood, a well regarded movie
    # in the real MovieLens data is a reasonable proxy for "most people
    # who start this finish it".
    rating = movie["avg_rating"] if movie["avg_rating"] is not None else 3.0
    completion_bias = rating / 5.0

    # Rough expectation for context fit, if this candidate already came
    # from the context_aware generator in stage 1, it already fits the
    # current moment reasonably well.
    context_bias = 0.75 if "context_aware" in candidate["sources"] else 0.45

    return {
        "taste_fit": Score(
            "How well does this match this user's personal taste?",
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
            bias_hint=0.7 if genre_overlap_count >= 2 and dislike_penalty > 0 else 0.1,
        ),
    }
