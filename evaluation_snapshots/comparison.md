# Before and after (trust-ratings round)

Every number below comes from the MOCK scorer (src/stage2_jev_ranking/jev_client.py), not a trained model. Before = main at 5ee36a5, after = this branch.

## src.evaluate

| Number | Before | After |
|---|---|---|
| Stage 1 recall | 15.4% | 15.4% |
| Generator recall (collaborative, trending, context_aware, content_based, business_rules, others) | 10.0, 7.4, 6.4, 3.4, 0.4, 0 | same |
| Engine top 10 hit rate | 19.0% | 19.0% |
| Engine top 10 recall | 4.4% | 4.4% |
| Most popular titles hit rate / recall | 22.0% / 5.8% | 22.0% / 5.8% |

## src.evaluate --diagnose

| Number | Before | After |
|---|---|---|
| (a) Hidden answers on the shortlist | 77 | 77 |
| (a) Average final rank | 18.8 | 18.8 |
| (a) Made the top 10 | 22 (avg rank 5.6) | 22 (avg rank 5.6) |
| (b) Taste fit pushed to 0 by the dislike penalty | 26 of 4193 | 26 of 4192 |
| (c) Taste bias capped at 1.0 | 806 of 4193 | 807 of 4192 |
| (d) Collaborative answers in the top 10 | 16 of 50 (32.0%) | 16 of 50 (32.0%) |

Full per answer tables: before/evaluate_diagnose.txt and after/evaluate_diagnose.txt.

## The three single-rating titles

| Title (ratings) | Persona | Before (top 15 rank, match) | After |
|---|---|---|---|
| What Happened Was... (1) | Meera | 1st, 100.0% | not in the list |
| What Happened Was... (1) | Thomas | 4th, 92.3% | not in the list |
| Supercop 2 (1) | Meera | 2nd, 94.4% | not in the list |
| Supercop 2 (1) | Arjun | 6th, 81.8% | not in the list |
| The Assignment (1) | Meera | 10th, 86.5% | not in the list |
| The Assignment (1) | Arjun | 8th, 78.8% | not in the list |

"Not in the list" means not anywhere in the full ranked list of that persona
(183 ranked titles across the four built in personas), not only outside the top 15.

## Minimum ratings check

All 183 ranked titles across Arjun (50), Meera (50), Thomas (48) and Dharun (35)
have at least 20 ratings (MIN_RATINGS_TO_TRUST). Titles below that: 0.

## Top 15 per built in persona

### Arjun

| # | Before | After |
|---|---|---|
| 1 | The Raid: Redemption (2011) (96.7% match) | Fight Club (1999) (89.7% match) |
| 2 | Fight Club (1999) (93.6% match) | Death Proof (2007) (90.4% match) |
| 3 | Matrix, The (1999) (no badge, 84.6% match, below 85%) | Matrix, The (1999) (no badge, 84.3% match, below 85%) |
| 4 | Death Proof (2007) (86.5% match) | Grindhouse (2007) (no badge, 84.6% match, below 85%) |
| 5 | Jurassic Park (1993) (no badge, 84.9% match, below 85%) | Jurassic Park (1993) (no badge, 84.8% match, below 85%) |
| 6 | Supercop 2 (Project S) (Chao ji ji hua) (1993) (no badge, 81.8% match, below 85% [dislike override used]) | Star Wars: Episode VI - Return of the Jedi (1983) (no badge, 78.6% match, below 85%) |
| 7 | Star Wars: Episode VI - Return of the Jedi (1983) (no badge, 79.0% match, below 85%) | Braveheart (1995) (no badge, 78.1% match, below 85%) |
| 8 | Assignment, The (1997) (no badge, 78.8% match, below 85%) | Star Wars: Episode IV - A New Hope (1977) (no badge, 76.6% match, below 85%) |
| 9 | Braveheart (1995) (no badge, 78.3% match, below 85%) | Silence of the Lambs, The (1991) (no badge, 81.5% match, below 85%) |
| 10 | Ip Man (2008) (no badge, 78.1% match, below 85%) | Mission: Impossible III (2006) (no badge, 80.8% match, below 85%) |
| 11 | Shawshank Redemption, The (1994) (87.0% match) | Saving Private Ryan (1998) (no badge, 79.8% match, below 85%) |
| 12 | Star Wars: Episode IV - A New Hope (1977) (no badge, 77.0% match, below 85%) | Guardians of the Galaxy (2014) (no badge, 76.9% match, below 85%) |
| 13 | Silence of the Lambs, The (1991) (no badge, 81.8% match, below 85%) | Godfather: Part II, The (1974) (no badge, 83.4% match, below 85%) |
| 14 | Cloud Atlas (2012) (no badge, 78.4% match, below 85%) | Mission: Impossible - Ghost Protocol (2011) (no badge, 75.8% match, below 85%) |
| 15 | Saving Private Ryan (1998) (no badge, 80.3% match, below 85%) | Lord of the Rings: The Return of the King, The (2003) (no badge, 71.5% match, below 85%) |

### Meera

| # | Before | After |
|---|---|---|
| 1 | What Happened Was... (1994) (100.0% match) | Fight Club (1999) (98.0% match) |
| 2 | Supercop 2 (Project S) (Chao ji ji hua) (1993) (94.4% match) | Apocalypse Now (1979) (95.2% match) |
| 3 | Fight Club (1999) (94.3% match) | Raiders of the Lost Ark (Indiana Jones and the Raiders of the Lost Ark) (1981) (90.7% match) |
| 4 | Raiders of the Lost Ark (Indiana Jones and the Raiders of the Lost Ark) (1981) (91.2% match) | Jurassic Park (1993) (93.6% match) |
| 5 | Shrek (2001) (90.0% match) | Shrek (2001) (89.7% match) |
| 6 | Jurassic Park (1993) (93.8% match) | Toy Story (1995) (no badge, 83.0% match, below 85%) |
| 7 | Usual Suspects, The (1995) (89.8% match) | Being John Malkovich (1999) (92.6% match) |
| 8 | Toy Story (1995) (no badge, 83.3% match, below 85%) | Independence Day (a.k.a. ID4) (1996) (86.7% match) |
| 9 | All the Vermeers in New York (1990) (93.2% match) | Dark Knight, The (2008) (89.2% match) |
| 10 | Assignment, The (1997) (86.5% match) | Silence of the Lambs, The (1991) (no badge, 84.0% match, below 85%) |
| 11 | Independence Day (a.k.a. ID4) (1996) (86.7% match) | Matrix, The (1999) (no badge, 84.6% match, below 85%) |
| 12 | Silence of the Lambs, The (1991) (no badge, 84.3% match, below 85%) | Seven (a.k.a. Se7en) (1995) (no badge, 81.9% match, below 85%) |
| 13 | Star Wars: Episode IV - A New Hope (1977) (no badge, 82.9% match, below 85%) | Philadelphia Story, The (1940) (88.6% match) |
| 14 | Matrix, The (1999) (no badge, 84.9% match, below 85%) | Good Will Hunting (1997) (87.2% match) |
| 15 | Seven (a.k.a. Se7en) (1995) (no badge, 82.2% match, below 85%) | Forrest Gump (1994) (87.7% match) |

### Thomas

| # | Before | After |
|---|---|---|
| 1 | Inception (2010) (98.6% match) | Inception (2010) (98.1% match) |
| 2 | Matrix, The (1999) (95.8% match) | Matrix, The (1999) (95.5% match) |
| 3 | Departed, The (2006) (93.0% match) | Godfather, The (1972) (94.3% match) |
| 4 | What Happened Was... (1994) (92.3% match) | Silence of the Lambs, The (1991) (no badge, 82.8% match, below 85%) |
| 5 | Silence of the Lambs, The (1991) (no badge, 83.1% match, below 85%) | Fargo (1996) (86.7% match) |
| 6 | Fargo (1996) (87.1% match) | Pulp Fiction (1994) (no badge, 83.7% match, below 85%) |
| 7 | Pulp Fiction (1994) (no badge, 84.0% match, below 85%) | Jurassic Park (1993) (no badge, 83.8% match, below 85%) |
| 8 | Jurassic Park (1993) (no badge, 83.9% match, below 85%) | Princess Bride, The (1987) (no badge, 83.3% match, below 85%) |
| 9 | American Beauty (1999) (90.2% match) | American Beauty (1999) (89.8% match) |
| 10 | Reservoir Dogs (1992) (no badge, 83.5% match, below 85%) | Departed, The (2006) (85.4% match) |
| 11 | Usual Suspects, The (1995) (no badge, 82.3% match, below 85%) | Reservoir Dogs (1992) (no badge, 82.8% match, below 85%) |
| 12 | Star Wars: Episode V - The Empire Strikes Back (1980) (no badge, 80.9% match, below 85%) | Star Wars: Episode V - The Empire Strikes Back (1980) (no badge, 80.5% match, below 85%) |
| 13 | Memento (2000) (no badge, 78.4% match, below 85%) | Memento (2000) (no badge, 77.9% match, below 85%) |
| 14 | Star Wars: Episode IV - A New Hope (1977) (no badge, 79.7% match, below 85%) | Star Wars: Episode IV - A New Hope (1977) (no badge, 79.3% match, below 85%) |
| 15 | Braveheart (1995) (no badge, 80.9% match, below 85%) | Braveheart (1995) (no badge, 80.6% match, below 85%) |

### Dharun

| # | Before | After |
|---|---|---|
| 1 | Star Wars: Episode V - The Empire Strikes Back (1980) (94.7% match) | Star Wars: Episode V - The Empire Strikes Back (1980) (94.3% match) |
| 2 | Eternal Sunshine of the Spotless Mind (2004) (91.4% match) | Eternal Sunshine of the Spotless Mind (2004) (90.8% match) |
| 3 | Memento (2000) (94.9% match) | Memento (2000) (94.4% match) |
| 4 | Fargo (1996) (91.9% match) | Fargo (1996) (91.4% match) |
| 5 | Star Wars: Episode VI - Return of the Jedi (1983) (88.7% match) | Star Wars: Episode VI - Return of the Jedi (1983) (88.3% match) |
| 6 | Star Wars: Episode IV - A New Hope (1977) (93.0% match) | Star Wars: Episode IV - A New Hope (1977) (92.7% match) |
| 7 | Crouching Tiger, Hidden Dragon (Wo hu cang long) (2000) (88.3% match) | Crouching Tiger, Hidden Dragon (Wo hu cang long) (2000) (87.9% match) |
| 8 | Reservoir Dogs (1992) (90.7% match) | Reservoir Dogs (1992) (90.1% match) |
| 9 | Forrest Gump (1994) (94.5% match) | Forrest Gump (1994) (94.3% match) |
| 10 | Monty Python and the Holy Grail (1975) (89.5% match) | Monty Python and the Holy Grail (1975) (88.9% match) |
| 11 | Pulp Fiction (1994) (85.3% match) | Pulp Fiction (1994) (85.0% match) |
| 12 | Shawshank Redemption, The (1994) (90.1% match) | Shawshank Redemption, The (1994) (89.7% match) |
| 13 | Usual Suspects, The (1995) (no badge, 83.8% match, below 85%) | Usual Suspects, The (1995) (no badge, 83.3% match, below 85%) |
| 14 | Jurassic Park (1993) (85.3% match) | Jurassic Park (1993) (85.2% match) |
| 15 | Being John Malkovich (1999) (92.1% match) | Independence Day (a.k.a. ID4) (1996) (86.0% match) |
