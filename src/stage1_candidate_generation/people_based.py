"""
src/stage1_candidate_generation/people_based.py

GENERATOR 9 of 9: Preferred directors and cast

Finds unwatched titles that have one of the user's preferred directors or
actors, best known first (most IMDb votes), with a reason like "directed by
Michael Mann" or "stars Al Pacino".

Needs the IMDb data (data/download_imdb.py). Without it every movie has
empty director and cast lists, so this generator returns nothing and the
rest of the engine runs as before. The single "IMDb data is not downloaded"
warning is printed by the persona loader, not here.
"""

from typing import Any, Dict, List

from src.user_profile.people_match import describe_match, matched_preferred_people


def generate(
    user: Dict[str, Any], catalog: Dict[int, Dict[str, Any]], max_candidates: int = 15
) -> List[Dict[str, Any]]:
    """Returns up to max_candidates candidates, the most voted titles first."""
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}

    matches = [
        movie for movie in catalog.values()
        if movie["movie_id"] not in watched_ids and matched_preferred_people(user, movie)
    ]
    # A title with no vote count is unknown, so it goes last. Sorting by votes
    # puts a famous film above an obscure one, both with the same director.
    matches.sort(key=lambda movie: movie["imdb_votes"] or 0, reverse=True)

    return [
        {
            "movie_id": movie["movie_id"],
            "source": "people_based",
            "reason": describe_match(user, movie),
        }
        for movie in matches[:max_candidates]
    ]
