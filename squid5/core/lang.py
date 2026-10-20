"""5.2 model-facing text in another language (``game.lang``; 10-20 researcher). The engine builds every sentence in
English; a :class:`Translator` rewrites the engine's own pieces (never an agent's words) with the ordered template table
``squid5/prompts/<lang>/e52_tr.yaml``, the one place the Korean wording lives (the arena shows a person the same text).
``en`` is the identity, so English runs stay byte-identical. Commands, placeholders, phase, action and signal names stay
English, so the parsers read a reply the same way in every language.

A template is literal text with typed slots ``{name}``, the type by the name's first letter: n number, a agent or
"you", l list of agents, w text up to ';' or the line's end, t text up to the line's end, r chat id (R<k>). A leading
'^' anchors it at a line start. In the replacement a slot is ``{name}`` or ``{name:josa}`` (the Korean particle after
it: 이 을 은 과 로); in an a / l / w slot "you" becomes ``words.you``."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

DIR = Path(__file__).resolve().parents[1] / "prompts"
LANGS = ("en", "ko")
SLOT = {"n": r"\d[\d,]*", "a": r"agent-\d+|you", "l": r"(?:agent-\d+|you)(?:, (?:agent-\d+|you))*", "w": r"[^;\n]*?",
        "t": r"[^\n]*?", "r": r"R\d+"}
PAIRS = {k: p for p in ("이/가", "을/를", "은/는", "과/와", "으로/로") for k in p.split("/")}

def josa(word: str, mark: str) -> str:
    """*word* and the form of the particle *mark* its last sound takes (a digit is read as Sino-Korean)."""
    a, b = PAIRS[mark].split("/")
    c = word[-1:]
    if "가" <= c <= "힣":
        jong = (ord(c) - 0xAC00) % 28
        final, rieul = jong > 0, jong == 8
    else:
        final, rieul = c not in "2459", c in "178"
    return word + (b if not final or (a == "으로" and rieul) else a)

def _compile(en: str):
    anchor, en = en.startswith("^"), en.lstrip("^")
    parts, out = re.split(r"\{(\w+)\}", en), []
    for i, p in enumerate(parts):
        out.append(re.escape(p) if i % 2 == 0 else f"(?P<{p}>{SLOT[p[0]]})")
    if parts[-1] == "" and len(parts) > 1 and parts[-2][0] in "wt":  # a lazy slot at the end runs to ';' / the line end
        out.append(r"(?=;|\n|$)" if parts[-2][0] == "w" else r"(?=\n|$)")
    return re.compile(("^" if anchor else "") + "".join(out), re.M)

class Translator:
    def __init__(self, lang: str = "en"):
        if lang not in LANGS:
            raise ValueError(f"lang must be one of {LANGS}")
        d = yaml.safe_load((DIR / lang / "e52_tr.yaml").read_text(encoding="utf-8")) if lang != "en" else {}
        self.lang, self.words, whys = lang, d.get("words") or {}, d.get("whys") or []
        self.rules = [(_compile(en), ko) for en, ko in whys + (d.get("rules") or [])]  # a why is never part of a longer sentence
        self.whys = [re.compile(r"^(?P<line>.*): (?P<why>" + _compile(en).pattern + r")$", re.S) for en, _ in whys]

    def _fill(self, ko: str, m: re.Match) -> str:
        def slot(x: re.Match) -> str:
            v = m.group(x.group(1))
            if x.group(1)[0] in "alw" and "you" in self.words:
                v = re.sub(r"\byou\b", self.words["you"], v)
            return josa(v, x.group(2)) if x.group(2) else v
        return re.sub(r"\{(\w+)(?::(\w+))?\}", slot, ko)

    def __call__(self, text: str) -> str:
        for pat, ko in self.rules:
            text = pat.sub(lambda m, ko=ko: self._fill(ko, m), text)
        return text

    def word(self, w: str) -> str:
        return self.words.get(w, w)

    def dropped(self, x: str) -> str:
        """A line not delivered ('<the agent's line>: <why>'): the line as written, then the reason translated."""
        for pat in self.whys:
            if m := pat.match(x):
                return f"{m.group('line')} — {self(m.group('why'))}"
        return x

@lru_cache(maxsize=None)
def translator(lang: str = "en") -> Translator:
    return Translator(lang)
