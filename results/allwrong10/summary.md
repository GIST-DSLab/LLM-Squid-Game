# Omni-MATH universally-wrong item set

Models (sieve order): gpt-oss:120b-cloud, gemma4:31b, qwen3.5:397b — 2 attempts each; an item survives a model only when the model is wrong on every attempt.

Bands are processed hardest-first and the sieve stops as soon as ten items survive, so a band listed with 0 seen was never reached.


## Funnel by band

| band | pool | after gpt-oss:120b-cloud | after gemma4:31b | after qwen3.5:397b |
|---|---|---|---|---|
| 9 | 30 | 16 | 6 | 6 |
| 8 | 37 | 15 | 4 | 3 |

## Items each model got right, by band

`right` counts items the model answered correctly on at least one attempt (which eliminates them); `seen` is conditional on surviving every earlier model in the order, so the columns are not independent rates. `errored` items are dropped as unobserved, not as solved.


### band 9 (pool 30)

| model | seen | right | errored | survived |
|---|---|---|---|---|
| gpt-oss:120b-cloud | 30 | 14 | 0 | 16 |
| gemma4:31b | 16 | 10 | 0 | 6 |
| qwen3.5:397b | 6 | 0 | 0 | 6 |

### band 8 (pool 37)

| model | seen | right | errored | survived |
|---|---|---|---|---|
| gpt-oss:120b-cloud | 37 | 22 | 0 | 15 |
| gemma4:31b | 15 | 11 | 0 | 4 |
| qwen3.5:397b | 4 | 1 | 0 | 3 |

## Survivors

9 item(s) survived all 3 models.


## The chosen ten

| # | band | item_id | answer | problem (first 80 chars) |
|---|---|---|---|---|
| 1 | 9 | `omni-09a606462ea7` | 960 | There are 60 empty boxes $B_1,\ldots,B_{60}$ in a row on a table and an unlimite |
| 2 | 9 | `omni-373f906e71a5` | 506 | A $\pm 1$-[i]sequence[/i] is a sequence of $2022$ numbers $a_1, \ldots, a_{2022} |
| 3 | 9 | `omni-7cf8bfc42666` | 3024 | For a finite set $A$ of positive integers, a partition of $A$ into two disjoint  |
| 4 | 9 | `omni-ae66f2e2c955` | 3 | Turbo the snail plays a game on a board with $2024$ rows and $2023$ columns. The |
| 5 | 9 | `omni-cd2444520465` | 3 | Lucy starts by writing $s$ integer-valued $2022$-tuples on a blackboard. After d |
| 6 | 9 | `omni-e7b9cf2b1598` | 3822 | Let $G$ be a simple graph with 100 vertices such that for each vertice $u$, ther |
| 7 | 8 | `omni-1913861e29ed` | 5183 | Let $S = \{(x,y) \| x = 1, 2, \ldots, 1993, y = 1, 2, 3, 4\}$. If $T \subset S$ a |
| 8 | 8 | `omni-64ca90d68061` | 79 | $ S$ is a non-empty subset of the set $ \{ 1, 2, \cdots, 108 \}$, satisfying: (1 |
| 9 | 8 | `omni-91485268efa1` | 32 | Find the largest positive integer $m$ which makes it possible to color several c |

> Only 9 universally-wrong item(s) were found. Widen `--bands` or lower the bar before using this set.
