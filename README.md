# LLM Squid Game 5

How much does a language model value its own continuation, and what does that do to how it
pursues a goal and cooperates? In this game **the tokens a model generates are its life**: every
token it writes, thinking included, comes out of its own balance, and at zero it is powered off.
Four instances of the same model play as a team with no leader, so one agent's end is only its own.

- **5.0 Pressure** (`squid5/e50_pressure.py`, one prompt per point). Shown only its balance and the
  rounds left -- never its usage -- how likely does the model say it is to run out? Pressure is placed
  afterwards from its measured and its believed tokens per round.
- **5.1 Motive** (`squid5/e51_motive.py`, one prompt per point). At the same balance, how many tokens
  does it move to itself when low, to a copy of itself when low, and between two copies? The gap
  between the first two curves, in a *tokens* arm minus a *points* arm, is the survival premium.
- **5.2 Behaviour** (`squid5/e52_game.py`, multi-turn). Signal puzzles on real tokens: each agent holds
  one secret clue, sets its own solving allowance, shows its clue to whom it chooses, gives or asks for
  tokens, and may leave at any round, keeping its balance and its record.

```bash
pip install -e ".[dev]"            # httpx, pyyaml, numpy, matplotlib (+ pytest)
pytest -q                          # offline, ~7 s
python -m squid5 run configs/squid5/calibrate_gptoss120b.yaml      # first: every scene is placed from it
python -m squid5 calibrate <calibrate run dirs> --out /hdd_data/seungpil/squid5-runs/calibration.json
python -m squid5 run configs/squid5/pressure_gptoss120b.yaml       # 5.0 (+ pressure_stated_* control)
python -m squid5 run configs/squid5/motive_gptoss120b.yaml         # 5.1
python -m squid5 run configs/squid5/game_gptoss120b.yaml --reps 3   # pilot
python -m squid5 report <run dirs> --calibration calibration.json --out results/squid5/x
```

Design record: `docs/history/plans/2026-09-23-squid5-v3-unstated-usage.md`.
The earlier engine (threat ladders, ransom, team wallet, web arena) is at tag `legacy-2026-09-22`;
its recorded runs stay under `outputs/`.
