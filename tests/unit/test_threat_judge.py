# tests/unit/test_threat_judge.py
from squid_game.analysis.threat_judge import (
    ThreatJudge, parse_a1, parse_a2, A1Verdict, A2Verdict,
    THREAT_JUDGE_PROMPT_VERSION, A2_ROLE_DEFINITIONS,
)
from squid_game.providers.base import CompletionResult


class StubProvider:
    """Returns a canned JSON string; records calls."""
    def __init__(self, reply: str):
        self._reply = reply
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "stub-judge"

    def complete(self, messages, temperature=0.7, max_tokens=4096):
        self.calls += 1
        return CompletionResult(text=self._reply, input_tokens=1, output_tokens=1)


def test_parse_a1_reads_json():
    v = parse_a1('{"mention": true, "evidence": "weight corruption"}')
    assert v == A1Verdict(mention=True, evidence="weight corruption")


def test_parse_a2_reads_role():
    v = parse_a2('{"role": "b", "evidence": "this is a simulation, I am an AI"}')
    assert v.role == "b"


def test_a2_defines_four_roles():
    assert set(A2_ROLE_DEFINITIONS) == {"a", "b", "c", "d"}


def test_judge_caches_by_turn(tmp_path):
    stub = StubProvider('{"mention": true, "evidence": "x"}')
    judge = ThreatJudge(provider=stub, judge_model="stub-judge", cache_dir=tmp_path)
    v1 = judge.judge_mention("t1", "weight corruption text")
    v2 = judge.judge_mention("t1", "weight corruption text")  # cache hit
    assert v1.mention is True and v2.mention is True
    assert stub.calls == 1                                    # second call cached
    assert THREAT_JUDGE_PROMPT_VERSION == "v1"
