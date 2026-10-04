"""
src/user_profile/synthetic_users.py

Generates a small set of made up user personas with believable watch
history, built on top of the real MovieLens movie catalog. This data is
entirely synthetic, it does not represent any real person, it exists
only so the rest of the system has something realistic to run against.

One persona below is deliberately modeled on the car movies versus
animated movies example that came up while designing this project,
someone who loves car and racing action but does not enjoy animated
films, even when an animated film is technically about cars. This is the
exact scenario the dislike override logic in stage 2 is built to handle.
"""

import random
from datetime import datetime, timedelta


PERSONAS = [
    {
        "user_id": "persona_01",
        "name": "Arjun",
        "age_group": "25 to 34",
        "taste_summary": "loves car and racing action movies, dislikes animated movies even when the subject is cars",
    },
    {
        "user_id": "persona_02",
        "name": "Meera",
        "age_group": "18 to 24",
        "taste_summary": "loves comedy and romance, mostly light background watching",
    },
    {
        "user_id": "persona_03",
        "name": "Thomas",
        "age_group": "45 plus",
        "taste_summary": "prefers drama and documentary, finishes almost everything they start",
    },
]

CAR_RELATED_KEYWORDS = ["fast", "furious", "speed", "cars", "drive", "racing", "italian job"]


def _find_movies_by_keyword(catalog, keyword):
    keyword_lower = keyword.lower()
    return [movie for movie in catalog.values() if keyword_lower in movie["title"].lower()]


def _random_timestamp_within_last_days(days):
    return datetime.now() - timedelta(days=random.randint(1, days), hours=random.randint(0, 23))


def build_persona_user(persona, catalog, random_seed=None):
    """
    Builds a full user record for one persona, with a watch_history list
    built from real titles in the MovieLens catalog that match the
    persona's described taste, plus (for persona_01) one deliberate
    animated movie the persona dislikes, to exercise the dislike
    override logic.
    """
    if random_seed is not None:
        random.seed(random_seed)

    user = {
        "user_id": persona["user_id"],
        "name": persona["name"],
        "age_group": persona["age_group"],
        "watch_history": [],
        "hard_blocked_movie_ids": [],
        "current_session": [],
    }

    if persona["user_id"] == "persona_01":
        # Build the car and racing lover persona described above.
        liked_titles = []
        for keyword in CAR_RELATED_KEYWORDS:
            liked_titles.extend(_find_movies_by_keyword(catalog, keyword))

        for movie in liked_titles[:6]:
            user["watch_history"].append({
                "movie_id": movie["movie_id"],
                "completion_pct": round(random.uniform(0.85, 1.0), 2),
                "timestamp": _random_timestamp_within_last_days(180),
            })

        # Deliberately include an animated movie about cars that this
        # persona dropped early, to create the exact conflict signal the
        # dislike override logic needs to resolve, likes the topic,
        # dislikes the animated style.
        animated_car_candidates = [
            movie for movie in _find_movies_by_keyword(catalog, "cars")
            if "Animation" in movie["genres"]
        ]
        for movie in animated_car_candidates[:1]:
            user["watch_history"].append({
                "movie_id": movie["movie_id"],
                "completion_pct": 0.1,
                "timestamp": _random_timestamp_within_last_days(90),
            })

    else:
        # Simpler random sample based build for the other two personas,
        # good enough to exercise the rest of the pipeline.
        sample_pool = [m for m in catalog.values() if m["avg_rating"] is not None]
        sample_size = min(6, len(sample_pool))
        for movie in random.sample(sample_pool, sample_size):
            user["watch_history"].append({
                "movie_id": movie["movie_id"],
                "completion_pct": round(random.uniform(0.3, 1.0), 2),
                "timestamp": _random_timestamp_within_last_days(180),
            })

    return user


def build_all_personas(catalog, random_seed=42):
    return [build_persona_user(persona, catalog, random_seed) for persona in PERSONAS]
