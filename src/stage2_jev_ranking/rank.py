"""
src/stage2_jev_ranking/rank.py

This is the composite scoring engine for stage 2. For every candidate
movie in the shortlist it does the following:
1. builds the state and questions (scoring_questions.py)
2. calls the mock JEV client to get taste_fit, completion_likelihood,
   context_fit and the dislike_override answer
3. resolves the dislike override logic
4. combines everything into one final score out of 100 using the
   weights locked in during planning (config/weights.py)
5. works out the match percent shown to the user and decides whether the
   badge is shown, using BADGE_DISPLAY_THRESHOLD_PERCENT on the match percent,
   without changing the ranking order itself (that uses the final score)

Remember, every JEV flavoured number here comes from a mock client. The
final scores and the order of this list are a demonstration of the
architecture, not a measured result from a real trained model.
"""

from src.stage2_jev_ranking import jev_client, scoring_questions
from src.catalog_pools import catalog_mean_rating
from src.stage1_candidate_generation.business_rules import business_weight_for_user
from src.user_profile.people_match import matched_preferred_people
from config.weights import (
    TASTE_FIT_WEIGHT,
    COMPLETION_LIKELIHOOD_WEIGHT,
    CONTEXT_FIT_WEIGHT,
    BUSINESS_WEIGHT_WEIGHT,
    MATCH_TASTE_WEIGHT,
    MATCH_COMPLETION_WEIGHT,
    BADGE_DISPLAY_THRESHOLD_PERCENT,
    BUSINESS_WEIGHT_NEUTRAL,
    LIKED_COMPLETION_THRESHOLD,
    DISLIKE_PENALTY_SCALE,
    DISLIKE_STRENGTH_CAP_FOR_PENALTY,
    OVERRIDE_CONFIDENCE_THRESHOLD,
    OVERRIDE_PENALTY_RETAINED,
)


def _genre_overlap_count(user, catalog, movie):
    liked_genres = set()
    for entry in user["watch_history"]:
        if entry["completion_pct"] >= LIKED_COMPLETION_THRESHOLD:
            liked_movie = catalog.get(entry["movie_id"])
            if liked_movie:
                liked_genres.update(liked_movie["genres"])
    return len(liked_genres.intersection(movie["genres"]))


def match_percent_for(taste_fit_after_penalty, completion_likelihood):
    """
    Pure. How well the title fits the PERSON, 0 to 100. Only taste fit (after
    the dislike penalty) and completion count. Promotion and context fit are
    left out on purpose, see MATCH_TASTE_WEIGHT in config/weights.py.
    """
    return round(
        (taste_fit_after_penalty * MATCH_TASTE_WEIGHT + completion_likelihood * MATCH_COMPLETION_WEIGHT) * 100,
        1,
    )


def rank_candidates(user, catalog, shortlist, context, dislike_scores):
    """
    dislike_scores: dict of genre mapped to dislike_score, already
    computed and decayed using src/user_profile/taste_score.py for this
    user.

    Returns the shortlist, each candidate now carrying a final_score (0
    to 100), a match_percent (0 to 100, shown to the user), a show_badge flag, and the raw JEV style answers for
    transparency, sorted by final_score, highest first.
    """
    ranked = []
    # The catalog wide average that thinly rated titles are pulled toward,
    # worked out once per run (see shrunk_rating in src/catalog_pools.py).
    prior_rating = catalog_mean_rating(catalog)

    for candidate in shortlist:
        movie = catalog[candidate["movie_id"]]

        # The strongest matching dislike signal across this movie's own
        # genres is what the override question has to try to beat.
        relevant_dislike_scores = [dislike_scores.get(genre, 0.0) for genre in movie["genres"]]
        dislike_penalty = max(relevant_dislike_scores) if relevant_dislike_scores else 0.0

        genre_overlap_count = _genre_overlap_count(user, catalog, movie)

        preferred_people = matched_preferred_people(user, movie)

        state = scoring_questions.build_state(
            user, movie, candidate, context, dislike_penalty, preferred_people
        )
        questions = scoring_questions.build_questions(
            movie, candidate, context, dislike_penalty, genre_overlap_count, len(preferred_people),
            prior_rating,
        )
        jev_answers = jev_client.ask(state, questions)

        # The taste fit question is asked "ignoring any general dislike", so
        # this is a before penalty score. The dislike penalty is applied
        # below, and ONLY there. Nowhere else in stage 2 subtracts it, so it
        # can never be counted twice.
        taste_fit_score = jev_answers["taste_fit"]["answer"]
        taste_fit_before_penalty = taste_fit_score

        # Dislike override logic, if JEV's override question comes back
        # as override_show_anyway with reasonable confidence, we soften
        # the penalty instead of fully applying it. This is the "heavily
        # weighted soft penalty that JEV can occasionally overrule"
        # behaviour chosen during planning.
        override_answer = jev_answers["dislike_override"]["answer"]
        override_confidence = jev_answers["dislike_override"]["confidence"]
        override_used = False

        if dislike_penalty > 0:
            # Cap first, so the override then softens a penalty that already
            # cannot be bigger than one thumbs down.
            penalty_strength = min(dislike_penalty, DISLIKE_STRENGTH_CAP_FOR_PENALTY)
            if override_answer == "override_show_anyway" and override_confidence >= OVERRIDE_CONFIDENCE_THRESHOLD:
                effective_penalty = penalty_strength * OVERRIDE_PENALTY_RETAINED  # mostly overruled
                override_used = True
            else:
                effective_penalty = penalty_strength  # penalty stands
            taste_fit_score = max(0.0, taste_fit_score - (effective_penalty * DISLIKE_PENALTY_SCALE))

        completion_score = jev_answers["completion_likelihood"]["answer"]
        context_score = jev_answers["context_fit"]["answer"]
        # A title nobody promoted has no business weight and adds nothing.
        # Promotion is a small nudge, worth at most 7.5 extra points.
        # Promotion is switched off for a genre the user declared they dislike.
        business_score = business_weight_for_user(
            candidate.get("business_weight", BUSINESS_WEIGHT_NEUTRAL), user, movie
        )

        final_score = (
            taste_fit_score * TASTE_FIT_WEIGHT
            + completion_score * COMPLETION_LIKELIHOOD_WEIGHT
            + context_score * CONTEXT_FIT_WEIGHT
            + business_score * BUSINESS_WEIGHT_WEIGHT
        ) * 100

        final_score = round(final_score, 1)

        match_percent = match_percent_for(taste_fit_score, completion_score)

        ranked.append({
            "movie_id": movie["movie_id"],
            "title": movie["title"],
            "year": movie["year"],
            "genres": movie["genres"],
            "avg_rating": movie["avg_rating"],
            "sources": candidate["sources"],
            "reasons": candidate["reasons"],
            "final_score": final_score,
            "match_percent": match_percent,
            "show_badge": match_percent >= BADGE_DISPLAY_THRESHOLD_PERCENT,
            "dislike_override_used": override_used,
            "jev_answers": jev_answers,
            # Read only numbers for src/evaluate.py --diagnose. Nothing in
            # the ranking reads them.
            "diagnostics": {
                "genre_overlap_count": genre_overlap_count,
                "dislike_penalty": dislike_penalty,
                "taste_fit_before_penalty": taste_fit_before_penalty,
                "taste_fit_after_penalty": taste_fit_score,
                "taste_bias_before_cap": scoring_questions.taste_bias(
                    genre_overlap_count, len(preferred_people), candidate.get("collab_strength", 0.0)
                ),
            },
        })

    ranked.sort(key=lambda item: item["final_score"], reverse=True)
    return ranked
