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
(this must be run from the project's root folder, not from inside src)
"""

from concurrent.futures import ThreadPoolExecutor

from src.catalog import load_catalog
from src.user_profile.synthetic_users import build_all_personas
from src.user_profile.taste_score import update_dislike_score
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


def run_stage1(user, catalog, context):
    """
    Runs all eight generators. They are independent of each other and
    each one only reads data, it never writes anything, so they are
    safe to run in parallel threads to save wall clock time.
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

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda job: job(), jobs))

    return merge(results)


def build_dislike_scores(user, catalog):
    """
    Walks this user's watch history once and builds up a dislike score
    per genre using the decay formula, simulating what would normally
    be an incremental background job updating these scores a little bit
    at a time as events happen, instead of recomputing from scratch on
    every single request.
    """
    dislike_scores = {}
    last_updated = {}

    for entry in sorted(user["watch_history"], key=lambda e: e["timestamp"]):
        if entry["completion_pct"] >= 0.5:
            continue  # not a dislike style signal

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

    return dislike_scores


def run_pipeline_for_user(user, catalog, context):
    shortlist = run_stage1(user, catalog, context)
    cleaned_shortlist = exclude(shortlist, user)
    dislike_scores = build_dislike_scores(user, catalog)
    ranked = rank_candidates(user, catalog, cleaned_shortlist, context, dislike_scores)
    return ranked


def print_results(user, ranked):
    print(f"\n=== Recommendations for {user['name']} ({user['user_id']}) ===")
    for item in ranked[:15]:
        badge = f"{item['final_score']}% match" if item["show_badge"] else "no badge, below 72%"
        override_note = " [dislike override used]" if item["dislike_override_used"] else ""
        print(f"- {item['title']} ({item['year']}) | {badge}{override_note}")


def main():
    print("Loading MovieLens catalog ...")
    catalog = load_catalog()
    print(f"Loaded {len(catalog)} titles.")

    users = build_all_personas(catalog)

    # A simple example context, a Friday evening session. You can change
    # this to try the other buckets defined in context_aware.py
    context = {
        "time_of_day": "evening",
        "day_of_week": "Friday",
        "device": "tv",
    }

    for user in users:
        ranked = run_pipeline_for_user(user, catalog, context)
        print_results(user, ranked)


if __name__ == "__main__":
    main()
