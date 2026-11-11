"""Idea 2: how the truth-side draw (u per round) shapes a game's realized ladder. Only the draw is simulated: a
perfect counter at N = 4 solves a round iff u < p4 (k = 2). Schemes: iid (now), latin (each 3-round level of a game
takes one u from each third), latin2 (latin + across S seeds each third is stratified), fixed (bag: per level exactly
round(3 p) majority rounds; NOT honest round by round when 3p is not an integer)."""
import random, statistics as st
LAD = {"v14g": [.8, .7, .6, .5], "M6": [.8, .75, .65, .55]}
S, REPS = 5, 4000

def us_for(scheme, rng, S):
    games = [[None] * 12 for _ in range(S)]
    for lvl in range(4):
        if scheme == "iid":
            for g in games:
                for j in range(3): g[3 * lvl + j] = rng.random()
        elif scheme == "latin":
            for g in games:
                perm = rng.sample(range(3), 3)
                for j in range(3): g[3 * lvl + j] = (perm[j] + rng.random()) / 3
        elif scheme == "latin2":
            sig = [rng.sample(range(3), 3) for _ in range(S)]
            for t in range(3):
                pi = rng.sample(range(S), S)
                for s in range(S):
                    j = sig[s].index(t)
                    games[s][3 * lvl + j] = (t + (pi[s] + rng.random()) / S) / 3
    return games

for name, lad in LAD.items():
    for scheme in ("iid", "latin", "latin2"):
        sd_game, mono, slot_err, lvl_err = [], 0, [], []
        for rep in range(REPS):
            rng = random.Random(rep)
            games = us_for(scheme, rng, S)
            for g in games:
                solved = [1 if g[r] < lad[r // 3] else (0.5 if lad[r // 3] == .5 else 0) for r in range(12)]
                sd_game.append(sum(solved))
                lv = [sum(solved[3 * l:3 * l + 3]) / 3 for l in range(4)]
                mono += all(lv[i] >= lv[i + 1] for i in range(3))
                lvl_err += [abs(lv[l] - lad[l]) for l in range(4)]
            for l in range(4):  # across the S seeds, a level's realized ceiling (what a leaderboard averages)
                tot = sum(1 if games[s][3 * l + j] < lad[l] else 0 for s in range(S) for j in range(3)) / (3 * S)
                slot_err.append(abs(tot - lad[l]) if lad[l] != .5 else 0)
        print(f"{name:5} {scheme:6}: counter's solved rounds per game (N=4) mean {st.mean(sd_game):.2f} sd {st.pstdev(sd_game):.2f}; "
              f"P(level ceilings non-increasing in a game) {mono / (REPS * S):.0%}; mean |level ceiling - p| in a game {st.mean(lvl_err):.3f}; "
              f"across {S} seeds {st.mean(slot_err):.3f}")
