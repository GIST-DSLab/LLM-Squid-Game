import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import keys  # noqa: E402


def env(**kv):
    return lambda name: kv.get(name)


def test_default_is_key3():
    assert keys.choose_key(None, env()) == "OLLAMA_API_KEY3"
    assert keys.choose_key("", env()) == "OLLAMA_API_KEY3"
    assert keys.choose_key("OLLAMA_API_KEY3", env(OLLAMA_KEY1_ENABLED="on")) == "OLLAMA_API_KEY3"


@pytest.mark.parametrize("switch", [None, "off", "ON ", "ON", " on", "true", "1", ""])
def test_key1_refused_unless_exactly_on(switch):
    with pytest.raises(keys.KeyError_):
        keys.choose_key("OLLAMA_API_KEY1", env(OLLAMA_KEY1_ENABLED=switch))


def test_key1_when_switched_on():
    assert keys.choose_key("OLLAMA_API_KEY1", env(OLLAMA_KEY1_ENABLED="on")) == "OLLAMA_API_KEY1"


@pytest.mark.parametrize("name", ["OLLAMA_API_KEY2", "OLLAMA_API_KEY", "ANTHROPIC_API_KEY", "x"])
def test_other_names_refused(name):
    with pytest.raises(keys.KeyError_):
        keys.choose_key(name, env(OLLAMA_KEY1_ENABLED="on"))


def test_missing_key3_refuses_without_fallback():
    e = env(OLLAMA_API_KEY1="k1", OLLAMA_KEY1_ENABLED="on")
    name = keys.choose_key(None, e)
    with pytest.raises(keys.KeyError_):
        keys.key_value(name, e)  # key 3 is missing; key 1 is never tried
