# AI Assisted Recommendation Engine

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

**Stage one, candidate generation.** Nine independent methods each look
at the user and the catalog from a different angle, and each one
produces a small list of candidate titles. In a real platform the nine
would run in parallel, each as its own service. In this project they run
one after another, because inside one Python process this work is pure
CPU, so parallel threads would not make it faster. Their output gets
merged into one list. A cleanup step called the exclusion filter then
removes anything the user has already watched, has explicitly blocked, or
that falls below the user's own quality floor. Only after that is the list
trimmed to the best 30 to 50 titles, so titles the filter removes never
take up a place that another title should have had.

**Stage two, JEV ranking.** The shortlist from stage one, now cleaned up,
goes to JEV. JEV does not search the whole catalog, it is not built for
that. Its job is to look at one title at a time, answer a few small,
specific questions about it for this user, and give back a score. The
engine asks JEV multiple small questions per title instead of one big
vague question, then combines the answers itself using fixed weights,
into one final score out of 100 for each title.

## Stage one, the nine candidate generators

Each generator lives in its own file inside `src/stage1_candidate_generation/`

1. **Content based filtering** (`content_based.py`) Uses the user's
   explicitly declared `preferred_genres` first when they exist, like
   from an onboarding quiz. Each preferred genre gets its own list of
   unwatched titles with at least 20 ratings, best known first, and the
   generator's slots are filled by taking one title from each genre in
   turn, so the picks are spread evenly across the preferred genres. Only
   when no preferred genres are set does it infer favourite genres from
   the titles the user has already watched and liked, and rank titles by
   how many of those genres they share. In that inferred case it only
   keeps titles with at least 20 ratings, and sorts by the real genre
   overlap count, then rating count, then average rating (it used to
   return titles in catalog file order). Works well once a user has some
   history or declared taste, struggles for a brand new user with neither.

2. **Collaborative filtering** (`collaborative.py`) Uses the real
   MovieLens ratings from hundreds of real anonymous people to find
   patterns like, people who rated movie A highly also tended to rate
   movie B highly. This is the exact Harry Potter style example that
   came up while designing this project, watch and like the first one,
   get the second one recommended because other real viewers followed
   that same pattern. Links are scored with cosine similarity, which
   divides the number of shared fans by the square root of the two
   movies' fan counts, so a blockbuster that everybody liked no longer
   wins for every user just because it shares fans with everything. Pairs
   with fewer than 3 shared fans are ignored as noise.

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
   afternoon, bigger content on a weekend evening. Friday evening counts
   as a weekend evening. It only keeps titles with at least 20 ratings and
   lists the best known first (it used to take the first matching titles
   in catalog file order, which let random 1995 films fill the results).

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
   This exists specifically to fight the filter bubble problem. A title
   needs at least 20 ratings behind its average to be offered, because a
   high average from two raters is luck, not quality.

9. **Preferred directors and cast** (`people_based.py`) Only active for a
   persona file that names favourite directors or actors (see "Run it
   with your own taste"). It finds unwatched titles with one of those
   people, best known first, with a reason like "directed by Michael
   Mann". For the four built in personas it returns nothing.

All nine are designed to run in parallel in a real platform, and run one
after another in this project, because threads give no speed up for pure
CPU work in one Python process. Their results get merged and deduplicated in
`merge_shortlist.py`. If more than one generator independently suggests
the same title, that title is treated as a stronger candidate. Ties are
settled by best position, so a title that was some generator's top pick
beats one that only barely made another generator's list.

## The exclusion filter

`src/exclusion_filter/exclude.py` sits between stage one and stage two.
It does not add anything, it only removes. It removes titles the user
has already watched, as a safety net, titles the user explicitly told the
system to never recommend again, and, for a user who set a quality floor,
titles rated below it, with no rating, or with fewer than 20 ratings (a
high average from only a few raters cannot be trusted). This is different
from a soft dislike, which stage two still handles with a penalty, not a
removal. The list is trimmed to its maximum size only after this step.

A persona file adds three more hard rules, each active only when the file
sets it: a release year range, an IMDb rating floor (titles with no IMDb
rating, or fewer than 1000 IMDb votes, are removed too, and this floor
replaces the MovieLens one for that persona), and directors or cast the
user never wants to see. Disliked genres stay a soft penalty in stage two on
purpose: a genre dislike is a lean, an avoided person is a rule.

## Stage two, JEV ranking, in detail

For every title in the cleaned up shortlist, the engine asks JEV a small
set of narrow questions, following the pattern recommended in
TypeSafe's own cookbooks, several small specific questions combined in
code, rather than one big vague question.

The three main questions are:
1. **Taste fit**, how well does this match the user's personal taste,
   asked as "ignoring any general dislike of this genre", so the answer is
   a before penalty score
2. **Completion likelihood**, how likely is the user to actually finish
   watching this, not just start it
3. **Context fit**, how well does this suit the user's current situation

A fourth question, the **dislike override**, only matters when a
dislike penalty is already active, explained below.

These answers get combined with a business weight (coming straight from
stage one's business rules generator, not from JEV) into one final
score, using fixed weights set in `config/weights.py`. A normal title has
a business weight of 0 and a promoted title gets a small positive weight,
so promotion is worth at most 7.5 extra points:

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
The penalty is applied in exactly one place, `rank.py`. It is never also
folded into the taste fit question, which would count it twice and stop
the override from working. In the mock, the override question is answered
"show anyway" rarely for weak fits and often for strong fits. What counts as
a strong fit is explained in "Round three changes" below: it now takes a
standout rating, not just shared genres.

### How the dislike score itself is built, the decay formula

User taste signals should not live forever at full strength, and they
should not need to be recalculated from scratch every single time either.
`src/user_profile/taste_score.py` implements a half life decay formula:

```
new_score = old_score * decay_factor_for_elapsed_time + new_signal_weight
```

Every signal loses half its strength every 60 days, and every score is
also faded up to today whenever it is read, so an old dislike with no
newer event still fades away. A dislike from today matters a lot, the
same dislike a year ago matters very little.
Different behaviours carry different starting strength, an explicit
thumbs down counts for more than quietly skipping a title in the first
15 percent of its runtime, which in turn counts for more than simply
never opening something sitting in the watchlist. Only leaving early
counts as a dislike. A watch is read in three bands: 70 percent or more is
liked, below 20 percent is a dislike signal, and anything in between is
neutral and creates no dislike at all, because stopping midway can have
many reasons such as falling asleep or getting busy. This is designed to
be updated incrementally as events happen, not recalculated from the
user's entire history on every single request, which keeps it fast.

### The match percentage badge

Every recommended title gets two numbers, and they do different jobs.

- **Ranking score** (`final_score`, in the CSV). The weighted sum of taste
  fit, completion, context fit and promotion. It decides the ORDER of the
  list and nothing else.
- **Match %** (`match_percent`, the Match column). How well the title fits
  the person: 65 percent taste fit (after the dislike penalty) and 35 percent
  completion likelihood. Promotion and context fit are not part of it, so a
  promoted title can never look like a better match than it is. The ranking
  score could not be shown directly because it never goes above about 74:
  a normal title always scores 0 on promotion, which costs 15 points, and
  context fit sits near 0.45.

Because the list is ordered by the ranking score, the Match column is not
always strictly descending.

The badge (a small "91% match" label on the tile) is shown when the match %
is 85 or higher (`BADGE_DISPLAY_THRESHOLD_PERCENT`). 85 was chosen after looking at 228 titles across the four
built in personas and one saved persona: it badges about 1 in 5 titles
(18 percent), while the old cut off of 72 would have badged 54 percent of
them. That 1 in 5 was measured before round three. After it, 34 of the 60
titles in the four built in top 15 lists carry the badge (57 percent), because the
dislike penalty is capped and context fit now lifts every title that suits the
moment. The cut off was not changed, it is a locked decision. Titles below 85 still get recommended and shown normally, they just do
not carry the badge. The threshold never changes the ranking order. For titles without a badge, the tile
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
AI_Assisted_Recommendation_Engine/
├── README.md                     This file
├── CLAUDE.md                     Project instructions for Claude Code (the coding style mode)
├── recommend                     The one word launcher script, see "Run it in one word"
├── requirements.txt              Only pytest, everything else is standard Python
├── .gitignore
├── config/
│   └── weights.py                Every scoring weight and threshold, in one place
├── data/
│   ├── README.md                 Explains the MovieLens dataset and the synthetic data
│   ├── download_movielens.py     Run this once to download the real dataset
│   └── download_imdb.py          Optional, adds IMDb rating, directors and cast
├── personas/
│   ├── README.md                 Every persona file field explained
│   └── example.json              A persona file to copy and edit
├── src/
│   ├── catalog.py                 Loads the MovieLens (and optional IMDb) data into memory
│   ├── launcher.py                 The one word launcher: data check, menu, table (run by `recommend`)
│   ├── interactive.py              The questions that build a persona file from your answers
│   ├── results_report.py           Printed list, results CSV and the filter report
│   ├── run_warnings.py             The grouped "Warnings" section
│   ├── pipeline.py                 The main entry point, runs everything end to end
│   ├── evaluate.py                 Offline evaluation on real MovieLens users
│   ├── stage1_candidate_generation/   The nine generators, plus the merge step
│   ├── exclusion_filter/            Removes watched, blocked and low quality titles
│   ├── stage2_jev_ranking/          The mock JEV client, the questions, and the ranking logic
│   └── user_profile/                Synthetic personas, the persona file loader, the dislike decay formula
└── tests/
    ├── test_pipeline.py           Tests for the core logic, filters, merge and decay
    ├── test_rank.py               Tests for the stage 2 penalty, override, business weight and badge
    ├── test_jev_client.py         Tests for how the mock JEV client behaves
    ├── test_evaluate.py           Tests that the evaluation split never leaks an answer, plus the --diagnose helpers
    ├── test_generators.py         Tests for the content based, diversity and context aware fixes
    ├── test_interactive.py        Tests for the questions and the --badged-only / --top flags
    ├── test_launcher.py           Tests for the one word launcher
    ├── test_imdb_data.py          Tests for the IMDb download helpers and catalog fields
    ├── test_persona_loader.py     Tests for the persona file, one group per failure level
    ├── test_hard_filters.py       Tests for the year, IMDb floor and avoided people filters
    ├── test_people.py             Tests for the people generator and the capped taste boost
    └── test_results_report.py     Tests for the printed list, the CSV and the filter report
```

## Run it in one word

```
recommend
```

That is all. Type it in any Terminal folder (it needs Python 3.9 or newer, and
the one time setup below). It first asks:

1. **Use a ready made persona** picks one of the four built in personas, or one
   of your saved `personas/*.json` files, and goes straight to the results.
2. **Enter your own preferences** asks one plain English question at a time.
   Only the genres you like are required, press Enter to skip the rest. A
   wrong answer is explained and asked again, and a name that is not found
   offers a "did you mean" you accept with `y`.

Then you see a short summary and type `go` (show recommendations), `redo`
(start the questions over) or `quit` (exit, nothing saved). Press Ctrl+C at
any time to stop, nothing is saved.

The results are one table with every ranked movie: rank, title, year, IMDb
rating, match %, a ✓ badge for 85 or above, and the main reason. Your answers
are saved to `personas/<name>.json` and the results to `results/*.csv`,
neither is committed to git.

One time setup, from the project folder:

```
python3 data/download_movielens.py     # the movies
python3 data/download_imdb.py          # ratings, directors, cast
echo 'alias recommend="'"$PWD"'/recommend"' >> ~/.zshrc   # then open a new Terminal window
```

If a download is missing, `recommend` says which one and the exact command to
fix it. Other commands:

```
python3 -m src.pipeline               # the four built in personas, plain output
python3 -m src.evaluate               # offline evaluation (see Evaluation)
python3 -m unittest discover tests    # all the tests
```

## Run it with your own taste

You can describe your own taste in a small file and get recommendations
from it. Steps:

1. Download MovieLens (once): `python3 data/download_movielens.py`
2. Download the IMDb data (once, several hundred MB, takes a few minutes):
   `python3 data/download_imdb.py`
3. Copy the example and edit it: `cp personas/example.json personas/me.json`.
   Every field is explained in `personas/README.md`.
4. Run it: `python3 -m src.pipeline --persona-file personas/me.json`
5. Open the CSV it saved in `results/` (the path is printed at the end).

What you get: the full ranked list as a table (rank, title, year, IMDb rating,
match %, badge, reason), the full list in the CSV, a filter report
saying how many titles each of your rules removed (and which one to relax
if the list is short), and a short "Warnings" section.

Problems are handled in three levels. The run **stops with a clear error**
only when the results would be meaningless (unreadable file, no name, no
valid liked genre, backwards year range, a rating outside 0 to 10, no
MovieLens data). It **warns and carries on** when one preference cannot be
used (an unknown genre, a director or favourite title not found, with a
"did you mean", or IMDb data not downloaded). A **single movie with missing
data** is counted quietly, never one line per movie.

Honest limits:
- MovieLens small has only about 9,700 movies, mostly up to 2018. A year
  range after 2018 will return almost nothing.
- Movies only, no shows.
- Stage 2 is still the mock scorer, so the scores show the architecture, not
  a measured result from a trained model.
- Cast is the top 5 billed actors and actresses. Documentaries often list
  people as "self", so their cast can be empty.

## How this project works

For someone who does not code. Think of the engine as a funnel.

1. **Know the movies.** MovieLens gives about 9,700 real movies with
   genres and ratings. IMDb data (optional) adds a rating, directors and cast.
2. **Know the person.** A persona is a description of someone's taste: what
   they like, dislike, and a few movies they love. Yours lives in a small
   JSON file, which you can write by hand or let `--interactive` create by
   asking you questions. If you give no favourite movies, a believable history is made
   from your liked genres, because the engine needs some history to learn from.
3. **Find many candidates.** Nine small "finders" each suggest titles from a
   different angle (similar genres, what similar people watched, what is
   popular, your favourite directors, and so on).
4. **Remove what must never appear.** Already seen, wrong years, rated too
   low, with someone you never want to see, or a title you named in
   `never_recommend_titles`. These are rules, so they
   always win.
5. **Rank what is left.** A scorer (a mock stand in, not a real AI model yet)
   gives each title a score out of 100. Disliked genres only lower a score a
   little, because a dislike is a lean, not a rule.
6. **Show and keep the result.** You get a short list on screen, the full list
   in a spreadsheet file, a note on what each rule removed, and a short list
   of warnings.

If something is missing or wrong, the engine tells you once, in plain words,
and keeps going unless the answer would be meaningless.

## Sample results

Meera and Thomas have watch histories built from the 20 highest rated
movies in their preferred genres (Comedy and Romance, Drama and
Documentary) that have at least 50 ratings, six of them picked at
random. Arjun's history is built from title keywords like "fast" and
"drive". These are the top results from one run, and every percentage is
produced by the mock scorer, not a trained model.

| Persona | Top result | Match | Titles with the badge (match 85 or above, top 15) |
|---|---|---|---|
| Arjun | The Raid: Redemption (2011) | 96.7% | 4 |
| Meera | What Happened Was... (1994) | 100.0% | 10 |
| Thomas | Inception (2010) | 98.6% | 6 |
| Dharun | Star Wars: Episode V - The Empire Strikes Back (1980) | 94.7% | 14 |

The percentage is the match %, not the ranking score. Meera's top pick is a
100.0% match (What Happened Was..., 1994), a title with a single rating. **A 100% match is not a
real perfect fit.** Taste and completion are both answered by the mock
scorer, whose random wobble can push both to the top, so 100% means the
wobble was lucky, nothing more. These numbers are higher than the tables
older versions of this README showed because they are a different measure
(see "The match percentage badge"). Do not compare them with the old 72.8%
and 76.0%, those were ranking scores.

The sections below describe an older round of changes, written when the
table showed ranking scores. In plain English, what changed in that round. Meera's top pick used to be Toy Story (82.5%) and Dharun's used to
be Pulp Fiction (81.0%). Those two were the promoted titles in the example
promotion list, and promotion used to hand them up to 13.5 free points over
every other title, so they won because they were promoted, not because of
taste. Promotion is now a nudge of at most 7.5 points, and the other
persona lists changed too, because collaborative filtering no longer
favours blockbusters and ties in the merge now go to each generator's
strongest picks. The badge counts stayed the same for Arjun, Thomas and
Dharun, and went from 6 to 5 for Meera.

Content based picks are spread evenly across a persona's preferred
genres. Each preferred genre gets its own list of titles with at least
20 ratings, best known first, and the generator takes one title from
each list in turn. Before this, titles that carried several preferred
genres crowded out genres that rarely come with a second tag, such as
Documentary. Documentaries now reach the shortlist for Thomas and
Dharun, but none of them make the final top 15. Dharun's best
documentary, Hoop Dreams, ranks 33rd with 54.7%.

Genre fixes in stage one: Arjun's keyword matches are now whole word
and limited to live action Action titles (so "Fast Times at Ridgemont
High" no longer counts as a car movie), and the content based generator
uses a persona's declared `preferred_genres` instead of genres inferred
from history, which Action and Crime dramas used to skew. The reasons
shown for Arjun now say "Action" and Thomas's genre based picks say
"Drama". Many items in all four lists still come from the trending,
popularity and collaborative generators, which do not look at genre, so
some off taste titles remain.

## The Dharun persona, a profile with two rules

The fourth persona is built on the author's own taste. He likes action,
thriller, documentary and comedy, dislikes animation, and avoids
anything rated low. His watch history takes two top rated titles from
each liked genre, so all four genres show up in it. The two dislikes
work in two different ways on purpose:

1. **Animation is a soft dislike.** It counts as an explicit thumbs down
   on the whole genre, so every animated title takes a heavy penalty in
   stage 2, and the override question can still lift it for one
   standout title. This is the same mechanism as the car movies versus
   animated movies story above.
2. **The rating floor is a hard rule.** A user who says they never
   watch anything rated below 6 out of 10 is not leaning, they are
   asking for a filter. So the exclusion filter removes those titles
   before stage 2 ever sees them, along with titles that have no rating or
   fewer than 20 ratings.

Two honest limits. MovieLens rates out of 5 and has no IMDb scores, so
6 out of 10 is stood in for by 3.0 out of 5. And MovieLens only has
movies, not shows. Run it with:

```
python -m src.pipeline --persona dharun
```

The output shows each title's average rating, and ends with a dislike
check that counts how many animated titles reached the top 15.

## Evaluation

Every percentage printed by the pipeline comes from the mock, so it cannot
tell you whether the engine recommends well. `src/evaluate.py` measures
something real instead. Run it with:

```
python -m src.evaluate
```

How it works. It picks 100 real MovieLens users with a fixed seed, so every
run uses the same ones. For each user it sorts their ratings by time and
hides their last 5 ratings of 4 stars or more as the "answers". Everything
before the first hidden rating becomes their watch history. Then it runs
the real pipeline and checks whether the hidden titles show up. The
collaborative table is built without the hidden ratings, so it never sees
the answers it is tested on. A rating becomes a completion like this: 4 or
more is 0.95 (liked), 3 or 3.5 is 0.6 (neutral), 2.5 or less is 0.1 (a
dislike signal).

Results from one run (500 hidden answers, 5 per user). Running it again
gives the same numbers.

| Measure | Result |
|---|---|
| Stage 1 recall, hidden titles that reached the shortlist | 15.4% (was 13.2%) |
| Recall of collaborative filtering alone | 10.0% (unchanged) |
| Recall of trending alone | 7.4% (unchanged) |
| Recall of context aware alone | 6.4% (was 0.0%) |
| Recall of content based alone | 3.4% (was 1.6%) |
| Recall of business rules alone | 0.4% (unchanged) |
| Recall of demographic, session based and diversity | 0.0% each |

| Top 10 | Hit Rate | Recall |
|---|---|---|
| This engine, after stage 2 | 19.0% (round three; 17.0% before it, 22.0% originally) | 4.4% (4.0% before it, 4.6% originally) |
| Plain "most popular titles" list | 22.0% | 5.8% |

Hit Rate is the share of users with at least one hidden title in their top
10. Recall is the share of all hidden titles found in the top 10.

Honest reading, round three. Hit Rate rose from 17.0 to 19.0 percent and
Recall from 4.0 to 4.4 percent. That is 2 more users out of 100 and 3 more
hidden titles out of 500, which is within what the noise of a 100 user test
can do on its own, so treat it as "no worse, probably a little better", not
as proof. The engine is still behind the plain popular list (22.0 percent).
Stage 1 recall did not move (15.4 percent) because round three only changed
stage 2 scoring. The newly found titles are still better known but not clearly
better matches, and the mock scorer cannot tell them apart.

Honest reading, from the generator fixes round (before round three). The generator fixes helped stage 1: more hidden titles now
reach the shortlist (15.4 percent, up from 13.2), and the context aware and
content based generators now find something. But the final top 10 got
**worse**: Hit Rate fell from 22.0 to 17.0 percent and Recall from 4.6 to
4.0 percent, so the engine is now clearly behind a plain list of the most
popular titles. The likely reason is that the newly found titles are better
known but not better matches, and the mock scorer cannot tell them apart
from the rest. That is a guess; this evaluation cannot prove it. The
ranking weights are locked decisions, so they were left alone.
Collaborative filtering and trending still do most of the work in stage 1.
The mock scorer decides stage 2, so none of this says how a real JEV model
would do.

The diagnosis report (`python -m src.evaluate --diagnose`) prints where each
hidden answer ended up and why. Its summary, before the generator fixes and
after:

| Diagnosis | Before | After |
|---|---|---|
| Hidden answers on the shortlist | 66 | 77 |
| Their average final rank | 22.2 | 20.8 |
| Of those, in the top 10 (average rank) | 23 (5.6) | 20 (5.8) |
| Shortlisted titles with taste fit pushed to 0 by the dislike penalty | 999 of 5000 | 849 of 4193 |
| Shortlisted titles with taste bias capped at 1.0 | 569 of 5000 | 575 of 4193 |
| Collaborative answers that made the top 10 | 14 of 46 (30.4%) | 12 of 50 (24.0%) |

The same summary after round three (the "before" below is the row above):

| Diagnosis | Before round three | After round three |
|---|---|---|
| Hidden answers on the shortlist | 77 | 77 |
| Their average final rank | 20.8 | 18.8 |
| Of those, in the top 10 (average rank) | 20 (5.8) | 22 (5.6) |
| Shortlisted titles with taste fit pushed to 0 by the dislike penalty | 849 of 4193 | 26 of 4193 |
| Shortlisted titles with taste bias capped at 1.0 | 575 of 4193 | 806 of 4193 |
| Collaborative answers that made the top 10 | 12 of 50 (24.0%) | 16 of 50 (32.0%) |

The titles with taste bias capped at 1.0 went UP. That is the collaborative
boost doing what it was built to do, but it also means more titles now sit at
the ceiling where the mock cannot tell them apart. The 26 titles still at 0
are ones whose taste fit was already below the largest penalty, 0.55.

Without `--diagnose` the output is exactly the same as before.

Limits of this evaluation:
- It is small, about 600 users in the dataset and 100 tested, so the numbers
  are noisy.
- The rating to completion mapping is a proxy, not real watch data.
- Stage 2 uses the mock scorer, so the stage 2 numbers measure the mock's
  simple rules, not a real JEV model.
- Catalog averages and rating counts still include the hidden ratings. This
  small leak affects trending, the quality floor and the mock scorer, and it
  also helps the popularity baseline.
- Every user gets the same example context (Friday evening).

## Round three changes

All ten changes keep the locked decisions (watch bands, the 0.55 penalty
scale, hard filters, the 7.5 point promotion limit, the preferred person boost,
the mock scorer, the ranking weights 45/25/15/15, the match percent and the
85 badge). In plain English:

1. **A dislike can no longer erase a whole genre.** The dislike score can grow
   to 3.0 after repeated early exits, and 3.0 x 0.55 is more than all of a
   title's taste fit, so every title in that genre dropped to 0. The penalty now
   reads the score only up to 1.0 (one explicit thumbs down), so the biggest
   penalty is 0.55 of taste fit. The stored score and its decay are untouched.
   Titles pushed to 0 fell from 849 to 26 (`DISLIKE_STRENGTH_CAP_FOR_PENALTY`).
2. **The override is now occasional.** Before, any title sharing two liked
   genres had a strong chance to beat a dislike, which is how Toy Story beat the
   animation dislike. A title now also needs a standout average rating of 4.2
   (`OVERRIDE_STANDOUT_RATING`) from at least 20 raters. In the catalog 972
   titles reach 4.2 on rating alone, but most are averages of a handful of
   raters; 39 pass with the 20 rater minimum. Toy Story (3.92) does not. For
   Dharun it fell from rank 2 to rank 31 of 35.
3. **Promotion never pushes a declared dislike.** A promoted title with a genre
   in the user's `disliked_genres` gets business weight 0 for that user.
   Dislikes learned from watch history do not count, only declared ones.
4. **Context fit is about the title.** It used to give 0.75 only when the
   context aware generator happened to pick the title, a free 4.5 points for 15
   popular titles for everyone. Now it is 0.75 when the title's genres match the
   current context bucket and 0.45 otherwise, whichever generator found it. The
   bucket logic lives in `context_aware.py` and is reused, not copied.
5. **Stage 2 uses the collaborative match strength.** Each collaborative pick
   now carries how strong the match was (0 to 1, the best pick of a user's list
   being 1). It adds up to 0.12 to the expected taste fit, the same as one
   shared genre. Collaborative answers in the top 10 went from 12 of 50 to 16 of 50.
6. **You can block titles.** `never_recommend_titles` in a persona file, and one
   optional interview question. A name blocks every title that contains it as
   whole words ("Star Wars" blocks all 13 Star Wars titles in the data, "Her"
   does not block "Mother"). The blocked titles are listed in Warnings, and a
   name that matches nothing gets a "did you mean".
7. **No more copies of config values.** The two printed sentences that said "85"
   and the repeated "top 15" now read `BADGE_DISPLAY_THRESHOLD_PERCENT` and
   `PRINTED_TOP_COUNT`.

Before and after for every number and each persona's top 15 are saved in
`evaluation_snapshots/` (`comparison.md`). **Every number in this README still
comes from the mock scorer.** The evaluation measures the mock's rules, not a
trained JEV model.

An honest finding from the comparison: Meera's top pick is a title with one
rating (average 5.0), and three other single rating titles sit in her top 15.
This is not new, the same title was already 3rd before round three. The mock
trusts a perfect average from one rater, because completion is guessed from the
average rating. Round three did not touch this and it is the next thing worth fixing.

## Changes after code review

A code review found the problems below, and each was fixed:

1. **Every scoring number now lives in `config/weights.py`.** Numbers were
   hidden inside logic files, and "liked" meant different things in
   different files. One shared rule now reads a watch as liked (70 percent
   or more), neutral, or a dislike signal (under 20 percent), so stopping
   midway no longer counts as a dislike.
2. **The dislike penalty is applied once.** It was subtracted in two places,
   so the override could never fully work. It now lives only in `rank.py`.
3. **The mock's override is rare for weak fits.** A flawed choice rule and a
   confidence number tied to the answer let weak fits override about one time
   in three. A test now checks the rates (about 10 percent and 70 percent).
4. **Dislikes fade up to today.** A score only decayed when a new event
   arrived, so an old dislike kept full strength. It is now faded when read.
5. **Promotion is a small nudge.** Two promoted titles used to get up to 13.5
   free points and won on promotion alone. A promoted title now gets at most
   7.5 points and a normal title gets none.
6. **Filter first, then trim.** The list was cut to 50 before the filter
   removed titles, which could leave too few. Ties also went to whichever
   generator ran first. Now it merges, filters, then trims, and ties go to
   each generator's strongest picks.
7. **Generators run one after another.** The threads gave no speed up for
   CPU work and the global random seed could affect other code. Each file
   now uses its own random generator. The results did not change.
8. **Collaborative filtering uses cosine similarity.** Raw counts made
   blockbusters win for everyone. Links are now normalised by popularity and
   noisy pairs are dropped.
9. **The ranking logic has tests.** Nothing tested the penalty, override,
   business weight or badge. `tests/test_rank.py` now does.
10. **There is a real evaluation.** Before, nothing measured whether the
    engine recommends well. `src/evaluate.py` now does, with a hold out
    split, a leak free collaborative table and a popularity baseline.

## Known limits of this version

- **The scoring is mocked.** JEV is a mock, so every match percentage
  is simulated, not measured.
- **Mock noise can outweigh small boosts.** Taste, completion and context
  each wobble at the same time. The typical gap between two titles' noise
  is about 6.6 points, and in the worst case one title's score can be off
  by about 12.75 points (so two titles could differ by up to about 25).
  That is bigger than a small boost such as a preferred director, so exact
  ranks between close titles are not meaningful until a real scorer
  replaces the mock. **Every number in this README, the match %, the ranking
  score and the badge, still comes from the mock scorer.** A match of 100%
  can come from the wobble, not from a real perfect fit.
- **No IMDb scores.** MovieLens has no IMDb ratings. The Dharun persona
  uses a MovieLens average of 3.0 out of 5 as a stand in for IMDb 6 out
  of 10. Titles with fewer than 20 ratings are removed by this rule,
  because a high average from only a few raters cannot be trusted.
- **Movies only.** MovieLens has no TV shows.
- **Popularity bias.** Titles in the results mostly come from 1993 to
  2003. The small dataset is dominated by older, heavily rated movies.
- **Niche genres rarely reach the top 15.** Stage 2 rewards titles that
  match several of the user's genres. This is a deliberate choice. So
  single genre titles, such as documentaries, reach the shortlist but
  rarely reach the top 15. Only 5 of the 440 documentaries have enough
  ratings to pass the 20 rating rule.
- **A fix that was tried and reverted.** Scoring genre fit by the share
  of a movie's genres was tried, then reverted. It ranked weak fits
  above strong multi genre fits and made the lists worse for Dharun and
  Arjun.
- **Good next step.** Reserve a slot in the top list for a liked genre
  that is under represented.
- **Promotion is a small score nudge.** A promoted title gets up to
  7.5 extra points. Real platforms often show promoted titles in their
  own row or a reserved slot instead of boosting their score. This
  project uses a small score nudge to keep things simple.
- **Genre dislikes are a soft penalty.** A strong animated title can
  still appear in the list.
- **Dropped titles taint all their genres.** When a watched title is
  left early (under 20 percent watched), all of its genres are marked as
  disliked. This is a known simplification.
- **Tie breaks use list order.** When two titles have the same number of
  sources, the merge prefers the one with the better position in a
  generator's list. The session based generator does not
  sort its list by quality, so position is only a rough signal there.
- **The evaluation is small and rough.** See the Evaluation section for its
  limits.

## Data credit

Movie data, F. Maxwell Harper and Joseph A. Konstan. 2015. The
MovieLens Datasets, History and Context. ACM Transactions on
Interactive Intelligent Systems, GroupLens Research, University of
Minnesota. Dataset available at https://grouplens.org/datasets/movielens/

Ratings, directors and cast (optional): Information courtesy of IMDb
(https://www.imdb.com). Used with permission. IMDb datasets are for personal
and non commercial use only, see `data/README.md`.

## What would change with real JEV access

If a real TypeSafe API key becomes available, only one file needs
changing in the whole project, `src/stage2_jev_ranking/jev_client.py`.
Everything else, the state and question building, the weighting, the
dislike override logic, the badge threshold, was deliberately written to
match the real SDK's shape so the swap stays small and contained.
