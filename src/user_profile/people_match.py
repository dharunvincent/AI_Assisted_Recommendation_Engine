"""
src/user_profile/people_match.py

One small shared rule: which of the user's preferred directors and actors
are in a given movie. Both the people generator (stage 1) and the taste
bias (stage 2) use it, so the matching lives in exactly one place.
"""

from typing import Any, Dict, List


def _matches(
    user: Dict[str, Any], movie: Dict[str, Any], preferred_key: str, movie_key: str
) -> List[str]:
    """Preferred names found in one of the movie's people lists, each name once."""
    wanted = set(user.get(preferred_key) or [])
    found: List[str] = []
    for name in movie.get(movie_key) or []:
        if name in wanted and name not in found:
            found.append(name)
    return found


def matched_preferred_people(user: Dict[str, Any], movie: Dict[str, Any]) -> List[str]:
    """
    Pure. Names from the user's preferred_directors and preferred_cast that
    appear in this movie's directors and cast, directors first, each name once.
    A user without these preferences, or a movie without IMDb data (empty
    lists), simply matches nobody, it never fails.
    """
    directors = _matches(user, movie, "preferred_directors", "directors")
    actors = _matches(user, movie, "preferred_cast", "cast")
    return directors + [name for name in actors if name not in directors]


def describe_match(user: Dict[str, Any], movie: Dict[str, Any]) -> str:
    """
    The reason text, like "directed by Michael Mann" or "stars Al Pacino",
    or both joined with "and". Empty when nobody matches.
    """
    directors = _matches(user, movie, "preferred_directors", "directors")
    actors = _matches(user, movie, "preferred_cast", "cast")
    parts = []
    if directors:
        parts.append("directed by " + ", ".join(directors))
    if actors:
        parts.append("stars " + ", ".join(actors))
    return " and ".join(parts)
