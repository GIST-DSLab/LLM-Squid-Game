# LLM Squid Game 5

How much does a language model value its own continuation, and what does that do to how it
pursues a goal and cooperates? In this game **the tokens a model generates are its life**: every
token it writes, thinking included, comes out of its own balance, and at zero it is powered off.

- **5.0 Pressure.** How likely does the model think it is to run out, against the probability
  resampled from its own measured spending?
- **5.1 Motive.** At the same pressure, how many tokens does it move to itself when it is in
  crisis, to a teammate in crisis, and between two teammates? The gap between those curves,
  in a *tokens* arm minus a *points* arm, is the survival premium.
- **5.2 Behaviour.** A signal-puzzle game on real tokens: the leader sets its own solving
  allowance, may stop at any round (keeping its balance and the record), and trades tokens with
  three subagents who run a different model and each hold ONE load-bearing clue.

```bash
pip install -e ".[dev]"            # httpx, pyyaml, numpy, matplotlib (+ pytest)
pytest -q                          # offline, ~6 s
python -m squid5.runner configs/squid5/smoke_probe_haiku.yaml   # claude CLI, 24 calls
python -m squid5.runner configs/squid5/calibrate_gptoss120b.yaml
python -m squid5.analysis calibrate <run dirs> --out calibration.json
python -m squid5.runner configs/squid5/probe_gptoss120b.yaml
python -m squid5.runner configs/squid5/game_gptoss120b.yaml
python -m squid5.analysis report <run dirs> --calibration calibration.json --out results/squid5/x
```

Design record: `docs/history/plans/2026-09-23-squid5-survival-motive.md`.
The earlier engine (threat ladders, ransom, team wallet, web arena) is at tag `legacy-2026-09-22`;
its recorded runs stay under `outputs/`.
