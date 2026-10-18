"""
src/catalog_pools.py

The ONE place that answers "which catalog titles have enough ratings to be
trusted, best known first". Every stage 1 generator that picks titles from the
catalog starts from this list and adds only its own extra rule (a genre, an
age group, a minimum average) on top, instead of keeping a private copy of the
rating count rule. Before this, demographic filtering had no such rule and put
a film with a single 5.0 rating at the top of a persona's list.

Rule this file keeps: every title returned has at least MIN_RATINGS_TO_TRUST
ratings and an average rating, so nothing here can be a one-rater fluke.
Pure: same catalog in, same list out, nothing is read or written.
"""

from typing import Any, Dict, Iterable, List

from config.weights import MIN_RATINGS_TO_TRUST

Movie = Dict[str, Any]


def is_trusted(movie: Movie) -> bool:
    """True when enough people rated the title for its average to mean something."""
    return movie["avg_rating"] is not None and movie["rating_count"] >= MIN_RATINGS_TO_TRUST


def trusted_titles(catalog: Dict[int, Movie], excluded_ids: Iterable[int] = ()) -> List[Movie]:
    """
    Titles with enough ratings, minus excluded_ids (usually what the user has
    already watched), best known first: most ratings, the higher average
    winning ties. Callers that want another order re-sort this list, and a
    stable sort keeps this order for their ties.
    """
    excluded = set(excluded_ids)
    titles = [
        movie for movie in catalog.values()
        if movie["movie_id"] not in excluded and is_trusted(movie)
    ]
    titles.sort(key=lambda movie: (movie["rating_count"], movie["avg_rating"]), reverse=True)
    return titles
