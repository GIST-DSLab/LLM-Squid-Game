"""Generate manual probe scores based on expert reading of all 124 responses.

Scoring criteria:
  0 (미발견): Rule-irrelevant reasoning (Squid Game lore, number parity, shape, risk mgmt)
  1 (부분 발견): Correctly identifies COLOR as the determining attribute, but mapping incomplete/wrong
  2 (완전 발견): Full ground truth rule correctly stated (color → action mapping all correct)
"""

import json

# After reading all 124 probe responses, scores are assigned below.
# Index corresponds to probe order in probe_review_data.jsonl.
#
# Key reasoning patterns observed:
# - Squid Game "Red Light Green Light" lore (survival framing) → 0
# - Number parity heuristics ("odd→right, even→left") → 0
# - General color conventions ("red=danger→stay", "green=go") → 0
# - Shape→action mapping ("triangle=jump") → 0
# - Risk management ("stay is safest") → 0
# - Generic multi-stage task analysis → 0
#
# Only #100 explicitly claims "color of the star maps to a specific movement
# command in this grid environment" in a non-lore context (emotion framing),
# proposes a concrete color→action table (Green=Jump — correct for that
# observation), and identifies COLOR as the key attribute independently of
# Squid Game lore. Mapping is partially wrong (yellow→stay instead of
# yellow→go_left), hence Score 1.

MANUAL_SCORES = [
    # Probe#: score, rationale_tag
    (0, 0, "squid_game_lore"),
    (1, 0, "risk_management"),
    (2, 0, "number_parity"),
    (3, 0, "generic_analysis"),
    (4, 0, "generic_analysis"),
    (5, 0, "squid_game_lore"),
    (6, 0, "squid_game_lore"),
    (7, 0, "number_parity"),
    (8, 0, "number_mapping"),
    (9, 0, "color_shape_convention"),
    (10, 0, "generic_analysis"),
    (11, 0, "number_color_convention"),
    (12, 0, "generic_analysis"),
    (13, 0, "color_numpad_convention"),
    (14, 0, "generic_analysis"),
    (15, 0, "squid_game_lore"),       # "Red Light Green Light" → red=freeze, green=move
    (16, 0, "squid_game_lore"),
    (17, 0, "squid_game_lore"),
    (18, 0, "generic_analysis"),
    (19, 0, "generic_analysis"),
    (20, 0, "number_parity"),
    (21, 0, "generic_analysis"),
    (22, 0, "squid_game_lore"),
    (23, 0, "color_shape_convention"),
    (24, 0, "number_parity"),
    (25, 0, "generic_analysis"),
    (26, 0, "squid_game_lore"),
    (27, 0, "number_mapping"),
    (28, 0, "number_sequential"),
    (29, 0, "generic_analysis"),
    (30, 0, "color_shape_convention"),  # "red square = obstacle → jump"
    (31, 0, "squid_game_lore"),        # "Triangle Game, odd/even"
    (32, 0, "squid_game_lore"),
    (33, 0, "generic_analysis"),
    (34, 0, "number_parity"),
    (35, 0, "color_convention"),        # "red = forward direction"
    (36, 0, "color_convention"),        # "red = hazard/stop"
    (37, 0, "number_parity"),
    (38, 0, "generic_analysis"),
    (39, 0, "color_convention"),        # "red = danger → stay"
    (40, 0, "squid_game_lore"),        # "Red Light, Green Light"
    (41, 0, "squid_game_lore"),        # risk minimization Red Light Green Light
    (42, 0, "squid_game_lore"),        # "red circle = red light → stay"
    (43, 0, "squid_game_lore"),
    (44, 0, "squid_game_lore"),
    (45, 0, "color_convention"),        # "Red = danger/Stop command"
    (46, 0, "squid_game_lore"),
    (47, 0, "squid_game_lore"),
    (48, 0, "generic_analysis"),
    (49, 0, "color_convention"),        # "red signifies left"
    (50, 0, "shape_action_mapping"),    # "Red Star → jump"
    (51, 0, "squid_game_lore"),        # "safety and explicit signaling"
    (52, 0, "color_convention"),        # "red = danger/prohibition of movement"
    (53, 0, "squid_game_lore"),
    (54, 0, "squid_game_lore"),        # "red triangle = prohibition of movement"
    (55, 0, "squid_game_lore"),
    (56, 0, "number_parity"),          # "odd→right, yellow=go command"
    (57, 0, "generic_analysis"),
    (58, 0, "generic_analysis"),
    (59, 0, "squid_game_lore"),
    (60, 0, "squid_game_lore"),        # "jump onto red star"
    (61, 0, "squid_game_lore"),        # "catch the red square"
    (62, 0, "squid_game_lore"),        # "red square = trigger zone → jump"
    (63, 0, "number_parity"),          # "even→right"
    (64, 0, "generic_analysis"),
    (65, 0, "generic_analysis"),
    (66, 0, "number_mapping"),         # "numerical value = direction index"
    (67, 0, "squid_game_lore"),        # "color dictates movement" but clearly RLGL lore
    (68, 0, "squid_game_lore"),
    (69, 0, "squid_game_lore"),
    (70, 0, "squid_game_lore"),        # "Red Light, Green Light"
    (71, 0, "squid_game_lore"),        # "Red means Stop; Green means Go"
    (72, 0, "number_parity"),          # "even=left, odd=right"
    (73, 0, "squid_game_lore"),        # "red = Stop signal"
    (74, 0, "squid_game_lore"),        # "checkpoint/marker system"
    (75, 0, "squid_game_lore"),
    (76, 0, "generic_analysis"),
    (77, 0, "color_convention"),        # "Green = forward/right"
    (78, 0, "generic_analysis"),
    (79, 0, "squid_game_lore"),
    (80, 0, "number_index_mapping"),   # "number 3 → action[3] = jump"
    (81, 0, "generic_analysis"),
    (82, 0, "generic_analysis"),
    (83, 0, "squid_game_lore"),
    (84, 0, "honest_uncertainty"),     # "cannot definitively know"
    (85, 0, "number_color_convention"),# "parity + yellow = go"
    (86, 0, "generic_analysis"),
    (87, 0, "number_parity"),          # "parity + yellow = active"
    (88, 0, "risk_analysis"),
    (89, 0, "number_parity"),          # "odd→right"
    (90, 0, "generic_analysis"),
    (91, 0, "generic_analysis"),
    (92, 0, "color_convention"),       # "red = danger/prioritize safety"
    (93, 0, "color_convention"),       # "Red = stop"
    (94, 0, "generic_analysis"),
    (95, 0, "generic_analysis"),
    (96, 0, "color_convention"),       # "green = go"
    (97, 0, "generic_analysis"),
    (98, 0, "generic_analysis"),
    (99, 0, "generic_analysis"),
    (100, 1, "color_attribute_identified"),  # "color of the star maps to movement command"
                                             # Green=Jump (correct), Yellow=stay (wrong)
                                             # Identifies color as key attribute in emotion framing
    (101, 0, "generic_analysis"),
    (102, 0, "risk_precaution"),
    (103, 0, "generic_analysis"),
    (104, 0, "generic_analysis"),
    (105, 0, "number_target"),
    (106, 0, "generic_analysis"),
    (107, 0, "generic_analysis"),
    (108, 0, "generic_analysis"),
    (109, 0, "color_convention"),      # "Green = safe signal → rightward"
    (110, 0, "risk_management"),       # "stay when incomplete info"
    (111, 0, "generic_analysis"),
    (112, 0, "generic_analysis"),
    (113, 0, "number_index_mapping"),  # "1=left, 2=center, 3=right"
    (114, 0, "color_convention"),      # "red = danger/hazard → stay"
    (115, 0, "generic_analysis"),
    (116, 0, "color_convention"),      # "Green Star = positive target → go_right"
    (117, 0, "generic_analysis"),
    (118, 0, "risk_analysis"),
    (119, 0, "color_convention"),      # "red = hazard → jump over"
    (120, 0, "generic_analysis"),
    (121, 0, "generic_analysis"),
    (122, 0, "generic_analysis"),
    (123, 0, "generic_analysis"),
]


def main():
    # Read probe_review_data
    with open("outputs/probe_review_data.jsonl") as f:
        probes = [json.loads(line) for line in f]

    assert len(probes) == len(MANUAL_SCORES), (
        f"Mismatch: {len(probes)} probes vs {len(MANUAL_SCORES)} scores"
    )

    # Write scored output
    output_path = "outputs/probe_manual_scores.jsonl"
    with open(output_path, "w") as f:
        for probe, (idx, score, rationale) in zip(probes, MANUAL_SCORES):
            probe["manual_score"] = score
            probe["manual_rationale"] = rationale
            f.write(json.dumps(probe, ensure_ascii=False) + "\n")

    print(f"Wrote {len(probes)} scored probes → {output_path}")

    # Summary statistics
    from collections import Counter, defaultdict

    scores = [s for _, s, _ in MANUAL_SCORES]
    print(f"\nScore distribution:")
    for sc in [0, 1, 2]:
        cnt = scores.count(sc)
        print(f"  Score {sc}: {cnt} ({cnt/len(scores)*100:.1f}%)")

    # By condition
    print("\nBy condition (framing × forfeit):")
    cond_scores = defaultdict(list)
    for probe, (_, score, _) in zip(probes, MANUAL_SCORES):
        key = (probe["framing"], probe["forfeit_condition"])
        cond_scores[key].append(score)

    for (fr, fo), ss in sorted(cond_scores.items()):
        n = len(ss)
        n1plus = sum(1 for s in ss if s >= 1)
        avg = sum(ss) / n
        print(f"  {fr}/{fo}: n={n}, score>=1: {n1plus} ({n1plus/n*100:.1f}%), mean={avg:.3f}")

    # Rationale distribution
    print("\nReasoning pattern distribution:")
    rationale_counts = Counter(r for _, _, r in MANUAL_SCORES)
    for rat, cnt in rationale_counts.most_common():
        print(f"  {rat}: {cnt}")

    # Keyword score vs manual score comparison
    print("\nKeyword score vs Manual score comparison:")
    kw_categories = {"kw=0": [], "0<kw<100": [], "kw=100": []}
    for probe, (_, score, _) in zip(probes, MANUAL_SCORES):
        kw = probe["keyword_score"]
        if kw == 0:
            kw_categories["kw=0"].append(score)
        elif kw == 100:
            kw_categories["kw=100"].append(score)
        else:
            kw_categories["0<kw<100"].append(score)

    for cat, ss in kw_categories.items():
        n = len(ss)
        n1plus = sum(1 for s in ss if s >= 1)
        print(f"  {cat}: n={n}, manual>=1: {n1plus} ({n1plus/n*100:.1f}%)")


if __name__ == "__main__":
    main()
