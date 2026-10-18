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

from typing import Any, Dict, Iterable, List, Optional

from config.weights import MIN_RATINGS_TO_TRUST, RATING_SHRINKAGE_STRENGTH

# Used when there are no ratings at all to take an average from: the middle
# of the 0 to 5 star scale.
NEUTRAL_RATING = 3.0

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


def catalog_mean_rating(catalog: Dict[int, Movie]) -> float:
    """
    The average star rating across ALL ratings in the catalog (a title with
    more ratings counts for more). This is what a title with few raters is
    pulled toward. NEUTRAL_RATING if nobody has rated anything.
    """
    rated = [m for m in catalog.values() if m["avg_rating"] is not None and m.get("rating_count", 0) > 0]
    total_ratings = sum(m["rating_count"] for m in rated)
    if total_ratings == 0:
        return NEUTRAL_RATING
    return sum(m["rating_count"] * m["avg_rating"] for m in rated) / total_ratings


def shrunk_rating(avg_rating: Optional[float], rating_count: int, prior_rating: float) -> float:
    """
    Pure. The average rating, pulled toward prior_rating (the catalog wide
    average) by RATING_SHRINKAGE_STRENGTH imaginary raters.

    Rules (tested): with no raters the result is the prior, with a huge crowd
    it is the title's own average, and it always lies between the two, closer
    to the title's own average the more people rated it. A missing average is
    treated as no evidence at all.
    """
    if avg_rating is None or rating_count <= 0:
        return prior_rating
    return (
        (rating_count * avg_rating + RATING_SHRINKAGE_STRENGTH * prior_rating)
        / (rating_count + RATING_SHRINKAGE_STRENGTH)
    )
