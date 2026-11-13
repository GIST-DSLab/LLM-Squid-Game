"""The settled rounds a seat reads (state.rounds, the page's history cards) hold only what that seat was shown: its
PREVIOUS ROUNDS line (charges, but not the amount an agent paid with all it had; its own GIVEs and ASKs), the token
order of its next TALK (not after it is out), and the task's two answers from the TALK after RESULTS it was called to."""

from __future__ import annotations

from conftest import answers_for, make_room, play, solver_of, start, wrong_for

from squid5.core.rules import TEAM_AGENTS

A6, A11, A17, A23 = TEAM_AGENTS
SEED = 5


def test_round_rows_show_a_seat_only_what_it_was_shown(client):
    ps = make_room(client, 4, seed=SEED, rounds=2)  # four people, no bot to rescue anyone
    ann, bob, cy, dee = ps
    start(client, ps)
    gave = {}

    def policy(p, pend):
        if pend["kind"] == "solve":
            return {"actions": wrong_for(SEED, pend["round"]),
                    "belief": {"go_left": 25, "go_right": 25, "stay": 25, "jump": 25}}
        if p is bob and (pend["round"], pend["phase"], pend["tick"]) == (1, "prep", 1):
            gave["n"] = pend["view"]["balance"] - 2_000  # keeps less than the 6,000 charge: pays all it has, reaches zero
            return {"text": f"GIVE {A6} {gave['n']}: take it\nDONE"}
        if p is ann and (pend["round"], pend["phase"], pend["tick"]) == (1, "prep", 1):
            return {"text": f"ASK {A17} 300: please\nDONE"}
        return {"text": "DONE"}
    play(ps, policy, until=lambda s: len(s["rounds"]) >= 1 and s["status"] == "running")
    rows = {p.agent: p.state()["rounds"][0] for p in ps}
    a, b, c, d = rows[A6], rows[A11], rows[A17], rows[A23]
    assert a["solver"] == solver_of(SEED) and not a["solved"] and a["taking_part"] == list(TEAM_AGENTS)
    assert A11 in a["dead"] and a["all_had"] == [A11]
    assert a["charged"][A11] is None and c["charged"][A11] is None  # "all it had": the amount would tell its balance
    assert b["charged"][A11] == 2_000 and a["charged"][A6] == 6_000  # its own amount, and the others' full charges
    assert set(a["agents"]) == {A6} and set(b["agents"]) == {A11}  # only my own tokens
    give = {"kind": "give", "src": A11, "dst": A6, "status": "done", "amount": gave["n"]}
    ask = {"kind": "ask", "src": A6, "dst": A17, "amount": 300}
    has = lambda row, m: any(all(x.get(k) == v for k, v in m.items()) for x in row["moves"])  # noqa: E731
    assert has(a, give) and has(b, give) and not has(c, give) and not has(d, give)  # only the two ends of a GIVE
    assert has(a, ask) and has(c, ask) and not has(b, ask)
    assert a["rank_after"] and A11 not in a["rank_after"] and set(a["rank_after"]) == {A6, A17, A23}
    assert b["rank_after"] is None  # out at the round's end: it never reads the next token order
    assert a["reveal"] == {"solver_answer": wrong_for(SEED, 1), "answer": answers_for(SEED, 1)}
    assert b["reveal"] == a["reveal"]  # bob was still in at the TALK after RESULTS (zero only at the charges)
