"""
src/exclusion_filter/exclude.py

This sits between stage 1 and stage 2. It is a cleanup step, not a
generator, it never adds new candidates, it only removes ones that
should never be shown to this user at all.

Kinds of removal happen here, each one only active when it applies:
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
   clear the floor. So are titles with too few ratings, because a high
   average from only a few raters is not trustworthy. There are two floors:
   the MovieLens one (min_avg_rating) and the IMDb one (min_imdb_rating).
   A persona file sets the IMDb one and leaves the MovieLens one empty, so
   the IMDb floor replaces the MovieLens stand in for that persona.
4. Titles outside the release year range (year_from, year_to).
5. Titles with a director or cast member the user never wants to see.

What is deliberately NOT here: disliked genres. A genre dislike is a lean,
an avoided person is a rule. A lean stays a soft penalty in stage 2, so a
title the user would probably love can still get through. A rule is a hard
removal here, because the user said "never".

Rule this file keeps: the filters only ever remove, the kept titles are
the input titles in the same order, and a filter whose preference is not
set never removes anything.
"""

from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from config.weights import MIN_IMDB_VOTES_FOR_FLOOR, MIN_RATINGS_FOR_QUALITY_FLOOR

Movie = Optional[Dict[str, Any]]
# A rule takes a movie id and its catalog record (None if the catalog does not
# have it) and returns True when the title must be removed.
Rule = Callable[[int, Movie], bool]


class FilterOutcome(NamedTuple):
    """kept is the cleaned list, removed_counts maps each ACTIVE rule to its count."""
    kept: List[Dict[str, Any]]
    removed_counts: Dict[str, int]


def _watched_rule(user: Dict[str, Any]) -> Rule:
    """Removes titles the user has already watched."""
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}
    return lambda movie_id, movie: movie_id in watched_ids


def _hard_blocked_rule(user: Dict[str, Any]) -> Rule:
    """Removes titles the user asked never to see again."""
    blocked_ids = set(user.get("hard_blocked_movie_ids", []))
    return lambda movie_id, movie: movie_id in blocked_ids


def _movielens_floor_rule(min_avg_rating: float) -> Rule:
    """Removes titles under the MovieLens average rating floor, or too little rated."""
    def removes(movie_id: int, movie: Movie) -> bool:
        return (
            movie is None
            or movie["avg_rating"] is None
            or movie["rating_count"] < MIN_RATINGS_FOR_QUALITY_FLOOR
            or movie["avg_rating"] < min_avg_rating
        )
    return removes


def _imdb_floor_rule(min_imdb_rating: float) -> Rule:
    """
    Removes titles under the IMDb floor. A title with no IMDb rating, or with
    fewer than MIN_IMDB_VOTES_FOR_FLOOR votes, is removed too: the floor is the
    user's rule, and a title that cannot show it clears the floor does not pass.
    """
    def removes(movie_id: int, movie: Movie) -> bool:
        return (
            movie is None
            or movie["imdb_rating"] is None
            or movie["imdb_votes"] is None
            or movie["imdb_votes"] < MIN_IMDB_VOTES_FOR_FLOOR
            or movie["imdb_rating"] < min_imdb_rating
        )
    return removes


def _year_rule(year_from: Optional[int], year_to: Optional[int]) -> Rule:
    """
    Removes titles released outside the range. Either end may be left open.
    A title with no known year cannot be shown to be in the range, so it goes.
    """
    def removes(movie_id: int, movie: Movie) -> bool:
        if movie is None or movie["year"] is None:
            return True
        too_early = year_from is not None and movie["year"] < year_from
        too_late = year_to is not None and movie["year"] > year_to
        return too_early or too_late
    return removes


def _avoided_people_rule(avoided: List[str], field: str) -> Rule:
    """Removes any title whose directors or cast (field) include an avoided person."""
    avoided_names = set(avoided)
    return lambda movie_id, movie: movie is not None and bool(avoided_names & set(movie[field]))


def _active_rules(user: Dict[str, Any]) -> List[Tuple[str, Rule]]:
    """
    The rules that apply to this user, in a fixed order, each with the name
    shown in the filter report. A rule whose preference is not set is not in
    the list at all, so it cannot remove anything.
    """
    rules = [
        ("already watched", _watched_rule(user)),
        ("never recommend again", _hard_blocked_rule(user)),
    ]
    if user.get("min_avg_rating") is not None:
        rules.append(("MovieLens quality floor", _movielens_floor_rule(user["min_avg_rating"])))
    if user.get("min_imdb_rating") is not None:
        rules.append(("IMDb rating floor", _imdb_floor_rule(user["min_imdb_rating"])))
    if user.get("year_from") is not None or user.get("year_to") is not None:
        rules.append(("year range", _year_rule(user.get("year_from"), user.get("year_to"))))
    if user.get("avoided_directors"):
        rules.append(
            ("avoided directors", _avoided_people_rule(user["avoided_directors"], "directors"))
        )
    if user.get("avoided_cast"):
        rules.append(("avoided cast", _avoided_people_rule(user["avoided_cast"], "cast")))
    return rules


def build_removal_check(user: Dict[str, Any]) -> Callable[[int, Movie], bool]:
    """
    Returns a function that says whether ANY active rule would remove a title
    for this user. Lets a generator skip titles that are doomed anyway, using
    these very rules instead of its own copy of them.
    """
    rules = _active_rules(user)
    return lambda movie_id, movie: any(removes(movie_id, movie) for _, removes in rules)


def apply_hard_filters(
    shortlist: List[Dict[str, Any]], user: Dict[str, Any], catalog: Dict[int, Dict[str, Any]]
) -> FilterOutcome:
    """
    Runs every active rule on every title. Each rule's count is how many titles
    THAT rule would remove on its own, so one title can be counted by two rules.
    That is on purpose: the report then shows which preference is the strictest
    (the one to relax), instead of crediting whichever rule happens to run first.
    """
    rules = _active_rules(user)
    removed_counts = {name: 0 for name, _ in rules}
    kept = []

    for candidate in shortlist:
        movie_id = candidate["movie_id"]
        movie = catalog.get(movie_id)
        broken = [name for name, removes in rules if removes(movie_id, movie)]
        for name in broken:
            removed_counts[name] += 1
        if not broken:
            kept.append(candidate)

    return FilterOutcome(kept, removed_counts)


def exclude(
    shortlist: List[Dict[str, Any]], user: Dict[str, Any], catalog: Dict[int, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """The cleaned shortlist only. Use apply_hard_filters when the counts are needed."""
    return apply_hard_filters(shortlist, user, catalog).kept
