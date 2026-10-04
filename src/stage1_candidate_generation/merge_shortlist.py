"""
src/stage1_candidate_generation/merge_shortlist.py

Takes the output of all eight stage 1 generators and merges them into
one single shortlist. The same movie can get suggested by more than one
generator, for example a movie might show up from both content_based and
trending. When that happens we keep it once, but we remember every
source that suggested it, because stage 2 can use that information later.

The final shortlist size is capped using config/weights.py so stage 2,
which is slower and costs more per call, never has to score more titles
than it needs to.
"""

from config.weights import STAGE1_SHORTLIST_MAX_SIZE


def merge(generator_results):
    """
    generator_results: a list of lists, one list per generator, each
    containing candidate dicts with at least a "movie_id" and "source" key.
    """
    merged = {}

    for candidate_list in generator_results:
        for candidate in candidate_list:
            movie_id = candidate["movie_id"]
            if movie_id not in merged:
                merged[movie_id] = {
                    "movie_id": movie_id,
                    "sources": [candidate["source"]],
                    "reasons": [candidate["reason"]],
                    "business_weight": candidate.get("business_weight", 0.0),
                }
            else:
                merged[movie_id]["sources"].append(candidate["source"])
                merged[movie_id]["reasons"].append(candidate["reason"])
                if candidate.get("business_weight", 0.0) > merged[movie_id]["business_weight"]:
                    merged[movie_id]["business_weight"] = candidate["business_weight"]

    # A movie suggested by more than one generator independently is
    # usually a stronger candidate, so we rank by how many generators
    # agreed on it before trimming down to the max shortlist size.
    shortlist = sorted(merged.values(), key=lambda c: len(c["sources"]), reverse=True)

    return shortlist[:STAGE1_SHORTLIST_MAX_SIZE]
