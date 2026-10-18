"""
src/stage1_candidate_generation/people_based.py

GENERATOR 9 of 9: Preferred directors and cast

Finds titles that have one of the user's preferred directors or actors, best
known first (most IMDb votes), with a reason like "directed by Michael Mann"
or "stars Al Pacino".

Two rules keep it from wasting its slots:
1. Titles the persona's hard rules would remove anyway (outside the year
   range, under the IMDb floor, an avoided person, already watched) are
   skipped BEFORE slots are handed out. These are the rules in
   exclusion_filter/exclude.py, reused, not copied. Without this, famous
   films from outside the year range took slots and were removed later.
2. Every preferred person gets their own share of slots
   (PEOPLE_CANDIDATES_PER_PERSON) and the generator takes turns between
   them. Without this, the most voted person (say Christopher Nolan) took
   every slot and the others never appeared.

Needs the IMDb data (data/download_imdb.py). Without it every movie has
empty director and cast lists, so this generator returns nothing and the
rest of the engine runs as before. The single "IMDb data is not downloaded"
warning is printed by the persona loader, not here.
"""

from typing import Any, Dict, List

from config.weights import PEOPLE_CANDIDATES_PER_PERSON
from src.exclusion_filter.exclude import build_removal_check
from src.user_profile.people_match import describe_match, matched_preferred_people

Movie = Dict[str, Any]


def _titles_by_person(
    user: Dict[str, Any], catalog: Dict[int, Movie]
) -> Dict[str, List[Movie]]:
    """
    For each preferred person, the titles they are in that survive the hard
    rules, most voted first. A title with no vote count is unknown, so it goes
    last. People with no usable titles are left out.
    """
    is_removed = build_removal_check(user)
    by_person: Dict[str, List[Movie]] = {}
    for movie in catalog.values():
        if is_removed(movie["movie_id"], movie):
            continue
        for person in matched_preferred_people(user, movie):
            by_person.setdefault(person, []).append(movie)

    for titles in by_person.values():
        titles.sort(key=lambda movie: movie["imdb_votes"] or 0, reverse=True)
    return by_person


def _take_turns(by_person: Dict[str, List[Movie]], user: Dict[str, Any]) -> List[Movie]:
    """
    Round robin: each round, every person who still has room takes their best
    title not chosen yet. A title shared by two people is chosen once and is
    credited to both, so it uses up one slot of each. Stops when everybody is
    full or out of titles, so it always ends.
    """
    preferred = (user.get("preferred_directors") or []) + (user.get("preferred_cast") or [])
    people = [person for person in preferred if person in by_person]
    credited = {person: 0 for person in people}
    next_index = {person: 0 for person in people}
    chosen: List[Movie] = []
    chosen_ids = set()

    progress = True
    while progress:
        progress = False
        for person in people:
            titles = by_person[person]
            has_room = credited[person] < PEOPLE_CANDIDATES_PER_PERSON
            while has_room and next_index[person] < len(titles):
                movie = titles[next_index[person]]
                next_index[person] += 1
                if movie["movie_id"] in chosen_ids:
                    continue  # already chosen for someone else and credited to us there
                chosen.append(movie)
                chosen_ids.add(movie["movie_id"])
                for name in matched_preferred_people(user, movie):
                    if name in credited:
                        credited[name] += 1
                progress = True
                break  # one title per person per round: that is the "taking turns"
    return chosen


def generate(user: Dict[str, Any], catalog: Dict[int, Movie]) -> List[Dict[str, Any]]:
    """Returns the chosen titles in the order they were picked, strongest first."""
    chosen = _take_turns(_titles_by_person(user, catalog), user)
    return [
        {
            "movie_id": movie["movie_id"],
            "source": "people_based",
            "reason": describe_match(user, movie),
        }
        for movie in chosen
    ]
