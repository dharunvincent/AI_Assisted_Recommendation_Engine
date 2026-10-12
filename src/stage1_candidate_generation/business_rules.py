"""
src/stage1_candidate_generation/business_rules.py

GENERATOR 7 of 8: Business rules based promotion

Some content gets pushed by the platform itself for business reasons,
for example a new show the platform spent a lot of money on, or a title
they have a deal to promote. This has nothing to do with the user's
taste, it comes from a decision made by the content management team.

In this project, PROMOTED_CONTENT below stands in for a real content
management dashboard a business team would use to flag titles for
promotion. Each entry carries a business_weight. A promoted weight must
be between BUSINESS_WEIGHT_NEUTRAL (0.5, where every normal title sits)
and 1.0, because promotion is a nudge above neutral, never a penalty.
This weight is carried all the way through to stage 2 ranking, where it
becomes 15 percent of the final score (see config/weights.py).

The two movie_id values below are just examples using well known real
titles from the MovieLens ml-latest-small dataset (Toy Story and Pulp
Fiction), so the project has something to show immediately. Feel free to
change these to any movie_id from your own downloaded movies.csv file.
"""

from config.weights import BUSINESS_WEIGHT_NEUTRAL

PROMOTED_CONTENT = {
    1: 0.9,     # Toy Story, example promoted title
    296: 0.6,   # Pulp Fiction, example promoted title
}


def validate_promoted_content(promoted_content):
    """
    Fails loudly if a promoted weight is outside the allowed range, so a typo
    in the promotion list cannot quietly demote a title below the neutral
    middle or push its weight past 1.0.
    """
    for movie_id, business_weight in promoted_content.items():
        if not BUSINESS_WEIGHT_NEUTRAL <= business_weight <= 1.0:
            raise ValueError(
                f"Promoted movie {movie_id} has business_weight {business_weight}, "
                f"but it must be between {BUSINESS_WEIGHT_NEUTRAL} and 1.0"
            )


validate_promoted_content(PROMOTED_CONTENT)


def generate(user, catalog, max_candidates=10):
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}

    candidates = []
    for movie_id, business_weight in PROMOTED_CONTENT.items():
        if movie_id in watched_ids or movie_id not in catalog:
            continue
        candidates.append({
            "movie_id": movie_id,
            "source": "business_rules",
            "reason": "promoted by the platform",
            "business_weight": business_weight,
        })

    candidates.sort(key=lambda c: c["business_weight"], reverse=True)
    return candidates[:max_candidates]
