"""
src/evaluate.py

An offline evaluation: does this engine actually recommend titles that real
people went on to like? The rest of the project only shows that the pipeline
runs. This file measures something.

Run with:  python3 -m src.evaluate
(from the project's root folder, same as src.pipeline. It lives in src/
so it can import the pipeline the same way, and so one command style works
for everything.)

How the test works:
1. Pick 100 real MovieLens users (with a fixed seed, so every run picks the
   same ones).
2. For each user, sort their ratings by time. Their LAST 5 ratings of 4
   stars or more are hidden as the "answers". Everything that happened
   before the first hidden rating becomes their watch history.
3. Run the real pipeline on that history and check whether the hidden
   titles show up in the recommendations.

Honest limits, please read:
- MovieLens has no "completion" data, so a rating is turned into a
  completion with a simple stand in (see completion_for_rating). That is a
  proxy, not a measurement.
- Stage 2 uses the MOCK scorer, not a real JEV model. The stage 2 numbers
  measure the mock's simple rules (genre overlap, average rating and so
  on), not real JEV.
- The collaborative table is built WITHOUT the hidden ratings, so it never
  sees its own answers. But catalog averages and rating counts (used by
  trending, the quality floor and the mock scorer) still include the hidden
  ratings. That is a small known leak. It helps the popularity baseline too.
- The dataset is small (about 600 users), so the numbers are noisy.
"""

import csv
import os
import random
from collections import defaultdict
from datetime import datetime

from src.catalog import load_catalog, DATA_FOLDER
from src.pipeline import run_pipeline_stages
from src.stage1_candidate_generation.collaborative import get_similarity_table

# These describe the evaluation, they are not product settings.
EVAL_USER_COUNT = 100         # how many real users are tested
EVAL_SEED = 42                # fixed, so every run picks the same users
MIN_RATINGS_PER_USER = 20     # a user needs at least this many ratings to be tested
HELD_OUT_COUNT = 5            # how many hidden answers each user gets
HELD_OUT_MIN_RATING = 4.0     # only ratings at or above this can be hidden answers
TOP_K = 10                    # the "top 10" used for Hit Rate and Recall

# The stand in that turns a rating into a completion. A high rating means
# the user stayed to the end, a low rating means they would have left early,
# and a middle rating is neutral: neither a like nor a dislike (see
# config/weights.py for how the pipeline reads these).
MIDDLE_RATING_MIN = 3.0
COMPLETION_FOR_HIGH_RATING = 0.95    # rated 4 or more
COMPLETION_FOR_MIDDLE_RATING = 0.6   # rated 3 or 3.5, neutral
COMPLETION_FOR_LOW_RATING = 0.1      # rated 2.5 or less, a dislike signal

# The same example context the demo pipeline uses. MovieLens has no real
# time of day for the recommendation moment, so every user gets this one.
EVAL_CONTEXT = {"time_of_day": "evening", "day_of_week": "Friday"}


# Generators that only work from preferences a persona file states. These
# evaluation users are built from rating history alone, so such a generator
# could only ever show 0.0 percent here. It is left out of the report so the
# evaluation output stays exactly as it was before the persona file work.
PERSONA_ONLY_GENERATORS = {"people_based"}


def read_ratings_by_user():
    """Returns {user_id: [(timestamp, movie_id, rating), ...]} sorted by time."""
    ratings_by_user = defaultdict(list)
    with open(os.path.join(DATA_FOLDER, "ratings.csv"), encoding="utf-8") as file:
        for row in csv.DictReader(file):
            ratings_by_user[int(row["userId"])].append(
                (int(row["timestamp"]), int(row["movieId"]), float(row["rating"]))
            )
    for ratings in ratings_by_user.values():
        ratings.sort()  # by timestamp, then movie id, so ties are always ordered the same way
    return ratings_by_user


def split_ratings(time_sorted_ratings):
    """
    Hides the user's last HELD_OUT_COUNT ratings of HELD_OUT_MIN_RATING or
    more. Returns (history, held_out), or None if the user cannot be split.

    History is everything BEFORE the earliest hidden rating, so no hidden
    title can ever appear in the history, and nothing from the "future" of
    the first answer is used as history.
    """
    high_positions = [
        position for position, (_, _, rating) in enumerate(time_sorted_ratings)
        if rating >= HELD_OUT_MIN_RATING
    ]
    if len(high_positions) < HELD_OUT_COUNT:
        return None

    held_out_positions = high_positions[-HELD_OUT_COUNT:]
    history = time_sorted_ratings[:held_out_positions[0]]
    if not history:
        return None

    held_out = [time_sorted_ratings[position] for position in held_out_positions]
    return history, held_out


def completion_for_rating(rating):
    """The stand in described near the top of this file."""
    if rating >= HELD_OUT_MIN_RATING:
        return COMPLETION_FOR_HIGH_RATING
    if rating >= MIDDLE_RATING_MIN:
        return COMPLETION_FOR_MIDDLE_RATING
    return COMPLETION_FOR_LOW_RATING


def build_eval_user(user_id, history):
    """
    Turns a real user's history into the same user dict the pipeline uses.
    MovieLens has no age group, no declared genres, no blocked titles and no
    live session, so those get neutral defaults. An age group of "not set"
    simply switches the demographic generator off.
    """
    return {
        "user_id": f"movielens_{user_id}",
        "name": f"MovieLens user {user_id}",
        "preferred_genres": [],
        "disliked_genres": [],
        "min_avg_rating": None,
        "age_group": "not set",
        "taste_summary": "a real MovieLens user",
        "watch_history": [
            {
                "movie_id": movie_id,
                "completion_pct": completion_for_rating(rating),
                "timestamp": datetime.fromtimestamp(timestamp),
            }
            for timestamp, movie_id, rating in history
        ],
        "hard_blocked_movie_ids": [],
        "current_session": [],
    }


def pick_test_users(ratings_by_user):
    """Picks EVAL_USER_COUNT users that can be split, the same ones every run."""
    splittable = {}
    for user_id in sorted(ratings_by_user):
        ratings = ratings_by_user[user_id]
        if len(ratings) < MIN_RATINGS_PER_USER:
            continue
        split = split_ratings(ratings)
        if split:
            splittable[user_id] = split

    chosen_ids = random.Random(EVAL_SEED).sample(sorted(splittable), EVAL_USER_COUNT)
    return [(user_id, *splittable[user_id]) for user_id in chosen_ids]


def most_popular_titles(catalog, history_ids, how_many):
    """The plain baseline: the most rated titles this user has not seen."""
    by_popularity = sorted(catalog.values(), key=lambda movie: movie["rating_count"], reverse=True)
    return [movie["movie_id"] for movie in by_popularity if movie["movie_id"] not in history_ids][:how_many]


def share(part, whole):
    return part / whole if whole else 0.0


def evaluate():
    catalog = load_catalog()
    test_users = pick_test_users(read_ratings_by_user())

    # Keep every hidden rating out of the collaborative table.
    hidden_pairs = {
        (user_id, movie_id)
        for user_id, _, held_out in test_users
        for _, movie_id, _ in held_out
    }
    similarity_table = get_similarity_table(hidden_pairs)

    total_answers = 0
    shortlist_hits = 0
    generator_hits = defaultdict(int)
    stage2_hits = stage2_users_with_a_hit = 0
    popular_hits = popular_users_with_a_hit = 0

    for user_id, history, held_out in test_users:
        answers = {movie_id for _, movie_id, _ in held_out}
        total_answers += len(answers)

        user = build_eval_user(user_id, history)
        last_history_time = user["watch_history"][-1]["timestamp"]  # this user's "now"
        stages = run_pipeline_stages(user, catalog, EVAL_CONTEXT, last_history_time, similarity_table)

        shortlist_hits += len(answers & {c["movie_id"] for c in stages["shortlist"]})
        for name, candidates in stages["generator_results"].items():
            if name in PERSONA_ONLY_GENERATORS:
                continue
            generator_hits[name] += len(answers & {c["movie_id"] for c in candidates})

        top_ranked = {item["movie_id"] for item in stages["ranked"][:TOP_K]}
        stage2_hits += len(answers & top_ranked)
        stage2_users_with_a_hit += bool(answers & top_ranked)

        popular = set(most_popular_titles(catalog, {m for _, m, _ in history}, TOP_K))
        popular_hits += len(answers & popular)
        popular_users_with_a_hit += bool(answers & popular)

    user_count = len(test_users)
    return {
        "users": user_count,
        "answers": total_answers,
        "stage1_recall": share(shortlist_hits, total_answers),
        "generator_recall": {name: share(hits, total_answers) for name, hits in generator_hits.items()},
        "stage2_hit_rate": share(stage2_users_with_a_hit, user_count),
        "stage2_recall": share(stage2_hits, total_answers),
        "popular_hit_rate": share(popular_users_with_a_hit, user_count),
        "popular_recall": share(popular_hits, total_answers),
    }


def print_report(results):
    print(f"\nOffline evaluation on {results['users']} real MovieLens users, "
          f"{results['answers']} hidden answers ({HELD_OUT_COUNT} per user)\n")
    print(f"Stage 1 recall (hidden titles that reached the shortlist): {results['stage1_recall']:.1%}")
    print("Recall of each generator on its own (before the exclusion filter and trim):")
    for name, recall in sorted(results["generator_recall"].items(), key=lambda item: -item[1]):
        print(f"  {name:15} {recall:.1%}")
    print(f"\n{'Top ' + str(TOP_K):31}Hit Rate    Recall")
    print(f"  {'This engine (after stage 2)':29}{results['stage2_hit_rate']:7.1%}   {results['stage2_recall']:7.1%}")
    print(f"  {'Most popular titles':29}{results['popular_hit_rate']:7.1%}   {results['popular_recall']:7.1%}")
    print("\nNOTE: stage 2 uses the MOCK scorer. The stage 2 numbers measure the mock's simple")
    print("rules, not a real JEV model. Catalog averages and rating counts still include the")
    print("hidden ratings, a small known leak that also helps the popularity baseline.")


if __name__ == "__main__":
    print_report(evaluate())
