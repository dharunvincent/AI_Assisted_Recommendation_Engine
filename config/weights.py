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
# BADGE DISPLAY THRESHOLD
# This does NOT affect ranking order. It only decides whether the
# percentage match badge is shown on the content tile in the user
# interface. Below this number, the content can still be recommended
# and shown, it just will not carry a score badge on it.
# -----------------------------------------------------------------------
BADGE_DISPLAY_THRESHOLD_PERCENT = 72

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
# removing duplicates from the output of all eight generators.
# -----------------------------------------------------------------------
STAGE1_SHORTLIST_MIN_SIZE = 30
STAGE1_SHORTLIST_MAX_SIZE = 50
