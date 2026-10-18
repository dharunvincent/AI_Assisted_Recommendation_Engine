# Persona files

A persona file describes your own taste in plain JSON. Run the engine on it with:

    python3 -m src.pipeline --persona-file personas/example.json

Copy `example.json`, change the values, and run again. JSON has no comments,
so every field is explained here.

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Your name, used in the printout and the results file name. |
| `liked_genres` | yes | MovieLens genres you like, for example `"Action"`. At least one valid genre is needed. |
| `disliked_genres` | no | Genres you lean against. This is a soft penalty in ranking, not a ban: a title you would probably love can still get through. |
| `min_imdb_rating` | no | A number from 0 to 10. Titles rated lower on IMDb are removed. Titles with no IMDb rating, or fewer than 1000 IMDb votes, are removed too. Needs the IMDb data. |
| `year_from`, `year_to` | no | Whole years. Only titles released in this range are kept. `year_from` cannot be bigger than `year_to`. |
| `preferred_directors` | no | Directors you like. Their movies get found and ranked higher. Needs the IMDb data. |
| `preferred_cast` | no | Actors and actresses you like, same effect. Only the top 5 billed cast of each movie are known. |
| `avoided_directors`, `avoided_cast` | no | People you never want to see. A hard rule: any title with them is removed. |
| `favourite_titles` | no | A few movies you already love. They become your watch history, which the "people who liked this also liked" part of the engine needs. Without them, a history is made up from your liked genres. |

Valid genres: Action, Adventure, Animation, Children, Comedy, Crime,
Documentary, Drama, Fantasy, Film-Noir, Horror, IMAX, Musical, Mystery,
Romance, Sci-Fi, Thriller, War, Western.

## What happens when something is wrong

- **The run stops with a clear message** when the file is not valid JSON,
  `name` is missing, no valid liked genre is left, `year_from` is bigger than
  `year_to`, or a rating is outside 0 to 10.
- **The run continues with a warning** when one preference cannot be used:
  an unknown genre is dropped, a director, actor or favourite title that is not
  found is skipped (with "did you mean ..."), and without the IMDb data the
  IMDb based fields are skipped.
- **Movies with missing data** (no cast, no rating) are counted quietly and
  shown as one line in the "Warnings" section at the end.

Names are matched ignoring capital letters. Title matching ignores "The" and
"A" at the start, so "The Usual Suspects" works.
