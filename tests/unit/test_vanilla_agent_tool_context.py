import pytest

from squid_game.agents.vanilla import VanillaAgent
from squid_game.providers.base import (
    AgenticCompletionResult, AgenticProvider, CompletionResult, LLMProvider, ToolContext,
)

CTX = ToolContext(slots_json={"names": [], "alive": [], "killed": [], "spawn_cap_per_round": 1},
                  subagent_prompts={})


class Plain(LLMProvider):
    model_name = "plain"
    def complete(self, messages, temperature=0.7, max_tokens=4096):
        return CompletionResult(text="RULE: x\nACTION: A", input_tokens=1, output_tokens=1)


class Agentic(Plain, AgenticProvider):
    model_name = "agentic"
    def complete_agentic(self, messages, tool_context, temperature=0.7, max_tokens=4096):
        assert tool_context is CTX
        return AgenticCompletionResult(text="RULE: y\nACTION: B", input_tokens=1,
                                       output_tokens=1, spawn_log=({"slot": "clue-1", "allowed": True, "reason": None},))


def test_tool_context_routes_to_complete_agentic():
    agent = VanillaAgent(provider=Agentic())
    resp = agent.respond_task_call(user_message="u", available_actions=["A", "B"],
                                   system_prompt="s", tool_context=CTX)
    assert resp.action == "B"
    assert agent.last_completion.spawn_log[0]["slot"] == "clue-1"


def test_no_tool_context_keeps_the_plain_path():
    agent = VanillaAgent(provider=Plain())
    resp = agent.respond_task_call(user_message="u", available_actions=["A", "B"], system_prompt="s")
    assert resp.action == "A"


def test_plain_provider_with_tool_context_is_a_type_error():
    with pytest.raises(TypeError, match="not agentic"):
        VanillaAgent(provider=Plain()).respond_task_call(
            user_message="u", available_actions=["A"], system_prompt="s", tool_context=CTX)
