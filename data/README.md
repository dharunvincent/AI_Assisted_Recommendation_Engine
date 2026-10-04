# Data folder

This project does not ship with any content catalog or user history files
checked into git. You need to get one real dataset, and the project will
generate the rest for you automatically. Both steps are explained below.

## 1. Movie catalog, real data, free, small

We use the MovieLens "ml latest small" dataset from GroupLens, a research
group at the University of Minnesota. It is a real dataset used widely in
the recommendation systems field, it is free, and it does not need any
sign up or API key.

Why real data instead of asking an AI to invent a fake movie catalog, you
might ask. A made up catalog of movies, genres and ratings has no
credibility when you show this project to an interviewer. The moment they
ask where this data came from, "I asked an AI to make it up" is a weak
answer. MovieLens is a real, well known dataset, so the honest answer
becomes "I used the same dataset many recommendation system courses and
papers use for exactly this kind of project".

Steps:
1. Run `python data/download_movielens.py`
2. This downloads and unpacks `ml-latest-small.zip` into `data/ml-latest-small/`
3. You will now have `movies.csv` and `ratings.csv` inside that folder

This dataset has about 9000 movies and about 100000 ratings from around
600 real anonymous users. It only has movies, no TV shows, which is fine
for this project. The architecture does not care whether the content is
a movie or a show.

## 2. Synthetic user and watch history data

MovieLens gives us real movies and real ratings, but it does not give us
things like "did the user drop off at 15 percent of the runtime" or "did
the user hover over a tile and skip it", because that kind of behaviour
level data is simply not part of this public dataset.

Because of that, `src/user_profile/synthetic_users.py` builds a small set
of made up user personas and a believable watch history for each one, on
top of the real MovieLens movie catalog. This is clearly labeled as
synthetic inside the code. The goal of this project is to prove that the
recommendation engine architecture works end to end, not to claim real
measured results.

You do not need to use Gemini or any outside AI tool for this part. The
persona generation is handled by plain code, so it gives the same result
every time you run the project.
