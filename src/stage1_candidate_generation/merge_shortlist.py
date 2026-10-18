"""
src/stage1_candidate_generation/merge_shortlist.py

Takes the output of all nine stage 1 generators and merges them into
one single list. The same movie can get suggested by more than one
generator, for example a movie might show up from both content_based and
trending. When that happens we keep it once, but we remember every
source that suggested it, because stage 2 can use that information later.

This file only merges and sorts, it does NOT trim the list. Trimming to
the maximum shortlist size happens in pipeline.py, AFTER the exclusion
filter, so that titles the filter removes never take up a place.
"""

from config.weights import BUSINESS_WEIGHT_NEUTRAL


def merge(generator_results):
    """
    generator_results: a list of lists, one list per generator, each
    containing candidate dicts with at least a "movie_id" and "source" key,
    in that generator's own order, strongest pick first.

    Returns every merged title, strongest candidates first.
    """
    merged = {}
    best_position = {}  # movie_id mapped to its best rank in any generator's list

    for candidate_list in generator_results:
        for position, candidate in enumerate(candidate_list):
            movie_id = candidate["movie_id"]
            best_position[movie_id] = min(position, best_position.get(movie_id, position))

            if movie_id not in merged:
                merged[movie_id] = {
                    "movie_id": movie_id,
                    "sources": [candidate["source"]],
                    "reasons": [candidate["reason"]],
                    "business_weight": candidate.get("business_weight", BUSINESS_WEIGHT_NEUTRAL),
                    # Only collaborative candidates carry a strength, 0 for the rest.
                    "collab_strength": candidate.get("collab_strength", 0.0),
                }
            else:
                merged[movie_id]["sources"].append(candidate["source"])
                merged[movie_id]["reasons"].append(candidate["reason"])
                # A title not promoted by this generator has no promotion weight,
                # so a promotion from any generator can only raise it.
                candidate_weight = candidate.get("business_weight", BUSINESS_WEIGHT_NEUTRAL)
                if candidate_weight > merged[movie_id]["business_weight"]:
                    merged[movie_id]["business_weight"] = candidate_weight
                # Keep the strongest collaborative strength seen for the title.
                merged[movie_id]["collab_strength"] = max(
                    merged[movie_id]["collab_strength"], candidate.get("collab_strength", 0.0)
                )

    # A movie suggested by more than one generator independently is
    # usually a stronger candidate, so those come first. Ties are then
    # settled by best position: a title that was some generator's top pick
    # (position 0) beats one that only barely made another generator's
    # list. Without this, ties went to whichever generator happened to run
    # first, and the last generators (business rules, diversity) always lost.
    return sorted(
        merged.values(),
        key=lambda candidate: (-len(candidate["sources"]), best_position[candidate["movie_id"]]),
    )
