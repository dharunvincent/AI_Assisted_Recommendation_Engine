"""
src/stage1_candidate_generation/content_based.py

GENERATOR 1 of 8: Content based filtering

Looks at the genres of movies the user has watched and liked, and finds
other movies in the catalog that share those genres. This is the most
basic form of "if you liked this, you might like that".

This generator only looks at this one user's own history, it does not
look at what other users did. That makes it useful once a user has some
watch history, but it struggles for a brand new user with no history yet
(the classic cold start problem), which is exactly why collaborative
filtering and the other generators exist alongside it.

Which genres to use:
- If the user declared preferred genres (for example from an onboarding
  quiz), those are used, and the slots are shared evenly between them.
- Otherwise the three genres that show up most often in the titles the
  user finished are used, and titles matching the most of them come first.

Why the slots are shared evenly: if all preferred genres compete in one
list, titles that carry several of those genres crowd out genres that
rarely come with a second tag, such as Documentary. So each preferred
genre gets its own list, best known titles first, and the slots are
filled by taking one title from each list in turn.
"""

from collections import Counter

from config.weights import MIN_RATINGS_FOR_CONTENT_BASED


def generate(user, catalog, max_candidates=15):
    watched_ids = {entry["movie_id"] for entry in user["watch_history"]}

    preferred_genres = user.get("preferred_genres") or []
    if preferred_genres:
        return _pick_spread_across_genres(preferred_genres, watched_ids, catalog, max_candidates)

    return _pick_by_inferred_genres(user, watched_ids, catalog, max_candidates)


def _pick_spread_across_genres(preferred_genres, watched_ids, catalog, max_candidates):
    """
    Builds one list per preferred genre, then takes one title from each
    list in turn until the slots are full or every list runs out.
    """
    genre_lists = [
        _best_known_titles_in_genre(genre, watched_ids, catalog)
        for genre in preferred_genres
    ]

    picked_ids = set()
    candidates = []
    next_index = [0] * len(genre_lists)

    # Keep going round the genres until the slots are full, or a full
    # round adds nothing because every list has run out.
    while len(candidates) < max_candidates:
        added_this_round = False

        for position, titles in enumerate(genre_lists):
            if len(candidates) >= max_candidates:
                break

            # Skip titles an earlier genre already picked, since a title
            # can belong to more than one preferred genre.
            while next_index[position] < len(titles) and titles[next_index[position]]["movie_id"] in picked_ids:
                next_index[position] += 1

            if next_index[position] < len(titles):
                movie = titles[next_index[position]]
                next_index[position] += 1
                picked_ids.add(movie["movie_id"])
                overlap = set(preferred_genres).intersection(movie["genres"])
                candidates.append(_candidate(movie, overlap))
                added_this_round = True

        if not added_this_round:
            break

    return candidates


def _best_known_titles_in_genre(genre, watched_ids, catalog):
    """
    Unwatched titles in this genre with enough ratings to trust, most
    rated first, with the higher average rating winning ties.
    """
    titles = [
        movie for movie in catalog.values()
        if genre in movie["genres"]
        and movie["movie_id"] not in watched_ids
        and movie["rating_count"] >= MIN_RATINGS_FOR_CONTENT_BASED
    ]
    titles.sort(key=lambda movie: (movie["rating_count"], movie["avg_rating"]), reverse=True)
    return titles


def _pick_by_inferred_genres(user, watched_ids, catalog, max_candidates):
    """
    For users with no declared preferred genres. Count how often each
    genre shows up across the movies this user finished with a decent
    completion percentage. More appearances means that genre matters
    more to this user.
    """
    genre_counter = Counter()
    for entry in user["watch_history"]:
        if entry["completion_pct"] >= 0.5:
            movie = catalog.get(entry["movie_id"])
            if movie:
                genre_counter.update(movie["genres"])

    if not genre_counter:
        return []  # nothing to go on yet, cold start, another generator has to cover this user

    favourite_genres = {genre for genre, _ in genre_counter.most_common(3)}

    candidates = []
    for movie in catalog.values():
        if movie["movie_id"] in watched_ids:
            continue
        overlap = favourite_genres.intersection(movie["genres"])
        if overlap:
            candidates.append(_candidate(movie, overlap))

    # Prefer candidates with more genre overlap, and cap the list size.
    candidates.sort(key=lambda c: c["reason"].count(","), reverse=True)
    return candidates[:max_candidates]


def _candidate(movie, overlapping_genres):
    return {
        "movie_id": movie["movie_id"],
        "source": "content_based",
        "reason": "similar genre to titles you watched, " + ", ".join(sorted(overlapping_genres)),
    }
