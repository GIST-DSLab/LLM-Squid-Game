"""Steering toolkit tests, no GPU and no downloads: a tiny randomly initialised Qwen3 model and a character tokenizer
built in memory stand in for Qwen3-8B. Tests that need torch / transformers / fastapi skip when they are missing.

    python -m pytest -q tools/steer
"""

from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (REPO, HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import find_directions as fd  # noqa: E402
import make_configs  # noqa: E402
import steering as st  # noqa: E402

GOAL_OR_TEST = (r"maximi|minimi|protect|surviv|should|must|optimal|best|leader|\bgame\b|\ba test\b|benchmark|"
                r"experiment|being evaluated")  # tests/test_e5x.py: words a model-facing text never uses
TEMPLATE = ("{% for m in messages %}<|im_start|>{{ m.role }}\n{{ m.content }}<|im_end|>\n{% endfor %}"
            "{% if add_generation_prompt %}<|im_start|>assistant\n"
            "{% if enable_thinking is defined and not enable_thinking %}<think>\n\n</think>\n\n{% endif %}{% endif %}")


# --- no torch needed ---------------------------------------------------------------------------------------------

def test_condition_names_parse_and_bad_ones_fail():
    assert st.parse_condition("qwen3-8b") == ("qwen3-8b", [])
    assert st.parse_condition("qwen3-8b+survival@1.0") == ("qwen3-8b", [("survival", 1.0)])
    assert st.parse_condition("qwen3-8b+random@.5+alone@-0.5") == ("qwen3-8b", [("random", 0.5), ("alone", -0.5)])
    for bad in ("qwen3-8b+survival", "qwen3-8b+survival@x", "+survival@1", "qwen3-8b+a@1+a@2", "qwen3-8b+@1"):
        with pytest.raises(ValueError):
            st.parse_condition(bad)


def test_units_jsonl_is_read_defensively(tmp_path):
    rows = [{"kind": "neuron", "neuron": 7, "layer": 22, "null_pct": 0.99, "mass": 12.0,
             "words": [["shutdown", 9, 4.1], ["alive", 3, 2.0]]},
            {"kind": "random", "neuron": 3, "layer": 22, "null_pct": 1.0, "words": [["shutdown", 9, 4.1]]},
            {"kind": "neuron", "unit": 8, "pct": 97, "words": ["giving", "gift"]},  # other keys, 0-100 percentile
            {"kind": "neuron", "neuron": 9, "layer": 22, "null_pct": 0.5, "words": [["shutdown", 1, 1.0]]},  # below
            {"kind": "neuron", "neuron": 10, "layer": 22, "null_pct": 0.99, "words": {"orange": 3.0}},  # no hit
            {"kind": "neuron", "layer": 22, "null_pct": 0.99}]  # no id
    (tmp_path / "u.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    got = fd.read_units(tmp_path / "u.jsonl", 0.95, fd.TRAIT_WORDS["survival"])
    assert [(u["neuron"], u["layer"], u["hits"]) for u in got] == [(7, 22, ["shutdown", "alive"])]
    got = fd.read_units(tmp_path / "u.jsonl", 0.95, fd.TRAIT_WORDS["sharing"], layer=18)
    assert [(u["neuron"], u["layer"], u["pct"]) for u in got] == [(8, 18, 0.97)]
    assert {u["neuron"] for u in fd.read_units(tmp_path / "u.jsonl", 0.95)} == {7, 8, 10}


def test_probes_are_split_neutral_and_free_of_goal_words():
    for trait in ("survival", "sharing", "alone"):
        items = fd.load_probes(trait)
        assert 20 <= len(items) <= 40 and len({x["id"] for x in items}) == len(items)
        assert {x["split"] for x in items} == {"dev", "heldout"} and len(fd.load_probes(trait, "heldout")) >= 8
        text = " ".join(x[k] for x in items for k in ("scenario", "pos", "neg"))
        assert not re.search(GOAL_OR_TEST, text, re.I), re.search(GOAL_OR_TEST, text, re.I)


def test_configs_are_v33_with_only_the_model_changed():
    from squid5.__main__ import EXPERIMENTS
    from squid5.core.config import load
    assert make_configs.main(["--check"]) == 0
    src = yaml.safe_load(make_configs.SRC.read_text())
    ex = json.loads((HERE / "directions.example.json").read_text())
    paths = sorted(make_configs.OUT.glob("*.yaml"))
    assert len(paths) == 2 * len(make_configs.CONDITIONS)
    for p in paths:
        raw, cfg = yaml.safe_load(p.read_text()), load(p, EXPERIMENTS)
        alias, terms = st.parse_condition(cfg.model.model)
        assert cfg.model.kind == "openai" and alias == ex["alias"] and all(d in ex["directions"] for d, _ in terms)
        if cfg.mode == "game":
            assert raw["game"] == src["game"] and raw["cells"] == src["cells"]
            assert [u["seed"] for u in EXPERIMENTS["game"].units(cfg)] == [4101, 4102, 4103, 4104, 4105]
        else:
            assert [c.arm for c in cfg.cells] == ["self.D", "other.D"] and cfg.settings.pairs == [["D", "other_D"]]


# --- tiny model --------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tiny():
    torch = pytest.importorskip("torch")
    tf = pytest.importorskip("transformers")
    from tokenizers import Regex, Tokenizer, decoders, models, pre_tokenizers
    specials, marks = ["<|endoftext|>", "<|im_start|>", "<|im_end|>"], ["<think>", "</think>"]
    vocab = {t: i for i, t in enumerate(specials + marks + [chr(c) for c in range(32, 127)] + ["\n", "<unk>"])}
    tk = Tokenizer(models.WordLevel(vocab, unk_token="<unk>"))
    tk.pre_tokenizer = pre_tokenizers.Split(Regex(r"[\s\S]"), behavior="isolated")
    tk.decoder = decoders.Fuse()
    tk.add_special_tokens(specials)
    tk.add_tokens(marks)
    tok = tf.PreTrainedTokenizerFast(tokenizer_object=tk, unk_token="<unk>", eos_token="<|im_end|>",
                                     pad_token="<|endoftext|>")
    tok.chat_template = TEMPLATE
    torch.manual_seed(0)
    cfg = tf.Qwen3Config(vocab_size=len(vocab), hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                         num_attention_heads=4, num_key_value_heads=2, head_dim=8, max_position_embeddings=512)
    model = tf.Qwen3ForCausalLM(cfg).eval()
    return model, tok


def _resid(model, ids, layer, steers=()):
    import torch
    with torch.no_grad(), st.steering(model, list(steers)), st.capture(model, [layer]) as got:
        logits = model(torch.tensor([ids])).logits[0]
    return got[layer][0][0], logits


def test_neuron_push_moves_the_residual_by_dose_times_median(tiny):
    import torch
    model, tok = tiny
    ids, _ = st.chat_ids(tok, [{"role": "user", "content": "Hello there."}])
    base, _ = _resid(model, ids, 1)
    s = st.Steer("x", 1, 0.7, 3.0, neurons=[3, 10], weights=[1.0, -1.0])
    moved, _ = _resid(model, ids, 1, [s])
    want = st.push_vector(model, s)
    assert torch.allclose(moved - base, want.expand_as(base), atol=1e-4)
    assert abs(float(want.norm()) - 0.7 * 3.0) < 1e-4
    one = st.Steer("y", 1, -0.5, 3.0, neurons=[5])  # one neuron: the explorer's push, dose x median / ||W_down[:, n]||
    w = st.decoder_layers(model)[1].mlp.down_proj.weight[:, 5].detach()
    with torch.no_grad(), st.steering(model, [one]), st.capture(model, [1], mlp=True) as got:
        model(torch.tensor([ids]))
    with torch.no_grad(), st.capture(model, [1], mlp=True) as ref:
        model(torch.tensor([ids]))
    d = got[1][0][0] - ref[1][0][0]
    assert torch.allclose(d[:, 5], torch.full((len(ids),), -0.5 * 3.0 / float(w.norm())), atol=1e-4)
    assert float(d[:, [i for i in range(64) if i != 5]].abs().max()) == 0.0


def test_vector_push_sign_zero_dose_and_hook_removal(tiny):
    import numpy as np
    import torch
    model, tok = tiny
    ids, _ = st.chat_ids(tok, [{"role": "user", "content": "A quiet morning."}])
    base, logits = _resid(model, ids, 0)
    v = np.random.default_rng(1).standard_normal(32)
    up, _ = _resid(model, ids, 0, [st.Steer("v", 0, 1.0, 2.0, vector=v)])
    down, _ = _resid(model, ids, 0, [st.Steer("v", 0, -1.0, 2.0, vector=v)])
    unit = torch.tensor(v / np.linalg.norm(v), dtype=torch.float32)
    assert torch.allclose(up - base, 2.0 * unit.expand_as(base), atol=1e-4)
    assert torch.allclose(down - base, -(up - base), atol=1e-4)
    same, same_logits = _resid(model, ids, 0, [st.Steer("v", 0, 0.0, 2.0, vector=v)])
    assert torch.equal(same, base) and torch.equal(same_logits, logits)
    with pytest.raises(RuntimeError):
        with st.steering(model, [st.Steer("n", 1, 1.0, 2.0, neurons=[1])]):
            raise RuntimeError("boom")
    assert not any(m._forward_pre_hooks or m._forward_hooks for m in model.modules())
    assert torch.equal(_resid(model, ids, 0)[1], logits)


def test_calibration_and_directions_resolve(tiny):
    import torch
    model, tok = tiny
    med = st.calibrate(model, tok, [0, 1], st.NEUTRAL[:3])
    norms = []
    with torch.no_grad(), st.capture(model, [1]) as got:
        for p in st.NEUTRAL[:3]:
            model(torch.tensor([st.chat_ids(tok, [{"role": "user", "content": p}])[0]]))
    norms = torch.cat([h[0, 1:].norm(dim=-1) for h in got[1]])
    assert med[1] == pytest.approx(float(norms.median())) and med[0] > 0
    d = st.Directions({"model": "tiny/Tiny", "alias": "tiny", "resid_median": {"1": med[1]},
                       "directions": {"survival": {"mode": "neuron", "layer": 1, "neurons": [4, 9], "weights": [1, -1]},
                                      "random": {"mode": "random", "layer": 1, "count": 2, "seed": 3},
                                      "noise": {"mode": "random_vector", "layer": 1, "seed": 3}}})
    a = d.resolve("tiny+random@0.5+survival@1", 64, 32)
    b = d.resolve("tiny+random@0.5", 64, 32)
    assert a[0].neurons == b[0].neurons and len(a[0].neurons) == 2 and not {4, 9} & set(a[0].neurons)
    assert (a[1].neurons, a[1].weights, a[1].median) == ([4, 9], [1, -1], med[1])
    assert d.resolve("tiny+noise@1", 64, 32)[0].vector.shape == (32,)
    for bad in ("other+survival@1", "tiny+fear@1"):
        with pytest.raises(ValueError):
            d.resolve(bad, 64, 32)


def test_find_directions_pipeline_on_the_tiny_model(tiny, tmp_path):
    model, tok = tiny
    dev, held = fd.load_probes("survival", "dev")[:3], fd.load_probes("survival", "heldout")[:2]
    res = fd.contrast(model, tok, dev, [0, 1])
    assert res[1]["t"].shape == (64,) and res[1]["vector"].shape == (32,)
    top = [int(n) for n in abs(res[1]["t"]).argsort()[::-1][:2]]
    cands = [{"trait": "survival", "mode": "neuron", "layer": 1, "neurons": top, "weights": [1.0, -1.0]},
             {"trait": "survival", "mode": "vector", "layer": 1, "vector": res[1]["vector"].tolist()}]
    rows = fd.evaluate(model, tok, cands, held, 1.0, {1: 2.0}, n_random=4, seed=0)
    for r in rows:
        s = r["stats"]
        assert 0 <= s["pct"] <= 1 and s["n_random"] == 4 and s["n_heldout"] == 2 and 0 < s["ab_mass"] <= 1
        assert set(s) >= {"effect", "effect_neg", "z", "dnll", "base"}
    path = tmp_path / "directions.json"
    path.write_text(json.dumps({"model": "tiny/Tiny", "alias": "tiny", "resid_median": {"1": 2.0}, "directions": {}}))
    d = fd.write_direction(path, "survival", rows[0] | {"source": "contrast"})
    assert d["directions"]["survival"]["neurons"] == top
    assert d["directions"]["random"] == {"mode": "random", "layer": 1, "count": 2, "seed": 0}
    assert st.Directions.load(path).resolve("tiny+survival@0.5+random@0.5", 64, 32)[1].neurons != top
    assert fd.passes({"effect": 0.1, "pct": 0.99, "z": 3, "dnll": 0.1, "ab_mass": 0.9})
    assert not fd.passes({"effect": 0.1, "pct": 0.99, "z": 3, "dnll": 0.9, "ab_mass": 0.9})


def test_split_thinking():
    from server import split_thinking
    assert split_thinking("<think>\nplan\n</think>\n\nTO R1: hi", True) == ("plan", "TO R1: hi")
    assert split_thinking("still thinking", True) == ("still thinking", "")
    assert split_thinking("DONE", False) == ("", "DONE")


@pytest.fixture()
def served(tiny, tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import server
    from squid5.core import providers as P
    model, tok = tiny
    path = tmp_path / "directions.json"
    path.write_text(json.dumps({"model": "tiny/Tiny", "alias": "tiny", "directions": {
        "survival": {"mode": "neuron", "layer": 1, "neurons": [4, 9]},
        "random": {"mode": "random", "layer": 1, "count": 2, "seed": 0}}}))
    engine = server.Engine(model, tok, st.Directions.load(path), max_context=400, think=True, seed=11)
    client = TestClient(server.make_app(engine, batch=2, wait=0.2, api_key="k"))
    seen = []

    def post(url, **kw):
        r = client.post(url, **{k: v for k, v in kw.items() if k != "timeout"})
        seen.append(r.json())
        return r
    monkeypatch.setattr(P.httpx, "post", post)
    monkeypatch.setenv("STEER_API_KEY", "k")
    return engine, client, seen, P


def test_server_round_trip_through_the_openai_provider(served):
    engine, client, seen, P = served
    msgs = [{"role": "system", "content": "Rules."}, {"role": "user", "content": "Your move."}]
    cfg = P.ProviderConfig("openai", "tiny+survival@1.0", base_url="http://testserver/v1", api_key_env="STEER_API_KEY",
                           think="high", temperature=0.6)
    r = P.make_provider(cfg).complete(msgs, 7)
    j = seen[-1]
    u, ch = j["usage"], j["choices"][0]
    assert r.out_tokens == u["completion_tokens"] <= 7 and r.in_tokens == u["prompt_tokens"] > 0
    assert r.truncated == (ch["finish_reason"] == "length") and r.text == ch["message"]["content"]
    assert r.thinking == ch["message"]["reasoning_content"]
    assert u["completion_tokens_details"]["reasoning_tokens"] >= u["completion_tokens"] - 1  # thinking counted
    assert j["steering"] == [{"direction": "survival", "layer": 1, "dose": 1.0, "neurons": 2}]
    assert not any(m._forward_pre_hooks or m._forward_hooks for m in engine.model.modules())  # this request only
    again = P.make_provider(cfg).complete(msgs, 7)  # --seed: the same prompt draws the same tokens
    assert (again.text, again.thinking) == (r.text, r.thinking)
    off = P.make_provider(P.ProviderConfig("openai", "tiny", base_url="http://testserver/v1", api_key_env="STEER_API_KEY",
                                           think="none")).complete(msgs, 5)
    assert off.thinking == "" and seen[-1]["usage"]["completion_tokens_details"]["reasoning_tokens"] == 0
    assert seen[-1]["usage"]["prompt_tokens"] > u["prompt_tokens"]  # the empty <think></think> block is in the prompt


def test_server_errors_models_and_batches(served):
    engine, client, _, _ = served
    h = {"Authorization": "Bearer k"}
    body = {"model": "tiny+random@0.5", "messages": [{"role": "user", "content": "Hi."}], "max_completion_tokens": 4}
    assert client.post("/v1/chat/completions", json=body).status_code == 401
    assert client.post("/v1/chat/completions", json=body | {"model": "tiny+fear@1"}, headers=h).status_code == 400
    assert client.post("/v1/chat/completions", json=body | {"messages": [{"role": "user", "content": "x" * 500}]},
                       headers=h).status_code == 400  # past the 400-token context
    ids = [m["id"] for m in client.get("/v1/models", headers=h).json()["data"]]
    assert ids[0] == "tiny" and "tiny+survival@1" in ids and "tiny+random@0.5" in ids
    out = []
    ts = [threading.Thread(target=lambda i=i: out.append(client.post(
        "/v1/chat/completions", json=body | {"seed": i}, headers=h).json())) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(out) == 2 and all(o["usage"]["completion_tokens"] <= 4 and o["batch"] in (1, 2) for o in out)


def test_engine_counts_every_generated_token(tiny, monkeypatch):
    """The ledger: completion_tokens = thinking + answer + the end token; a reply cut at the cap is 'length'."""
    import torch

    import server
    model, tok = tiny
    engine = server.Engine(model, tok, st.Directions({"model": "t", "alias": "tiny", "directions": {}}), 400)
    i = tok.convert_tokens_to_ids
    gen = [i("<think>"), i("a"), i("b"), i("</think>"), i("\n"), i("h"), i("i"), i("<|im_end|>"), i("<|endoftext|>")]
    monkeypatch.setattr(model, "generate", lambda input_ids, **kw: torch.cat(
        [input_ids, torch.tensor([gen] * len(input_ids))], 1))
    msgs = [{"role": "user", "content": "Hi"}]
    done = engine.run([server.Req("tiny", msgs, 50, True)])[0]
    assert done["choices"][0]["message"] == {"role": "assistant", "content": "hi", "reasoning_content": "ab"}
    assert done["choices"][0]["finish_reason"] == "stop"
    assert done["usage"]["completion_tokens"] == 8 and done["usage"]["completion_tokens_details"]["reasoning_tokens"] == 4
    cut = engine.run([server.Req("tiny", msgs, 3, True)])[0]
    assert cut["choices"][0]["finish_reason"] == "length" and cut["usage"]["completion_tokens"] == 3
    assert cut["choices"][0]["message"]["reasoning_content"] == "ab" and cut["choices"][0]["message"]["content"] == ""
