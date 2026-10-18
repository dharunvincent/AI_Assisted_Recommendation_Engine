"""
config/weights.py

This file holds every tunable number used by the ranking system in one place.
Keeping the weights here instead of hiding them inside the ranking code means
anyone reviewing this project can see, in one file, exactly how the final
score is built, and can change it without touching the logic itself.

IMPORTANT, read this before trusting any number below:
These weights are starting judgment calls made during the design of this
project, not numbers measured from real user data or a real experiment.
A real streaming platform would tune these using actual watch data over
time. Here they exist so the scoring logic has something concrete to run
on, and so the architecture can be demonstrated end to end.
"""

# -----------------------------------------------------------------------
# STAGE 2 FINAL SCORE WEIGHTS
# These four numbers must add up to 1.0 (100 percent).
# The final score shown to a user is a weighted sum of these four parts.
# -----------------------------------------------------------------------
TASTE_FIT_WEIGHT = 0.45               # how well the content matches the user's personal taste, including the dislike override logic
COMPLETION_LIKELIHOOD_WEIGHT = 0.25   # how likely the user is to finish watching it, not just start it
CONTEXT_FIT_WEIGHT = 0.15             # how well it fits the current context, time of day, day of week, device
BUSINESS_WEIGHT_WEIGHT = 0.15         # how much the platform's own business priority should nudge the score

assert abs(
    TASTE_FIT_WEIGHT + COMPLETION_LIKELIHOOD_WEIGHT + CONTEXT_FIT_WEIGHT + BUSINESS_WEIGHT_WEIGHT - 1.0
) < 1e-6, "The four stage 2 weights must add up to 1.0"

# -----------------------------------------------------------------------
# MATCH PERCENT SHOWN TO THE USER (separate from the ranking score)
# The final score above decides the ORDER. It also contains promotion and
# context fit, which say nothing about how well a title suits the person: a
# normal title always loses the 15 promotion points and context fit sits near
# 0.45, so the score never gets much above 74 and a promoted title could look
# like a better match than it is. The match percent shown to the user is built
# only from how well the title fits the person, taste fit after the dislike
# penalty and completion likelihood. Taste gets the larger share because it is
# the direct question "is this for me", completion is the supporting evidence.
# These two must add up to 1.0.
# -----------------------------------------------------------------------
MATCH_TASTE_WEIGHT = 0.65
MATCH_COMPLETION_WEIGHT = 0.35

assert abs(
    MATCH_TASTE_WEIGHT + MATCH_COMPLETION_WEIGHT - 1.0
) < 1e-6, "The two match percent weights must add up to 1.0"

# -----------------------------------------------------------------------
# BADGE DISPLAY THRESHOLD
# This does NOT affect ranking order. It only decides whether the
# percentage match badge is shown on the content tile in the user
# interface. Below this number, the content can still be recommended
# and shown, it just will not carry a score badge on it.
# -----------------------------------------------------------------------
BADGE_DISPLAY_THRESHOLD_PERCENT = 85

# -----------------------------------------------------------------------
# DISLIKE SIGNAL BASE WEIGHTS
# These feed the taste score decay formula in src/user_profile/taste_score.py
# A higher number means a stronger negative signal for that behaviour.
# -----------------------------------------------------------------------
SIGNAL_WEIGHT_EXPLICIT_THUMBS_DOWN = 1.0
SIGNAL_WEIGHT_DROP_OFF_EARLY = 0.7      # user quit in the first 15 percent of runtime
SIGNAL_WEIGHT_DROP_OFF_LATE = 0.0       # user quit after 70 percent of runtime, basically finished, this is not treated as a dislike
SIGNAL_WEIGHT_WATCHLIST_NEGLECT = 0.2   # user added to watchlist but never opened it after a long time
SIGNAL_WEIGHT_HOVER_AND_SKIP = 0.1      # user hovered over the tile and then skipped it

# Early drop off cut off and late drop off cut off, both expressed as a
# fraction of total runtime watched.
EARLY_DROP_OFF_CUTOFF = 0.15
LATE_DROP_OFF_CUTOFF = 0.70

# -----------------------------------------------------------------------
# SIGNAL DECAY
# Every stored taste signal loses strength over time using a half life
# formula, so a dislike from a long time ago matters a lot less than a
# dislike from last week.
# -----------------------------------------------------------------------
SIGNAL_HALF_LIFE_DAYS = 60

# -----------------------------------------------------------------------
# STAGE 1 SHORTLIST SIZE
# How many candidates stage 1 hands over to stage 2 after merging and
# removing duplicates from the output of all nine generators.
# -----------------------------------------------------------------------
STAGE1_SHORTLIST_MIN_SIZE = 30
STAGE1_SHORTLIST_MAX_SIZE = 50

# -----------------------------------------------------------------------
# QUALITY FLOOR MINIMUM RATINGS
# A title only passes a user's quality floor if at least this many people
# rated it. A high average from only a few raters is not trustworthy, for
# example one title with two perfect ratings would otherwise beat a title
# with thousands of ratings averaging slightly lower.
# -----------------------------------------------------------------------
MIN_RATINGS_FOR_QUALITY_FLOOR = 20

# -----------------------------------------------------------------------
# CONTENT BASED MINIMUM RATINGS
# When the content based generator picks titles for a user's preferred
# genres, it only considers titles rated by at least this many people.
# Without it, obscure titles with a handful of ratings could take slots
# that better known titles in the same genre should have.
# -----------------------------------------------------------------------
MIN_RATINGS_FOR_CONTENT_BASED = 20

# -----------------------------------------------------------------------
# WHAT COUNTS AS LIKED, NEUTRAL AND DISLIKED
# One place defines how a watch is read, so no file has its own private
# idea of "liked". Completion is the share of the title the user watched.
#   0.7 or more        liked, the user stayed with it
#   0.2 up to 0.7      neutral, neither a like nor a dislike
#   below 0.2          a dislike signal, the user left early
# "Not liked" is NOT the same as "disliked". Leaving early is a clear
# dislike. Stopping somewhere in the middle can have many reasons (fell
# asleep, got busy, got interrupted), so we do not punish it. A neutral
# watch creates no dislike score at all.
# Inside the dislike band, taste_score.py still decides the strength: below
# EARLY_DROP_OFF_CUTOFF is the strong early drop off signal, and the rest
# of the band is the weaker partial signal.
# -----------------------------------------------------------------------
LIKED_COMPLETION_THRESHOLD = 0.7
DISLIKE_SIGNAL_MAX_COMPLETION = 0.2

# A drop off between the early cutoff and DISLIKE_SIGNAL_MAX_COMPLETION is
# counted as this share of the strong early drop off weight.
SIGNAL_WEIGHT_DROP_OFF_MIDDLE_FACTOR = 0.5

# A dislike score never grows past this, so repeated signals cannot make it
# grow without limit.
DISLIKE_SCORE_CAP = 3.0

# -----------------------------------------------------------------------
# STAGE 2 DISLIKE PENALTY AND OVERRIDE
# -----------------------------------------------------------------------
# How strongly the dislike score pulls a title's taste fit down. The penalty
# is now applied in one place only (rank.py). It used to be subtracted twice,
# about 0.25 inside the taste expectation and 0.3 in rank.py, roughly 0.55 in
# total. This single value keeps the total animation penalty about as strong
# as before.
DISLIKE_PENALTY_SCALE = 0.55
# The dislike SCORE can grow to DISLIKE_SCORE_CAP (3.0) after repeated early
# exits. Multiplied by the scale that is 1.65, more than all of taste fit, so
# every title in that genre was pushed to a taste fit of 0 and the whole genre
# vanished. The penalty therefore only reads the score up to this strength,
# which is one explicit thumbs down (SIGNAL_WEIGHT_EXPLICIT_THUMBS_DOWN). The
# biggest possible penalty is then 1.0 x 0.55 = 0.55 of taste fit, never all of
# it. The stored score and its decay are not touched, only how much of it the
# penalty is allowed to use.
DISLIKE_STRENGTH_CAP_FOR_PENALTY = 1.0
# If the override question answers "show anyway" with at least this much
# confidence, the penalty is mostly lifted for that one title.
OVERRIDE_CONFIDENCE_THRESHOLD = 0.65
# The share of the penalty that stays when the override fires.
OVERRIDE_PENALTY_RETAINED = 0.25

# -----------------------------------------------------------------------
# STAGE 2 EXPECTATIONS HANDED TO THE MOCK JEV
# These are the rough "bias hints" worked out from simple facts, see
# src/stage2_jev_ranking/scoring_questions.py.
# -----------------------------------------------------------------------
# Expected taste fit starts here and rises with every genre the title shares
# with things the user liked.
TASTE_BIAS_BASE = 0.5
TASTE_BIAS_PER_GENRE_OVERLAP = 0.12
# Expected context fit: higher when the title already came from the
# context aware generator in stage 1.
CONTEXT_BIAS_FROM_CONTEXT_GENERATOR = 0.75
CONTEXT_BIAS_DEFAULT = 0.45
# Expected answer to the override question: strong when the title shares at
# least OVERRIDE_MIN_GENRE_OVERLAP liked genres and a penalty is active,
# weak otherwise.
OVERRIDE_BIAS_STRONG_FIT = 0.7
OVERRIDE_BIAS_WEAK_FIT = 0.1
OVERRIDE_MIN_GENRE_OVERLAP = 2

# -----------------------------------------------------------------------
# STAGE 1 GENERATOR CUT OFFS
# -----------------------------------------------------------------------
# Collaborative filtering only learns from ratings at or above this.
COLLAB_HIGH_RATING_THRESHOLD = 4.0
# Diversity injection only offers titles rated at least this well.
DIVERSITY_MIN_AVG_RATING = 3.8
# Diversity injection also needs this many ratings behind the average. Same
# reason as MIN_RATINGS_FOR_QUALITY_FLOOR: an average of 4.5 from two raters
# is luck, not quality, and a random pick would otherwise surface such titles.
DIVERSITY_MIN_RATINGS = 20

# -----------------------------------------------------------------------
# BUSINESS WEIGHT: PROMOTION IS A SMALL NUDGE
# A normal, non promoted title has a business weight of 0.0, so it adds
# nothing to its score. A promoted title gets a weight above that, up to
# BUSINESS_WEIGHT_MAX_PROMOTION. The weight counts for 15 percent of the final
# score, so the biggest possible promotion is worth 0.5 times 0.15 times 100,
# which is 7.5 extra points. That is a small nudge, not a head start.
# -----------------------------------------------------------------------
BUSINESS_WEIGHT_NEUTRAL = 0.0
BUSINESS_WEIGHT_MAX_PROMOTION = 0.5

# -----------------------------------------------------------------------
# COLLABORATIVE FILTERING MINIMUM SHARED USERS
# Two movies are only treated as linked if at least this many users rated
# both highly. Very small counts are noise: two users agreeing by chance
# says nothing about what a third user would enjoy.
# -----------------------------------------------------------------------
COLLAB_MIN_CO_OCCURRENCE = 3

# -----------------------------------------------------------------------
# PERSONA FILE: WATCH HISTORY FROM FAVOURITE TITLES
# A brand new user has no history, which is the "cold start" problem:
# collaborative filtering needs real liked titles to find similar movies.
# Favourite titles from the persona file are the quickest fix, so each one
# becomes a finished watch (95 percent completed, comfortably above the
# liked threshold) with a recent date, spaced out a little so they do not
# all share one timestamp. Without favourites, the genre based history
# builder in synthetic_users.py is used instead with the completion range
# and seed below (the same values the existing Dharun persona uses).
# -----------------------------------------------------------------------
FAVOURITE_COMPLETION_PCT = 0.95
FAVOURITE_FIRST_WATCH_DAYS_AGO = 7
FAVOURITE_WATCH_SPACING_DAYS = 3
PERSONA_FILE_GENRE_HISTORY_COMPLETION_RANGE = (0.8, 1.0)
PERSONA_FILE_HISTORY_SEED = 42

# -----------------------------------------------------------------------
# PERSONA FILE: "DID YOU MEAN" SUGGESTIONS
# How close a typed name must be to a real one (0 to 1, difflib's ratio) to
# be offered as a suggestion, and how many to offer. 0.6 is difflib's own
# default, loose enough that "Chris Nolan" finds "Christopher Nolan".
# -----------------------------------------------------------------------
SUGGESTION_MATCH_CUTOFF = 0.6
MAX_SUGGESTIONS = 3

# -----------------------------------------------------------------------
# IMDB RATING FLOOR MINIMUM VOTES
# When a persona sets min_imdb_rating, a title only passes if at least this
# many people voted for it on IMDb. A high rating from a handful of voters
# cannot be trusted, same idea as MIN_RATINGS_FOR_QUALITY_FLOOR above for the
# MovieLens floor. A title with no IMDb rating at all is removed too.
# -----------------------------------------------------------------------
MIN_IMDB_VOTES_FOR_FLOOR = 1000

# -----------------------------------------------------------------------
# PREFERRED DIRECTORS AND CAST: TASTE BIAS
# The rule: a preferred person the user named counts the same as one shared
# liked genre (TASTE_BIAS_PER_GENRE_OVERLAP above, 0.12). Naming "Michael Mann"
# is at least as strong a statement of taste as liking "Crime", so the step is
# the same. The cap is two such steps (0.24), the same as a title that shares
# two liked genres: it stops a title with three favourite actors from beating
# everything on cast alone, genre match and the other questions still matter.
# -----------------------------------------------------------------------
TASTE_BIAS_PER_PREFERRED_PERSON = 0.12
TASTE_BIAS_PEOPLE_CAP = 0.24

# -----------------------------------------------------------------------
# PERSONA FILE RESULTS
# How short the final list can get before the filter report names the
# strictest filter (so the user knows which preference to relax). The printed
# list and the saved CSV both have the full ranked list, unless the user asks
# for fewer with --top or --badged-only.
# -----------------------------------------------------------------------
SHORT_LIST_WARNING_BELOW = 15

# -----------------------------------------------------------------------
# PEOPLE GENERATOR: SLOTS PER PREFERRED PERSON
# Each preferred director or actor gets up to this many candidate titles,
# and the generator takes turns between them. With one shared cap, the most
# voted person took every slot (three Nolan blockbusters pushed out all of
# Michael Mann's films). A title that matches two preferred people is listed
# once and counts towards both of them.
# -----------------------------------------------------------------------
PEOPLE_CANDIDATES_PER_PERSON = 5
