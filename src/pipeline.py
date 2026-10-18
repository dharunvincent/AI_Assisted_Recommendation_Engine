"""
src/pipeline.py

The single entry point that runs the whole recommendation engine end to
end, for one user, for one request. Run this file directly to see the
system work on the synthetic personas.

Order of operations:
1. Load the real MovieLens catalog
2. Build synthetic persona users on top of it
3. Run all nine stage 1 candidate generators
4. Merge their output into one shortlist
5. Run the exclusion filter cleanup step
6. Run stage 2 JEV ranking (mocked) to score and sort the shortlist
7. Print the final recommended list, with scores and badges

Run with:  python -m src.pipeline
Or for one persona only:  python -m src.pipeline --persona dharun
Or for your own taste file:  python -m src.pipeline --persona-file personas/example.json
Or answer questions about your taste:  python -m src.pipeline --interactive
Both of those also take --badged-only (only movies with the badge) and --top N.
(this must be run from the project's root folder, not from inside src)
"""

import argparse
import sys
from datetime import date, datetime

from src.catalog import load_catalog
from src.interactive import interview, save_persona_file
from src.results_report import (
    DisplayOptions,
    build_result_rows,
    format_filter_report,
    format_result_table,
    select_rows,
    write_results_csv,
)
from src.run_warnings import count_missing_movie_data, format_warning_section
from src.user_profile.persona_loader import PersonaResult, build_persona_result, load_persona_file
from src.user_profile.synthetic_users import build_all_personas
from src.user_profile.taste_score import update_dislike_score, decay_to
from src.exclusion_filter.exclude import apply_hard_filters
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
    people_based,
)
from src.stage1_candidate_generation.merge_shortlist import merge
from config.weights import (
    STAGE1_SHORTLIST_MIN_SIZE,
    STAGE1_SHORTLIST_MAX_SIZE,
    DISLIKE_SIGNAL_MAX_COMPLETION,
    BADGE_DISPLAY_THRESHOLD_PERCENT,
    PRINTED_TOP_COUNT,
)


def run_generators(user, catalog, context, similarity_table=None):
    """
    Runs all nine generators one after another. Returns a dict of generator
    name mapped to that generator's own candidate list, in running order.
    similarity_table lets the evaluation hand collaborative filtering a table
    that was built without the held out ratings, see src/evaluate.py.

    In a real platform each generator would be its own service, called in
    parallel over the network, and parallel calls really do save time there
    because each service does its own work. Inside this one Python process
    the generators are pure CPU work, so threads would give no speed up
    (Python lets only one thread run Python code at a time). A plain loop is
    simpler and gives exactly the same answers.
    """
    jobs = {
        "content_based": lambda: content_based.generate(user, catalog),
        "collaborative": lambda: collaborative.generate(user, catalog, similarity_table=similarity_table),
        "demographic": lambda: demographic.generate(user, catalog),
        "trending": lambda: trending.generate(user, catalog),
        "context_aware": lambda: context_aware.generate(user, catalog, context),
        "session_based": lambda: session_based.generate(user, catalog),
        "business_rules": lambda: business_rules.generate(user, catalog),
        "diversity": lambda: diversity.generate(user, catalog, random_seed=7),
        # Last on purpose: it returns nothing for users without preferred people,
        # so it never changes the result for the four built in personas.
        "people_based": lambda: people_based.generate(user, catalog),
    }

    return {name: job() for name, job in jobs.items()}


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


def run_pipeline_stages(user, catalog, context, as_of=None, similarity_table=None):
    """
    The whole pipeline, in order: generators, merge, exclusion filter, trim,
    then stage 2 ranking. Returns every stage's output so the evaluation can
    look inside, and so there is only one copy of this order in the project.

    as_of is the moment dislike scores are read (today by default).
    similarity_table is an optional collaborative table, see run_generators.
    """
    generator_results = run_generators(user, catalog, context, similarity_table)
    merged = merge(list(generator_results.values()))
    outcome = apply_hard_filters(merged, user, catalog)
    shortlist = trim_shortlist(outcome.kept)
    dislike_scores = build_dislike_scores(user, catalog, as_of)
    ranked = rank_candidates(user, catalog, shortlist, context, dislike_scores)
    return {
        "generator_results": generator_results,
        "shortlist": shortlist,
        "ranked": ranked,
        # What each hard filter removed, for the filter report of a persona file run.
        "filter_counts": outcome.removed_counts,
        "candidate_count": len(merged),
    }


def run_pipeline_for_user(user, catalog, context):
    stages = run_pipeline_stages(user, catalog, context)
    warn_if_shortlist_too_small(user, stages["shortlist"])
    return stages["ranked"]


def print_results(user, ranked):
    print(f"\n=== Recommendations for {user['name']} ({user['user_id']}) ===")
    print(f"Persona taste: {user['taste_summary']}")

    for item in ranked[:PRINTED_TOP_COUNT]:
        badge = f"{item['match_percent']}% match" if item["show_badge"] else (
            f"no badge, {item['match_percent']}% match, below {BADGE_DISPLAY_THRESHOLD_PERCENT}%"
        )
        override_note = " [dislike override used]" if item["dislike_override_used"] else ""
        top_reason = item["reasons"][0]
        # Only show the average rating for users who set a quality floor,
        # so they can see for themselves that nothing below it got through.
        rating_note = f" | avg rating {item['avg_rating']} of 5" if user.get("min_avg_rating") else ""
        print(f"- {item['title']} ({item['year']}) | {badge}{override_note}{rating_note} | {top_reason}")

    disliked = set(user.get("disliked_genres", []))
    if disliked:
        flagged = [item["title"] for item in ranked[:PRINTED_TOP_COUNT] if disliked.intersection(item["genres"])]
        flagged_note = f", {', '.join(flagged)}" if flagged else ""
        print(f"  dislike check: {len(flagged)} of the top {PRINTED_TOP_COUNT} carry a disliked genre{flagged_note}")

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


def missing_data_kinds(user):
    """
    Which kinds of missing movie data matter to this persona, so the warnings
    only mention data the persona actually uses.
    """
    kinds = []
    if user.get("min_imdb_rating") is not None:
        kinds.append("rating")
    if user.get("preferred_directors") or user.get("avoided_directors"):
        kinds.append("directors")
    if user.get("preferred_cast") or user.get("avoided_cast"):
        kinds.append("cast")
    return kinds


def print_warning_section(user, catalog, warnings):
    """Prints the grouped Warnings section once, nothing at all if it is empty."""
    missing_counts = count_missing_movie_data(catalog, missing_data_kinds(user))
    lines = format_warning_section(warnings, missing_counts)
    if lines:
        print("\n" + "\n".join(lines))


def run_persona_result(result, label, catalog, context, options):
    """
    Runs the pipeline for an already loaded persona. Returns the exit code:
    1 when the persona has an error that makes the results meaningless
    (printed clearly), otherwise 0. Warnings never stop the run, they print
    once at the end. `label` names the source in the error message, like "persona file 'x.json'".
    """
    if result.user is None:
        print(f"\nCannot run with {label}:")
        for error in result.errors:
            print(f"- {error}")
        return 1

    user = result.user
    stages = run_pipeline_stages(user, catalog, context)
    warn_if_shortlist_too_small(user, stages["shortlist"])
    rows = build_result_rows(stages["ranked"], catalog)
    shown = select_rows(rows, options)

    print(f"\n=== Recommendations for {user['name']} ===")
    print(f"Taste: {user['taste_summary']}")
    print(f"Showing {len(shown)} of {len(rows)} ranked titles (badge: match {BADGE_DISPLAY_THRESHOLD_PERCENT} percent or above)")
    print("\n".join(format_result_table(shown)))

    warnings = list(result.warnings)
    try:
        path = write_results_csv(rows, user["name"], date.today())
        print(f"\nFull ranked list ({len(rows)} titles) saved to {path}")
    except OSError as error:
        # The list is already on screen, so a failed save is a warning, not a stop.
        warnings.append(f"Could not save the results file: {error}")

    print("\n" + "\n".join(format_filter_report(
        stages["filter_counts"], stages["candidate_count"], len(rows)
    )))
    print_warning_section(user, catalog, warnings)
    return 0


def run_persona_file(path, catalog, context, options=DisplayOptions()):
    """Loads the persona file at path and runs it, see run_persona_result."""
    return run_persona_result(load_persona_file(path, catalog), f"persona file '{path}'", catalog, context, options)


def run_interactive(catalog, context, options=DisplayOptions(), ask=input, say=print):
    """
    Asks the questions, saves the answers to personas/<name>.json, then runs
    the engine on them. Answering n at the end (or ending the input) runs
    nothing and saves nothing. A failed save is a warning: the answers are
    still in memory, so the run goes ahead from them.
    """
    data = interview(ask, say, catalog)
    if data is None:
        say("Nothing saved, nothing run.")
        return 0

    path, save_problem = save_persona_file(data)
    result = build_persona_result(data, catalog, datetime.now())
    if save_problem:
        result = PersonaResult(result.user, result.errors, [save_problem] + result.warnings)
    else:
        say(f"Saved your answers to {path}")
    return run_persona_result(result, "your answers", catalog, context, options)


def positive_whole_number(text):
    """argparse type for --top: a whole number of 1 or more."""
    try:
        number = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a whole number")
    if number < 1:
        raise argparse.ArgumentTypeError(f"--top must be 1 or more, not {number}")
    return number


def main():
    parser = argparse.ArgumentParser(description="Run the recommendation engine on the synthetic personas.")
    parser.add_argument("--persona", help="run only this persona, by first name, for example dharun")
    parser.add_argument(
        "--persona-file", help="run on your own taste file, for example personas/example.json"
    )
    parser.add_argument(
        "--interactive", action="store_true",
        help="answer questions about your taste, they are saved to personas/<name>.json",
    )
    parser.add_argument(
        "--badged-only", action="store_true",
        help="with --persona-file or --interactive: show only movies with the badge",
    )
    parser.add_argument(
        "--top", type=positive_whole_number,
        help="with --persona-file or --interactive: show only the first N movies",
    )
    args = parser.parse_args()

    live = args.interactive or args.persona_file
    if (args.badged_only or args.top) and not live:
        parser.error("--badged-only and --top need --persona-file or --interactive")
    if args.interactive and (args.persona_file or args.persona):
        parser.error("--interactive cannot be combined with --persona-file or --persona")
    options = DisplayOptions(badged_only=args.badged_only, top=args.top)

    print("Loading MovieLens catalog ...")
    try:
        catalog = load_catalog()
    except FileNotFoundError as error:
        # Without MovieLens there is nothing to recommend, so stop clearly.
        print(error)
        return 1
    print(f"Loaded {len(catalog)} titles.")

    # A simple example context, a Friday evening session. You can change
    # this to try the other buckets defined in context_aware.py
    context = {
        "time_of_day": "evening",
        "day_of_week": "Friday",
    }

    if args.interactive:
        return run_interactive(catalog, context, options)
    if args.persona_file:
        return run_persona_file(args.persona_file, catalog, context, options)

    users = build_all_personas(catalog)

    if args.persona:
        users = [user for user in users if user["name"].lower() == args.persona.lower()]
        if not users:
            print(f"No persona named '{args.persona}'. Try one of: Arjun, Meera, Thomas, Dharun.")
            return 0

    for user in users:
        ranked = run_pipeline_for_user(user, catalog, context)
        print_results(user, ranked)
    return 0


if __name__ == "__main__":
    sys.exit(main())
