import pytest

import keys


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


def test_settings_default_model_think_off_and_key():
    import settings
    s = settings.make({}, env())
    assert s.model == "gemma4:31b" and s.think is None and s.api_key_env == "OLLAMA_API_KEY3"
    assert settings.make({"model": "gpt-oss:20b", "think": "medium"}, env()).think == "medium"
    with pytest.raises(keys.KeyError_):
        settings.make({"api_key_env": "OLLAMA_API_KEY1"}, env(OLLAMA_KEY1_ENABLED="ON "))
    from dataclasses import asdict
    again = settings.make(asdict(s))  # stored with think null
    assert again.think is None and again.seed == s.seed


def test_base_url_only_loopback():
    import modelcalls
    assert modelcalls.local_base(env(OLLAMA_BASE_URL="http://127.0.0.1:11435")) == "http://127.0.0.1:11435"
    assert modelcalls.local_base(env(OLLAMA_BASE_URL="https://evil.example")) == ""
    assert modelcalls.local_base(env()) == ""
