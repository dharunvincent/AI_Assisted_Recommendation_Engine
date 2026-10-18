"""
tests/test_people.py

Phase 4 tests: the people generator, the taste boost and its cap, and the
shortlist maximum with nine generators. Tiny hand made data.
"""

import unittest
from config.weights import (
    PEOPLE_CANDIDATES_PER_PERSON,
    STAGE1_SHORTLIST_MAX_SIZE,
    TASTE_BIAS_BASE,
    TASTE_BIAS_PEOPLE_CAP,
    TASTE_BIAS_PER_PREFERRED_PERSON,
)
from src.pipeline import run_generators, trim_shortlist
from src.stage1_candidate_generation import people_based
from src.stage1_candidate_generation.merge_shortlist import merge
from src.stage2_jev_ranking import scoring_questions
from src.user_profile.people_match import matched_preferred_people


def movie(movie_id, directors=(), cast=(), votes=1000):
    return {
        "movie_id": movie_id, "title": f"Movie {movie_id}", "year": 1995, "genres": ["Crime"],
        "rating_count": 50, "avg_rating": 4.0, "imdb_rating": 8.0 if votes else None,
        "imdb_votes": votes, "directors": list(directors), "cast": list(cast),
    }


def user(**changes):
    base = {"watch_history": [], "preferred_directors": [], "preferred_cast": []}
    base.update(changes)
    return base


CATALOG = {
    1: movie(1, directors=["Michael Mann"], votes=500),
    2: movie(2, directors=["Michael Mann"], cast=["Al Pacino"], votes=9000),
    3: movie(3, cast=["Al Pacino"], votes=2000),
    4: movie(4, directors=["Someone Else"], votes=99999),
    5: movie(5, directors=["Michael Mann"], votes=None),
}


class PeopleGeneratorTests(unittest.TestCase):
    def test_finds_titles_by_preferred_director_best_known_first(self):
        found = people_based.generate(user(preferred_directors=["Michael Mann"]), CATALOG)
        self.assertEqual([c["movie_id"] for c in found], [2, 1, 5])  # unknown votes go last
        self.assertEqual(found[0]["source"], "people_based")

    def test_reasons_name_the_person(self):
        found = people_based.generate(
            user(preferred_directors=["Michael Mann"], preferred_cast=["Al Pacino"]), CATALOG
        )
        reasons = {c["movie_id"]: c["reason"] for c in found}
        self.assertEqual(reasons[1], "directed by Michael Mann")
        self.assertEqual(reasons[3], "stars Al Pacino")
        self.assertEqual(reasons[2], "directed by Michael Mann and stars Al Pacino")

    def test_watched_titles_are_not_suggested(self):
        persona = user(preferred_directors=["Michael Mann"], watch_history=[{"movie_id": 2}])
        self.assertEqual([c["movie_id"] for c in people_based.generate(persona, CATALOG)], [1, 5])

    def test_gives_nothing_when_imdb_data_is_missing(self):
        no_imdb = {n: movie(n, votes=None) for n in range(1, 4)}  # empty people lists
        persona = user(preferred_directors=["Michael Mann"])
        self.assertEqual(people_based.generate(persona, no_imdb), [])

    def test_gives_nothing_without_preferred_people(self):
        self.assertEqual(people_based.generate(user(), CATALOG), [])


def catalog_of(*movies):
    return {m["movie_id"]: m for m in movies}


def dated(movie_id, year, **kwargs):
    entry = movie(movie_id, **kwargs)
    entry["year"] = year
    return entry


class HardRulesBeforeSlotsTests(unittest.TestCase):
    def test_titles_the_filters_would_remove_do_not_take_slots(self):
        # Five famous Mann films from the 1980s, then two lesser ones in range.
        old = [dated(n, 1985, directors=["Michael Mann"], votes=900000 + n) for n in range(1, 6)]
        new = [dated(10, 1995, directors=["Michael Mann"], votes=100),
               dated(11, 1999, directors=["Michael Mann"], votes=50)]
        persona = user(preferred_directors=["Michael Mann"], year_from=1990, year_to=2018)
        found = people_based.generate(persona, catalog_of(*old, *new))
        self.assertEqual([c["movie_id"] for c in found], [10, 11])

    def test_avoided_people_and_low_ratings_are_skipped_too(self):
        movies = [
            movie(1, directors=["Michael Mann"], cast=["Nic Cage"], votes=5000),
            movie(2, directors=["Michael Mann"], votes=4000),
            dated(3, 1995, directors=["Michael Mann"], votes=3000),
        ]
        movies[2]["imdb_rating"] = 5.0
        persona = user(preferred_directors=["Michael Mann"], avoided_cast=["Nic Cage"],
                       min_imdb_rating=7.0)
        found = people_based.generate(persona, catalog_of(*movies))
        self.assertEqual([c["movie_id"] for c in found], [2])


class TakingTurnsTests(unittest.TestCase):
    def test_every_person_gets_a_share_and_none_goes_over_it(self):
        many = [movie(n, directors=["Christopher Nolan"], votes=1000000 - n) for n in range(1, 11)]
        few = [movie(20, directors=["Michael Mann"], votes=10),
               movie(21, directors=["Michael Mann"], votes=5)]
        persona = user(preferred_directors=["Christopher Nolan", "Michael Mann"])
        found = [c["movie_id"] for c in people_based.generate(persona, catalog_of(*many, *few))]
        nolan = [i for i in found if i < 20]
        self.assertEqual(len(nolan), PEOPLE_CANDIDATES_PER_PERSON)
        self.assertEqual(sorted(i for i in found if i >= 20), [20, 21])
        # They alternate, so Mann's best is second, not last.
        self.assertEqual(found[:3], [1, 20, 2])

    def test_a_title_with_two_preferred_people_is_listed_once_and_credited_to_both(self):
        both = movie(1, cast=["Robert De Niro", "Al Pacino"], votes=9000)
        de_niro = [movie(n, cast=["Robert De Niro"], votes=8000 - n) for n in range(10, 20)]
        pacino = [movie(n, cast=["Al Pacino"], votes=7000 - n) for n in range(30, 40)]
        persona = user(preferred_cast=["Robert De Niro", "Al Pacino"])
        catalog = catalog_of(both, *de_niro, *pacino)
        found = [c["movie_id"] for c in people_based.generate(persona, catalog)]
        self.assertEqual(found.count(1), 1)
        self.assertEqual(len(found), 1 + 2 * (PEOPLE_CANDIDATES_PER_PERSON - 1))
        self.assertEqual(len([i for i in found if 10 <= i < 20]), PEOPLE_CANDIDATES_PER_PERSON - 1)

    def test_a_person_with_no_usable_titles_does_not_stop_the_others(self):
        persona = user(preferred_directors=["Nobody Known", "Michael Mann"])
        found = people_based.generate(persona, catalog_of(movie(1, directors=["Michael Mann"])))
        self.assertEqual([c["movie_id"] for c in found], [1])


class TasteBoostTests(unittest.TestCase):
    def taste_bias(self, people_count):
        questions = scoring_questions.build_questions(
            CATALOG[1], {"sources": []}, {}, 0.0, 0, people_count
        )
        return questions["taste_fit"].bias_hint

    def test_each_preferred_person_adds_the_step(self):
        gain = self.taste_bias(1) - self.taste_bias(0)
        self.assertAlmostEqual(gain, TASTE_BIAS_PER_PREFERRED_PERSON)

    def test_boost_never_goes_past_the_cap(self):
        for people_count in range(2, 10):
            self.assertAlmostEqual(
                self.taste_bias(people_count), TASTE_BIAS_BASE + TASTE_BIAS_PEOPLE_CAP
            )

    def test_no_people_means_no_boost(self):
        self.assertEqual(self.taste_bias(0), TASTE_BIAS_BASE)

    def test_state_only_carries_names_when_there_are_matches(self):
        context = {"time_of_day": "evening", "day_of_week": "Friday"}
        plain = scoring_questions.build_state(
            {"age_group": "x"}, CATALOG[1], {"sources": []}, context, 0.0
        )
        with_names = scoring_questions.build_state(
            {"age_group": "x"}, CATALOG[1], {"sources": []}, context, 0.0, ["Michael Mann"]
        )
        self.assertNotIn("preferred_people_matched", plain)
        self.assertEqual(with_names["preferred_people_matched"], ("Michael Mann",))

    def test_matching_ignores_users_without_the_fields(self):
        self.assertEqual(matched_preferred_people({}, CATALOG[2]), [])


class ShortlistSizeTests(unittest.TestCase):
    def test_shortlist_max_holds_with_nine_generators(self):
        big = {n: movie(n, directors=["Michael Mann"], votes=n) for n in range(1, 400)}
        persona = user(
            preferred_directors=["Michael Mann"], preferred_genres=["Crime"], age_group="not set",
            watch_history=[], current_session=[],
        )
        results = run_generators(persona, big, {"time_of_day": "evening", "day_of_week": "Friday"})
        self.assertEqual(len(results), 9)
        shortlist = trim_shortlist(merge(list(results.values())))
        self.assertLessEqual(len(shortlist), STAGE1_SHORTLIST_MAX_SIZE)


if __name__ == "__main__":
    unittest.main()
