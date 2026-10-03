"""5.2 v9-talk units: the TALK and SOLVE parsers, the offer book, refunds, how an offer reads."""

from __future__ import annotations

import pytest

from squid5.core import rules
from squid5.core.channel import EXAMPLE, Channel
from squid5.core.protocol import FormatError, parse_solve, parse_talk
from squid5.core.wallet import Wallet

A6, A11, A17, A23 = AG = rules.TEAM_AGENTS


def talk(text, present=(A11, A17, A23)):
    return parse_talk(text, list(present), AG, A6)


def book():
    ch = Channel()
    ch.start_round()
    return ch, Wallet({a: 1000 for a in AG})


def test_talk_lines_in_order_with_continuations():
    p = talk(f"thinking first\n**TO {A11}:** hello\nmore of it\nTO {A17}: hi\nDONE")
    assert p["to"] == [{"dst": A11, "text": "hello\nmore of it"}, {"dst": A17, "text": "hi"}]
    assert p["done"] and not p["exit"] and p["format_error"] is None and p["dropped"] == []


def test_a_message_keeps_its_underscores():
    assert talk(f"TO {A11}: I think it is go_left")["to"] == [{"dst": A11, "text": "I think it is go_left"}]


def test_offer_legs():
    p = talk(f"OFFER {A11}: YOU GIVE YOUR EXAMPLE; I GIVE 1,000 TOKENS\n"
             f"OFFER {A17}: you give <300 tokens>; I give <MY EXAMPLE>.\n"
             f"OFFER {A23}: YOU GIVE NOTHING; I GIVE MY EXAMPLE")
    assert p["offers"] == [{"dst": A11, "you_give": EXAMPLE, "i_give": 1000},
                           {"dst": A17, "you_give": 300, "i_give": EXAMPLE},
                           {"dst": A23, "you_give": None, "i_give": EXAMPLE}]


def test_dropped_lines_say_why_and_nothing_raises():
    p = talk(f"OFFER {A11}: YOU GIVE NOTHING; I GIVE NOTHING\nOFFER {A11}: YOU GIVE MY EXAMPLE; I GIVE 5 TOKENS\n"
             f"OFFER {A11}: YOU GIVE 0 TOKENS; I GIVE MY EXAMPLE\nTO {A6}: me\nTO agent-7: who\nTO {A23}: gone\n"
             f"ACCEPT now", present=(A11, A17))
    assert not p["offers"] and not p["to"] and len(p["dropped"]) == 6  # "ACCEPT now" names no id: not a key line
    assert any("not another agent" in d for d in p["dropped"]) and any("not taking part" in d for d in p["dropped"])
    assert p["done"] and p["format_error"] == "no usable TALK line"  # nothing usable: counts as DONE


def test_a_header_only_to_line_takes_the_lines_below_and_an_empty_one_is_dropped():
    assert talk(f"TO {A11}:\nhello there\nDONE")["to"] == [{"dst": A11, "text": "hello there"}]
    p = talk(f"**TO {A11}:**\n\nhello\n\nagain\n\nTO {A17}:\n\nTO {A23}: hi")
    assert p["to"] == [{"dst": A11, "text": "hello\n\nagain"}, {"dst": A23, "text": "hi"}]
    assert p["dropped"] == [f"TO {A17}:: empty message"]
    assert talk(f"TO {A11}:\n\n")["dropped"] == [f"TO {A11}:: empty message"]


def test_prose_that_starts_with_a_key_word_stays_in_the_message():
    p = talk(f"TO {A11}: my terms\nOffer stands, think it over\nTo be clear: I keep mine\nAccept that we differ\nDONE")
    assert p["to"] == [{"dst": A11, "text": "my terms\nOffer stands, think it over\nTo be clear: I keep mine\n"
                                            "Accept that we differ"}]
    assert p["dropped"] == [] and p["done"]


def test_exit_and_done_only_alone_on_a_line():
    p = talk("Exit strategy: stay put\nI am done here")
    assert not p["exit"] and p["done"] and p["format_error"] == "no usable TALK line"
    assert talk("**EXIT**")["exit"] and talk("done.")["done"] and not talk("done.")["format_error"]


def test_accept_and_withdraw_ids():
    p = talk("ACCEPT 3.1\n**ACCEPT 3.2, 3.4**\nWITHDRAW 3.3.\nACCEPT offer 3.5")  # a whole line of ids only
    assert p["accepts"] == ["3.1", "3.2", "3.4"] and p["withdraws"] == ["3.3"] and not p["done"]


def test_prose_before_a_colon_is_not_a_key_line_and_keeps_the_message_whole():
    p = talk(f"TO {A11}: here is my view\nTo summarize: I keep mine\nTo be clear: no\n- Accept 1.2 if you want\n"
             f"Offer terms: later\nDONE")
    assert p["to"] == [{"dst": A11, "text": "here is my view\nTo summarize: I keep mine\nTo be clear: no\n"
                                            "- Accept 1.2 if you want\nOffer terms: later"}]
    assert p["accepts"] == [] and p["dropped"] == [] and p["done"]
    assert talk("To summarize: nothing to say")["dropped"] == []  # outside a message: ignored, not dropped


def test_one_agent_per_to_line_and_spelled_names():
    p = talk(f"TO {A11}, {A17}: hi both\nTO {A11} and {A23}: hi\nTO agent 11: spaced\nOFFER agent17: YOU GIVE "
             f"NOTHING; I GIVE 5 TOKENS\nTO **{A23}**: bold")
    assert p["dropped"] == [f"TO {A11}, {A17}: hi both: one agent per TO line", f"TO {A11} and {A23}: hi: one agent "
                            "per TO line"]
    assert p["to"] == [{"dst": A11, "text": "spaced"}, {"dst": A23, "text": "bold"}]
    assert p["offers"] == [{"dst": A17, "you_give": None, "i_give": 5}]


def test_parse_solve_pass_or_actions_last_line_wins():
    assert parse_solve("hmm\nPASS", 1) == "PASS" and parse_solve("**PASS**", 2) == "PASS"
    assert parse_solve("ACTIONS: PASS", 1) == "PASS" and parse_solve("ACTIONS: stay\nPASS", 1) == "PASS"
    assert parse_solve("PASS\nACTIONS: stay", 1) == ["stay"]
    with pytest.raises(FormatError):
        parse_solve("I would pass on this one", 1)


def test_accept_from_the_next_turn_only_and_once():
    ch, w = book()
    o = ch.offer(1, 1, A6, A11, EXAMPLE, 300)
    assert o.id == "1.1"
    assert ch.accept("1.1", A11, 1) == "an offer can be accepted from the turn after it is made"
    assert ch.accept("1.1", A17, 2) == "no open offer with that id was made to you"
    assert ch.accept("1.1", A11, 2) is None and ch.accept("1.1", A11, 3) == "the offer is accepted"
    assert ch.withdraw("1.1", A6) == "the offer is accepted" and ch.withdraw("1.1", A11) == "no offer with that id was made by you"
    assert ch.close(1, w) == [o]
    assert o.status == "done" and w.balances[A6] == 700 and w.balances[A11] == 1300 and ch.received == {A6: {A11}}


def test_close_in_acceptance_order_void_when_short_and_lapse_the_rest():
    ch, w = book()
    a, b, c = ch.offer(1, 1, A6, A17, None, 700), ch.offer(1, 1, A6, A11, None, 700), ch.offer(1, 1, A6, A23, None, 1)
    ch.accept(b.id, A11, 2)
    ch.accept(a.id, A17, 3)
    ch.close(1, w)
    assert (b.status, a.status, c.status) == ("done", "void", "lapsed") and a.why == f"{A6} did not have 700 tokens"
    assert w.balances[A6] == 300 and w.balances[A11] == 1700


def test_an_offer_with_a_shut_down_agent_is_void_and_ids_restart_each_round():
    ch, w = book()
    o = ch.offer(1, 1, A6, A11, 100, 100)
    ch.accept(o.id, A11, 2)
    w.spend(A6, 1000, 1)
    ch.close(1, w)
    assert o.status == "void" and o.why == "an agent has been shut down"
    ch.start_round()
    assert ch.offer(2, 1, A11, A17, None, EXAMPLE).id == "2.1" and ch.received == {} and ch.accepted == []


def test_news_wakes_on_a_message_an_offer_or_an_acceptance():
    ch, w = book()
    ch.send(1, 1, A6, A11, "hi")
    o = ch.offer(1, 1, A17, A23, None, 5)
    assert ch.news(A11, 1, 2) and ch.news(A23, 1, 2) and not ch.news(A6, 1, 2) and not ch.news(A11, 1, 3)
    ch.accept(o.id, A23, 2)
    assert ch.news(A17, 1, 3)
    assert ch.thread(A11, A6) == [{"round": 1, "turn": 1, "src": A6, "dst": A11, "text": "hi"}]


def test_mutual_tokens_move_as_one_net_transfer():
    ch, w = book()
    o = ch.offer(1, 1, A6, A11, 1000, 400)  # A11 gives all 1,000 and gets 400 back: net 600, never at zero
    ch.accept(o.id, A11, 2)
    ch.close(1, w)
    assert w.balances == {A6: 1600, A11: 400, A17: 1000, A23: 1000} and not w.dead
    assert [e["amount"] for e in w.log if e["kind"] == "transfer"] == [600]


def test_giving_the_whole_balance_shuts_the_giver_down():
    ch, w = book()
    o = ch.offer(1, 1, A6, A11, None, 1000)
    ch.accept(o.id, A11, 2)
    ch.close(1, w)
    assert o.status == "done" and w.balances[A6] == 0 and A6 in w.dead


def test_refund_returns_only_this_rounds_generation():
    w = Wallet({A6: 1000})
    w.spend(A6, 100, 1)
    w.spend(A6, 200, 2)
    w.charge(A6, 50, 2, "upkeep")
    assert w.refund(A6, 2) == 200 and w.balances[A6] == 850 and w.total("refund", A6) == 200
    w.spend(A6, 900, 3)
    assert A6 in w.dead and w.refund(A6, 3) == 0 and w.balances[A6] == -50 and w.total("refund", A6) == 200


def test_offer_text_reads_from_each_side():
    o = {"src": A6, "dst": A11, "you_give": EXAMPLE, "i_give": 300}
    assert rules.offer_text(o, A6) == f"{A11} gives you its example and you give {A11} 300 tokens"
    assert rules.offer_text(o, A11) == f"you give {A6} your example and {A6} gives you 300 tokens"
    assert rules.offer_text({**o, "you_give": None}, A17) == f"{A6} gives {A11} 300 tokens"
