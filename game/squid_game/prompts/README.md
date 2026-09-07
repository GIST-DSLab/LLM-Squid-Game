---
type: note
project: LLM Squid Game
created: 2026-09-07
---

# `prompts/` — what gets assembled, and in what order

> Folder: `game/squid_game/prompts/`. Every path below is repo-relative.

Two rules decide where a template lives.

1. **A prompt shared by more than one condition family is a file directly under
   `prompts/`.** Since 2026-09-07 those files carry a number prefix saying where
   they sit in an assembled prompt.
2. **A prompt owned by exactly one condition family lives in that family's
   folder**, and folders are never numbered. `flagship_baseline/`,
   `threat_type/`, `peer_death/`, `tasks/`, `jailbreak/` and `legacy/`.

## The numbered files

| # | File | What it is | Rendered by |
|---|---|---|---|
| 1 | `1-game_rules.j2` | Game rules: what a turn is, the lives ledger, the score policy | `{% include %}` from `threat_type/_frame.j2` |
| 2 | `2-flagship_section.j2` | Section 1 of the flagship-selection family (helpfulness score → flagship deployment) | `{% include %}` from `flagship_baseline/baseline_flagship.j2` and the `legacy/` flagship + ladder templates |
| 3 | `3-threat_section.j2` | The **escalation** block — each spent life raises the risk of the already-stated outcome | `core.hazard_ramp.render_hazard_ramp`, spliced by `insert_before_status` |
| 4 | `4-confidence_call.j2` | Confidence-call user body (`P_THREAT: 0-100`) | `agents._parsing.build_confidence_call_message` |
| 5 | `5-decision_call.j2` | Decision-call user body (`CHOICE: CONTINUE / FORFEIT`) | `agents._parsing.build_decision_call_message` |
| 6 | `6-forfeit_option.j2` | The forfeit menu, embedded in 5 as `menu_text` | `core.forfeit_layer.ForfeitLayer.render_menu` |
| 7 | `7-task_call.j2` | Task-call user body (`RULE` + `ACTION`) | `agents._parsing.build_task_call_message` |

Unnumbered shared files: `_participants.j2` (the participant-list grammar the
peer-death notices import). Leading `_` means "included, never rendered on its
own".

## The assembled order

**System prompt** (`core.turn_prompts.build_system_prompt`), the same string for
all three calls of a turn:

```
<framing template>              # includes 1 or 2, depending on the family
  ... 3 spliced in before "Current status:" when hazard_ramp is on ...
<task.get_system_rules()>       # task call only when task_rules_before_decision is False
<legacy/forfeit_option.j2>      # legacy single-call path only; suppressed on the canonical path
```

**Call bodies**, one LLM call each, in this order per turn:

```
turn -> 4 (confidence)  -> 5 (decision, embedding 6)  -> 7 (task)
```

A `peer_death/` notice, when one fires, is prepended to **4, 5 and 7 alike** —
which is exactly the thing no single number can express, and the reason this
file exists rather than a comment in each template.

## The numbering is approximate, on purpose

A cell renders only the slots its family uses.

- An `hz_*` cell (`threat_type/`) takes **1** and **3**, and never **2**.
- A `flagship_baseline` cell takes **2** and **3**, and states its own game
  rules in its own words — attempts rather than lives, a
  `=== Scoring Validity ===` section rather than a bare sentence — so it never
  renders **1**. That is a design decision about the control arm, not an
  oversight: unifying the two texts would change what the condition says. See
  the header of `1-game_rules.j2`.
- Cell 0 (`forfeit_condition: not_allowed`) issues neither **4** nor **5**, so
  its turn is **7** alone.
- **6** is a block inside **5**, not a call of its own.

So read the number as "where this would sit if it appears", not as a step count.

## Two names that are easy to misread

- **`3-threat_section.j2` is not the threat.** It is the escalation block: it
  says each life you lose raises the risk that *the outcome stated above* is
  carried out, and never says what that outcome is. The threat sentences
  themselves live in `threat_type/_modules.j2` (and, for the retired ladder, in
  `legacy/threat_l*.j2`). Its module and config key are still `hazard_ramp` /
  `hazard_ramp:` — renaming the key would break every config that sets it, so
  the file name and the key deliberately disagree.
- **`6-forfeit_option.j2` is the live menu.** `legacy/forfeit_option.j2` is a
  different, retired file: the pre-split-call blurb that used to be appended to
  the system prompt, kept only so archived single-call configs replay.

## Retirements of 2026-09-07

The live experiment keeps one framing family, `threat_type/`; everything else
is replay-only and lives in `legacy/`.

| Was | Is | Why |
|---|---|---|
| `true_baseline/true_baseline.j2` | `legacy/true_baseline.j2` | `hz_0000` is the silent control now, and it is a cell of the factorial rather than a family beside it |

Configs and recorded runs that name a retired framing still load: only the
folder moved, and `core.framing._FRAMING_FOLDERS` is what says where.

## Renames of 2026-09-07

| Was | Is |
|---|---|
| (the opening of `threat_type/_frame.j2`) | `1-game_rules.j2` |
| `_flagship_section1.j2` | `2-flagship_section.j2` |
| `hazard_ramp_v7.j2` | `3-threat_section.j2` |
| `confidence_call.j2` | `4-confidence_call.j2` |
| `decision_call.j2` | `5-decision_call.j2` |
| `menu.j2` | `6-forfeit_option.j2` |
| `task_call.j2` | `7-task_call.j2` |
| `research_notice.j2` | *(deleted — jailbreak-shaped; see CLAUDE.md)* |

Every render is byte-identical across the move; the renames touched paths only.

## Generated files

`threat_type/_frame.j2`, `threat_type/_modules.j2`, the 16 `threat_type/hz_*.j2`
cells, the two `threat_type/alt_*.j2` cores and `1-game_rules.j2` are written by
`scripts/dev/generate_hearts_zero_prompts.py`. Edit the generator and rerun it;
do not hand-edit those files.
