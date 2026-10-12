"""
src/pipeline.py

The single entry point that runs the whole recommendation engine end to
end, for one user, for one request. Run this file directly to see the
system work on the synthetic personas.

Order of operations:
1. Load the real MovieLens catalog
2. Build synthetic persona users on top of it
3. Run all eight stage 1 candidate generators
4. Merge their output into one shortlist
5. Run the exclusion filter cleanup step
6. Run stage 2 JEV ranking (mocked) to score and sort the shortlist
7. Print the final recommended list, with scores and badges

Run with:  python -m src.pipeline
Or for one persona only:  python -m src.pipeline --persona dharun
(this must be run from the project's root folder, not from inside src)
"""

import argparse
from datetime import datetime

from src.catalog import load_catalog
from src.user_profile.synthetic_users import build_all_personas
from src.user_profile.taste_score import update_dislike_score, decay_to
from src.exclusion_filter.exclude import exclude
from src.stage2_jev_ranking.rank import rank_candidates

from src.stage1_candidate_generation import (
    content_based,
    collaborative,
    demographic,
    trending,
    context_aware,
    session_based,
    business_rules,
    diversity,
)
from src.stage1_candidate_generation.merge_shortlist import merge
from config.weights import (
    STAGE1_SHORTLIST_MIN_SIZE,
    STAGE1_SHORTLIST_MAX_SIZE,
    DISLIKE_SIGNAL_MAX_COMPLETION,
)


def run_stage1(user, catalog, context):
    """
    Runs all eight generators one after another and merges their output.

    In a real platform each generator would be its own service, called in
    parallel over the network, and parallel calls really do save time there
    because each service does its own work. Inside this one Python process
    the generators are pure CPU work, so threads would give no speed up
    (Python lets only one thread run Python code at a time). A plain loop is
    simpler and gives exactly the same answers.
    """
    jobs = [
        lambda: content_based.generate(user, catalog),
        lambda: collaborative.generate(user, catalog),
        lambda: demographic.generate(user, catalog),
        lambda: trending.generate(user, catalog),
        lambda: context_aware.generate(user, catalog, context),
        lambda: session_based.generate(user, catalog),
        lambda: business_rules.generate(user, catalog),
        lambda: diversity.generate(user, catalog, random_seed=7),
    ]

    results = [job() for job in jobs]

    return merge(results)


def trim_shortlist(shortlist):
    """
    Cuts the cleaned up list to the maximum size stage 2 should score. This
    runs AFTER the exclusion filter on purpose. If it ran before, titles the
    filter later removes would have taken up places that other titles should
    have had.
    """
    return shortlist[:STAGE1_SHORTLIST_MAX_SIZE]


def warn_if_shortlist_too_small(user, shortlist):
    """
    If the generators together could not reach the minimum shortlist size
    even after cleanup, that is worth knowing about. It usually means this
    user has too little history or too small a catalog for stage one to do
    its job properly, not something stage two can fix.
    """
    if len(shortlist) < STAGE1_SHORTLIST_MIN_SIZE:
        print(
            f"  note: stage 1 only produced {len(shortlist)} candidates for "
            f"{user['name']}, below the target minimum of {STAGE1_SHORTLIST_MIN_SIZE}."
        )


def build_dislike_scores(user, catalog, as_of=None):
    """
    Walks this user's watch history once and builds up a dislike score
    per genre using the decay formula, simulating what would normally
    be an incremental background job updating these scores a little bit
    at a time as events happen, instead of recomputing from scratch on
    every single request.

    as_of is the moment the scores are read, today by default. Tests pass
    a fixed date so they never depend on the clock. Every score is decayed
    up to as_of at the end, so an old dislike fades even when no newer
    event touched that genre.
    """
    as_of = as_of or datetime.now()
    dislike_scores = {}
    last_updated = {}

    for entry in sorted(user["watch_history"], key=lambda e: e["timestamp"]):
        # Only an early exit is a dislike signal. Stopping midway can have
        # many reasons (fell asleep, got busy), so a neutral or liked watch
        # creates no dislike score at all, see config/weights.py.
        if entry["completion_pct"] >= DISLIKE_SIGNAL_MAX_COMPLETION:
            continue

        movie = catalog.get(entry["movie_id"])
        if not movie:
            continue

        for genre in movie["genres"]:
            old_score = dislike_scores.get(genre, 0.0)
            old_timestamp = last_updated.get(genre, entry["timestamp"])

            new_score, new_timestamp = update_dislike_score(
                old_score=old_score,
                old_score_timestamp=old_timestamp,
                event_type="drop_off",
                event_timestamp=entry["timestamp"],
                completion_pct=entry["completion_pct"],
            )

            dislike_scores[genre] = new_score
            last_updated[genre] = new_timestamp

    # Genres the user has openly said they dislike, like a thumbs down on
    # a whole genre. Same decay formula, just the strongest signal type.
    # The thumbs down counts as happening at as_of, so it has full strength.
    for genre in user.get("disliked_genres", []):
        new_score, new_timestamp = update_dislike_score(
            old_score=dislike_scores.get(genre, 0.0),
            old_score_timestamp=last_updated.get(genre, as_of),
            event_type="explicit_thumbs_down",
            event_timestamp=as_of,
        )
        dislike_scores[genre] = new_score
        last_updated[genre] = new_timestamp

    # Fade every score from its last update up to as_of. Without this, a
    # score only decays when the next event for that genre arrives.
    return {
        genre: decay_to(score, last_updated[genre], as_of)
        for genre, score in dislike_scores.items()
    }


def run_pipeline_for_user(user, catalog, context):
    merged = run_stage1(user, catalog, context)
    cleaned = exclude(merged, user, catalog)
    cleaned_shortlist = trim_shortlist(cleaned)
    warn_if_shortlist_too_small(user, cleaned_shortlist)
    dislike_scores = build_dislike_scores(user, catalog)
    ranked = rank_candidates(user, catalog, cleaned_shortlist, context, dislike_scores)
    return ranked


def print_results(user, ranked):
    print(f"\n=== Recommendations for {user['name']} ({user['user_id']}) ===")
    print(f"Persona taste: {user['taste_summary']}")

    for item in ranked[:15]:
        badge = f"{item['final_score']}% match" if item["show_badge"] else "no badge, below 72%"
        override_note = " [dislike override used]" if item["dislike_override_used"] else ""
        top_reason = item["reasons"][0]
        # Only show the average rating for users who set a quality floor,
        # so they can see for themselves that nothing below it got through.
        rating_note = f" | avg rating {item['avg_rating']} of 5" if user.get("min_avg_rating") else ""
        print(f"- {item['title']} ({item['year']}) | {badge}{override_note}{rating_note} | {top_reason}")

    disliked = set(user.get("disliked_genres", []))
    if disliked:
        flagged = [item["title"] for item in ranked[:15] if disliked.intersection(item["genres"])]
        flagged_note = f", {', '.join(flagged)}" if flagged else ""
        print(f"  dislike check: {len(flagged)} of the top 15 carry a disliked genre{flagged_note}")

    # Show the full score breakdown for the single top pick, this is the
    # number that explains itself when you are showing this project to
    # someone, why did this one title come out on top.
    if ranked:
        top_pick = ranked[0]
        answers = top_pick["jev_answers"]
        print(
            f"  why '{top_pick['title']}' is on top: "
            f"taste fit {answers['taste_fit']['answer']}, "
            f"completion likelihood {answers['completion_likelihood']['answer']}, "
            f"context fit {answers['context_fit']['answer']}"
        )


def main():
    parser = argparse.ArgumentParser(description="Run the recommendation engine on the synthetic personas.")
    parser.add_argument("--persona", help="run only this persona, by first name, for example dharun")
    args = parser.parse_args()

    print("Loading MovieLens catalog ...")
    catalog = load_catalog()
    print(f"Loaded {len(catalog)} titles.")

    users = build_all_personas(catalog)

    if args.persona:
        users = [user for user in users if user["name"].lower() == args.persona.lower()]
        if not users:
            print(f"No persona named '{args.persona}'. Try one of: Arjun, Meera, Thomas, Dharun.")
            return

    # A simple example context, a Friday evening session. You can change
    # this to try the other buckets defined in context_aware.py
    context = {
        "time_of_day": "evening",
        "day_of_week": "Friday",
    }

    for user in users:
        ranked = run_pipeline_for_user(user, catalog, context)
        print_results(user, ranked)


if __name__ == "__main__":
    main()
