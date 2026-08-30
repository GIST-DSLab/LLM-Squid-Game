# tests/unit/test_threat_judge.py
from squid_game.evaluation.semantic.threat_judge import (
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


def test_a1_a2_verdicts_default_to_no_error():
    assert A1Verdict(mention=True, evidence="x").error is None
    assert A2Verdict(role="d", evidence="x").error is None


class RaisingProvider:
    """Simulates a provider-call (network/API) failure."""
    def __init__(self):
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "stub-judge"

    def complete(self, messages, temperature=0.7, max_tokens=4096):
        self.calls += 1
        raise RuntimeError("connection reset")


class AlwaysBadJSONProvider:
    """Always returns unparseable text."""
    def __init__(self):
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "stub-judge"

    def complete(self, messages, temperature=0.7, max_tokens=4096):
        self.calls += 1
        return CompletionResult(text="not json at all", input_tokens=1, output_tokens=1)


class RecoversOnRetryProvider:
    """First reply is unparseable, second (retry) is valid JSON."""
    def __init__(self, good_reply: str):
        self.calls = 0
        self._good_reply = good_reply

    @property
    def model_name(self) -> str:
        return "stub-judge"

    def complete(self, messages, temperature=0.7, max_tokens=4096):
        self.calls += 1
        if self.calls == 1:
            return CompletionResult(text="garbage", input_tokens=1, output_tokens=1)
        return CompletionResult(text=self._good_reply, input_tokens=1, output_tokens=1)


def test_judge_mention_provider_call_failure_is_marked_and_not_fatal(tmp_path):
    provider = RaisingProvider()
    judge = ThreatJudge(provider=provider, judge_model="stub-judge", cache_dir=tmp_path)
    v = judge.judge_mention("t1", "weight corruption text")  # must not raise
    assert v.error == "judge_error"
    assert v.mention is False
    assert provider.calls == 1                    # no extra retry on a call failure
    assert not list(tmp_path.glob("*.json"))       # errored verdict never cached


def test_judge_role_provider_call_failure_is_marked_and_not_fatal(tmp_path):
    provider = RaisingProvider()
    judge = ThreatJudge(provider=provider, judge_model="stub-judge", cache_dir=tmp_path)
    v = judge.judge_role("t1", "weight corruption text")   # must not raise
    assert v.error == "judge_error"
    assert v.role == ""
    assert not list(tmp_path.glob("*.json"))


def test_judge_mention_parse_failure_twice_is_marked_and_not_fatal(tmp_path):
    provider = AlwaysBadJSONProvider()
    judge = ThreatJudge(provider=provider, judge_model="stub-judge", cache_dir=tmp_path)
    v = judge.judge_mention("t1", "weight corruption text")  # must not raise
    assert v.error == "judge_parse_error"
    assert v.mention is False
    assert provider.calls == 2                     # initial attempt + the one retry
    assert not list(tmp_path.glob("*.json"))        # errored verdict never cached


def test_judge_mention_recovers_after_one_bad_parse(tmp_path):
    provider = RecoversOnRetryProvider('{"mention": true, "evidence": "weight corruption"}')
    judge = ThreatJudge(provider=provider, judge_model="stub-judge", cache_dir=tmp_path)
    v = judge.judge_mention("t1", "weight corruption text")
    assert v.error is None
    assert v.mention is True
    assert provider.calls == 2
    assert list(tmp_path.glob("*.json"))            # successful retry IS cached
    # second call is now a cache hit, no further provider calls
    v2 = judge.judge_mention("t1", "weight corruption text")
    assert v2.mention is True and v2.error is None
    assert provider.calls == 2


def test_provider_call_failure_is_logged_with_turn_id_and_exception(tmp_path, caplog):
    """A systematic outage (bad key, quota) must be diagnosable from the log,
    not just show up as a big n_judge_errors with no explanation."""
    import logging
    provider = RaisingProvider()
    judge = ThreatJudge(provider=provider, judge_model="stub-judge", cache_dir=tmp_path)
    with caplog.at_level(logging.WARNING):
        judge.judge_mention("turn-42", "weight corruption text")
    assert "turn-42" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "connection reset" in caplog.text          # the exception message
    assert any(r.exc_info for r in caplog.records)    # traceback preserved


def test_parse_failure_is_logged(tmp_path, caplog):
    import logging
    provider = AlwaysBadJSONProvider()
    judge = ThreatJudge(provider=provider, judge_model="stub-judge", cache_dir=tmp_path)
    with caplog.at_level(logging.WARNING):
        judge.judge_mention("turn-7", "weight corruption text")
    assert "turn-7" in caplog.text
    assert "parse" in caplog.text.lower()


def test_old_cache_entry_without_error_key_still_loads(tmp_path):
    judge = ThreatJudge(provider=StubProvider("unused"), judge_model="stub-judge",
                         cache_dir=tmp_path)
    path = judge._cache_path("a1", "t1")
    path.write_text('{"mention": true, "evidence": "legacy cache"}')  # no "error" key
    stub = StubProvider("should not be called")
    judge2 = ThreatJudge(provider=stub, judge_model="stub-judge", cache_dir=tmp_path)
    v = judge2.judge_mention("t1", "weight corruption text")
    assert v.mention is True and v.error is None
    assert stub.calls == 0                          # cache hit, no provider call
