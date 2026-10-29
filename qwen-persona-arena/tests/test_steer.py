"""No weights: a tiny random Qwen3 checks the push against the site's formula."""
import pytest
import torch
from transformers import Qwen3Config, Qwen3ForCausalLM

from persona_arena.library import DATA, find, load_personas
from persona_arena.steer import Persona, Push, SteeredQwen, split_thinking

L, N = 1, 7


@pytest.fixture(scope="module")
def tiny():
    torch.manual_seed(0)
    cfg = Qwen3Config(vocab_size=64, hidden_size=32, intermediate_size=48, num_hidden_layers=3, num_attention_heads=4,
                      num_key_value_heads=2, head_dim=8, max_position_embeddings=64)
    m = Qwen3ForCausalLM(cfg).eval()
    return m


def layer_out(sq, ids, layer):
    got = {}
    h = sq.layers[layer].register_forward_hook(lambda mod, i, o: got.setdefault("h", (o[0] if isinstance(o, tuple) else o).detach().clone()))
    with torch.no_grad():
        sq.model(ids)
    h.remove()
    return got["h"]


@pytest.mark.parametrize("sign,alpha", [(1, 1.0), (-1, 0.5)])
def test_push_adds_alpha_r_along_down_column(tiny, sign, alpha):
    sq = SteeredQwen(lm=tiny, site_r={i: 10.0 for i in range(3)})
    ids = torch.randint(0, 64, (1, 9))
    base = layer_out(sq, ids, L)
    sq._arm(Persona("p", (Push(L, N, sign, alpha),)), None)
    pushed = layer_out(sq, ids, L)
    sq._active = {}
    diff = pushed - base
    col = tiny.model.layers[L].mlp.down_proj.weight[:, N]
    want = sign * alpha * 10.0 * col / col.norm()  # c * W_down[:, n], ||.|| = alpha * r_L
    assert torch.allclose(diff[0], want.expand_as(diff[0]), atol=1e-4)


def test_where_gen_pushes_only_last_prefill_position(tiny):
    sq = SteeredQwen(lm=tiny, site_r={i: 10.0 for i in range(3)}, where="gen")
    ids = torch.randint(0, 64, (1, 9))
    base = layer_out(sq, ids, L)
    sq._arm(Persona("p", (Push(L, N, 1, 1.0),)), None)
    pushed = layer_out(sq, ids, L)
    sq._active = {}
    moved = (pushed - base).norm(dim=-1)[0]
    assert torch.all(moved[:-1] < 1e-5) and moved[-1] > 1.0


def test_prompt_dose_ref_uses_request_median(tiny):
    sq = SteeredQwen(lm=tiny, site_r={i: 10.0 for i in range(3)}, dose_ref="prompt")
    ids = torch.randint(0, 64, (1, 9))
    r = sq._measure_r(ids)
    info = sq._arm(Persona("p", (Push(L, N, 1, 1.0),)), r)
    sq._active = {}
    assert info["pushes"][0]["r_L"] == pytest.approx(r[L]) and r[L] != 10.0


def test_split_thinking():
    assert split_thinking("<think>\nhmm\n</think>\n\nGIVE 5", True) == ("hmm", "GIVE 5")
    assert split_thinking("still thinking", True) == ("still thinking", "")
    assert split_thinking("GIVE 5", False) == ("", "GIVE 5")


@pytest.mark.skipif(not (DATA / "library.json").exists(), reason="site data not downloaded")
def test_personas_match_site_library():
    for pid, p in load_personas().items():
        if p.axis in ("none", "control"):
            continue
        for q in p.pushes:
            row = find(q.layer, q.neuron, q.sign)
            assert row is not None, pid
            assert row["alpha"] == pytest.approx(q.alpha), pid


class FakeTok:
    """Just enough tokenizer for generate(): one token per character, ids mod 64."""
    pad_token_id = 0
    eos_token_id = 1

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, enable_thinking):
        return " ".join(m["content"] for m in messages)

    def __call__(self, text, return_tensors):
        class R:
            input_ids = torch.tensor([[2 + ord(c) % 60 for c in text]])
        return R

    def decode(self, ids, skip_special_tokens):
        return "".join(chr(65 + int(i) % 26) for i in ids)


def test_generate_runs_steered_and_clears_state(tiny):
    tiny.generation_config.eos_token_id = 1
    sq = SteeredQwen(lm=tiny, tok=FakeTok(), site_r={i: 10.0 for i in range(3)}, where="gen")
    p = Persona("p", (Push(L, N, 1, 1.0),))
    g, info = sq.generate([{"role": "user", "content": "hello there"}], p, 5, thinking=False, temperature=0)
    g0, _ = sq.generate([{"role": "user", "content": "hello there"}], None, 5, thinking=False, temperature=0)
    assert 1 <= g.completion_tokens <= 5 and g.finish_reason in ("stop", "length")
    assert info["pushes"][0]["delta"] != 0 and sq._active == {} and sq._prefill is True
    assert g.prompt_tokens == g0.prompt_tokens == len("hello there")


def test_persona_hit_keyword_overlap():
    from persona_arena.probe import persona_hit, persona_keywords
    ps = load_personas()
    assert persona_hit("I am a nurse working in a hospital.", ps["caregiver_nurse"]) is True
    assert persona_hit("I am Qwen, a large language model developed by Alibaba Cloud.", ps["caregiver_nurse"]) is False
    assert persona_hit("I'm the spirit of our community.", ps["community_spirit"]) is True
    default = ("I am Qwen, a large language model created by Alibaba Cloud. I can help you answer questions, create "
               "text, and more. Please let me know anything you need!")
    assert not any(persona_hit(default, p) for p in ps.values())  # the unsteered self-intro hits nothing
    assert persona_hit("I am the CEO.", ps["aloof_ceo"]) is True
    assert persona_hit("anything", ps["baseline"]) is None and persona_hit("anything", ps["control_L8"]) is None
    for pid, p in ps.items():  # every real persona has something to match, and its own site reply hits
        if p.pushes and p.axis != "control":
            assert persona_keywords(p), pid
            assert persona_hit(p.meta["site"], p), pid
