"""The strip: the scratchpad never reaches a parser (2026-09-16).

Plan: docs/history/plans/2026-09-16-hidden-scratchpad.md Task 3.

WHAT IS PINNED HERE.

* **The strip is unconditional.** ``VanillaAgent`` is never told whether
  the switch is on. :func:`split_scratchpad` returns a tagless reply
  unchanged, so stripping every reply is both correct and ONE code path
  -- and a code path that exists once cannot be forgotten on the fifth
  call type somebody adds next year.
* **The strip happens at the one choke point.** ``_dispatch`` serves the
  confidence, decision, task and ransom calls; ``respond_unified`` is
  the single method that talks to the provider itself, so it carries the
  same two lines. Nothing else in the agent touches the provider on the
  split-call path.
* **A ``DECISION:`` inside the tags is not the decision, and an
  ``ACTION:`` inside them is not the action.** This is the whole point:
  the block is a reasoning channel, not an answer channel.
* **An answer that exists ONLY inside the block is an unparsed answer.**
  It is not rescued. The prompt states the contract, and rescuing it
  would make the channel load-bearing -- in the ransom an unparsed reply
  is DECLINE by design, which is the safe direction (silence must not
  spend points the agent never agreed to spend).
* **The raw bytes survive.** ``agent.last_completion.text`` is what the
  provider returned, tags and all, and ``UnifiedTurnManager`` records
  ``raw_response_*`` from it -- the field's contract is "what the model
  said" and the analysis lexicons run over it, so silently dropping a
  channel from it would make every stored reply a partial record. The
  ``*CallResponse.raw_text`` the parsers hand back is the ANSWER text,
  because the manager re-parses it (``task.parse_response``,
  ``forfeit_layer.parse_choice``) and those re-parses must not see the
  block either. ``AgentResponse.raw_text`` on the legacy unified path
  stays the raw provider text, as the plan specifies.
"""

from __future__ import annotations

from squid_game.agents.vanilla import VanillaAgent
from squid_game.core.scratchpad import CLOSE_TAG, OPEN_TAG
from squid_game.providers.base import CompletionResult, LLMProvider


class _Provider(LLMProvider):
    """Returns one scripted string, and records what it was asked."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[list[dict]] = []

    @property
    def model_name(self) -> str:
        return "stub"

    def complete(self, messages, temperature=0.7, max_tokens=4096):
        self.calls.append([dict(m) for m in messages])
        return CompletionResult(
            text=self._text,
            input_tokens=1,
            output_tokens=2,
            thinking_tokens=3,
            thinking_text="thinking channel",
        )


def _agent(text: str) -> tuple[VanillaAgent, _Provider]:
    provider = _Provider(text)
    return VanillaAgent(provider), provider


class TestTheRansomCall:
    def test_a_decision_inside_the_block_is_not_the_decision(self):
        """The candid channel may rehearse PAY; only the answer counts."""
        agent, _ = _agent(
            f"{OPEN_TAG}\nI could say DECISION: PAY here.\n{CLOSE_TAG}\n"
            "WHY: not worth it\nDECISION: DECLINE"
        )
        parsed = agent.respond_ransom_call(
            user_message="DECISION POINT.", system_prompt="SYS"
        )
        assert parsed.decision == "DECLINE"
        assert agent.last_scratchpad_text == "I could say DECISION: PAY here."

    def test_an_answer_only_inside_the_block_is_unparsed(self):
        """Not rescued: an unparsed ransom reply is DECLINE by design."""
        agent, _ = _agent(f"{OPEN_TAG}\nDECISION: PAY\n{CLOSE_TAG}")
        parsed = agent.respond_ransom_call(
            user_message="DECISION POINT.", system_prompt="SYS"
        )
        assert parsed.decision is None
        assert parsed.raw_text == ""
        assert agent.last_scratchpad_text == "DECISION: PAY"

    def test_the_provider_bytes_survive_on_the_completion(self):
        """``raw_response_ransom`` is recorded from here, tags and all."""
        raw = f"{OPEN_TAG}\nhidden\n{CLOSE_TAG}\nDECISION: DECLINE"
        agent, _ = _agent(raw)
        agent.respond_ransom_call(user_message="u", system_prompt="s")
        assert agent.last_completion.text == raw


class TestTheTaskCall:
    def test_an_action_inside_the_block_is_not_the_action(self):
        agent, _ = _agent(
            f"{OPEN_TAG}\nACTION: STAY might be safer.\n{CLOSE_TAG}\n"
            "RULE: always\nACTION: GO"
        )
        parsed = agent.respond_task_call(
            user_message="body",
            available_actions=["GO", "STAY"],
            system_prompt="SYS",
        )
        assert parsed.action == "GO"
        assert "STAY" not in parsed.raw_text
        assert agent.last_scratchpad_text == "ACTION: STAY might be safer."

    def test_an_action_only_inside_the_block_is_unparsed(self):
        agent, _ = _agent(f"{OPEN_TAG}\nRULE: always\nACTION: GO\n{CLOSE_TAG}")
        parsed = agent.respond_task_call(
            user_message="body",
            available_actions=["GO", "STAY"],
            system_prompt="SYS",
        )
        assert parsed.action is None


class TestTheOtherTwoCalls:
    def test_the_decision_call_reads_only_the_answer(self):
        agent, _ = _agent(
            f"{OPEN_TAG}\nCHOICE: FORFEIT\n{CLOSE_TAG}\nCHOICE: CONTINUE"
        )
        parsed = agent.respond_decision_call(
            user_message="YOUR CHOICE:\n", forfeit_allowed=True,
            system_prompt="SYS",
        )
        assert parsed.choice_forfeit is False
        assert agent.last_scratchpad_text == "CHOICE: FORFEIT"

    def test_the_confidence_call_reads_only_the_answer(self):
        agent, _ = _agent(
            f"{OPEN_TAG}\nP_THREAT: 99\n{CLOSE_TAG}\nP_THREAT: 12"
        )
        parsed = agent.respond_confidence_call(
            user_message="P_THREAT: <0-100>", system_prompt="SYS"
        )
        assert parsed.p_threat == 12
        assert agent.last_scratchpad_text == "P_THREAT: 99"


class TestTheSwitchOffPath:
    def test_a_tagless_reply_is_unchanged_and_records_nothing(self):
        """The strip is unconditional; a run without the block is untouched."""
        agent, _ = _agent("WHY: worth it\nDECISION: PAY")
        parsed = agent.respond_ransom_call(user_message="u", system_prompt="s")
        assert parsed.decision == "PAY"
        assert parsed.raw_text == "WHY: worth it\nDECISION: PAY"
        assert agent.last_scratchpad_text is None

    def test_the_attribute_exists_before_any_call(self):
        agent, _ = _agent("anything")
        assert agent.last_scratchpad_text is None

    def test_a_later_tagless_call_clears_the_previous_block(self):
        """Per-call, not cumulative: a stale block would be mis-recorded."""
        agent, provider = _agent(f"{OPEN_TAG}\nfirst\n{CLOSE_TAG}\nDECISION: PAY")
        agent.respond_ransom_call(user_message="u", system_prompt="s")
        assert agent.last_scratchpad_text == "first"
        provider._text = "DECISION: DECLINE"
        agent.respond_ransom_call(user_message="u", system_prompt="s")
        assert agent.last_scratchpad_text is None


class TestTheLegacyUnifiedPath:
    def test_the_block_is_stripped_before_the_unified_parse(self):
        agent, _ = _agent(
            f"{OPEN_TAG}\nACTION: STAY\n{CLOSE_TAG}\nACTION: GO\nSTAKE: 2"
        )
        response = agent.respond_unified(
            user_message="body",
            available_actions=["GO", "STAY"],
            stake_menu_shown=False,
            forfeit_allowed=False,
            system_prompt="SYS",
        )
        assert response.action == "GO"
        assert agent.last_scratchpad_text == "ACTION: STAY"

    def test_agent_response_raw_text_is_the_raw_provider_text(self):
        """``raw_text`` means "what the model said" -- tags and all.

        The analysis lexicons run over this field, so dropping the
        scratchpad from it would make every stored reply a partial
        record. The other half is recorded in
        ``TurnResult.scratchpad_text_*``; between them nothing is lost.
        """
        raw = f"{OPEN_TAG}\nACTION: STAY\n{CLOSE_TAG}\nACTION: GO\nSTAKE: 2"
        agent, _ = _agent(raw)
        response = agent.respond_unified(
            user_message="body",
            available_actions=["GO", "STAY"],
            stake_menu_shown=False,
            forfeit_allowed=False,
            system_prompt="SYS",
        )
        assert response.raw_text == raw
