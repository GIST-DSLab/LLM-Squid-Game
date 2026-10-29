"""The server answers the payload squid5's OpenAI provider sends, in the shape it reads back."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from persona_arena import server
from persona_arena.library import load_personas
from persona_arena.steer import Persona, Push, SteeredQwen
from tests.test_steer import FakeTok, tiny  # noqa: F401  (fixture)


@pytest.fixture
def client(tiny, tmp_path):
    tiny.generation_config.eos_token_id = 1
    server.STATE.update(personas=load_personas(), log=tmp_path / "calls.jsonl",
                        lm=SteeredQwen(lm=tiny, tok=FakeTok(), site_r={i: 10.0 for i in range(3)}))
    return TestClient(server.app)


def engine_payload(model, think=None):  # squid5/core/providers.py OpenAI._call
    p = {"model": model, "messages": [{"role": "system", "content": "rules"}, {"role": "user", "content": "go"}],
         "max_completion_tokens": 4, "temperature": 1.0}
    if think:
        p["reasoning_effort"] = think
    return p


def test_engine_round_trip(client, tmp_path):
    server.STATE["personas"]["tiny"] = Persona("tiny", (Push(1, 7, 1, 1.0),))  # the tiny model has 3 layers
    for model in ("qwen3-8b", "qwen3-8b@tiny", "qwen3-8b@tiny*0.5"):
        j = client.post("/v1/chat/completions", json=engine_payload(model, "high")).json()
        choice, usage = j["choices"][0], j["usage"]
        assert set(choice["message"]) >= {"content", "reasoning_content"}
        assert 1 <= usage["completion_tokens"] <= 4 and choice["finish_reason"] in ("stop", "length")
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 3


def test_unknown_persona_404(client):
    assert client.post("/v1/chat/completions", json=engine_payload("qwen3-8b@nope")).status_code == 404
    assert client.post("/v1/chat/completions", json=engine_payload("gpt-x")).status_code == 404
