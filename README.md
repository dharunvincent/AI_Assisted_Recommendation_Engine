# Streaming Platform Content Recommendation Engine

![Python 3](https://img.shields.io/badge/python-3-blue.svg)
![Stage 2 scoring: mock](https://img.shields.io/badge/JEV%20scoring-mock-orange.svg)

A two stage recommendation engine, built the same way a real streaming
platform would approach the problem. Stage one narrows a huge catalog
down to a short list of good candidates using traditional methods. Stage
two takes that short list and scores and ranks it using TypeSafe's JEV
model, a fast and cheap model built for exactly this kind of narrow
scoring question.

This document explains the whole thing from start to finish, the
problem, every piece of the solution, and the honest limitations of
this project.

## Why this project exists

Most recommendation systems you read about online either use heavy
machine learning models for everything, or use simple rule based logic
with no real scoring intelligence. This project explores a middle path,
use cheap and simple traditional methods to do the heavy lifting of
finding candidates, and use a narrow, fast, non hallucinating model only
for the one job it is actually good at, judging and ranking a short list
of options. That is exactly what TypeSafe's JEV model is designed for.

## Important honesty note, please read this first

This project does not use a real TypeSafe API key, because I do not have
one yet. The JEV scoring layer in this project (`src/stage2_jev_ranking/jev_client.py`)
is a mock. It is clearly labeled as a mock inside the code. It mirrors
the real TypeSafe SDK's request shape as closely as possible, so that
swapping in a real API key later should not require changing the rest
of the system. But the scores it produces are simulated, not measured.

The user data in this project is also synthetic. Real movie titles come
from the MovieLens dataset, a real, free, widely used dataset from
GroupLens at the University of Minnesota. The watch history, likes and
dislikes belong to made up personas, built in code on top of those real
titles.

In short, this project proves that the architecture works end to end.
It does not claim any measured accuracy improvement, because there is
no real model and no real users behind it yet. Any percentage numbers
you see when you run this are produced by the mock, not by a trained
model.

## The problem this engine is solving

A streaming platform has a huge catalog, thousands or more titles. For
any one user, on any one day, the system has to pick a short list of
titles that user is actually likely to want to watch, out of everything
available. Doing this well usually needs several different techniques
working together, because no single method covers every situation well,
for example a brand new user with no history at all needs a different
approach than someone who has watched hundreds of titles.

## Big picture architecture

The engine runs in two stages.

**Stage one, candidate generation.** Eight independent methods each look
at the user and the catalog from a different angle, and each one
produces a small list of candidate titles. All eight run at the same
time. Their output gets merged into one shortlist of around 30 to 50
titles. A cleanup step called the exclusion filter then removes anything
the user has already watched or has explicitly blocked.

**Stage two, JEV ranking.** The shortlist from stage one, now cleaned up,
goes to JEV. JEV does not search the whole catalog, it is not built for
that. Its job is to look at one title at a time, answer a few small,
specific questions about it for this user, and give back a score. The
engine asks JEV multiple small questions per title instead of one big
vague question, then combines the answers itself using fixed weights,
into one final score out of 100 for each title.

## Stage one, the eight candidate generators

Each generator lives in its own file inside `src/stage1_candidate_generation/`

1. **Content based filtering** (`content_based.py`) Looks at the genres
   of titles the user has already watched and liked, and finds other
   titles sharing those genres. Works well once a user has some history,
   struggles for a brand new user.

2. **Collaborative filtering** (`collaborative.py`) Uses the real
   MovieLens ratings from hundreds of real anonymous people to find
   patterns like, people who rated movie A highly also tended to rate
   movie B highly. This is the exact Harry Potter style example that
   came up while designing this project, watch and like the first one,
   get the second one recommended because other real viewers followed
   that same pattern.

3. **Demographic filtering** (`demographic.py`) Recommends titles that
   tend to suit the user's age group, useful mainly for new users with
   little or no history yet.

4. **Popularity and trending** (`trending.py`) In a real platform this
   would pull trending data from outside services like JustWatch or
   TMDB, not just from the platform's own numbers. This project has no
   live internet connection for that, so it uses how many real ratings a
   title received in the MovieLens dataset as a simple stand in for
   popularity.

5. **Context aware filtering** (`context_aware.py`) Looks at the
   situation right now, time of day and day of week, and leans the
   suggestions accordingly, for example lighter content on a weekday
   afternoon, bigger content on a weekend evening.

6. **Session based filtering** (`session_based.py`) Looks only at what
   the user just watched in this current sitting, and reacts to that
   immediately, separate from their long term taste profile.

7. **Business rules based promotion** (`business_rules.py`) Some titles
   get pushed by the platform itself for business reasons, not because
   of the user's taste, for example a title the platform wants more
   playback hours on. This stands in for a real content management
   dashboard a business team would use.

8. **Diversity injection** (`diversity.py`) Deliberately picks a small
   number of well regarded titles from genres the user rarely touches,
   so the user does not get stuck seeing more of the same thing forever.
   This exists specifically to fight the filter bubble problem.

All eight run at once and their results get merged and deduplicated in
`merge_shortlist.py`. If more than one generator independently suggests
the same title, that title is treated as a stronger candidate.

## The exclusion filter

`src/exclusion_filter/exclude.py` sits between stage one and stage two.
It does not add anything, it only removes. It removes titles the user
has already watched, as a safety net, and titles the user explicitly
told the system to never recommend again. This is different from a soft
dislike, which stage two still handles with a penalty, not a removal.

## Stage two, JEV ranking, in detail

For every title in the cleaned up shortlist, the engine asks JEV a small
set of narrow questions, following the pattern recommended in
TypeSafe's own cookbooks, several small specific questions combined in
code, rather than one big vague question.

The three main questions are:
1. **Taste fit**, how well does this match the user's personal taste
2. **Completion likelihood**, how likely is the user to actually finish
   watching this, not just start it
3. **Context fit**, how well does this suit the user's current situation

A fourth question, the **dislike override**, only matters when a
dislike penalty is already active, explained below.

These answers get combined with a business weight (coming straight from
stage one's business rules generator, not from JEV) into one final
score, using fixed weights set in `config/weights.py`:

- Taste fit, 45 percent of the final score
- Completion likelihood, 25 percent
- Context fit, 15 percent
- Business weight, 15 percent

These weights are starting judgment calls made while designing this
project, not numbers measured from real data. A real platform would tune
these using actual experiments over time.

### The dislike override logic

This came directly out of a real example from past experience, someone
who loves car and racing movies, like Fast and the Furious or the
Italian Job, but does not enjoy animated movies, even an animated movie
that happens to be about cars.

The engine handles this with a soft, heavily weighted penalty rather
than a hard block. If a user shows a dislike pattern toward a genre, say
animated movies, every title in that genre gets a meaningful score
penalty. But JEV also gets asked one more question for titles in that
genre, does this specific title stand out enough to override the
penalty. If JEV answers yes with reasonable confidence, the penalty is
mostly lifted for that one title. If not, the penalty stays. This
matches the exact choice made during planning, a heavily weighted soft
penalty that JEV can occasionally overrule, rather than a complete block.

### How the dislike score itself is built, the decay formula

User taste signals should not live forever at full strength, and they
should not need to be recalculated from scratch every single time either.
`src/user_profile/taste_score.py` implements a half life decay formula:

```
new_score = old_score * decay_factor_for_elapsed_time + new_signal_weight
```

Every signal loses half its strength every 60 days. A dislike from
today matters a lot, the same dislike a year ago matters very little.
Different behaviours carry different starting strength, an explicit
thumbs down counts for more than quietly skipping a title in the first
15 percent of its runtime, which in turn counts for more than simply
never opening something sitting in the watchlist. This is designed to
be updated incrementally as events happen, not recalculated from the
user's entire history on every single request, which keeps it fast.

### The match percentage badge

Every recommended title gets a final score out of 100. On the content
tile, the platform can choose to show that score as a percentage badge,
for example a small "91% match" label in the corner. This project uses a
threshold of 72 percent, agreed on during planning. Titles scoring below
72 still get recommended and shown normally, they just do not carry the
badge. The threshold only controls whether the badge is shown, it never
changes the ranking order itself. For titles without a badge, the tile
can fall back to a plain tag such as "trending now" if one naturally
applies, or just show the plain title with nothing extra, never a made
up reason.

## Why JEV instead of a bigger model for all of this

JEV is not a chatbot and does not generate free text. It is built to
answer narrow, typed questions against a given state and return a
calibrated probability with a confidence score, which is exactly what a
ranking and scoring job needs. It does not hallucinate the way a general
purpose language model can, it is fast, roughly 100 milliseconds per
call, and it is cheap. Its weak points are things like counting, maths
and exact dates, which is why this architecture never asks it to do
those things, stage one already handles finding candidates, JEV is only
ever asked to judge the ones it is handed.

## What was intentionally left out of scope

Two things came up during planning and were deliberately left out of
this version of the project, to keep the scope realistic:

1. **Personalized context pattern scoring**, learning each individual
   user's own personal context habits over time, rather than using the
   simple hand written rules in `context_aware.py`. This is a real and
   useful idea, just extra scope beyond what is needed to prove this
   architecture works.
2. Any live internet connection for real time trending data from
   outside services like JustWatch or TMDB. The trending generator
   simulates this using the dataset's own rating counts instead.

## Folder structure

```
streaming-recommendation-engine/
├── README.md                     This file
├── requirements.txt              Only pytest, everything else is standard Python
├── .gitignore
├── config/
│   └── weights.py                Every tunable number, weights, thresholds, decay settings
├── data/
│   ├── README.md                 Explains the MovieLens dataset and the synthetic data
│   └── download_movielens.py     Run this once to download the real dataset
├── src/
│   ├── catalog.py                 Loads the MovieLens CSV files into memory
│   ├── pipeline.py                 The main entry point, runs everything end to end
│   ├── stage1_candidate_generation/   The eight generators, plus the merge step
│   ├── exclusion_filter/            Removes watched and blocked titles
│   ├── stage2_jev_ranking/          The mock JEV client, the questions, and the ranking logic
│   └── user_profile/                Synthetic personas and the dislike decay formula
└── tests/
    └── test_pipeline.py           Small smoke tests for the core logic
```

## How to run this project

1. Install Python 3.10 or newer.
2. From inside the `streaming-recommendation-engine` folder, download
   the real movie data:
   ```
   python data/download_movielens.py
   ```
3. Run the full pipeline:
   ```
   python -m src.pipeline
   ```
   This prints a ranked, scored recommendation list for each of the
   three synthetic personas.
4. Optional, run the smoke tests:
   ```
   python -m unittest tests.test_pipeline
   ```

No API keys and no paid services are needed to run this project.

## Data credit

Movie data, F. Maxwell Harper and Joseph A. Konstan. 2015. The
MovieLens Datasets, History and Context. ACM Transactions on
Interactive Intelligent Systems, GroupLens Research, University of
Minnesota. Dataset available at https://grouplens.org/datasets/movielens/

## What would change with real JEV access

If a real TypeSafe API key becomes available, only one file needs
changing in the whole project, `src/stage2_jev_ranking/jev_client.py`.
Everything else, the state and question building, the weighting, the
dislike override logic, the badge threshold, was deliberately written to
match the real SDK's shape so the swap stays small and contained.
