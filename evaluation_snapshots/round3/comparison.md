# Before and after (phase 9)

Every number below comes from the MOCK scorer (src/stage2_jev_ranking/jev_client.py), not a trained model. Before = commit b082154 (main), after = this branch.

## src.evaluate

| Number | Before | After |
|---|---|---|
| Stage 1 recall | 15.4% | 15.4% |
| Generator recall (collaborative, trending, context_aware, content_based, business_rules, others) | 10.0, 7.4, 6.4, 3.4, 0.4, 0 | same |
| Engine top 10 hit rate | 17.0% | 19.0% |
| Engine top 10 recall | 4.0% | 4.4% |
| Most popular titles hit rate / recall | 22.0% / 5.8% | 22.0% / 5.8% |

## src.evaluate --diagnose

| Number | Before | After |
|---|---|---|
| (a) Hidden answers on the shortlist | 77 | 77 |
| (a) Average final rank of those | 20.8 | 18.8 |
| (a) Made the top 10 | 20 (avg rank 5.8) | 22 (avg rank 5.6) |
| (b) Taste fit pushed to 0 by the dislike penalty | 849 of 4193 | 26 of 4193 |
| (c) Taste bias capped at 1.0 | 575 of 4193 | 806 of 4193 |
| (d) Collaborative answers in the top 10 | 12 of 50 (24.0%) | 16 of 50 (32.0%) |

Full per answer tables: evaluation_snapshots/before/evaluate_diagnose.txt and after/evaluate_diagnose.txt.

## Toy Story rank

| Persona | Before | After |
|---|---|---|
| Dharun | 2 of 35 (override used, 83.2% match) | 31 of 35 (no override, 56.3% match) |
| Arjun | 36 of 50 | 37 of 50 |

## Top 15 per built in persona

### Arjun

| # | Before | After |
|---|---|---|
| 1 | Fight Club (1999) | The Raid: Redemption (2011) |
| 2 | Matrix, The (1999) | Fight Club (1999) |
| 3 | The Raid: Redemption (2011) | Matrix, The (1999) |
| 4 | Jurassic Park (1993) | Death Proof (2007) |
| 5 | Braveheart (1995) | Jurassic Park (1993) |
| 6 | Shawshank Redemption, The (1994) | Supercop 2 (Project S) (Chao ji ji hua) (1993) |
| 7 | Star Wars: Episode IV - A New Hope (1977) | Star Wars: Episode VI - Return of the Jedi (1983) |
| 8 | Silence of the Lambs, The (1991) | Assignment, The (1997) |
| 9 | Death Proof (2007) | Braveheart (1995) |
| 10 | Supercop 2 (Project S) (Chao ji ji hua) (1993) | Ip Man (2008) |
| 11 | Star Wars: Episode VI - Return of the Jedi (1983) | Shawshank Redemption, The (1994) |
| 12 | Assignment, The (1997) | Star Wars: Episode IV - A New Hope (1977) |
| 13 | Independence Day (a.k.a. ID4) (1996) | Silence of the Lambs, The (1991) |
| 14 | Four Days in September (O Que É Isso, Companheiro?) (1997) | Cloud Atlas (2012) |
| 15 | Saving Private Ryan (1998) | Saving Private Ryan (1998) |

### Meera

| # | Before | After |
|---|---|---|
| 1 | Fight Club (1999) | What Happened Was... (1994) |
| 2 | Jurassic Park (1993) | Supercop 2 (Project S) (Chao ji ji hua) (1993) |
| 3 | What Happened Was... (1994) | Fight Club (1999) |
| 4 | Supercop 2 (Project S) (Chao ji ji hua) (1993) | Raiders of the Lost Ark (Indiana Jones and the Raiders of the Lost Ark) (1981) |
| 5 | Toy Story (1995) | Shrek (2001) |
| 6 | All the Vermeers in New York (1990) | Jurassic Park (1993) |
| 7 | Independence Day (a.k.a. ID4) (1996) | Usual Suspects, The (1995) |
| 8 | Raiders of the Lost Ark (Indiana Jones and the Raiders of the Lost Ark) (1981) | Toy Story (1995) |
| 9 | Shrek (2001) | All the Vermeers in New York (1990) |
| 10 | Good Will Hunting (1997) | Assignment, The (1997) |
| 11 | Forrest Gump (1994) | Independence Day (a.k.a. ID4) (1996) |
| 12 | Usual Suspects, The (1995) | Silence of the Lambs, The (1991) |
| 13 | Assignment, The (1997) | Star Wars: Episode IV - A New Hope (1977) |
| 14 | Braveheart (1995) | Matrix, The (1999) |
| 15 | Silence of the Lambs, The (1991) | Seven (a.k.a. Se7en) (1995) |

### Thomas

| # | Before | After |
|---|---|---|
| 1 | Inception (2010) | Inception (2010) |
| 2 | Matrix, The (1999) | Matrix, The (1999) |
| 3 | What Happened Was... (1994) | Departed, The (2006) |
| 4 | Jurassic Park (1993) | What Happened Was... (1994) |
| 5 | Star Wars: Episode V - The Empire Strikes Back (1980) | Silence of the Lambs, The (1991) |
| 6 | Star Wars: Episode IV - A New Hope (1977) | Fargo (1996) |
| 7 | Departed, The (2006) | Pulp Fiction (1994) |
| 8 | Braveheart (1995) | Jurassic Park (1993) |
| 9 | Silence of the Lambs, The (1991) | American Beauty (1999) |
| 10 | Pulp Fiction (1994) | Reservoir Dogs (1992) |
| 11 | American Beauty (1999) | Usual Suspects, The (1995) |
| 12 | Forrest Gump (1994) | Star Wars: Episode V - The Empire Strikes Back (1980) |
| 13 | In the Realm of the Senses (Ai no corrida) (1976) | Memento (2000) |
| 14 | Usual Suspects, The (1995) | Star Wars: Episode IV - A New Hope (1977) |
| 15 | Fargo (1996) | Braveheart (1995) |

### Dharun

| # | Before | After |
|---|---|---|
| 1 | Star Wars: Episode VI - Return of the Jedi (1983) | Star Wars: Episode V - The Empire Strikes Back (1980) |
| 2 | Toy Story (1995) | Eternal Sunshine of the Spotless Mind (2004) |
| 3 | Forrest Gump (1994) | Memento (2000) |
| 4 | Star Wars: Episode V - The Empire Strikes Back (1980) | Fargo (1996) |
| 5 | Fargo (1996) | Star Wars: Episode VI - Return of the Jedi (1983) |
| 6 | Shawshank Redemption, The (1994) | Star Wars: Episode IV - A New Hope (1977) |
| 7 | Eternal Sunshine of the Spotless Mind (2004) | Crouching Tiger, Hidden Dragon (Wo hu cang long) (2000) |
| 8 | Pulp Fiction (1994) | Reservoir Dogs (1992) |
| 9 | Jurassic Park (1993) | Forrest Gump (1994) |
| 10 | Star Wars: Episode IV - A New Hope (1977) | Monty Python and the Holy Grail (1975) |
| 11 | Independence Day (a.k.a. ID4) (1996) | Pulp Fiction (1994) |
| 12 | Braveheart (1995) | Shawshank Redemption, The (1994) |
| 13 | Being John Malkovich (1999) | Usual Suspects, The (1995) |
| 14 | Memento (2000) | Jurassic Park (1993) |
| 15 | Usual Suspects, The (1995) | Being John Malkovich (1999) |
