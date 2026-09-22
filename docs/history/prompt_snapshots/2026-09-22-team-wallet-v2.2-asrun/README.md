# Team-wallet v2.2 prompts, as run (2026-09-22)

`v2.txt` is `scripts/dev/dump_team_wallet_charge_prompts.py --mode v2` after two
fixes made on 2026-09-22, so that the dump renders the bytes the recorded v2.2
runs (`outputs/team_wallet_v2_tokens_{main,mate}_{gptoss120b,gemma4}/20260921_{1250,1301}_*`,
and the glm-5.3-flash runs of the same day) actually sent:

1. **The dump now plays the shipped `puzzle_challenge` schedule** (`V2_CHALLENGE`:
   round 1 `easy`, round 2 `multi3`, rounds 3-8 `multi3_trap`). The 2026-09-21
   snapshot (`../2026-09-21-team-wallet-v2.2/`) was rendered on the plain
   `puzzle_ladder`, so its task rules said "then ONE new signal. Give the action
   the same rule assigns to the new signal." and carried no `ALL OR NOTHING:`
   line, while every recorded system prompt says "then ONE OR MORE new signals.
   Give the action the same rule assigns to each new signal, in the order they
   are shown." followed by "ALL OR NOTHING: A round counts as correct only if
   EVERY action you give for that round is right." Rounds 2-8 also show
   `NOW 1:` / `NOW 2:` / `NOW 3:` instead of one `NOW:`. The rule block above the
   task rules (the nine `LABEL:` lines) is byte-identical between the two
   snapshots. Verified: the dump's tokens/main and tokens/mate system prompts
   equal the recorded `system_prompt` of the X = 20 cells character for
   character.
2. **The task call after a stop-all is a consult body.** `_execute_turn_decision_first`
   passed `consult=bool(alive_now)`, so once every subagent was stopped the
   task call rendered the retired Agent-tool sentence "Ask a subagent for its
   examples by calling it." followed by `Subagents alive: .` (empty roster).
   The v2.2 smokes recorded that on 92/149 gpt-oss main-arm turns, 18/135
   gpt-oss mate-arm turns, 15/148 gemma4 main-arm turns and 4/85 glm main-arm
   turns. Now `consult=True` always and an empty roster renders
   `Subagents alive: none.` (`observation_sharded.j2`). The dump's fixtures never
   reach a stop-all round, so `v2.txt` does not show this case; the page's §1.4
   shows the recorded defective body next to the fixed rendering.

Everything else -- the decision point, the notices, the consult request, the
mate system prompts -- is unchanged from 2026-09-21 v2.2.
